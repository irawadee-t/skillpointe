"""Infer a career field for applicants who stated one in free text.

The 2026-08 golden-set audit found applicants who typed their exact target
career ("aviation maintenance technician", "Automotive Technician GM ASEP")
into specific_career but have no canonical field — so the family gate treats
them as unknown-neutral and their exact-match jobs rank by generic
same-state order. The job side already runs a classifier at ingest; this is
the applicant-side twin.

Politeness invariant: only FILLS canonical_job_family_id where NULL — a
field chosen by the applicant or an admin is never overwritten. Free text
is classified with the same deterministic trades classifier the job
pipeline uses, resolved through the SKILLED Nation taxonomy bridge.

Usage:
  python scripts/classify_applicant_fields.py [--dry-run]

Prints the ids it updated so a scoped recompute can follow:
  python scripts/recompute_matches.py --applicant-id <id> --prefilter --skip-geocode
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))

import psycopg2  # noqa: E402
from matching import sn_taxonomy  # noqa: E402
from scraper.trades import classify  # noqa: E402

DSN = "postgresql://postgres:postgres@localhost:54322/postgres"


def main() -> int:
    dry = "--dry-run" in sys.argv
    import os
    conn = psycopg2.connect(os.environ.get("DATABASE_URL") or DSN)
    cur = conn.cursor()

    cur.execute("SELECT code, id FROM public.canonical_job_families WHERE is_active")
    fam_ids = dict(cur.fetchall())

    cur.execute(
        """SELECT id, specific_career, career_goals_raw, program_name_raw
             FROM public.applicants
            WHERE canonical_job_family_id IS NULL
              AND (COALESCE(specific_career,'') <> ''
                   OR COALESCE(career_goals_raw,'') <> ''
                   OR COALESCE(program_name_raw,'') <> '')"""
    )
    rows = cur.fetchall()
    audit: Counter = Counter()
    fam_dist: Counter = Counter()
    updated_ids: list[str] = []

    for aid, specific, goals, program in rows:
        # specific_career is the strongest signal (the person named the job);
        # classify it as if it were a posting title, with goals/program as body.
        m = classify(specific or program or "", goals)
        if not (m.is_trade and m.family):
            audit["no_field_inferred"] += 1
            continue
        code = sn_taxonomy.resolve_field_code(m.family)
        if not code or code not in fam_ids:
            audit["unresolvable"] += 1
            continue
        fam_dist[code] += 1
        audit["classified"] += 1
        updated_ids.append(str(aid))
        if not dry:
            cur.execute(
                """UPDATE public.applicants
                      SET canonical_job_family_id = %s,
                          sector_code = COALESCE(sector_code, %s)
                    WHERE id = %s AND canonical_job_family_id IS NULL""",
                (fam_ids[code], sn_taxonomy.FIELDS[code]["sectors"][0], aid),
            )

    if not dry:
        conn.commit()
    conn.close()

    print(f"{'(dry run) ' if dry else ''}candidates={len(rows)} audit={dict(audit)}")
    for code, n in fam_dist.most_common(15):
        print(f"  {code:35} {n}")
    if updated_ids and not dry:
        out = REPO / "audit" / "applicant_field_backfill_ids.txt"
        out.write_text("\n".join(updated_ids))
        print(f"{len(updated_ids)} applicant ids written to {out} (recompute them next)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
