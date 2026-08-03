#!/usr/bin/env python3
"""
regenerate_job_sections.py — Re-parse every active job's display sections.

The job_display_sections cache is content-hash keyed, and the parser version is
folded into the hash — so bumping the parser automatically invalidates stale
rows on next read. This script eagerly regenerates ALL rows instead of waiting
for first view, and reports display-quality stats across the whole catalog:

  * quality distribution (good vs messy)
  * sections-per-job distribution
  * snapped-bullet count (bullets starting lowercase / with punctuation)
  * pay-fragment count (bullets that are bare amounts or end with "$")
  * baseline: how many RAW lines exhibited those defects before parsing

Deterministic — no API keys required. Run from repo root with the API venv:

    python scripts/regenerate_job_sections.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from app.skilled_pro.job_sections import (  # noqa: E402
    SECTION_KEYS,
    compute_content_hash,
    parse_job_sections,
)

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
)

_LIST_KEYS = ("duties", "needs", "nice_to_have", "benefits", "schedule")
_SNAP_START = re.compile(r"^[a-z,.;:)%]")
_BARE_AMOUNT = re.compile(r"^\$?\d[\d.,]*%?$")


def _defects(items: list[str]) -> tuple[int, int]:
    """(snapped_bullets, pay_fragments) in a list of rendered bullets."""
    snaps = sum(1 for i in items if _SNAP_START.match(i))
    frags = sum(1 for i in items if _BARE_AMOUNT.match(i) or i.rstrip().endswith("$"))
    return snaps, frags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="parse + report, no writes")
    args = parser.parse_args()

    import psycopg2

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, description_raw, requirements_raw,
               preferred_qualifications_raw, responsibilities_raw
        FROM public.jobs
        WHERE is_active = TRUE
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    print(f"Parsing {len(rows)} active jobs…")

    quality = Counter()
    section_counts = Counter()
    total_snaps = total_frags = 0
    raw_snaps = raw_frags = 0
    worst: list[tuple[int, str]] = []

    for job_id, desc, req, pref, resp in rows:
        raws = (desc, req, pref, resp)
        # Baseline defects in the raw text (what the old UI rendered as bullets).
        for raw in raws:
            for ln in (raw or "").split("\n"):
                ln = ln.strip()
                if not ln:
                    continue
                if _SNAP_START.match(ln):
                    raw_snaps += 1
                if _BARE_AMOUNT.match(ln) or ln.endswith("$"):
                    raw_frags += 1

        result = parse_job_sections(*raws)
        quality[result["quality"]] += 1
        non_empty = sum(1 for k in SECTION_KEYS if result[k])
        section_counts[non_empty] += 1

        items = [i for k in _LIST_KEYS for i in result[k]]
        snaps, frags = _defects(items)
        total_snaps += snaps
        total_frags += frags
        if snaps or frags:
            worst.append((snaps + frags, str(job_id)))

        if not args.dry_run:
            sections_payload = {k: result[k] for k in SECTION_KEYS}
            sections_payload["facts"] = result["facts"]
            sections_payload["quality"] = result["quality"]
            cur.execute(
                """
                INSERT INTO public.job_display_sections
                    (job_id, sections, source, content_hash, updated_at)
                VALUES (%s, %s, 'parser', %s, now())
                ON CONFLICT (job_id) DO UPDATE SET
                    sections = EXCLUDED.sections,
                    source = EXCLUDED.source,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = now()
                """,
                (job_id, json.dumps(sections_payload), compute_content_hash(*raws)),
            )

    if not args.dry_run:
        conn.commit()
        print(f"Upserted {len(rows)} job_display_sections rows.")
    conn.close()

    print("\n=== Sweep report ===")
    print(f"quality: {dict(quality)}")
    print(f"sections per job: {dict(sorted(section_counts.items()))}")
    print(f"raw baseline: {raw_snaps} snapped lines, {raw_frags} pay-fragment lines")
    print(f"parsed output: {total_snaps} snapped bullets, {total_frags} pay fragments")
    if worst:
        print("jobs with residual defects:")
        for n, jid in sorted(worst, reverse=True)[:10]:
            print(f"  {jid}: {n}")
    return 1 if (total_snaps or total_frags) else 0


if __name__ == "__main__":
    raise SystemExit(main())
