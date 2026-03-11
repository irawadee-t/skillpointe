#!/usr/bin/env python3
"""
inspect_matches.py — CLI inspection of computed match results.

Allows ranking quality validation BEFORE building polished UI dashboards.
Per BUILD_PLAN.md §7 (Early Data / Ranking Validation Rule).

Usage:
  # List imported applicants (with IDs for use below)
  python scripts/inspect_matches.py --list-applicants

  # List imported jobs
  python scripts/inspect_matches.py --list-jobs

  # Top 10 jobs for one applicant
  python scripts/inspect_matches.py --applicant-id <uuid>

  # Top 10 applicants for one job
  python scripts/inspect_matches.py --job-id <uuid>

  # Show dimension score breakdown
  python scripts/inspect_matches.py --applicant-id <uuid> --breakdown

  # Show top-N (default 10)
  python scripts/inspect_matches.py --applicant-id <uuid> --top 20

  # Include ineligible results (hidden by default)
  python scripts/inspect_matches.py --applicant-id <uuid> --show-ineligible

  # Export to CSV
  python scripts/inspect_matches.py --applicant-id <uuid> --export-csv /tmp/matches.csv

  # Overall stats across all matches
  python scripts/inspect_matches.py --stats

See BUILD_PLAN.md §7 (Early Data / Ranking Validation Rule).
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect SkillPointe Match results from CLI"
    )
    parser.add_argument("--applicant-id", default=None,
                        help="Show top-N jobs for this applicant UUID")
    parser.add_argument("--job-id", default=None,
                        help="Show top-N applicants for this job UUID")
    parser.add_argument("--list-applicants", action="store_true",
                        help="List first 30 applicants with their IDs")
    parser.add_argument("--list-jobs", action="store_true",
                        help="List first 30 jobs with their IDs")
    parser.add_argument("--top", type=int, default=10,
                        help="Show top N results (default: 10)")
    parser.add_argument("--show-ineligible", action="store_true",
                        help="Include ineligible results in output")
    parser.add_argument("--breakdown", action="store_true",
                        help="Show dimension score breakdown for each match")
    parser.add_argument("--export-csv", default=None, metavar="PATH",
                        help="Export results to CSV file")
    parser.add_argument("--stats", action="store_true",
                        help="Show overall match statistics")
    args = parser.parse_args()

    try:
        from etl.db import get_connection
        conn = get_connection()
    except Exception as e:
        print(f"ERROR: {e}")
        print("Is Supabase running?  Run: supabase start")
        return 1

    # ----------------------------------------------------------------
    # Dispatch
    # ----------------------------------------------------------------
    if args.stats:
        _show_stats(conn)

    elif args.list_applicants:
        _list_applicants(conn, limit=30)

    elif args.list_jobs:
        _list_jobs(conn, limit=30)

    elif args.applicant_id:
        rows = _top_jobs_for_applicant(
            conn, args.applicant_id,
            top=args.top,
            include_ineligible=args.show_ineligible,
        )
        _print_applicant_view(conn, args.applicant_id, rows, args.breakdown)
        if args.export_csv:
            _export_csv(rows, args.export_csv, view="applicant")
            print(f"\nExported to {args.export_csv}")

    elif args.job_id:
        rows = _top_applicants_for_job(
            conn, args.job_id,
            top=args.top,
            include_ineligible=args.show_ineligible,
        )
        _print_job_view(conn, args.job_id, rows, args.breakdown)
        if args.export_csv:
            _export_csv(rows, args.export_csv, view="job")
            print(f"\nExported to {args.export_csv}")

    else:
        parser.print_help()

    conn.close()
    return 0


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _top_jobs_for_applicant(conn, applicant_id: str, top=10, include_ineligible=False) -> list[dict]:
    elig_filter = "" if include_ineligible else "AND m.eligibility_status != 'ineligible'"
    sql = f"""
        SELECT
            m.id AS match_id,
            m.applicant_id, m.job_id,
            m.eligibility_status, m.match_label,
            m.base_fit_score, m.policy_adjusted_score,
            m.weighted_structured_score, m.semantic_score,
            m.hard_gate_cap,
            m.top_strengths, m.top_gaps, m.required_missing_items,
            m.recommended_next_step,
            m.confidence_level, m.requires_review,
            m.hard_gate_failures,
            j.title_raw, j.title_normalized, j.city AS job_city, j.state AS job_state,
            j.work_setting, j.pay_raw, j.pay_min, j.pay_max, j.pay_type,
            e.name AS employer_name, e.is_partner
        FROM public.matches m
        JOIN public.jobs j ON j.id = m.job_id
        JOIN public.employers e ON e.id = j.employer_id
        WHERE m.applicant_id = %s
          {elig_filter}
        ORDER BY m.policy_adjusted_score DESC NULLS LAST
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (applicant_id, top))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _top_applicants_for_job(conn, job_id: str, top=10, include_ineligible=False) -> list[dict]:
    elig_filter = "" if include_ineligible else "AND m.eligibility_status != 'ineligible'"
    sql = f"""
        SELECT
            m.id AS match_id,
            m.applicant_id, m.job_id,
            m.eligibility_status, m.match_label,
            m.base_fit_score, m.policy_adjusted_score,
            m.weighted_structured_score, m.semantic_score,
            m.hard_gate_cap,
            m.top_strengths, m.top_gaps, m.required_missing_items,
            m.recommended_next_step,
            m.confidence_level, m.requires_review,
            m.hard_gate_failures,
            a.first_name, a.last_name, a.program_name_raw,
            a.city AS app_city, a.state AS app_state,
            a.expected_completion_date,
            jf.code AS app_family_code
        FROM public.matches m
        JOIN public.applicants a ON a.id = m.applicant_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
        WHERE m.job_id = %s
          {elig_filter}
        ORDER BY m.policy_adjusted_score DESC NULLS LAST
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (job_id, top))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _get_dimension_scores(conn, match_id: str) -> list[dict]:
    sql = """
        SELECT dimension, weight, raw_score, weighted_score, rationale,
               null_handling_applied, null_handling_default
        FROM public.match_dimension_scores
        WHERE match_id = %s
        ORDER BY weight DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (match_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

ELIG_ICON = {"eligible": "✓", "near_fit": "~", "ineligible": "✗"}
LABEL_ICON = {"strong_fit": "★★★", "good_fit": "★★ ", "moderate_fit": "★  ", "low_fit": "   "}


def _print_applicant_view(conn, applicant_id: str, rows: list[dict], breakdown: bool):
    # Fetch applicant info
    with conn.cursor() as cur:
        cur.execute(
            """SELECT a.first_name, a.last_name, a.program_name_raw,
                      a.city, a.state, jf.code
               FROM public.applicants a
               LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
               WHERE a.id = %s""",
            (applicant_id,)
        )
        a = cur.fetchone()

    if a:
        name = f"{a[0] or ''} {a[1] or ''}".strip() or "(unnamed)"
        prog = a[2] or "(no program)"
        loc = f"{a[3] or ''}, {a[4] or ''}".strip(", ") or "(no location)"
        fam = a[5] or "(not normalised)"
        print(f"\n{'=' * 70}")
        print(f"  APPLICANT: {name}")
        print(f"  Program:   {prog}")
        print(f"  Location:  {loc}  |  Family: {fam}")
        print(f"  ID:        {applicant_id}")
        print(f"{'=' * 70}")

    if not rows:
        print("  No matches found. Run recompute_matches.py first.")
        return

    print(f"\n  {'#':>2}  {'ELIG':10s}  {'SCORE':6s}  {'LABEL':12s}  JOB / EMPLOYER\n")
    for i, r in enumerate(rows, 1):
        icon = ELIG_ICON.get(r["eligibility_status"], "?")
        lbl = r.get("match_label") or ""
        title = (r.get("title_normalized") or r.get("title_raw") or "")[:35]
        emp = (r.get("employer_name") or "")[:25]
        loc = f"{r.get('job_city') or ''}, {r.get('job_state') or ''}".strip(", ")
        pay = _pay_str(r)
        ws = (r.get("work_setting") or "")[:8]
        partner = "⭐" if r.get("is_partner") else "  "

        print(
            f"  {i:>2}  {icon} {r['eligibility_status']:10s}  "
            f"{r['policy_adjusted_score']:5.1f}  "
            f"{lbl:12s}  {partner} {emp[:20]:20s} | {title}"
        )
        print(f"       Location: {loc:20s}  Pay: {pay:20s}  Work: {ws}")

        if r.get("top_strengths"):
            strengths = _parse_json_list(r["top_strengths"])
            if strengths:
                print(f"       Strengths: {'; '.join(strengths[:2])}")

        if r.get("top_gaps"):
            gaps = _parse_json_list(r["top_gaps"])
            if gaps:
                print(f"       Gaps:      {'; '.join(gaps[:2])}")

        if r.get("recommended_next_step"):
            print(f"       Next step: {r['recommended_next_step']}")

        if r.get("requires_review"):
            print(f"       ⚠ Requires review")

        if breakdown:
            dims = _get_dimension_scores(conn, str(r["match_id"]))
            if dims:
                print(f"       Dimensions:")
                for d in dims:
                    null_flag = " [null-default]" if d.get("null_handling_applied") else ""
                    print(f"         {d['dimension']:35s}  {d['raw_score']:5.1f}  w={d['weight']:.0f}{null_flag}")
                    print(f"           {d['rationale']}")

        print()


def _print_job_view(conn, job_id: str, rows: list[dict], breakdown: bool):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT j.title_raw, j.city, j.state, j.work_setting, j.pay_raw,
                      e.name, jf.code
               FROM public.jobs j
               JOIN public.employers e ON e.id = j.employer_id
               LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
               WHERE j.id = %s""",
            (job_id,)
        )
        j = cur.fetchone()

    if j:
        loc = f"{j[1] or ''}, {j[2] or ''}".strip(", ") or "(no location)"
        fam = j[6] or "(not normalised)"
        print(f"\n{'=' * 70}")
        print(f"  JOB:       {j[0] or '(no title)'}")
        print(f"  Employer:  {j[5] or '(unknown)'}  |  Family: {fam}")
        print(f"  Location:  {loc}  |  Work: {j[3] or '?'}  |  Pay: {j[4] or '?'}")
        print(f"  ID:        {job_id}")
        print(f"{'=' * 70}")

    if not rows:
        print("  No matches found. Run recompute_matches.py first.")
        return

    print(f"\n  {'#':>2}  {'ELIG':10s}  {'SCORE':6s}  {'LABEL':12s}  APPLICANT\n")
    for i, r in enumerate(rows, 1):
        icon = ELIG_ICON.get(r["eligibility_status"], "?")
        lbl = r.get("match_label") or ""
        name = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "(unnamed)"
        prog = (r.get("program_name_raw") or "(no program)")[:35]
        loc = f"{r.get('app_city') or ''}, {r.get('app_state') or ''}".strip(", ")
        fam = r.get("app_family_code") or "?"
        comp_date = r.get("expected_completion_date")
        comp_str = str(comp_date) if comp_date else "no date"

        print(
            f"  {i:>2}  {icon} {r['eligibility_status']:10s}  "
            f"{r['policy_adjusted_score']:5.1f}  "
            f"{lbl:12s}  {name[:25]:25s} | {fam}"
        )
        print(f"       Program: {prog:35s}  Loc: {loc:15s}  Avail: {comp_str}")

        if r.get("top_gaps"):
            gaps = _parse_json_list(r["top_gaps"])
            if gaps:
                print(f"       Gaps:     {'; '.join(gaps[:2])}")

        if r.get("requires_review"):
            print(f"       ⚠ Requires review")

        if breakdown:
            dims = _get_dimension_scores(conn, str(r["match_id"]))
            if dims:
                print(f"       Dimensions:")
                for d in dims:
                    null_flag = " [null-default]" if d.get("null_handling_applied") else ""
                    print(f"         {d['dimension']:35s}  {d['raw_score']:5.1f}  w={d['weight']:.0f}{null_flag}")

        print()


def _list_applicants(conn, limit=30):
    sql = """
        SELECT a.id, a.first_name, a.last_name, a.program_name_raw,
               a.city, a.state, jf.code AS family
        FROM public.applicants a
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
        ORDER BY a.created_at
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()

    print(f"\n{'ID':36s}  {'NAME':25s}  {'PROGRAM':35s}  {'LOC':12s}  FAMILY")
    print("-" * 120)
    for r in rows:
        uid, fn, ln, prog, city, state, fam = r
        name = f"{fn or ''} {ln or ''}".strip() or "(unnamed)"
        prog_s = (prog or "(none)")[:34]
        loc = f"{city or ''},{state or ''}".strip(",")[:11]
        fam_s = (fam or "?")[:15]
        print(f"{uid!s}  {name:25s}  {prog_s:35s}  {loc:12s}  {fam_s}")


def _list_jobs(conn, limit=30):
    sql = """
        SELECT j.id, j.title_raw, e.name, j.city, j.state, j.work_setting, j.pay_raw,
               jf.code AS family
        FROM public.jobs j
        JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE j.is_active = TRUE
        ORDER BY j.created_at
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()

    print(f"\n{'ID':36s}  {'TITLE':30s}  {'EMPLOYER':25s}  {'LOC':12s}  FAMILY")
    print("-" * 120)
    for r in rows:
        uid, title, emp, city, state, ws, pay, fam = r
        t = (title or "")[:29]
        e = (emp or "")[:24]
        loc = f"{city or ''},{state or ''}".strip(",")[:11]
        fam_s = (fam or "?")[:15]
        print(f"{uid!s}  {t:30s}  {e:25s}  {loc:12s}  {fam_s}")


def _show_stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.matches")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT eligibility_status, COUNT(*) AS n
            FROM public.matches
            GROUP BY eligibility_status
            ORDER BY n DESC
        """)
        elig_rows = cur.fetchall()

        cur.execute("""
            SELECT match_label, COUNT(*) AS n
            FROM public.matches
            GROUP BY match_label
            ORDER BY n DESC
        """)
        label_rows = cur.fetchall()

        cur.execute("""
            SELECT ROUND(AVG(policy_adjusted_score), 2) AS avg,
                   ROUND(MIN(policy_adjusted_score), 2) AS min,
                   ROUND(MAX(policy_adjusted_score), 2) AS max
            FROM public.matches
        """)
        score_stats = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM public.matches WHERE requires_review = TRUE")
        review_count = cur.fetchone()[0]

    print(f"\n{'=' * 50}")
    print(f"  MATCH STATISTICS")
    print(f"{'=' * 50}")
    print(f"  Total matches:  {total:,}")
    print()
    print("  By eligibility:")
    for row in elig_rows:
        print(f"    {row[0]:12s}  {row[1]:6,}")
    print()
    print("  By match label:")
    for row in label_rows:
        print(f"    {row[0]:14s}  {row[1]:6,}")
    if score_stats and score_stats[0] is not None:
        print()
        print(f"  Score distribution:")
        print(f"    avg={score_stats[0]}  min={score_stats[1]}  max={score_stats[2]}")
    print()
    print(f"  Requires review: {review_count:,}")
    print()


def _export_csv(rows: list[dict], path: str, view: str):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow({
                k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                for k, v in r.items()
            })


def _pay_str(r: dict) -> str:
    if r.get("pay_min"):
        lo, hi = r["pay_min"], r.get("pay_max") or r["pay_min"]
        pt = r.get("pay_type") or ""
        suffix = "/hr" if pt == "hourly" else ("/yr" if pt == "annual" else "")
        return f"${lo:.0f}–${hi:.0f}{suffix}"
    return r.get("pay_raw") or "(no pay)"


def _parse_json_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        import json
        return json.loads(val) if isinstance(val, str) else []
    except Exception:
        return []


if __name__ == "__main__":
    sys.exit(main())
