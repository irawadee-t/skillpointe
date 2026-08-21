"""Merge the partner-application extract onto applicants — join-key ready.

The 2026-08-20 "SN Data" extract (psa_partner_applications) carries the
fields matching has been missing — program start/end dates (the timing
gate), partner-sharing consent, internship text — keyed by the sponsor's
pseudonymous Stable Applicant ID. Today's applicant rows have no such id
(the original PSA export predates it), so this merge is a no-op until the
full student re-export arrives carrying the SAME id per row and the
importer stamps applicants.stable_applicant_id.

Run it any time; it only fills blanks (synthetic defaults and user-entered
values are never overwritten) and the database triggers rescore every
applicant it touches automatically.

Usage: python scripts/merge_partner_applications.py [--dry-run]
"""
from __future__ import annotations

import os
import sys

import psycopg2

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"

MERGE_SQL = """
UPDATE public.applicants a SET
    program_start_date       = COALESCE(a.program_start_date, p.program_start_date),
    expected_completion_date = COALESCE(a.expected_completion_date, p.program_end_date),
    available_from_date      = COALESCE(a.available_from_date, p.program_end_date),
    has_internship           = COALESCE(NULLIF(a.has_internship, FALSE), p.has_internship_text),
    internship_details       = COALESCE(NULLIF(a.internship_details, ''), p.internship_details)
  FROM public.psa_partner_applications p
 WHERE p.stable_applicant_id = a.stable_applicant_id
   AND a.stable_applicant_id IS NOT NULL
   AND (
        (a.program_start_date IS NULL AND p.program_start_date IS NOT NULL)
     OR (a.expected_completion_date IS NULL AND p.program_end_date IS NOT NULL)
     OR (COALESCE(a.internship_details, '') = '' AND p.internship_details IS NOT NULL)
   )
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM applicants WHERE stable_applicant_id IS NOT NULL")
    joinable = cur.fetchone()[0]
    if joinable == 0:
        print("No applicants carry stable_applicant_id yet — the full student "
              "export (with the Stable Applicant ID column) has not been "
              "imported. Nothing to merge; the staged application data is "
              "waiting in psa_partner_applications.")
        return 0
    cur.execute(MERGE_SQL)
    n = cur.rowcount
    if dry:
        conn.rollback()
        print(f"(dry run) would merge application fields into {n} applicants")
    else:
        conn.commit()
        print(f"Merged application fields into {n} applicants "
              "(triggers will rescore them automatically)")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
