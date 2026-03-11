#!/usr/bin/env python3
"""
recompute_matches.py — Phase 5: Match recomputation pipeline.

Fetches applicants and jobs from Supabase, runs the deterministic matching
engine, and upserts results into the matches + match_dimension_scores tables.

Prerequisites:
  1. normalize_data.py must have been run (canonical_job_family_id populated)
  2. Local Supabase must be running: supabase start

Usage:
  # Full recompute — all active applicants × all active jobs
  python scripts/recompute_matches.py

  # Single applicant (useful for debugging)
  python scripts/recompute_matches.py --applicant-id <uuid>

  # Single job
  python scripts/recompute_matches.py --job-id <uuid>

  # Limit to first N applicants × N jobs (fast smoke test)
  python scripts/recompute_matches.py --limit 10

  # Dry-run: compute but do not write to DB
  python scripts/recompute_matches.py --dry-run

  # Verbose: print score breakdowns during run
  python scripts/recompute_matches.py --verbose

For a full run with 335 applicants × 300 jobs = 100,500 pairs.
Expect ~2–5 min on local hardware with no parallelism.

See BUILD_PLAN.md §7 (Early Data / Ranking Validation Rule).
"""
import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path

# Allow importing from packages/
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from matching.config import load_config
from matching.engine import compute_match, MatchResult
from matching.normalizer import normalize_timing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute all applicant-job matches"
    )
    parser.add_argument("--applicant-id", default=None,
                        help="Only recompute matches for this applicant UUID")
    parser.add_argument("--job-id", default=None,
                        help="Only recompute matches for this job UUID")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit applicants AND jobs to first N each (testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write to DB")
    parser.add_argument("--verbose", action="store_true",
                        help="Print score breakdowns")
    args = parser.parse_args()

    # ----------------------------------------------------------------
    # Connect + load config
    # ----------------------------------------------------------------
    try:
        from etl.db import get_connection
    except ImportError:
        from etl.db import get_connection

    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR connecting to DB: {e}")
        print("Is Supabase running?  Run: supabase start")
        return 1

    config = _load_active_config(conn)
    print(f"Loaded policy config version: {config.version}")

    # ----------------------------------------------------------------
    # Fetch applicants + jobs
    # ----------------------------------------------------------------
    applicants = _fetch_applicants(conn, applicant_id=args.applicant_id, limit=args.limit)
    jobs = _fetch_jobs(conn, job_id=args.job_id, limit=args.limit)
    employers = _fetch_employers(conn)

    employer_map = {str(e["id"]): e for e in employers}

    total_pairs = len(applicants) * len(jobs)
    print(f"Applicants: {len(applicants)}, Jobs: {len(jobs)}, Pairs: {total_pairs}")
    if args.dry_run:
        print("(DRY RUN — no data will be written)\n")

    # ----------------------------------------------------------------
    # Scoring run metadata
    # ----------------------------------------------------------------
    run_id = str(uuid.uuid4())
    run_date = date.today().isoformat()
    print(f"Scoring run ID: {run_id}\n")

    # ----------------------------------------------------------------
    # Compute matches
    # ----------------------------------------------------------------
    counters = {"total": 0, "eligible": 0, "near_fit": 0, "ineligible": 0,
                "error": 0, "strong_fit": 0, "good_fit": 0}

    BATCH = 500  # commit every N rows

    for app in applicants:
        for job in jobs:
            emp = employer_map.get(str(job.get("employer_id")), {})
            try:
                result = compute_match(app, job, emp, config,
                                       today=date.today(),
                                       scoring_run_id=run_id)
                counters["total"] += 1
                counters[result.eligibility_status] = counters.get(result.eligibility_status, 0) + 1
                counters[result.match_label] = counters.get(result.match_label, 0) + 1

                if args.verbose:
                    _print_match(result, app, job)

                if not args.dry_run:
                    _upsert_match(conn, result)

                    if counters["total"] % BATCH == 0:
                        conn.commit()
                        print(f"  ... {counters['total']}/{total_pairs} committed")

            except Exception as e:
                counters["error"] += 1
                if args.verbose:
                    print(f"  ERROR app={app['id']!s:.8} job={job['id']!s:.8}: {e}")

    if not args.dry_run:
        conn.commit()
    conn.close()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"  Recompute summary: {run_date}{'  [DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)
    print(f"  Total pairs:    {counters['total']}")
    print(f"  Eligible:       {counters.get('eligible', 0)}")
    print(f"  Near-fit:       {counters.get('near_fit', 0)}")
    print(f"  Ineligible:     {counters.get('ineligible', 0)}")
    print(f"  Strong fit:     {counters.get('strong_fit', 0)}")
    print(f"  Good fit:       {counters.get('good_fit', 0)}")
    print(f"  Errors:         {counters['error']}")
    print(f"  Run ID:         {run_id}")
    print()
    return 0 if counters["error"] == 0 else 1


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_active_config(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT config FROM public.policy_configs WHERE is_active = TRUE LIMIT 1"
        )
        row = cur.fetchone()
    if row:
        import yaml  # type: ignore
        # config is stored as JSONB — convert to YAML-compatible dict
        cfg_dict = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        from matching.config import _from_yaml
        return _from_yaml(cfg_dict)
    return load_config()


def _fetch_applicants(conn, applicant_id=None, limit=None) -> list[dict]:
    where = "WHERE 1=1"
    params = []
    if applicant_id:
        where += " AND a.id = %s"
        params.append(applicant_id)
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT
            a.id, a.first_name, a.last_name, a.program_name_raw,
            a.state, a.region, a.city,
            a.willing_to_relocate, a.willing_to_travel, a.commute_radius_miles,
            a.experience_raw, a.bio_raw, a.career_goals_raw,
            a.expected_completion_date, a.available_from_date,
            jf.code AS canonical_job_family_code
        FROM public.applicants a
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
        {where}
        ORDER BY a.created_at
        {lim}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_jobs(conn, job_id=None, limit=None) -> list[dict]:
    where = "WHERE j.is_active = TRUE"
    params = []
    if job_id:
        where += " AND j.id = %s"
        params.append(job_id)
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT
            j.id, j.employer_id,
            j.title_raw, j.title_normalized, j.description_raw,
            j.requirements_raw, j.preferred_qualifications_raw,
            j.state, j.region, j.city,
            j.work_setting, j.travel_requirement,
            j.pay_min, j.pay_max, j.pay_type, j.pay_raw,
            j.required_credentials,
            jf.code AS canonical_job_family_code
        FROM public.jobs j
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        {where}
        ORDER BY j.created_at
        {lim}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_employers(conn) -> list[dict]:
    sql = "SELECT id, name, is_partner FROM public.employers"
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _upsert_match(conn, result: MatchResult):
    """Upsert into matches table, then replace dimension_scores rows."""
    match_data = {
        "applicant_id":           result.applicant_id,
        "job_id":                 result.job_id,
        "eligibility_status":     result.eligibility_status,
        "hard_gate_cap":          result.hard_gate_cap,
        "hard_gate_failures":     json.dumps(result.hard_gate_failures),
        "hard_gate_rationale":    json.dumps(result.hard_gate_rationale),
        "weighted_structured_score": result.weighted_structured_score,
        "semantic_score":         result.semantic_score,
        "base_fit_score":         result.base_fit_score,
        "policy_modifiers":       json.dumps(result.policy_modifiers),
        "policy_adjusted_score":  result.policy_adjusted_score,
        "match_label":            result.match_label,
        "top_strengths":          json.dumps(result.top_strengths),
        "top_gaps":               json.dumps(result.top_gaps),
        "required_missing_items": json.dumps(result.required_missing_items),
        "recommended_next_step":  result.recommended_next_step,
        "confidence_level":       result.confidence_level,
        "requires_review":        result.requires_review,
        "scoring_run_id":         result.scoring_run_id,
        "scoring_run_at":         result.scoring_run_at,
        "policy_version":         result.policy_version,
    }

    with conn.cursor() as cur:
        # Upsert match row
        cur.execute("""
            INSERT INTO public.matches (
                applicant_id, job_id,
                eligibility_status, hard_gate_cap, hard_gate_failures, hard_gate_rationale,
                weighted_structured_score, semantic_score, base_fit_score,
                policy_modifiers, policy_adjusted_score,
                match_label, top_strengths, top_gaps, required_missing_items,
                recommended_next_step,
                confidence_level, requires_review,
                scoring_run_id, scoring_run_at, policy_version
            ) VALUES (
                %(applicant_id)s, %(job_id)s,
                %(eligibility_status)s, %(hard_gate_cap)s,
                %(hard_gate_failures)s::jsonb, %(hard_gate_rationale)s::jsonb,
                %(weighted_structured_score)s, %(semantic_score)s, %(base_fit_score)s,
                %(policy_modifiers)s::jsonb, %(policy_adjusted_score)s,
                %(match_label)s,
                %(top_strengths)s::jsonb, %(top_gaps)s::jsonb,
                %(required_missing_items)s::jsonb,
                %(recommended_next_step)s,
                %(confidence_level)s, %(requires_review)s,
                %(scoring_run_id)s::uuid, %(scoring_run_at)s::date, %(policy_version)s
            )
            ON CONFLICT (applicant_id, job_id) DO UPDATE SET
                eligibility_status     = EXCLUDED.eligibility_status,
                hard_gate_cap          = EXCLUDED.hard_gate_cap,
                hard_gate_failures     = EXCLUDED.hard_gate_failures,
                hard_gate_rationale    = EXCLUDED.hard_gate_rationale,
                weighted_structured_score = EXCLUDED.weighted_structured_score,
                semantic_score         = EXCLUDED.semantic_score,
                base_fit_score         = EXCLUDED.base_fit_score,
                policy_modifiers       = EXCLUDED.policy_modifiers,
                policy_adjusted_score  = EXCLUDED.policy_adjusted_score,
                match_label            = EXCLUDED.match_label,
                top_strengths          = EXCLUDED.top_strengths,
                top_gaps               = EXCLUDED.top_gaps,
                required_missing_items = EXCLUDED.required_missing_items,
                recommended_next_step  = EXCLUDED.recommended_next_step,
                confidence_level       = EXCLUDED.confidence_level,
                requires_review        = EXCLUDED.requires_review,
                scoring_run_id         = EXCLUDED.scoring_run_id,
                scoring_run_at         = EXCLUDED.scoring_run_at,
                policy_version         = EXCLUDED.policy_version,
                updated_at             = NOW()
            RETURNING id
        """, match_data)

        match_row = cur.fetchone()
        if not match_row:
            return
        match_id = str(match_row[0])

        # Replace dimension scores (delete + insert)
        cur.execute(
            "DELETE FROM public.match_dimension_scores WHERE match_id = %s",
            (match_id,)
        )

        for dim in result.dimension_scores:
            cur.execute("""
                INSERT INTO public.match_dimension_scores
                    (match_id, dimension, weight, raw_score, weighted_score,
                     rationale, null_handling_applied, null_handling_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                match_id,
                dim.dimension,
                dim.weight,
                dim.raw_score,
                dim.weighted_score,
                dim.rationale,
                dim.null_handling_applied,
                dim.null_handling_default,
            ))


def _print_match(result: MatchResult, app: dict, job: dict):
    name = f"{app.get('first_name', '')} {app.get('last_name', '')}".strip() or str(app["id"])[:8]
    jtitle = (job.get("title_normalized") or job.get("title_raw") or "")[:30]
    print(
        f"  [{result.eligibility_status.upper():10s}] "
        f"score={result.policy_adjusted_score:5.1f} | "
        f"{name[:20]:20s} → {jtitle}"
    )


if __name__ == "__main__":
    sys.exit(main())
