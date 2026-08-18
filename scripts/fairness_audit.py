"""Adverse-impact audit: four-fifths rule over matching outcomes.

Computes selection rates by gender, age_range, and military_status for two
favorable outcomes, then the impact ratio of each group against the
highest-rate group (EEOC four-fifths guideline: ratios below 0.80 indicate
adverse impact worth investigating):

  1. surfaced   — applicant has at least one visible match (eligible/near_fit)
  2. actionable — applicant has at least one 0- or 1-gap match (the band the
                  product presents as "act on this now")

Demographics are used ONLY here, read-only, for auditing — they are not
inputs to the engine (verified: _fetch_applicants selects no protected
attribute, and packages/matching never reads gender/age/military/dob).

Usage: python scripts/fairness_audit.py [--min-group 50]
Writes audit/fairness/adverse_impact.md
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent
DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"

OUTCOMES = {
    "surfaced": """
        EXISTS (SELECT 1 FROM matches m WHERE m.applicant_id = a.id
                 AND m.eligibility_status IN ('eligible','near_fit'))""",
    "actionable": """
        EXISTS (SELECT 1 FROM matches m WHERE m.applicant_id = a.id
                 AND m.eligibility_status IN ('eligible','near_fit')
                 AND COALESCE(m.n_gaps, 9) <= 1)""",
}

GROUPS = {
    "gender": "NULLIF(trim(a.gender), '')",
    "age_range": "NULLIF(trim(a.age_range), '')",
    "military_status": "CASE WHEN a.military_status THEN 'veteran/military' ELSE 'civilian' END",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-group", type=int, default=50,
                    help="suppress groups smaller than this (noise + privacy)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    lines = ["# Adverse-impact audit (four-fifths rule)", "",
             "Groups below the minimum size are suppressed. Ratio = group rate /",
             "highest group rate; < 0.80 flags adverse impact (EEOC guideline).", ""]
    worst: list[tuple[float, str]] = []

    for gname, gexpr in GROUPS.items():
        for oname, opred in OUTCOMES.items():
            cur.execute(f"""
                SELECT {gexpr} AS grp, count(*) AS n,
                       count(*) FILTER (WHERE {opred}) AS hits
                  FROM applicants a
                 WHERE {gexpr} IS NOT NULL
                 GROUP BY 1 HAVING count(*) >= %s ORDER BY 2 DESC""",
                (args.min_group,))
            rows = [(g, n, h, h / n) for g, n, h in cur.fetchall()]
            if not rows:
                continue
            top = max(r[3] for r in rows)
            lines.append(f"## {gname} x {oname}")
            lines.append("")
            lines.append("| group | n | rate | impact ratio | flag |")
            lines.append("|---|---|---|---|---|")
            for g, n, h, rate in sorted(rows, key=lambda r: -r[3]):
                ratio = rate / top if top else 0.0
                flag = "ADVERSE (<0.80)" if ratio < 0.80 else ""
                lines.append(f"| {g} | {n} | {rate:.3f} | {ratio:.3f} | {flag} |")
                if ratio < 0.80:
                    worst.append((ratio, f"{gname}={g} on {oname}"))
            lines.append("")

    lines.append("## Summary")
    if worst:
        lines.append("Flagged (investigate the causal path before shipping ranking changes):")
        for ratio, desc in sorted(worst):
            lines.append(f"- {desc}: ratio {ratio:.3f}")
    else:
        lines.append("No group fell below the 0.80 impact-ratio threshold.")

    out = REPO / "audit" / "fairness" / "adverse_impact.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
