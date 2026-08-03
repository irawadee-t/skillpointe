#!/usr/bin/env python3
"""
Reconcile legacy scraped/imported jobs into career-source fingerprint memory.

Pre-career-sources jobs (the ~390-job demo catalog) have a source_url but are
invisible to the incremental sync's fingerprint memory, so source-site
removals never mark them stale. This enrolls every active URL-bearing job
whose URL matches a registered source (learned link patterns → listing host →
Workday tenant → registrable domain, same-employer only) into:

  * career_source_jobs   (first_seen from the job's created_at, fingerprint
                          from the stored content), and
  * the source's rolling batch as a 'published' row linked via
    published_job_id — the handle listing syncs use to deactivate the live
    job when its posting vanishes (after the 2-consecutive-miss grace).

Jobs matching no registered source stay orphans (the apply-link recheck keeps
covering them). Idempotent.

Usage (from repo root, API venv active):
  python scripts/reconcile_career_sources.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO / "apps" / "api"))


async def main() -> int:
    from app.db import close_db_pool, get_db
    from app.skilled_pro.reconcile import reconcile_legacy_jobs

    async with get_db() as conn:
        result = await reconcile_legacy_jobs(conn)

    print(f"\nScanned {result['jobs_scanned']} active jobs with a source URL\n")
    print(f"{'Source':<44} {'matched':>8} {'enrolled':>9} {'tracked':>8} "
          f"{'rows+':>6} {'linked':>7}")
    for s in result["sources"]:
        label = f"{s['employer_name']} ({s['url']})"[:44]
        print(f"{label:<44} {s['matched']:>8} {s['enrolled']:>9} "
              f"{s['already_tracked']:>8} {s['rows_created']:>6} {s['rows_linked']:>7}")
    print(f"\nEnrolled {result['jobs_enrolled']} new, "
          f"{result['jobs_already_tracked']} already tracked, "
          f"{result['orphans_total']} orphans (apply-link recheck still covers them).")
    if result["orphans_by_host"]:
        print("Orphans by host:")
        for host, n in result["orphans_by_host"].items():
            print(f"  {host}: {n}")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
