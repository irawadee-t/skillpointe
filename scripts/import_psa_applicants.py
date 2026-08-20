"""Import the PSA migration sheet as the applicant pool.

Source: "PSA Migration Data_For Tasha_July2026.xlsx" — one applicant per
contentful row (per Tasha/Riya), 22 columns, no names or emails. The sheet's
Field of Study Sector/Career columns use the SKILLED Nation taxonomy verbatim
(all 69 distinct career values match a field name or alias exactly).

Decisions, as directed:
  * Identities are synthetic (no PII in the sheet): deterministic names from
    the row number, emails psa-<row>@scholarship-import.local so every demo
    guard keyed on that domain keeps applying.
  * Geography: everyone "wants to be in state" — relocation_preference
    'within_state', willing_to_relocate false. Travel fields LEFT NULL.
  * Credentials: none imported (left blank on purpose).
  * Sector precedence: the sheet's own sector wins when it is one of the 8
    and legal for the career; otherwise the career's primary sector; blank
    sector + known career derives from the career; "Other Skilled Trade
    Industry" carries no sector signal on its own.
  * Blank career + known sector -> sector label only (family NULL; the
    matching gate treats unknown as neutral, never as a fail).
  * REPLACES the previous 335-row demo pool (same domain). Auth-linked test
    applicants are untouched.

Rerunnable: rows key on the deterministic email; existing rows update.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import openpyxl
import psycopg2
from psycopg2.extras import execute_values

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
from matching import sn_taxonomy

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"
XLSX = os.environ.get(
    "PSA_XLSX", "/Users/riyakarumanchi/Downloads/PSA Migration Data_For Tasha_July2026.xlsx"
)
DOMAIN = "scholarship-import.local"

ENROLLMENT = {
    "high school (seniors/upcoming seniors)": "high_school",
    "community college/technical school": "community_college",
    "skilledtrades certificate/vocational": "vocational_certificate",
    "not currently attending": "not_enrolled",
    "4+ year college program": "bachelors_plus",
    "early college/hs dual enrollment": "dual_enrollment",
    "apprenticeship program": "apprenticeship",
}
DEGREE = {
    "skilled trades certificate or diploma/vocational program": "skilled_trades_certificate",
    "associate's degree (2-year, including a.s., a.a.s., adn/asn, etc.)": "associates",
    "bachelor's degree (4-year)": "bachelors",
    "apprenticeship (with an educational/training component)": "apprenticeship",
    "graduate degree (master's or phd)": "other",
}
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR",
}

FIRST = ["Avery","Jordan","Riley","Casey","Morgan","Quinn","Taylor","Alex","Cameron","Devon",
         "Elliot","Emerson","Finley","Harper","Hayden","Jamie","Kendall","Logan","Micah","Parker",
         "Peyton","Reese","Rowan","Sage","Skyler","Blake","Charlie","Dakota","Ellis","Frankie"]
LAST = ["Alvarez","Bennett","Carter","Diaz","Edwards","Foster","Garcia","Hughes","Iverson","Jenkins",
        "Keller","Lawson","Mendoza","Nguyen","Ortiz","Porter","Quintana","Ramsey","Sullivan","Torres",
        "Underwood","Vasquez","Whitfield","Xiong","Young","Zamora","Beckett","Calloway","Dawson","Ellison"]


def norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(v)).strip())


def synth_name(row_num: int) -> tuple[str, str]:
    h = int(hashlib.md5(f"psa:{row_num}".encode()).hexdigest(), 16)
    return FIRST[h % len(FIRST)], LAST[(h // 97) % len(LAST)]


def main() -> int:
    wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))[1:]

    # Field lookups from the generated taxonomy (names + aliases, exact only).
    field_by_text = {}
    for code, f in sn_taxonomy.FIELDS.items():
        for surface in [f["name"], *f["aliases"]]:
            field_by_text[surface.lower()] = code
    sector_by_name = {m["name"].lower(): c for c, m in sn_taxonomy.SECTORS.items()}
    sector_by_name[sn_taxonomy.SECTORS["transportation"]["full_name"].lower()] = "transportation"

    audit: Counter = Counter()
    records = []
    for i, raw in enumerate(rows, start=2):   # 2 = first data row in the sheet
        r = [norm(c) for c in (tuple(raw) + ("",) * 22)[:22]]
        if not any(r):
            audit["skipped_empty"] += 1
            continue

        sheet_sector = sector_by_name.get(r[9].lower())
        if r[9] and sheet_sector is None:
            audit["sector_not_in_taxonomy"] += 1   # "Other Skilled Trade Industry" or blank-ish
        field_code = field_by_text.get(r[10].lower()) if r[10] else None
        if r[10] and field_code is None:
            audit["career_unmatched"] += 1         # should be zero per pre-check

        # Sector resolution: sheet sector if legal for the field, else the
        # field's primary sector, else the sheet sector alone.
        sector_code = None
        if field_code:
            legal = sn_taxonomy.FIELDS[field_code]["sectors"]
            if sheet_sector in legal:
                sector_code = sheet_sector
            else:
                sector_code = legal[0]
                if sheet_sector:
                    audit["sector_overridden_by_career"] += 1
        elif sheet_sector:
            sector_code = sheet_sector

        state = r[13].upper() if r[13].upper() in US_STATES else None
        if r[13] and state is None:
            audit["bad_state_dropped"] += 1

        first, last = synth_name(i)
        mil = r[20].lower() == "yes"
        dep = r[21].lower() == "yes"
        records.append((
            first, last, f"psa-{i}@{DOMAIN}",
            r[12] or None, state,
            ENROLLMENT.get(r[0].lower()), DEGREE.get(r[4].lower()),
            r[5] or None, r[6] or None, r[7] or None, (r[8].upper() if r[8].upper() in US_STATES else None),
            # Display continuity strings + taxonomy codes
            (sn_taxonomy.SECTORS[sector_code]["name"] if sector_code else (r[9] or None)),
            r[10] or None, r[11] or None, r[10] or None,
            sector_code, field_code,
            r[16] or None, r[14] or None, r[18] or None,
            mil, dep,
        ))
        audit["imported"] += 1
        if field_code:
            audit["with_field"] += 1
        elif sector_code:
            audit["sector_only"] += 1
        else:
            audit["no_taxonomy_signal"] += 1

    print("Parse audit:")
    for k in sorted(audit):
        print(f"  {k:28} {audit[k]}")

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    # Bulk import: suppress per-row match enqueue (an explicit
    # sharded recompute follows); 43k trigger inserts would
    # occupy the resident worker for hours to no benefit.
    cur.execute("SET skilled.skip_match_enqueue = 'on'")

    # Replace the previous demo pool (same domain, pre-PSA rows).
    cur.execute("DELETE FROM public.applicants WHERE email LIKE %s AND email NOT LIKE 'psa-%%'",
                (f"%@{DOMAIN}",))
    print(f"\nRemoved previous demo pool rows: {cur.rowcount}")

    execute_values(
        cur,
        """
        INSERT INTO public.applicants
            (first_name, last_name, email, city, state,
             enrollment_status, degree_type,
             school_name, school_campus, school_city, school_state,
             career_path, program_field, specific_career, program_name_raw,
             sector_code, canonical_job_family_id,
             age_range, gender, current_wages,
             military_status, military_dependent,
             relocation_preference, willing_to_relocate)
        VALUES %s
        ON CONFLICT (email) WHERE email IS NOT NULL DO UPDATE SET
            city = EXCLUDED.city, state = EXCLUDED.state,
            enrollment_status = EXCLUDED.enrollment_status,
            degree_type = EXCLUDED.degree_type,
            school_name = EXCLUDED.school_name,
            career_path = EXCLUDED.career_path,
            program_field = EXCLUDED.program_field,
            sector_code = EXCLUDED.sector_code,
            canonical_job_family_id = EXCLUDED.canonical_job_family_id
        """,
        records,
        template=(
            "(%s,%s,%s,%s,%s,"
            "%s::public.enrollment_status,%s::public.degree_type,"
            "%s,%s,%s,%s,"
            "%s,%s,%s,%s,"
            "%s,(SELECT id FROM public.canonical_job_families WHERE code = %s AND is_active),"
            "%s,%s,%s,"
            "%s,%s,"
            "'within_state'::public.relocation_willingness,FALSE)"
        ),
        page_size=2000,
    )
    conn.commit()

    cur.execute("SELECT count(*) FROM public.applicants")
    total = cur.fetchone()[0]
    cur.execute(
        "SELECT count(*) FROM public.applicants WHERE canonical_job_family_id IS NOT NULL")
    with_field = cur.fetchone()[0]
    print(f"\nApplicants now in DB: {total}  (with career field: {with_field})")

    cur.execute(
        """SELECT count(*) FROM public.applicants a
             JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            WHERE a.sector_code IS NOT NULL
              AND NOT (a.sector_code = ANY(jf.industries))"""
    )
    bad = cur.fetchone()[0]
    print(f"INVARIANT sector∈field.sectors: {'OK' if bad == 0 else f'VIOLATED x{bad}'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
