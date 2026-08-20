"""
scheduler.py — APScheduler for periodic match recomputation.

Runs a full recompute every 6 hours using a Redis distributed lock so
only one API instance runs the pipeline at a time.

Also exports `trigger_recompute_for_job` and `trigger_recompute_for_applicant`
for fire-and-forget triggers when a job is created or a profile is updated.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

logger = logging.getLogger(__name__)

def _find_repo_root() -> Path:
    """Locate the repo root by walking up for a marker.

    A fixed ``.parent`` chain silently lands on ``/`` when the deploy layout is
    flatter than the dev tree (Railway Root Directory = apps/api), because
    ``Path.parent`` saturates at the filesystem root instead of raising.
    """
    here = Path(__file__).resolve()
    chain = (here, *here.parents)
    # Strong markers first: only the real repo root has these, so in the dev tree
    # we skip past apps/api and land on the checkout root.
    for candidate in chain:
        if (candidate / ".git").exists() or (candidate / "scripts").is_dir():
            return candidate
    # Deployed layout: no .git, no scripts/. Settle for the app root so paths
    # stay inside the image rather than resolving against "/".
    for candidate in chain:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path("/app")


_REPO_ROOT = _find_repo_root()


async def _run_locked(lock_name: str, ttl: int, coro_factory) -> None:
    """Run an async job under a Redis distributed lock so that, across N API
    replicas, only ONE runs the job per tick. If Redis is unavailable we fall
    back to running unlocked (a single-replica dev box, or a Redis outage where
    a possibly-duplicated run is safer than skipping the job entirely).

    ``coro_factory`` is a zero-arg callable returning the coroutine to run, so we
    only construct it once we hold the lock.
    """
    try:
        import redis.asyncio as aioredis  # type: ignore
    except ImportError:
        logger.warning("redis package not installed — running %s unlocked", lock_name)
        await coro_factory()
        return

    try:
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        lock = r.lock(f"skillpointe:sched:{lock_name}", timeout=ttl)
        acquired = await lock.acquire(blocking=False)
    except Exception as exc:
        logger.warning("Lock backend error for %s (%s) — running unlocked", lock_name, exc)
        await coro_factory()
        return

    if not acquired:
        logger.debug("Scheduler job %s held by another instance — skipping", lock_name)
        await r.aclose()
        return
    try:
        await coro_factory()
    finally:
        try:
            await lock.release()
        except Exception:
            pass
        await r.aclose()


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()
    # Weekly FULL recompute — a safety net, not the steady state. Day-to-day
    # freshness is event-driven (match_queue) plus the 6h delta sweep below;
    # the full pass only exists to catch inputs that change without an
    # updated_at bump (e.g. scoring-config edits) and any drift.
    scheduler.add_job(
        _locked_recompute,
        trigger="interval",
        hours=168,
        id="full_recompute",
        name="Full match recompute (weekly safety net)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Drift detector — with database triggers guaranteeing every content
    # write enqueues matching, this sweep should find NOTHING. Anything it
    # does find is logged as a warning: evidence of a write path that
    # bypassed the triggers (or a trigger regression). Hourly because the
    # check is one indexed query.
    scheduler.add_job(
        _locked_delta_sweep,
        trigger="interval",
        hours=1,
        id="delta_sweep",
        name="Match drift detector (hourly)",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _locked_interview_reminders,
        trigger="interval",
        minutes=5,
        id="interview_reminders",
        name="Interview reminders (24h/1h/follow-up)",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # Career-source auto-sync — keeps connected careers pages fresh using the
    # learned-profile incremental path (one conditional listing fetch; details
    # only for changed jobs), so a frequent tick is cheap. Cadence/backoff per
    # source lives on employer_career_sources (next_auto_sync_at).
    scheduler.add_job(
        _locked_career_source_auto_sync,
        trigger="interval",
        minutes=15,
        id="career_source_auto_sync",
        name="Career-source auto-sync (per-source cadence)",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # Headless listing sweep — DAILY, one rendered page per JS-walled source
    # (platform undetected / no_jobs) when HEADLESS_SCRAPE_ENABLED. Sources it
    # converts are marked profile.headless and keep syncing daily via the
    # regular auto-sync tick's headless routing.
    scheduler.add_job(
        _locked_headless_sweep,
        trigger="interval",
        hours=24,
        id="headless_listing_sweep",
        name="Headless listing sweep for JS-walled sources (daily)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Apply-link revalidation — dead apply links on active scraped/imported
    # jobs get flagged for admin review instead of 404ing on applicants.
    scheduler.add_job(
        _locked_apply_link_recheck,
        trigger="interval",
        hours=12,
        id="apply_link_recheck",
        name="Apply-link revalidation (12h)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # GDPR deletion sweep — daily hard-delete of accounts whose grace elapsed.
    scheduler.add_job(
        _locked_deletion_sweep,
        trigger="interval",
        hours=24,
        id="deletion_sweep",
        name="GDPR/CCPA account deletion sweep (daily)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Live freshness probes — EVERY minute, every connected source gets one
    # cheap change probe (sitemap 304 / census fingerprint), concurrently
    # with a bounded fan-out. Detection latency for partner-site changes is
    # therefore ~60s, the practical limit of keyless polling; failing
    # sources back off exponentially so a dead site can't eat the budget.
    scheduler.add_job(
        _locked_fast_probe,
        trigger="interval",
        minutes=1,
        id="fast_probe",
        name="Career-source live probes (1m)",
        replace_existing=True,
        misfire_grace_time=90,
    )
    # Worker supervision — a dead resident worker with trigger-only writes
    # (raw SQL, scripts) would let the queue accumulate silently, because
    # database triggers cannot respawn a process. One cheap liveness check
    # per minute makes worker death a <=60s blip instead of an outage.
    scheduler.add_job(
        _supervise_match_worker,
        trigger="interval",
        minutes=1,
        id="match_worker_supervisor",
        name="Resident match worker supervision (1m)",
        replace_existing=True,
        misfire_grace_time=120,
    )
    # Recovery: mark stuck in_progress recompute rows as failed on startup.
    scheduler.add_job(
        _recover_stuck_recomputes,
        trigger="date",   # once, ~now
        id="recompute_recovery_boot",
        name="Recover stuck recompute runs on boot",
        replace_existing=True,
    )
    return scheduler


async def _deletion_sweep_tick() -> None:
    """Delegated to the account router so schema + logic stay colocated."""
    try:
        from app.routers.account import sweep_expired_deletions
        await sweep_expired_deletions()
    except Exception as exc:
        logger.exception("Deletion sweep failed: %s", exc)


# Lock-wrapped entrypoints — one instance runs each job per tick across replicas.
async def _locked_interview_reminders() -> None:
    await _run_locked("interview_reminders", ttl=280, coro_factory=_interview_reminders_tick)


async def _locked_career_source_auto_sync() -> None:
    await _run_locked("career_source_auto_sync", ttl=840, coro_factory=_career_source_auto_sync_tick)


async def _locked_deletion_sweep() -> None:
    await _run_locked("deletion_sweep", ttl=3600, coro_factory=_deletion_sweep_tick)


async def _locked_apply_link_recheck() -> None:
    await _run_locked("apply_link_recheck", ttl=3300, coro_factory=_apply_link_recheck_tick)


async def _locked_headless_sweep() -> None:
    await _run_locked("headless_listing_sweep", ttl=3300, coro_factory=_headless_sweep_tick)


# ---------------------------------------------------------------------------
# Headless listing sweep — JS-walled careers sources (platform undetected or
# stuck at no_jobs) get ONE rendered-listing attempt per day. Successes mark
# the source profile {"headless": true}; the auto-sync tick then keeps them
# fresh on a daily headless cadence. Failures keep the honest no_jobs state.
# ---------------------------------------------------------------------------

_HEADLESS_SWEEP_BATCH = 3   # rendered pages per daily tick — headless is heavy


async def _headless_sweep_tick() -> None:
    if not get_settings().headless_scrape_enabled:
        return
    from app.db import get_db
    from app.skilled_pro.career_sources import profile_is_headless, run_headless_pull

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, e.name AS employer_name
              FROM public.employer_career_sources s
              JOIN public.employers e ON e.id = s.employer_id
             WHERE (s.platform IS NULL OR s.last_status IN ('no_jobs', 'error'))
               AND COALESCE(s.extraction_profile->>'headless', '') <> 'true'
               AND (s.last_pulled_at IS NULL
                    OR s.last_pulled_at < now() - INTERVAL '20 hours')
             ORDER BY s.last_pulled_at ASC NULLS FIRST
             LIMIT $1
            """,
            _HEADLESS_SWEEP_BATCH,
        )
        if not rows:
            return
        logger.info("Headless sweep: %d JS-walled candidate source(s)", len(rows))
        for r in rows:
            if profile_is_headless(r["extraction_profile"]):
                continue  # belt-and-braces; the SQL already filters these
            try:
                result = await run_headless_pull(conn, dict(r), triggered_by=None)
                logger.info(
                    "Headless pull %s: %s — %d found / %d new",
                    str(r["id"]), result["status"],
                    result["jobs_found"], result["jobs_new"],
                )
            except Exception as exc:
                logger.exception("Headless pull failed for source %s: %s", str(r["id"]), exc)


# ---------------------------------------------------------------------------
# Apply-link revalidation — periodic HEAD/GET (through the SSRF guard) of the
# apply/source URL on active scraped or imported jobs. Dead links flag the job
# for admin review; nothing is deactivated automatically.
# ---------------------------------------------------------------------------

_LINK_RECHECK_BATCH = 150          # jobs per tick — keeps the tick bounded
_LINK_RECHECK_STALE_DAYS = 7       # recheck cadence per job


async def _apply_link_recheck_tick() -> None:
    from app.db import get_db
    from app.skilled_pro.career_sources import check_apply_links

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_url FROM public.jobs
             WHERE is_active = TRUE
               AND source_url IS NOT NULL
               AND source_url ~* '^https?://'
               AND (apply_link_checked_at IS NULL
                    OR apply_link_checked_at < NOW() - make_interval(days => $1))
             ORDER BY apply_link_checked_at ASC NULLS FIRST
             LIMIT $2
            """,
            _LINK_RECHECK_STALE_DAYS, _LINK_RECHECK_BATCH,
        )
        if not rows:
            return
        results = await asyncio.to_thread(
            check_apply_links, [r["source_url"] for r in rows]
        )
        newly_broken = 0
        for r in rows:
            link_status = results.get(r["source_url"])
            if not link_status:
                continue
            await conn.execute(
                "UPDATE public.jobs SET apply_link_status = $2, apply_link_checked_at = NOW() "
                "WHERE id = $1::uuid",
                str(r["id"]), link_status,
            )
            if link_status in ("broken", "blocked"):
                # Flag for admin review once per job (skip if a pending item exists).
                pending = await conn.fetchval(
                    "SELECT 1 FROM public.review_queue_items "
                    "WHERE item_type = 'broken_apply_link' AND entity_id = $1::uuid "
                    "AND status = 'pending' LIMIT 1",
                    str(r["id"]),
                )
                if not pending:
                    await conn.execute(
                        """
                        INSERT INTO public.review_queue_items
                            (item_type, entity_type, entity_id, description, flags, priority)
                        VALUES ('broken_apply_link', 'job', $1::uuid, $2,
                                $3::jsonb, 3)
                        """,
                        str(r["id"]),
                        f"Apply link no longer resolves ({link_status}): {r['source_url']}",
                        '[{"flag_type": "broken_apply_link"}]',
                    )
                    newly_broken += 1
        logger.info(
            "Apply-link recheck: %d checked, %d newly flagged", len(rows), newly_broken,
        )


async def _recover_stuck_recomputes() -> None:
    """Mark recompute_runs.status='in_progress' rows older than 15 min as failed.

    This makes crash recovery observable: monitoring can alert on any failed
    row with error='server restart' to spot instability.
    """
    from app.db import get_db
    try:
        async with get_db() as conn:
            rows = await conn.fetch(
                """
                UPDATE public.recompute_runs
                   SET status = 'failed',
                       error = 'server restart',
                       completed_at = NOW()
                 WHERE status = 'in_progress'
                   AND started_at < NOW() - INTERVAL '15 minutes'
             RETURNING id
                """
            )
            if rows:
                logger.warning(
                    "Recovered %d stuck recompute_runs row(s) on boot", len(rows),
                )
    except Exception as exc:
        logger.warning("Recompute recovery skipped (%s)", exc)


async def _record_run_start(kind: str, target_id: str | None) -> str | None:
    """Insert a pending→in_progress recompute_runs row; return its id."""
    from app.db import get_db
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.recompute_runs (kind, target_id, status, started_at)
                VALUES ($1, $2::uuid, 'in_progress', NOW())
                RETURNING id::text
                """,
                kind,
                target_id,
            )
            return row["id"] if row else None
    except Exception as exc:
        logger.warning("Could not record recompute start: %s", exc)
        return None


async def _record_run_end(run_id: str | None, ok: bool, error: str | None = None) -> None:
    if not run_id:
        return
    from app.db import get_db
    try:
        async with get_db() as conn:
            await conn.execute(
                """
                UPDATE public.recompute_runs
                   SET status = $2, completed_at = NOW(), error = $3
                 WHERE id = $1::uuid
                """,
                run_id,
                "complete" if ok else "failed",
                (error or "")[:2000] if not ok else None,
            )
    except Exception as exc:
        logger.warning("Could not record recompute end: %s", exc)


# ---------------------------------------------------------------------------
# Career-source auto-sync — every 15 minutes, syncs connected careers pages
# whose next_auto_sync_at has elapsed. Uses run_pull, which routes through the
# learned-profile incremental path (so a no-change sync is ~1 fetch), records
# the pull in the activity log, and handles failure backoff + next scheduling
# itself. Never publishes on its own — approval still goes through admins.
#
# (This consolidates and replaces the old reviewer_note-based ATS resync tick,
# which was never persisted anywhere — see the former TODO(#143).)
# ---------------------------------------------------------------------------

# Fast-lane probes are ~1.5s each and run every 15-min tick; 25 keeps every
# realistic source count fully covered per tick with bounded tick time.
_CS_FAST_LANE_BATCH = 25
_CS_AUTO_SYNC_BATCH = 5   # sources per tick — incremental syncs are cheap,
                          # but a relearn can be slow; keep the tick bounded.


async def _career_source_auto_sync_tick() -> None:
    from app.db import get_db
    from app.skilled_pro.career_sources import (
        profile_is_headless,
        run_headless_pull,
        run_pull,
    )

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, e.name AS employer_name
              FROM public.employer_career_sources s
              JOIN public.employers e ON e.id = s.employer_id
             WHERE s.auto_sync_enabled
               AND (s.next_auto_sync_at IS NULL OR s.next_auto_sync_at <= now())
             ORDER BY s.next_auto_sync_at ASC NULLS FIRST
             LIMIT $1
            """,
            _CS_AUTO_SYNC_BATCH,
        )
        if not rows:
            return
        logger.info("Career-source auto-sync: %d source(s) due", len(rows))
        for r in rows:
            try:
                # JS-walled sources (profile.headless) sync via the daily
                # rendered-listing path; everything else takes the cheap
                # learned-profile incremental path.
                if profile_is_headless(r["extraction_profile"]):
                    result = await run_headless_pull(conn, dict(r), triggered_by=None)
                else:
                    result = await run_pull(conn, dict(r), triggered_by=None)
                logger.info(
                    "Auto-sync %s: %s (%s) in %sms — %d new / %d updated / %d removed",
                    str(r["id"]), result["status"], result["sync_mode"],
                    result["duration_ms"], result["jobs_new"], result["jobs_updated"],
                    result["jobs_removed"],
                )
            except Exception as exc:
                # run_pull records its own failures; this guards the tick itself.
                logger.exception("Auto-sync failed for source %s: %s", str(r["id"]), exc)



# ---------------------------------------------------------------------------
# Interview reminder ticker — runs every 5 minutes.
# ---------------------------------------------------------------------------

async def _interview_reminders_tick() -> None:
    """Emit reminders for accepted interview slots.

    Uses a `sent_reminders` payload key on the notifications row to dedupe so
    we never fire the same reminder twice for the same slot.
    """
    from app.db import get_db
    from app.skilled_pro.notifications import notify

    async with get_db() as conn:
        # 24h reminder window: 23h55m..24h05m from now
        # 1h reminder window: 55..65min from now
        # Follow-up: end_at is 1h55m..2h05m ago
        rows = await conn.fetch(
            """
            WITH windows AS (
              SELECT s.id, s.start_at, s.end_at, s.application_id, s.location, s.meeting_url,
                     a.applicant_id, a.job_id, a.employer_id,
                     ap.user_id AS applicant_user, j.title_raw, e.name AS employer_name,
                     (SELECT ec.user_id FROM public.employer_contacts ec
                       WHERE ec.employer_id = a.employer_id ORDER BY ec.created_at LIMIT 1) AS employer_user,
                     s.start_at - NOW() AS until_start,
                     NOW() - s.end_at AS since_end
                FROM public.interview_slots s
                JOIN public.applications a ON a.id = s.application_id
                JOIN public.applicants ap  ON ap.id = a.applicant_id
                JOIN public.jobs j         ON j.id = a.job_id
                JOIN public.employers e    ON e.id = a.employer_id
               WHERE s.status = 'accepted'
                 AND (
                       (s.start_at - NOW()) BETWEEN INTERVAL '23 hours 55 minutes' AND INTERVAL '24 hours 5 minutes'
                    OR (s.start_at - NOW()) BETWEEN INTERVAL '55 minutes'          AND INTERVAL '65 minutes'
                    OR (NOW() - s.end_at)   BETWEEN INTERVAL '1 hour 55 minutes'   AND INTERVAL '2 hours 5 minutes'
                     )
            )
            SELECT * FROM windows
            """
        )
        if not rows:
            return

        for r in rows:
            slot_id = str(r["id"])
            until_start = r["until_start"]
            since_end = r["since_end"]

            # Determine which reminder applies
            hours_until = until_start.total_seconds() / 3600.0 if until_start else -1
            hours_since = since_end.total_seconds() / 3600.0 if since_end else -1
            if 23 < hours_until < 25:
                kind_slug = "reminder_24h"
                title = f"Interview tomorrow at {r['start_at'].strftime('%-I:%M %p')}"
                body  = f"{r['employer_name']} for {r['title_raw']}."
            elif 0.9 < hours_until < 1.1:
                kind_slug = "reminder_1h"
                title = "Interview in an hour"
                loc = r["location"] or r["meeting_url"] or ""
                body  = f"{r['employer_name']} at {r['start_at'].strftime('%-I:%M %p')}" + (f" · {loc}" if loc else "")
            elif 1.9 < hours_since < 2.1:
                kind_slug = "followup"
                title = "How'd the interview go?"
                body  = f"Your interview with {r['employer_name']} wrapped up a couple hours ago."
            else:
                continue

            # Dedupe key stored on the notification payload
            existing = await conn.fetchval(
                """
                SELECT 1 FROM public.notifications
                 WHERE payload->>'slot_id' = $1
                   AND payload->>'reminder' = $2
                 LIMIT 1
                """,
                slot_id, kind_slug,
            )
            if existing:
                continue

            # Send to applicant + employer contact
            for user_id in (r["applicant_user"], r["employer_user"]):
                if not user_id:
                    continue
                await notify(
                    conn,
                    recipient_user_id=str(user_id),
                    kind=f"interview_{kind_slug}",
                    title=title,
                    body=body,
                    link_href=f"/applicant/applications/{r['application_id']}" if user_id == r["applicant_user"] else f"/employer/applications/{r['application_id']}",
                    payload={"slot_id": slot_id, "reminder": kind_slug, "application_id": str(r['application_id'])},
                )
        logger.info("Interview reminders tick: processed %d slot windows", len(rows))


async def _locked_fast_probe() -> None:
    await _run_locked("fast_probe", ttl=55, coro_factory=_fast_probe_tick)


async def _fast_probe_tick() -> None:
    """One change probe per connected source per minute, fanned out.

    Failure backoff lives in the source profile (probe_fail_streak): a source
    that keeps erroring is probed at 2^n minutes (capped at 15) instead of
    every tick, so one dead site never consumes the minute's budget.
    """
    import asyncio as _aio
    import time as _time

    from app.db import get_db
    from app.skilled_pro.career_sources import _parse_profile, fast_freshness_check

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, e.name AS employer_name
              FROM public.employer_career_sources s
              JOIN public.employers e ON e.id = s.employer_id
             WHERE s.auto_sync_enabled AND NOT s.needs_attention
             ORDER BY s.updated_at ASC
             LIMIT $1
            """,
            _CS_FAST_LANE_BATCH,
        )
    if not rows:
        return

    sem = _aio.Semaphore(8)
    now = _time.time()

    async def probe(r) -> None:
        source = dict(r)
        profile = _parse_profile(source.get("extraction_profile")) or {}
        streak = int(profile.get("probe_fail_streak") or 0)
        last_fail = float(profile.get("probe_last_fail_at") or 0)
        if streak and now - last_fail < min(60 * (2 ** streak), 900):
            return                       # backing off a failing source
        async with sem:
            # Each probe writes through its own connection so one slow
            # source never serializes the others behind a shared conn.
            try:
                async with get_db() as pconn:
                    pulled = await fast_freshness_check(pconn, source)
                    if streak:
                        await pconn.execute(
                            """UPDATE public.employer_career_sources
                                  SET extraction_profile =
                                      COALESCE(extraction_profile,'{}'::jsonb)
                                      || '{"probe_fail_streak": 0}'::jsonb
                                WHERE id = $1""", source["id"])
                if pulled:
                    logger.info("Live probe pulled source %s (%s)",
                                str(source["id"]), source["employer_name"])
            except Exception as exc:
                logger.warning("Live probe failed for source %s: %s",
                               str(source["id"]), exc)
                try:
                    async with get_db() as pconn:
                        await pconn.execute(
                            """UPDATE public.employer_career_sources
                                  SET extraction_profile =
                                      COALESCE(extraction_profile,'{}'::jsonb)
                                      || $2::jsonb
                                WHERE id = $1""",
                            source["id"],
                            {"probe_fail_streak": streak + 1,
                             "probe_last_fail_at": now})
                except Exception:
                    pass

    await _aio.gather(*(probe(r) for r in rows))


async def _supervise_match_worker() -> None:
    try:
        _ensure_match_worker()
    except Exception as exc:
        logger.warning("match worker supervision failed: %s", exc)


async def _locked_delta_sweep() -> None:
    await _run_locked("delta_sweep", ttl=1800, coro_factory=_delta_sweep_tick)


async def _delta_sweep_tick() -> None:
    """Enqueue entities changed since the last completed sweep.

    Watermark = the previous delta run's start time (first run: 6h back, the
    old full-sweep cadence). The queue's pending-unique index absorbs
    overlap with event-driven triggers for free.
    """
    from app.db import get_db
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                """INSERT INTO public.recompute_runs (kind, status, started_at)
                   VALUES ('delta', 'in_progress', now()) RETURNING id::text""")
            run_id = row["id"]
            wm = await conn.fetchval(
                """SELECT max(started_at) FROM public.recompute_runs
                    WHERE kind = 'delta' AND status = 'complete'""")
            # Only entities whose change has NO queue record at/after the
            # change time are drift — routine trigger-handled changes leave
            # a (possibly processed) queue row and must not raise alarms.
            jobs = await conn.fetch(
                """INSERT INTO public.match_queue (entity_type, entity_id)
                   SELECT 'job', j.id FROM public.jobs j
                    WHERE j.is_active AND j.updated_at > COALESCE(
                          $1::timestamptz, now() - interval '6 hours')
                      AND NOT EXISTS (
                        SELECT 1 FROM public.match_queue q
                         WHERE q.entity_type = 'job' AND q.entity_id = j.id
                           AND q.enqueued_at >= j.updated_at - interval '1 minute')
                   ON CONFLICT (entity_type, entity_id)
                        WHERE processed_at IS NULL DO NOTHING
                   RETURNING id""", wm)
            apps = await conn.fetch(
                """INSERT INTO public.match_queue (entity_type, entity_id)
                   SELECT 'applicant', a.id FROM public.applicants a
                    WHERE a.updated_at > COALESCE(
                          $1::timestamptz, now() - interval '6 hours')
                      AND NOT EXISTS (
                        SELECT 1 FROM public.match_queue q
                         WHERE q.entity_type = 'applicant' AND q.entity_id = a.id
                           AND q.enqueued_at >= a.updated_at - interval '1 minute')
                   ON CONFLICT (entity_type, entity_id)
                        WHERE processed_at IS NULL DO NOTHING
                   RETURNING id""", wm)
            await conn.execute("NOTIFY match_queue")
            # Queue hygiene: processed rows are audit breadcrumbs, not data.
            await conn.execute(
                "DELETE FROM public.match_queue WHERE processed_at < now() - interval '7 days'")
            await conn.execute(
                """UPDATE public.recompute_runs
                      SET status='complete', completed_at=now() WHERE id=$1::uuid""",
                run_id)
        if jobs or apps:
            _ensure_match_worker()
            # Triggers should have caught these at write time. Finding work
            # here means something wrote match-relevant data outside the
            # trigger guarantee — surface it loudly, then heal it anyway.
            logger.warning(
                "Match drift detector found %d job(s), %d applicant(s) that "
                "were NOT enqueued at write time — investigate the write path",
                len(jobs), len(apps))
    except Exception as exc:
        logger.exception("Delta sweep failed: %s", exc)


async def _locked_recompute() -> None:
    """Full recompute guarded by a Redis distributed lock."""
    try:
        import redis.asyncio as aioredis  # type: ignore
    except ImportError:
        logger.warning("redis package not installed — skipping distributed lock")
        await _run_recompute_subprocess()
        return

    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    lock = r.lock("skillpointe:recompute_lock", timeout=7200)  # 2-hour max
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.info("Recompute lock held by another instance — skipping")
        await r.aclose()
        return

    logger.info("Starting scheduled full match recompute")
    try:
        await _run_recompute_subprocess()
    finally:
        try:
            await lock.release()
        except Exception:
            pass
        await r.aclose()


async def _run_recompute_subprocess(
    job_id: str | None = None,
    applicant_id: str | None = None,
) -> None:
    """
    Run scripts/recompute_matches.py as a subprocess.
    Uses sys.executable (the current Python interpreter with all packages).

    Every invocation writes a row to public.recompute_runs so we can:
      * see what's in-flight (status='in_progress'),
      * detect crashes on next boot (recovery job marks stuck rows failed),
      * alert on repeated failures.
    """
    script = _REPO_ROOT / "scripts" / "recompute_matches.py"

    # --prefilter: candidate generation (same-state + sector-plausible) —
    # a scoped run must never brute-force the whole cross product.
    # --skip-geocode: coordinate backfill hits Nominatim at 1 req/sec and is
    # a scheduled maintenance concern, never part of a hot recompute.
    cmd = [sys.executable, str(script), "--prefilter", "--skip-geocode"]
    if job_id:
        cmd += ["--job-id", job_id]
    if applicant_id:
        cmd += ["--applicant-id", applicant_id]

    label = f"job={job_id}" if job_id else (f"applicant={applicant_id}" if applicant_id else "full")
    kind = "job" if job_id else ("applicant" if applicant_id else "full")
    target = job_id or applicant_id
    logger.info("Running recompute (%s)", label)

    run_id = await _record_run_start(kind, target)

    # Record the miss as a failed run. Returning early here would leave no row in
    # recompute_runs at all, so a deploy that ships without scripts/ looks
    # identical to one where matches simply never needed recomputing.
    if not script.exists():
        msg = f"recompute_matches.py not found at {script}"
        logger.error("%s — is scripts/ shipped with this deploy?", msg)
        await _record_run_end(run_id, ok=False, error=msg)
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Recompute finished (%s)", label)
            await _record_run_end(run_id, ok=True)
        else:
            err = stderr.decode()[:500]
            logger.error(
                "Recompute failed (%s) rc=%d stderr=%s",
                label,
                proc.returncode,
                err,
            )
            await _record_run_end(run_id, ok=False, error=f"rc={proc.returncode} {err}")
    except Exception as exc:
        logger.exception("Recompute subprocess error (%s): %s", label, exc)
        await _record_run_end(run_id, ok=False, error=str(exc))


async def _acquire_recompute_slot(target_key: str, ttl: int = 90) -> bool:
    """Best-effort Redis debounce: return True if no recompute is already
    pending/running for this target within the window. Coalesces bursts of edits
    (e.g. an employer saving a job five times) into a single recompute instead
    of five overlapping subprocesses. Falls back to allowing the run if Redis is
    unavailable, since the periodic full recompute is the safety net either way."""
    try:
        import redis.asyncio as aioredis  # type: ignore

        r = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        # SET NX EX — only the first trigger in the window wins the slot.
        got = await r.set(f"recompute:pending:{target_key}", "1", nx=True, ex=ttl)
        await r.aclose()
        return bool(got)
    except Exception as exc:  # Redis down — don't block the recompute
        logger.warning("Recompute debounce unavailable (%s) — allowing run", exc)
        return True


async def _debounced_recompute(*, job_id: str | None = None, applicant_id: str | None = None) -> None:
    """Enqueue the target for the resident match worker.

    The queue's partial unique index (pending targets) IS the debounce —
    re-triggering an already-pending target is a silent no-op, with no Redis
    involved. NOTIFY wakes the worker immediately. Falls back to the old
    one-shot subprocess only if the enqueue itself fails (queue table absent
    mid-migration), so a trigger is never dropped.
    """
    from app.db import get_db
    etype = "job" if job_id else "applicant"
    eid = job_id or applicant_id
    try:
        async with get_db() as conn:
            await conn.execute(
                """INSERT INTO public.match_queue (entity_type, entity_id)
                   VALUES ($1, $2::uuid)
                   ON CONFLICT (entity_type, entity_id) WHERE processed_at IS NULL
                   DO NOTHING""",
                etype, eid,
            )
            await conn.execute("NOTIFY match_queue")
        _ensure_match_worker()
    except Exception as exc:
        logger.warning("match_queue enqueue failed (%s) — subprocess fallback", exc)
        target_key = f"job:{job_id}" if job_id else f"applicant:{applicant_id}"
        if not await _acquire_recompute_slot(target_key):
            return
        await _run_recompute_subprocess(job_id=job_id, applicant_id=applicant_id)


_match_worker_proc = None


def _ensure_match_worker() -> None:
    """Keep exactly one resident match worker alive.

    Cheap enough to call on every enqueue; the daemon's pg_advisory_lock
    makes accidental doubles exit immediately, so supervision here only has
    to be best-effort.
    """
    global _match_worker_proc
    if _match_worker_proc is not None and _match_worker_proc.poll() is None:
        return
    script = _REPO_ROOT / "scripts" / "match_worker_daemon.py"
    if not script.exists():
        logger.warning("match_worker_daemon.py not found — resident worker unavailable")
        return
    import subprocess
    _match_worker_proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=open("/tmp/match_worker.log", "ab"),
        stderr=subprocess.STDOUT,
        cwd=str(_REPO_ROOT),
    )
    logger.info("resident match worker started (pid %s)", _match_worker_proc.pid)


async def trigger_recompute_for_job(job_id: str) -> None:
    """
    Fire-and-forget: recompute matches for a specific job, debounced so repeated
    edits don't spawn overlapping subprocesses. Called after a job is created/edited.
    """
    asyncio.create_task(_debounced_recompute(job_id=job_id))


async def trigger_recompute_for_applicant(applicant_id: str) -> None:
    """
    Fire-and-forget: recompute matches for a specific applicant, debounced.
    Called after an applicant profile is materially updated.
    """
    asyncio.create_task(_debounced_recompute(applicant_id=applicant_id))
