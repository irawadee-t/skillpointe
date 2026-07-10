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

# Path to the repo root (apps/api/app/worker/ → repo root)
_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _locked_recompute,
        trigger="interval",
        hours=6,
        id="full_recompute",
        name="Full match recompute (6h)",
        replace_existing=True,
        misfire_grace_time=600,  # 10-min grace if server was down
    )
    scheduler.add_job(
        _interview_reminders_tick,
        trigger="interval",
        minutes=5,
        id="interview_reminders",
        name="Interview reminders (24h/1h/follow-up)",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _ats_auto_resync_tick,
        trigger="interval",
        hours=1,
        id="ats_auto_resync",
        name="ATS auto-resync (per-batch cadence)",
        replace_existing=True,
        misfire_grace_time=1800,  # 30-min grace
    )
    # GDPR deletion sweep — daily hard-delete of accounts whose grace elapsed.
    scheduler.add_job(
        _deletion_sweep_tick,
        trigger="interval",
        hours=24,
        id="deletion_sweep",
        name="GDPR/CCPA account deletion sweep (daily)",
        replace_existing=True,
        misfire_grace_time=3600,
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
# ATS auto-resync — runs hourly, resyncs URL-based import batches that the
# employer/admin has opted into. Cadence lives on the batch row via a JSON
# `auto_sync_interval_days` field; batches without opt-in are skipped.
# ---------------------------------------------------------------------------

async def _ats_auto_resync_tick() -> None:
    """Look at URL-based batches with an auto-sync opt-in and re-scrape if
    the interval has elapsed. Marks source-removed rows as `stale` and
    inserts newly-found rows as `staged`. Never publishes on its own — the
    employer/admin still has to approve.
    """
    from app.db import get_db
    from app.skilled_pro.job_imports import universal_scrape

    async with get_db() as conn:
        # Read batches with an opt-in cadence stored in reviewer_note JSON.
        # (Using reviewer_note rather than adding a new column keeps the
        # migration surface small; task #143 can promote this to its own field.)
        rows = await conn.fetch(
            """
            SELECT b.id, b.source_label, b.updated_at, b.employer_id,
                   e.name AS employer_name,
                   COALESCE(
                     NULLIF(b.reviewer_note, '')::jsonb->>'auto_sync_interval_days',
                     ''
                   ) AS interval_days
              FROM public.job_import_batches b
              JOIN public.employers e ON e.id = b.employer_id
             WHERE b.source = 'url'
               AND b.reviewer_note IS NOT NULL
               AND b.reviewer_note LIKE '%%auto_sync_interval_days%%'
            """
        )
        if not rows:
            return

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        eligible = []
        for r in rows:
            try:
                days = int(r["interval_days"] or 0)
            except ValueError:
                continue
            if days <= 0:
                continue
            last = r["updated_at"] or now
            if now - last >= timedelta(days=days):
                eligible.append(r)

        if not eligible:
            return

        logger.info("ATS auto-resync: %d batches eligible", len(eligible))
        for r in eligible:
            batch_id = str(r["id"])
            source_url = r["source_label"]
            emp_name = r["employer_name"]
            try:
                platform, scraped = universal_scrape(source_url, employer_name=emp_name, max_jobs=200)
                if platform == "unknown" or not scraped:
                    logger.info("Auto-resync skipped %s — unrecognised platform", batch_id)
                    continue
                fresh_urls = {j.source_url for j in scraped if j.source_url}
                # Insert new rows
                new_rows = [
                    {
                        "title_raw": j.title, "description_raw": j.description,
                        "responsibilities_raw": j.responsibilities, "requirements_raw": j.requirements,
                        "preferred_qualifications_raw": j.qualifications, "city": j.city, "state": j.state,
                        "country": j.country or "US", "work_setting": j.work_setting, "pay_raw": j.pay_raw,
                        "experience_level": j.experience_level, "employment_type": j.employment_type,
                        "req_id": j.req_id, "source_url": j.source_url, "job_category": j.job_category,
                        "posted_date": j.posted_date,
                    }
                    for j in scraped
                ]
                # Late-import helper to avoid circular deps at module import time.
                from app.routers.job_imports import _insert_rows
                await _insert_rows(conn, batch_id, new_rows)

                # Flag rows whose source_url is no longer present.
                if fresh_urls:
                    existing = await conn.fetch(
                        "SELECT id, source_url FROM public.job_import_rows "
                        "WHERE batch_id = $1::uuid AND source_url IS NOT NULL AND status = 'staged'",
                        batch_id,
                    )
                    stale_ids = [row["id"] for row in existing if row["source_url"] not in fresh_urls]
                    if stale_ids:
                        await conn.execute(
                            "UPDATE public.job_import_rows SET status = 'stale', updated_at = now() "
                            "WHERE id = ANY($1::uuid[])",
                            stale_ids,
                        )
                        logger.info("Auto-resync %s: marked %d stale", batch_id, len(stale_ids))

                await conn.execute(
                    "UPDATE public.job_import_batches SET updated_at = now() WHERE id = $1::uuid",
                    batch_id,
                )
            except Exception as exc:
                logger.exception("Auto-resync failed for batch %s: %s", batch_id, exc)


# ---------------------------------------------------------------------------
# Interview reminder ticker — runs every 5 minutes.
# ---------------------------------------------------------------------------

async def _interview_reminders_tick() -> None:
    """Emit reminders for accepted interview slots.

    Uses a `sent_reminders` payload key on the notifications row to dedupe so
    we never fire the same reminder twice for the same slot.
    """
    import asyncpg
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
                title = f"Interview in an hour"
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
    if not script.exists():
        logger.error("recompute_matches.py not found at %s", script)
        return

    cmd = [sys.executable, str(script)]
    if job_id:
        cmd += ["--job-id", job_id]
    if applicant_id:
        cmd += ["--applicant-id", applicant_id]

    label = f"job={job_id}" if job_id else (f"applicant={applicant_id}" if applicant_id else "full")
    kind = "job" if job_id else ("applicant" if applicant_id else "full")
    target = job_id or applicant_id
    logger.info("Running recompute (%s)", label)

    run_id = await _record_run_start(kind, target)

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


async def trigger_recompute_for_job(job_id: str) -> None:
    """
    Fire-and-forget: recompute matches for a specific job.
    Called after a new job is created.
    """
    asyncio.create_task(_run_recompute_subprocess(job_id=job_id))


async def trigger_recompute_for_applicant(applicant_id: str) -> None:
    """
    Fire-and-forget: recompute matches for a specific applicant.
    Called after an applicant profile is materially updated.
    """
    asyncio.create_task(_run_recompute_subprocess(applicant_id=applicant_id))
