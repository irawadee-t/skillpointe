#!/usr/bin/env python3
"""
scrape_jobs.py — Scrape job postings from employer career sites.

Scrapes listings from configured employer sites, normalizes them into
the standard jobs table schema, and upserts into Supabase. Stale jobs
(not seen in the latest scrape) are deactivated automatically.

Usage:
  python scripts/scrape_jobs.py                 # scrape all sites
  python scripts/scrape_jobs.py --site ball     # scrape one site
  python scripts/scrape_jobs.py --list-sites    # list available sites
  python scripts/scrape_jobs.py --dry-run       # scrape but don't write to DB
  python scripts/scrape_jobs.py --refresh       # re-scrape + deactivate stale
"""
import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from scraper.adapters import ADAPTERS
from scraper.base import ScrapedJob

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape job postings from employer career sites")
    parser.add_argument("--site", choices=list(ADAPTERS.keys()), help="Scrape a specific site only")
    parser.add_argument("--list-sites", action="store_true", help="List available scraping adapters")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't write to DB")
    parser.add_argument("--refresh", action="store_true", help="Deactivate stale jobs not found in scrape")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    if args.list_sites:
        print("Available scraping adapters:")
        for name, cls in ADAPTERS.items():
            print(f"  {name:15s} — {cls.site_name}")
        return 0

    try:
        from etl.db import get_connection
        conn = get_connection()
    except Exception as e:
        print(f"ERROR connecting to DB: {e}")
        print("Is Supabase running?  Run: supabase start")
        return 1

    sites = [args.site] if args.site else list(ADAPTERS.keys())
    total_created = 0
    total_updated = 0
    total_deactivated = 0

    for site_name in sites:
        adapter_cls = ADAPTERS[site_name]
        adapter = adapter_cls(delay=args.delay)  # type: ignore
        run_id = str(uuid.uuid4())

        logger.info(f"Starting scrape: {adapter.site_name}")

        if not args.dry_run:
            _create_scrape_run(conn, run_id, site_name)

        try:
            jobs = adapter.scrape_all()
            logger.info(f"[{site_name}] Scraped {len(jobs)} jobs")

            employer_id = _ensure_employer(conn, adapter.site_name, args.dry_run)

            seen_urls: set[str] = set()
            created = 0
            updated = 0

            for job in jobs:
                seen_urls.add(job.source_url)
                if not args.dry_run:
                    was_created = _upsert_job(conn, job, employer_id)
                    if was_created:
                        created += 1
                    else:
                        updated += 1

            deactivated = 0
            if args.refresh and not args.dry_run:
                deactivated = _deactivate_stale(conn, site_name, seen_urls)

            if not args.dry_run:
                _complete_scrape_run(conn, run_id, len(jobs), created, updated, deactivated)
                conn.commit()

            total_created += created
            total_updated += updated
            total_deactivated += deactivated

            logger.info(
                f"[{site_name}] Done: {created} created, {updated} updated, "
                f"{deactivated} deactivated"
            )

        except Exception as e:
            logger.error(f"[{site_name}] Scrape failed: {e}")
            if not args.dry_run:
                _fail_scrape_run(conn, run_id, str(e))
                conn.commit()
        finally:
            adapter.close()

    conn.close()

    print()
    print("=" * 50)
    print(f"  Scrape complete {'[DRY RUN]' if args.dry_run else ''}")
    print("=" * 50)
    print(f"  Sites scraped:    {len(sites)}")
    print(f"  Jobs created:     {total_created}")
    print(f"  Jobs updated:     {total_updated}")
    print(f"  Jobs deactivated: {total_deactivated}")
    print()
    return 0


def _ensure_employer(conn, employer_name: str, dry_run: bool):
    """Find or create an employer record for the scraped company."""
    if dry_run:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.employers WHERE name = %s LIMIT 1",
            (employer_name,)
        )
        row = cur.fetchone()
        if row:
            return str(row[0])

        eid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO public.employers (id, name, source)
               VALUES (%s, %s, 'scraper')""",
            (eid, employer_name)
        )
        conn.commit()
        logger.info(f"Created employer: {employer_name} ({eid})")
        return eid


def _upsert_job(conn, job: ScrapedJob, employer_id: str) -> bool:
    """Upsert a scraped job into the jobs table. Returns True if created (new)."""
    work_setting = _coerce_work_setting(job.work_setting)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.jobs WHERE source_url = %s LIMIT 1",
            (job.source_url,)
        )
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE public.jobs SET
                    title_raw = %s,
                    description_raw = %s,
                    requirements_raw = %s,
                    preferred_qualifications_raw = %s,
                    responsibilities_raw = %s,
                    city = %s, state = %s,
                    pay_raw = %s,
                    work_setting = %s,
                    experience_level = %s,
                    is_active = TRUE,
                    last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (
                job.title, job.description, job.requirements,
                job.qualifications, job.responsibilities,
                job.city, job.state,
                job.pay_raw,
                work_setting,
                job.experience_level,
                str(existing[0]),
            ))
            return False

        cur.execute("""
            INSERT INTO public.jobs (
                employer_id, title_raw, description_raw,
                requirements_raw, preferred_qualifications_raw,
                responsibilities_raw,
                city, state, country,
                pay_raw, work_setting, experience_level,
                source, source_url, source_site,
                is_active, last_verified_at, posted_date
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                'scraper', %s, %s,
                TRUE, NOW(), %s
            )
        """, (
            employer_id, job.title, job.description,
            job.requirements, job.qualifications,
            job.responsibilities,
            job.city, job.state, job.country,
            job.pay_raw, work_setting, job.experience_level,
            job.source_url, job.source_site,
            job.posted_date,
        ))
        return True


def _coerce_work_setting(raw):
    """Map scraped work_setting to the enum values in the DB."""
    if not raw:
        return None
    mapping = {
        "remote": "remote",
        "on_site": "on_site",
        "onsite": "on_site",
        "hybrid": "hybrid",
        "flexible": "flexible",
    }
    return mapping.get(raw.lower())


def _deactivate_stale(conn, source_site: str, seen_urls: set[str]) -> int:
    """Deactivate scraped jobs from this site that weren't found in the latest scrape."""
    if not seen_urls:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.jobs
               SET is_active = FALSE, updated_at = NOW()
               WHERE source_site = %s
                 AND source = 'scraper'
                 AND is_active = TRUE
                 AND source_url NOT IN %s
               RETURNING id""",
            (source_site, tuple(seen_urls))
        )
        return cur.rowcount


def _create_scrape_run(conn, run_id: str, source_site: str):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO public.scrape_runs (id, source_site, status)
               VALUES (%s, %s, 'running')""",
            (run_id, source_site)
        )
    conn.commit()


def _complete_scrape_run(conn, run_id: str, found: int, created: int, updated: int, deactivated: int):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.scrape_runs
               SET status = 'completed', completed_at = NOW(),
                   jobs_found = %s, jobs_created = %s,
                   jobs_updated = %s, jobs_deactivated = %s
               WHERE id = %s""",
            (found, created, updated, deactivated, run_id)
        )


def _fail_scrape_run(conn, run_id: str, error: str):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.scrape_runs
               SET status = 'failed', completed_at = NOW(),
                   error_message = %s
               WHERE id = %s""",
            (error[:500], run_id)
        )


if __name__ == "__main__":
    sys.exit(main())
