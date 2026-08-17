"""Remap existing applicants and jobs onto the SKILLED Nation taxonomy.

Deterministic, audited, and conservative:

  Rule 1 — already-canonical: the row's family code is a current field code.
           Only the sector label is filled in (field's primary sector when the
           field spans several).
  Rule 2 — exact text match: the applicant's program text (program_field >
           specific_career > program_name_raw) equals a field name or alias,
           case-insensitively. No fuzzy matching here: anything less than
           exact falls through.
  Rule 3 — legacy bridge: the old family code maps through
           sn_taxonomy.LEGACY_FAMILY_BRIDGE (reviewed by hand, checked in).
  Rule 4 — no honest home: left untouched and routed to review_queue_items.

Prints a per-rule audit and never guesses silently. Rerunnable: rows already
on a current code only ever gain a sector label.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))

from matching import sn_taxonomy  # noqa: E402

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"


def primary_sector(field_code: str) -> str:
    return sn_taxonomy.FIELDS[field_code]["sectors"][0]


def build_text_index() -> dict[str, str]:
    """lowercased exact surface form -> field code (names + aliases)."""
    idx: dict[str, str] = {}
    for code, f in sn_taxonomy.FIELDS.items():
        for surface in [f["name"], *f["aliases"]]:
            idx[surface.strip().lower()] = code
    return idx


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    text_idx = build_text_index()

    # family code -> id for current fields
    cur.execute("SELECT code, id FROM public.canonical_job_families WHERE is_active")
    fam_ids = dict(cur.fetchall())

    audit: Counter = Counter()

    # ---------------- applicants ----------------
    cur.execute(
        """SELECT a.id, jf.code, a.sector_code, a.program_field, a.specific_career, a.program_name_raw
             FROM public.applicants a
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id"""
    )
    review_rows: list[tuple] = []
    for aid, old_code, sector, p_field, p_career, p_raw in cur.fetchall():
        new_code = None
        rule = None
        if old_code in sn_taxonomy.FIELDS:
            new_code, rule = old_code, "already_canonical"
        else:
            for text in (p_field, p_career, p_raw):
                if text and text.strip().lower() in text_idx:
                    new_code, rule = text_idx[text.strip().lower()], "exact_text"
                    break
            if new_code is None and old_code is not None:
                bridged = sn_taxonomy.LEGACY_FAMILY_BRIDGE.get(old_code)
                if bridged:
                    new_code, rule = bridged, "legacy_bridge"
                elif old_code in sn_taxonomy.LEGACY_FAMILY_BRIDGE:
                    rule = "review_queue"       # explicit None mapping
                else:
                    rule = "unknown_code_review"
            elif new_code is None:
                rule = "no_signal"              # nothing to map from; leave as-is

        audit[f"applicant:{rule}"] += 1
        if new_code:
            cur.execute(
                """UPDATE public.applicants
                      SET canonical_job_family_id = %s,
                          sector_code = COALESCE(sector_code, %s)
                    WHERE id = %s""",
                (fam_ids[new_code], primary_sector(new_code), aid),
            )
        elif rule in ("review_queue", "unknown_code_review"):
            review_rows.append(("applicant", str(aid), old_code))

    # ---------------- jobs ----------------
    cur.execute(
        """SELECT j.id, jf.code, j.sector_code
             FROM public.jobs j
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id"""
    )
    for jid, old_code, sector in cur.fetchall():
        new_code = None
        rule = None
        if old_code in sn_taxonomy.FIELDS:
            new_code, rule = old_code, "already_canonical"
        elif old_code is not None:
            bridged = sn_taxonomy.LEGACY_FAMILY_BRIDGE.get(old_code)
            if bridged:
                new_code, rule = bridged, "legacy_bridge"
            elif old_code in sn_taxonomy.LEGACY_FAMILY_BRIDGE:
                rule = "review_queue"
            else:
                rule = "unknown_code_review"
        else:
            rule = "no_family"
        audit[f"job:{rule}"] += 1
        if new_code:
            cur.execute(
                """UPDATE public.jobs
                      SET canonical_job_family_id = %s,
                          sector_code = COALESCE(sector_code, %s)
                    WHERE id = %s""",
                (fam_ids[new_code], primary_sector(new_code), jid),
            )
        elif rule in ("review_queue", "unknown_code_review"):
            review_rows.append(("job", str(jid), old_code))

    # ---------------- review queue ----------------
    for entity, entity_id, old_code in review_rows:
        cur.execute(
            """INSERT INTO public.review_queue_items
                   (item_type, entity_type, entity_id, description, status, priority)
               VALUES ('taxonomy_mismatch', %s, %s::uuid, %s, 'pending', 3)""",
            (
                entity,
                entity_id,
                f"Old family '{old_code}' has no honest home in the SKILLED Nation "
                "taxonomy. Assign a sector and career field by hand.",
            ),
        )

    # ---------------- retire superseded legacy families ----------------
    legacy_only = [c for c in sn_taxonomy.LEGACY_FAMILY_BRIDGE if c not in sn_taxonomy.FIELDS]
    cur.execute(
        "UPDATE public.canonical_job_families SET is_active = FALSE WHERE code = ANY(%s)",
        (legacy_only,),
    )
    audit["legacy_families_retired"] = cur.rowcount

    conn.commit()

    print("Remap audit:")
    for key in sorted(audit):
        print(f"  {key:32} {audit[key]}")
    print(f"  review queue items added        {len(review_rows)}")

    # Post-remap invariants
    cur.execute(
        """SELECT count(*) FROM public.applicants a
             JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            WHERE a.sector_code IS NOT NULL
              AND NOT (a.sector_code = ANY(jf.industries))"""
    )
    bad = cur.fetchone()[0]
    print(f"  INVARIANT sector∈field.sectors  {'OK' if bad == 0 else f'VIOLATED x{bad}'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
