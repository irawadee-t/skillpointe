"""Post-hoc trades classification for raw-scraped jobs.

The raw adapter runner (scrape_jobs.py) ingests every listing a careers site
publishes; update_trades_jobs.py is the pipeline that classifies titles and
drops non-trades roles BEFORE ingest. When a raw run has already landed
(titles + descriptions in the table), this script reproduces the same
decision post-hoc, without re-fetching anything:

  * classify(title, description) from packages/scraper/trades.py
  * trades hit  -> stamp canonical_job_family_id (legacy code resolves through
                   the SKILLED Nation bridge) + sector_code
  * no hit      -> deactivate with a stamped reason in seniority_evidence
                   ("non_trades_classifier"), auditable and reversible

Only touches active jobs with no family assigned; hand-labeled and
employer-created rows are never overwritten.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))

from matching import sn_taxonomy  # noqa: E402
from scraper.trades import classify  # noqa: E402

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    cur.execute("SELECT code, id FROM public.canonical_job_families WHERE is_active")
    fam_ids = dict(cur.fetchall())

    # ALL active family-less jobs: an unclassified job near-fits every
    # same-state applicant (family unknown = neutral), so stragglers from any
    # source pollute lists. Employer-authored rows are never deactivated by a
    # classifier miss -- they go to the review queue instead.
    cur.execute(
        """SELECT id, title_raw, description_raw, source FROM public.jobs
            WHERE is_active AND canonical_job_family_id IS NULL"""
    )
    rows = cur.fetchall()
    audit: Counter = Counter()
    family_dist: Counter = Counter()

    for jid, title, desc, source in rows:
        m = classify(title or "", desc)
        if m.is_trade and m.family:
            new_code = sn_taxonomy.resolve_field_code(m.family)
            if new_code and new_code in fam_ids:
                family_dist[new_code] += 1
                audit["classified_trades"] += 1
                if not dry:
                    cur.execute(
                        """UPDATE public.jobs
                              SET canonical_job_family_id = %s,
                                  sector_code = %s
                            WHERE id = %s""",
                        (fam_ids[new_code],
                         sn_taxonomy.FIELDS[new_code]["sectors"][0], jid),
                    )
            else:
                audit["family_unresolvable"] += 1
        elif source in ("employer_created", "employer_import"):
            audit["employer_rows_to_review"] += 1
            if not dry:
                cur.execute(
                    """INSERT INTO public.review_queue_items
                           (item_type, entity_type, entity_id, description, status, priority)
                       VALUES ('taxonomy_mismatch', 'job', %s::uuid, %s, 'pending', 3)""",
                    (str(jid),
                     "Employer-authored job could not be auto-classified into a "
                     "career field. Assign sector and field by hand."),
                )
        else:
            audit["deactivated_non_trades"] += 1
            if not dry:
                cur.execute(
                    """UPDATE public.jobs
                          SET is_active = FALSE,
                              seniority_evidence = COALESCE(seniority_evidence, '{}'::jsonb)
                                  || %s::jsonb
                        WHERE id = %s""",
                    (json.dumps({"deactivated_by": "non_trades_classifier",
                                 "classifier_reason": m.reason}), jid),
                )

    if not dry:
        conn.commit()

    print(f"Scanned {len(rows)} unclassified scraped jobs{' (dry run)' if dry else ''}:")
    for k in sorted(audit):
        print(f"  {k:26} {audit[k]}")
    print("Top families assigned:")
    for code, n in family_dist.most_common(10):
        print(f"  {sn_taxonomy.FIELDS[code]['name'][:44]:46} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
