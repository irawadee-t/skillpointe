#!/usr/bin/env python3
"""
update_trades_jobs.py — Refresh all trades jobs from configured employer sites.

What this does, end-to-end:

  1. Runs each adapter (Ball, Delta, GE Vernova, Schneider, Southwire — and
     Ford if you keep it). Adapters return *every* listing they find.
  2. Classifies each listing's TITLE against the comprehensive trades taxonomy
     (packages/scraper/trades.py). Non-trades titles are dropped immediately —
     this avoids fetching their detail pages and is the main efficiency win.
  3. For trades-classified listings only, fetches the detail page to enrich
     the description / requirements / pay / etc.
  4. Upserts into public.jobs in the standardized ScrapedJob shape, with the
     canonical_job_family_code stamped from the classifier — so every job in
     the table has a consistent shape and family across every employer.
  5. Optionally deactivates stale postings (--refresh) and prints a tidy
     per-site + per-family summary.

Usage:
  python scripts/update_trades_jobs.py
  python scripts/update_trades_jobs.py --site ball
  python scripts/update_trades_jobs.py --dry-run        # don't write
  python scripts/update_trades_jobs.py --refresh        # deactivate stale
  python scripts/update_trades_jobs.py --max-per-site 50  # cap for testing

Defaults the site list to the 5 you actually use today: ball, delta, ge_vernova,
schneider, southwire. Add 'ford' with --include-ford if you want it.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from scraper.adapters import ADAPTERS  # type: ignore
from scraper.base import ScrapedJob  # type: ignore
from scraper.extract import parse_sections  # type: ignore
from scraper.trades import classify, TradeMatch  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_trades_jobs")

# Sites we actually maintain. (Ford is opt-in.)
DEFAULT_SITES = ["ball", "delta", "ge_vernova", "schneider", "southwire"]


# ---------------------------------------------------------------------------
# Per-site summary container
# ---------------------------------------------------------------------------

class SiteSummary:
    def __init__(self, site: str):
        self.site = site
        self.listings_total = 0     # raw listings returned by the adapter
        self.trades_kept = 0        # listings that classified as trades
        self.details_fetched = 0    # detail pages actually fetched
        self.jobs_created = 0
        self.jobs_updated = 0
        self.jobs_deactivated = 0
        self.errors = 0
        self.by_family: Counter[str] = Counter()
        self.elapsed_sec = 0.0

    def render(self) -> str:
        f = ", ".join(f"{k}={v}" for k, v in self.by_family.most_common())
        return (
            f"  {self.site:12s}  listings={self.listings_total:>4}  "
            f"trades={self.trades_kept:>4}  "
            f"detail={self.details_fetched:>4}  "
            f"created={self.jobs_created:>3}  "
            f"updated={self.jobs_updated:>3}  "
            f"deact={self.jobs_deactivated:>3}  "
            f"errors={self.errors:>2}  "
            f"({self.elapsed_sec:0.1f}s)"
            + (f"\n     families: {f}" if f else "")
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Refresh trades jobs from employer career sites")
    p.add_argument("--site", choices=list(ADAPTERS.keys()), help="Only scrape this site")
    p.add_argument("--include-ford", action="store_true", help="Include Ford in the default site set")
    p.add_argument("--dry-run", action="store_true", help="Scrape + classify but don't write to DB")
    p.add_argument("--refresh", action="store_true", help="Deactivate stale jobs not seen this run")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1.0)")
    p.add_argument("--max-per-site", type=int, default=0,
                   help="Cap detail fetches per site (0 = no cap, useful for smoke-tests)")
    p.add_argument("--list-sites", action="store_true", help="List adapters and exit")
    args = p.parse_args()

    if args.list_sites:
        for name, cls in ADAPTERS.items():
            print(f"  {name:12s} — {cls.site_name}")
        return 0

    if args.site:
        sites = [args.site]
    else:
        sites = list(DEFAULT_SITES)
        if args.include_ford and "ford" not in sites and "ford" in ADAPTERS:
            sites.append("ford")

    conn = None
    if not args.dry_run:
        try:
            from etl.db import get_connection  # type: ignore
            conn = get_connection()
        except Exception as exc:
            logger.error("DB connection failed: %s", exc)
            logger.error("Tip: ensure Supabase is running (`supabase start`).")
            return 1

    summaries: list[SiteSummary] = []
    for site in sites:
        summary = SiteSummary(site)
        summaries.append(summary)
        adapter_cls = ADAPTERS[site]
        adapter = adapter_cls(delay=args.delay)  # type: ignore
        start = time.time()

        try:
            _run_site(adapter, site, conn, args, summary)
        except Exception as exc:
            logger.exception("[%s] aborted with error: %s", site, exc)
            summary.errors += 1
        finally:
            adapter.close()
            summary.elapsed_sec = time.time() - start

    # Pretty summary
    print()
    print("=" * 78)
    print(f"  Trades-jobs refresh {'[DRY RUN]' if args.dry_run else ''}")
    print("=" * 78)
    for s in summaries:
        print(s.render())
    total = lambda f: sum(getattr(s, f) for s in summaries)
    print("-" * 78)
    print(
        f"  TOTAL         listings={total('listings_total'):>4}  "
        f"trades={total('trades_kept'):>4}  "
        f"detail={total('details_fetched'):>4}  "
        f"created={total('jobs_created'):>3}  "
        f"updated={total('jobs_updated'):>3}  "
        f"deact={total('jobs_deactivated'):>3}  "
        f"errors={total('errors'):>2}"
    )
    fam_totals: Counter[str] = Counter()
    for s in summaries:
        fam_totals.update(s.by_family)
    if fam_totals:
        print("\n  Families:")
        for fam, n in fam_totals.most_common():
            print(f"     {fam:28s} {n}")
    print()

    if conn is not None:
        conn.close()
    return 0


# ---------------------------------------------------------------------------
# Per-site pipeline
# ---------------------------------------------------------------------------

def _run_site(adapter, site: str, conn, args, summary: SiteSummary) -> None:
    """Scrape listings → classify → fetch detail for trades only → upsert."""
    logger.info("[%s] starting", site)

    # Most adapters separate listings (cheap) from detail-fetch (expensive),
    # which lets us classify titles before fetching detail. A few (Delta) run
    # a single Playwright session that returns full ScrapedJobs all at once —
    # we route those through a separate path below.
    if not hasattr(adapter, "scrape_listings"):
        _run_site_full(adapter, site, conn, args, summary)
        return

    listings = adapter.scrape_listings()
    summary.listings_total = len(listings)
    logger.info("[%s] %d listings returned", site, len(listings))

    # 1) Classify on title alone (cheap, no extra HTTP).
    trades_listings: list[tuple[dict[str, Any], TradeMatch]] = []
    for listing in listings:
        title = (listing.get("title") or "").strip()
        match = classify(title)
        if match.is_trade:
            trades_listings.append((listing, match))

    summary.trades_kept = len(trades_listings)
    logger.info("[%s] %d trades after title-classification (%.0f%% retained)",
                site, len(trades_listings),
                (len(trades_listings) / max(1, len(listings))) * 100)

    # Optional cap (smoke-test convenience)
    if args.max_per_site and len(trades_listings) > args.max_per_site:
        trades_listings = trades_listings[: args.max_per_site]
        logger.info("[%s] capped to %d listings (--max-per-site)", site, len(trades_listings))

    # 2) Fetch detail only for trades — the big efficiency win.
    employer_id = None
    if not args.dry_run:
        employer_id = _ensure_employer(conn, adapter.site_name)

    seen_urls: set[str] = set()
    for i, (listing, match) in enumerate(trades_listings):
        try:
            job = adapter.scrape_detail(listing)
        except Exception as exc:
            logger.warning("[%s] detail failed for %s: %s",
                           site, listing.get("url", "?"), exc)
            summary.errors += 1
            continue

        summary.details_fetched += 1
        if job is None:
            continue

        # ------------------------------------------------------------------
        # Standardize fields. Adapters return varying levels of detail:
        # Southwire/GE Vernova dump everything into description; Schneider
        # already splits qualifications/responsibilities. Parse the description
        # blob into structured sections and fill in any missing fields, never
        # overwriting fields the adapter already populated.
        # ------------------------------------------------------------------
        parsed = parse_sections(job.description)
        if parsed.description:
            job.description = parsed.description
        if not job.responsibilities and parsed.responsibilities:
            job.responsibilities = parsed.responsibilities
        if not job.requirements and parsed.requirements:
            job.requirements = parsed.requirements
        if not job.qualifications and parsed.qualifications:
            job.qualifications = parsed.qualifications
        if not job.pay_raw and parsed.pay_raw:
            job.pay_raw = parsed.pay_raw
        if not job.experience_level and parsed.experience_level:
            job.experience_level = parsed.experience_level

        # Pre-classify on rich content too — title may have been generic; the
        # description sometimes confirms a different (or no) family. Trust
        # whichever produced is_trade=True; family priority is title's.
        if not match.family and job.description:
            recheck = classify(job.title, job.description)
            if recheck.family:
                match = recheck

        seen_urls.add(job.source_url)
        summary.by_family[match.family or "unspecified"] += 1

        if args.dry_run:
            continue
        was_created = _upsert_job(conn, job, employer_id, match.family)
        if was_created:
            summary.jobs_created += 1
        else:
            summary.jobs_updated += 1
        if (i + 1) % 25 == 0:
            logger.info("[%s] processed %d/%d trades", site, i + 1, len(trades_listings))

    if args.refresh and not args.dry_run:
        summary.jobs_deactivated = _deactivate_stale(conn, site, seen_urls)

    if not args.dry_run:
        conn.commit()


def _run_site_full(adapter, site: str, conn, args, summary: SiteSummary) -> None:
    """Pipeline for adapters that only expose `scrape_all` (Playwright-driven).
    They return fully-detailed ScrapedJobs in one shot, so we classify the
    title afterwards and post-process the description like everything else."""
    jobs = adapter.scrape_all()
    summary.listings_total = len(jobs)
    logger.info("[%s] %d full jobs returned", site, len(jobs))

    employer_id = None
    if not args.dry_run:
        employer_id = _ensure_employer(conn, adapter.site_name)

    seen_urls: set[str] = set()
    for i, job in enumerate(jobs):
        match = classify(job.title, job.description)
        if not match.is_trade:
            continue
        summary.trades_kept += 1

        # Post-process description into structured sections.
        parsed = parse_sections(job.description)
        if parsed.description:
            job.description = parsed.description
        if not job.responsibilities and parsed.responsibilities:
            job.responsibilities = parsed.responsibilities
        if not job.requirements and parsed.requirements:
            job.requirements = parsed.requirements
        if not job.qualifications and parsed.qualifications:
            job.qualifications = parsed.qualifications
        if not job.pay_raw and parsed.pay_raw:
            job.pay_raw = parsed.pay_raw
        if not job.experience_level and parsed.experience_level:
            job.experience_level = parsed.experience_level

        seen_urls.add(job.source_url)
        summary.by_family[match.family or "unspecified"] += 1
        summary.details_fetched += 1
        if args.dry_run:
            continue
        was_created = _upsert_job(conn, job, employer_id, match.family)
        if was_created:
            summary.jobs_created += 1
        else:
            summary.jobs_updated += 1
        if (i + 1) % 25 == 0:
            logger.info("[%s] processed %d/%d", site, i + 1, len(jobs))

    if args.refresh and not args.dry_run:
        summary.jobs_deactivated = _deactivate_stale(conn, site, seen_urls)
    if not args.dry_run:
        conn.commit()


# ---------------------------------------------------------------------------
# DB helpers — keep the table shape consistent for every employer
# ---------------------------------------------------------------------------

def _ensure_employer(conn, employer_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.employers WHERE name = %s LIMIT 1",
            (employer_name,),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])
        eid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO public.employers (id, name, source) VALUES (%s, %s, 'scraper')",
            (eid, employer_name),
        )
    conn.commit()
    logger.info("created employer record: %s (%s)", employer_name, eid)
    return eid


def _resolve_family_id(conn, family_code: Optional[str]) -> Optional[str]:
    if not family_code:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.canonical_job_families WHERE code = %s LIMIT 1",
            (family_code,),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None


# Map the classifier's canonical-trade codes to the codes that actually exist
# in public.canonical_job_families. Keeps families consistent in the DB even
# though the classifier uses more specific names internally.
_FAMILY_ALIAS: dict[str, str] = {
    "manufacturing_production": "manufacturing",
    "industrial_maintenance":   "industrial_maintenance",  # dedicated family since 2026-08 taxonomy expansion
    "automotive_diesel":        "automotive",
    "machining_cnc":            "manufacturing",
    "construction_skilled":     "construction",
    "aviation_aerospace":       "aviation",
    "logistics_warehouse":      "logistics",
    "utilities_energy":         "energy_lineman",  # nearest existing bucket
    "hvac_r":                   "hvac",
    # Same-name passes through (classifier code == canonical code), including
    # the 2026-08 expansion families: power_plant, building_automation,
    # rail_transit, marine, field_service, civil_survey, security, electronics,
    # data_center, and the healthcare families.
    "electrical": "electrical", "welding": "welding", "plumbing": "plumbing",
}

_FAMILY_CACHE: dict[str, Optional[str]] = {}


def _family_id(conn, code: Optional[str]) -> Optional[str]:
    if code is None:
        return None
    db_code = _FAMILY_ALIAS.get(code, code)
    if db_code in _FAMILY_CACHE:
        return _FAMILY_CACHE[db_code]
    rid = _resolve_family_id(conn, db_code)
    _FAMILY_CACHE[db_code] = rid
    return rid


_WORK_SETTINGS = {"remote", "on_site", "onsite", "hybrid", "flexible"}


def _coerce_work_setting(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    v = raw.lower().replace("-", "_")
    if v == "onsite":
        v = "on_site"
    return v if v in _WORK_SETTINGS else None


def _upsert_job(conn, job: ScrapedJob, employer_id: str, family_code: Optional[str]) -> bool:
    """Upsert by source_url. Standardized columns for every site."""
    work_setting = _coerce_work_setting(job.work_setting)
    fam_id = _family_id(conn, family_code)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.jobs WHERE source_url = %s LIMIT 1",
            (job.source_url,),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
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
                    canonical_job_family_id = COALESCE(%s, canonical_job_family_id),
                    is_active = TRUE,
                    last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    job.title, job.description, job.requirements,
                    job.qualifications, job.responsibilities,
                    job.city, job.state, job.pay_raw,
                    work_setting, job.experience_level, fam_id,
                    str(existing[0]),
                ),
            )
            return False

        cur.execute(
            """
            INSERT INTO public.jobs (
                employer_id, title_raw, description_raw,
                requirements_raw, preferred_qualifications_raw, responsibilities_raw,
                city, state, country,
                pay_raw, work_setting, experience_level,
                canonical_job_family_id,
                source, source_url, source_site,
                is_active, last_verified_at, posted_date
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s,
                'scraper', %s, %s,
                TRUE, NOW(), %s
            )
            """,
            (
                employer_id, job.title, job.description,
                job.requirements, job.qualifications, job.responsibilities,
                job.city, job.state, job.country,
                job.pay_raw, work_setting, job.experience_level,
                fam_id,
                job.source_url, job.source_site,
                job.posted_date,
            ),
        )
        return True


def _deactivate_stale(conn, source_site: str, seen_urls: set[str]) -> int:
    if not seen_urls:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public.jobs
               SET is_active = FALSE, updated_at = NOW()
             WHERE source_site = %s
               AND source = 'scraper'
               AND is_active = TRUE
               AND source_url NOT IN %s
            """,
            (source_site, tuple(seen_urls)),
        )
        return cur.rowcount


if __name__ == "__main__":
    sys.exit(main())
