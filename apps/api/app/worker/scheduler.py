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
    return scheduler


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
    logger.info("Running recompute (%s)", label)

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
        else:
            logger.error(
                "Recompute failed (%s) rc=%d stderr=%s",
                label,
                proc.returncode,
                stderr.decode()[:500],
            )
    except Exception as exc:
        logger.exception("Recompute subprocess error (%s): %s", label, exc)


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
