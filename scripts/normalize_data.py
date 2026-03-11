#!/usr/bin/env python3
"""
normalize_data.py — Phase 4.3: Deterministic normalization layer.

Reads applicants and jobs from the database, applies normalization, and
writes normalized values back to the DB.  Raw source text is NEVER modified.

Normalization performed:
  Applicants:
    - program_name_raw → canonical_job_family_id (via alias/keyword matching)
    - state + geography_regions → region
  Jobs:
    - title_raw + career_pathway_raw (from extra) → canonical_job_family_id
    - title_normalized (cleaned title)
    - pay_raw → pay_min, pay_max, pay_type
    - state → region
    - work_setting (already set by import; re-validates if needed)

Flags ambiguous mappings for admin review (printed to stdout; future: review queue).

Usage:
  # Normalize all un-normalized applicants and jobs
  python scripts/normalize_data.py

  # Normalize everything (re-run even if already normalised)
  python scripts/normalize_data.py --all

  # Dry-run: show what would change without writing
  python scripts/normalize_data.py --dry-run

  # Only applicants or only jobs
  python scripts/normalize_data.py --applicants-only
  python scripts/normalize_data.py --jobs-only

  # Verbose: show each row result
  python scripts/normalize_data.py --verbose

See BUILD_PLAN.md §4 Step 4.3.
"""
import argparse
import sys
from pathlib import Path

# Allow importing from packages/
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from matching.normalizer import (
    normalize_program_to_job_family,
    normalize_job_title_to_family,
    normalize_pay_range,
    normalize_location,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize applicants and jobs in Supabase Postgres"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without writing to DB")
    parser.add_argument("--all", action="store_true",
                        help="Re-normalise even already-normalised rows")
    parser.add_argument("--applicants-only", action="store_true")
    parser.add_argument("--jobs-only", action="store_true")
    parser.add_argument("--verbose", action="store_true",
                        help="Show each row's normalization result")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N rows per table (testing)")
    args = parser.parse_args()

    # Connect to DB
    try:
        from etl.db import get_connection
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))
        from etl.db import get_connection

    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR connecting to database: {e}")
        print("Is local Supabase running?  Run: supabase start")
        return 1

    # Load reference data
    job_families = _load_job_families(conn)
    geo_regions = _load_geo_regions(conn)

    if not job_families:
        print("WARNING: no canonical_job_families found in DB.")
        print("Run: supabase db reset  to load seed data.")

    print(f"Loaded {len(job_families)} job families, {len(geo_regions)} geography regions.")

    results = {"applicant": {}, "job": {}}

    # ----------------------------------------------------------------
    # Normalize applicants
    # ----------------------------------------------------------------
    if not args.jobs_only:
        a_results = _normalize_applicants(
            conn, job_families, geo_regions, args, verbose=args.verbose
        )
        results["applicant"] = a_results

    # ----------------------------------------------------------------
    # Normalize jobs
    # ----------------------------------------------------------------
    if not args.applicants_only:
        j_results = _normalize_jobs(
            conn, job_families, geo_regions, args, verbose=args.verbose
        )
        results["job"] = j_results

    if not args.dry_run:
        conn.commit()
    conn.close()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"  Normalization summary{'  [DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)

    for entity, r in results.items():
        if not r:
            continue
        total = r.get("total", 0)
        matched = r.get("matched", 0)
        unmatched = r.get("unmatched", 0)
        review = r.get("needs_review", 0)
        print(f"\n  {entity.upper()}S  ({total} processed)")
        print(f"    Family matched:  {matched}")
        print(f"    No match:        {unmatched}")
        print(f"    Needs review:    {review}")
        if r.get("unmatched_programs"):
            print(f"\n  Unmatched {entity} programs (top 10 — add aliases to seed.sql):")
            for prog in list(set(r["unmatched_programs"]))[:10]:
                print(f"    - {prog!r}")

    print()
    if args.dry_run:
        print("  DRY RUN — no data was written.\n")

    return 0


# ---------------------------------------------------------------------------
# Applicant normalization
# ---------------------------------------------------------------------------

def _normalize_applicants(conn, job_families, geo_regions, args, verbose=False):
    where = "" if args.all else "WHERE canonical_job_family_id IS NULL"
    limit = f"LIMIT {args.limit}" if args.limit else ""
    sql = f"SELECT id, program_name_raw, state, city FROM public.applicants {where} {limit}"

    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    print(f"\nNormalizing {len(rows)} applicants ...")

    stats = {"total": len(rows), "matched": 0, "unmatched": 0,
             "needs_review": 0, "unmatched_programs": []}

    for row in rows:
        app_id = str(row["id"])
        program = row.get("program_name_raw") or ""
        state = row.get("state") or ""

        # Normalize program → job family
        norm = normalize_program_to_job_family(program, job_families)
        family_id = _family_code_to_id(norm.family_code, job_families)
        region = normalize_location(row.get("city"), state, geo_regions)

        if norm.family_code:
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1
            if program:
                stats["unmatched_programs"].append(program)

        if norm.needs_review:
            stats["needs_review"] += 1

        if verbose:
            status = "✓" if norm.family_code else "?"
            review = " [REVIEW]" if norm.needs_review else ""
            print(f"  {status} applicant {app_id[:8]} | {program[:40]!r:42s} → {norm.family_code or 'NO MATCH'} (conf: {norm.confidence}){review}")

        if not args.dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.applicants
                    SET canonical_job_family_id = %s,
                        region = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (family_id, region, app_id),
                )

    return stats


# ---------------------------------------------------------------------------
# Job normalization
# ---------------------------------------------------------------------------

def _normalize_jobs(conn, job_families, geo_regions, args, verbose=False):
    where = "" if args.all else "WHERE canonical_job_family_id IS NULL"
    limit = f"LIMIT {args.limit}" if args.limit else ""
    sql = f"""
        SELECT id, title_raw, pay_raw, state, city, work_setting,
               (SELECT raw_data->>'career_pathway_raw'
                FROM public.import_rows ir
                WHERE ir.entity_id = jobs.id::text
                  AND ir.entity_type = 'job'
                ORDER BY ir.created_at DESC LIMIT 1) AS career_pathway_raw
        FROM public.jobs {where} {limit}
    """

    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    print(f"\nNormalizing {len(rows)} jobs ...")

    stats = {"total": len(rows), "matched": 0, "unmatched": 0,
             "needs_review": 0, "unmatched_programs": []}

    for row in rows:
        job_id = str(row["id"])
        title = row.get("title_raw") or ""
        pathway = row.get("career_pathway_raw") or ""
        pay_raw = row.get("pay_raw") or ""
        state = row.get("state") or ""

        # Normalize job title → family
        norm = normalize_job_title_to_family(title, pathway, job_families)
        family_id = _family_code_to_id(norm.family_code, job_families)
        region = normalize_location(row.get("city"), state, geo_regions)

        # Parse pay range
        pay_min, pay_max, pay_type = normalize_pay_range(pay_raw)

        # Normalized title (pathway is cleaner than job_title usually)
        title_norm = pathway.strip() or title.strip() or None

        if norm.family_code:
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1
            if title:
                stats["unmatched_programs"].append(f"{pathway or title}")

        if norm.needs_review:
            stats["needs_review"] += 1

        if verbose:
            status = "✓" if norm.family_code else "?"
            pay_str = f"${pay_min}–${pay_max}/{pay_type}" if pay_min else "(no pay)"
            print(f"  {status} job {job_id[:8]} | {(pathway or title)[:35]!r:37s} → {norm.family_code or 'NO MATCH'} | {pay_str}")

        if not args.dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.jobs
                    SET canonical_job_family_id = %s,
                        title_normalized = %s,
                        region = %s,
                        pay_min = %s,
                        pay_max = %s,
                        pay_type = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (family_id, title_norm, region, pay_min, pay_max, pay_type, job_id),
                )

    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_job_families(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, name, aliases FROM public.canonical_job_families WHERE is_active = TRUE")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _load_geo_regions(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, name, states FROM public.geography_regions WHERE is_active = TRUE")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _family_code_to_id(code: str | None, job_families: list[dict]):
    if not code:
        return None
    for fam in job_families:
        if fam["code"] == code:
            return fam["id"]
    return None


if __name__ == "__main__":
    sys.exit(main())
