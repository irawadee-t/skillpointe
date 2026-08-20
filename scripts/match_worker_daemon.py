"""Resident match worker — sub-second incremental matching.

Why this exists: per-event recompute subprocesses paid ~25 seconds of data
loading (43k applicant profiles + signals + embeddings) to do ~1 second of
scoring, and uncoordinated triggers could stampede (observed: 77 concurrent
processes exhausting Postgres connection slots). This daemon loads the
marketplace ONCE, stays warm, and consumes match_queue serially:

  * LISTEN match_queue (NOTIFY wakes it instantly; 10s poll as fallback)
  * the queue's partial unique index dedupes pending targets — no Redis
  * the applicant/job pools refresh in the background every CACHE_TTL_S,
    and the TARGET of each task is always fetched fresh (a just-edited
    profile or just-published job never scores from stale cache)
  * scoring + batched writes reuse the exact functions the audited batch
    pipeline uses (scripts/recompute_matches.py) — one engine, no drift

Run: python scripts/match_worker_daemon.py   (the API scheduler supervises
one instance; a second instance exits via pg_advisory_lock).
"""
from __future__ import annotations

import logging
import select
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "scripts"))

import recompute_matches as rm  # noqa: E402  (battle-tested fetch/score/flush helpers)
from matching import sn_taxonomy  # noqa: E402
from matching.engine import compute_match  # noqa: E402
from matching.state_adjacency import neighbors  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s match-worker %(levelname)s %(message)s")
log = logging.getLogger("match_worker")

CACHE_TTL_S = 600          # idle refresh cadence (burst-start reloads dominate)
BURST_STALENESS_S = 30     # a work burst never scores against a pool older than this
POLL_S = 10                # fallback wake if a NOTIFY is missed
ADVISORY_LOCK_KEY = 0x534B4D57  # "SKMW" — single-instance guard

FLUSH_EVERY = 1000


class Cache:
    """The resident marketplace. Loaded once, refreshed on a timer."""

    def __init__(self) -> None:
        self.loaded_at = 0.0
        self.applicants: list[dict] = []
        self.jobs: list[dict] = []
        self.employer_map: dict[str, dict] = {}
        self.app_signals: dict[str, dict] = {}
        self.job_signals: dict[str, dict] = {}
        self.app_emb: dict[str, list[float]] = {}
        self.job_emb: dict[str, list[float]] = {}
        self.config = None

    def load(self, conn) -> None:
        t0 = time.monotonic()
        self.config = rm._load_active_config(conn)
        self.applicants = rm._fetch_applicants(conn)
        self.jobs = rm._fetch_jobs(conn)
        self.employer_map = {str(e["id"]): e for e in rm._fetch_employers(conn)}
        self.app_signals = rm._fetch_applicant_signals(conn)
        self.job_signals = rm._fetch_job_signals(conn)
        self.app_emb = rm._fetch_applicant_embeddings(conn)
        self.job_emb = rm._fetch_job_embeddings(conn)
        creds = rm._fetch_applicant_credentials(conn)
        rm._canonicalize_credential_inputs(
            self.jobs, self.applicants, self.app_signals, creds)
        self.loaded_at = time.monotonic()
        log.info("cache loaded: %d applicants, %d jobs in %.1fs",
                 len(self.applicants), len(self.jobs), self.loaded_at - t0)

    def maybe_refresh(self, conn) -> None:
        if time.monotonic() - self.loaded_at >= CACHE_TTL_S:
            self.load(conn)


def _candidate_jobs(cache: Cache, app: dict) -> list[dict]:
    a_state = (app.get("state") or "").upper()
    if not a_state:
        return []
    ok = {a_state} | set(neighbors(a_state))
    a_code = app.get("canonical_job_family_code")
    out = []
    for j in cache.jobs:
        if (j.get("state") or "").upper() not in ok and (j.get("work_setting") or "") != "remote":
            continue
        j_code = j.get("canonical_job_family_code")
        if a_code and j_code and sn_taxonomy.relate(a_code, j_code) == "unrelated":
            continue
        out.append(j)
    return out


def _candidate_applicants(cache: Cache, job: dict) -> list[dict]:
    j_state = (job.get("state") or "").upper()
    remote = (job.get("work_setting") or "") == "remote"
    j_code = job.get("canonical_job_family_code")
    ok = {j_state} | set(neighbors(j_state))
    out = []
    for a in cache.applicants:
        a_state = (a.get("state") or "").upper()
        if not a_state:
            continue
        if not remote and a_state not in ok:
            continue
        a_code = a.get("canonical_job_family_code")
        if a_code and j_code and sn_taxonomy.relate(a_code, j_code) == "unrelated":
            continue
        out.append(a)
    return out


def _score_pairs(conn, cache: Cache, pairs, run_id: str) -> dict:
    """compute_match over (applicant, job) pairs; batched flush; counters."""
    from datetime import date
    counters = {"total": 0, "eligible": 0, "near_fit": 0, "ineligible": 0, "skipped": 0}
    buf = []
    today = date.today()
    for app, job in pairs:
        a_id, j_id = str(app["id"]), str(job["id"])
        result = compute_match(
            app, job,
            cache.employer_map.get(str(job.get("employer_id"))),
            cache.config,
            today=today,
            scoring_run_id=run_id,
            applicant_signals=cache.app_signals.get(a_id),
            job_signals=cache.job_signals.get(j_id),
            applicant_embedding=cache.app_emb.get(a_id),
            job_embedding=cache.job_emb.get(j_id),
        )
        counters["total"] += 1
        counters[result.eligibility_status] = counters.get(result.eligibility_status, 0) + 1
        # Same storage rule as the batch pipeline: cross-state ineligible
        # rows are ballast, not information.
        if (result.eligibility_status == "ineligible"
                and (app.get("state") or "").upper() != (job.get("state") or "").upper()):
            counters["skipped"] += 1
            continue
        buf.append(result)
        if len(buf) >= FLUSH_EVERY:
            rm._flush_batch(conn, buf)
            buf.clear()
    if buf:
        rm._flush_batch(conn, buf)
    conn.commit()
    return counters


def _process(conn, cache: Cache, entity_type: str, entity_id: str) -> dict:
    import uuid as _uuid
    run_id = str(_uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.recompute_runs (kind, target_id, status, started_at) "
            "VALUES (%s, %s, 'in_progress', now()) RETURNING id",
            (entity_type, entity_id))
        rec_run = cur.fetchone()[0]
    conn.commit()
    try:
        if entity_type == "job":
            # Target always fetched fresh — never scored from cache.
            fresh = rm._fetch_jobs(conn, job_id=entity_id)
            if not fresh:                     # deactivated/deleted: clear rows
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.matches WHERE job_id = %s", (entity_id,))
                conn.commit()
                counters = {"total": 0, "cleared": True}
            else:
                job = fresh[0]
                cache.job_signals.update(rm._fetch_job_signals(conn))
                rm._canonicalize_credential_inputs([job], [], {}, {})
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.matches WHERE job_id = %s", (entity_id,))
                conn.commit()
                cands = _candidate_applicants(cache, job)
                counters = _score_pairs(conn, cache, ((a, job) for a in cands), run_id)
                counters["candidates"] = len(cands)
        else:
            fresh = rm._fetch_applicants(conn, applicant_id=entity_id)
            if not fresh:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.matches WHERE applicant_id = %s", (entity_id,))
                conn.commit()
                counters = {"total": 0, "cleared": True}
            else:
                app = fresh[0]
                creds = rm._fetch_applicant_credentials(conn)
                sigs = rm._fetch_applicant_signals(conn)
                self_sig = {entity_id: sigs.get(entity_id)} if sigs.get(entity_id) else {}
                rm._canonicalize_credential_inputs([], [app], self_sig, creds)
                if self_sig:
                    cache.app_signals.update(self_sig)
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.matches WHERE applicant_id = %s", (entity_id,))
                conn.commit()
                cands = _candidate_jobs(cache, app)
                counters = _score_pairs(conn, cache, ((app, j) for j in cands), run_id)
                counters["candidates"] = len(cands)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.recompute_runs SET status='complete', completed_at=now() "
                "WHERE id=%s", (rec_run,))
        conn.commit()
        return counters
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.recompute_runs SET status='failed', completed_at=now(), "
                "error=%s WHERE id=%s", (str(exc)[:500], rec_run))
        conn.commit()
        raise


def main() -> int:
    from etl.db import get_connection
    conn = get_connection()
    conn.autocommit = False

    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        if not cur.fetchone()[0]:
            log.info("another match worker holds the lock — exiting")
            return 0
    conn.commit()

    cache = Cache()
    cache.load(conn)

    # Dedicated autocommit connection for LISTEN.
    lconn = get_connection()
    lconn.autocommit = True
    with lconn.cursor() as cur:
        cur.execute("LISTEN match_queue")
    log.info("listening on match_queue")

    while True:
        # Burst-start freshness: tasks arriving now may reference entities
        # created seconds ago on EITHER side of the marketplace. A brand-new
        # job scored against a pool missing a brand-new applicant (or vice
        # versa) would silently skip that pair until the next refresh — so a
        # burst never begins against a pool older than BURST_STALENESS_S.
        # The reload is cheap (~0.2s measured) relative to any burst.
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM public.match_queue WHERE processed_at IS NULL LIMIT 1")
            has_work = cur.fetchone() is not None
        conn.commit()
        if has_work and time.monotonic() - cache.loaded_at > BURST_STALENESS_S:
            cache.load(conn)

        # Drain everything pending, oldest first.
        while True:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.match_queue SET claimed_at = now()
                     WHERE id = (SELECT id FROM public.match_queue
                                  WHERE processed_at IS NULL
                                  ORDER BY enqueued_at
                                  FOR UPDATE SKIP LOCKED LIMIT 1)
                    RETURNING id, entity_type, entity_id""")
                row = cur.fetchone()
            conn.commit()
            if not row:
                break
            qid, etype, eid = row[0], row[1], str(row[2])
            t0 = time.monotonic()
            try:
                counters = _process(conn, cache, etype, eid)
                err = None
            except Exception as exc:  # noqa: BLE001 - worker must survive any task
                log.exception("task %s %s failed", etype, eid)
                conn.rollback()
                counters, err = {}, str(exc)[:500]
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.match_queue SET processed_at = now(), error = %s "
                    "WHERE id = %s", (err, qid))
            conn.commit()
            log.info("%s %s: %s in %.1fs", etype, eid, counters, time.monotonic() - t0)

        cache.maybe_refresh(conn)
        # Sleep until NOTIFY or POLL_S timeout.
        if select.select([lconn], [], [], POLL_S)[0]:
            lconn.poll()
            lconn.notifies.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
