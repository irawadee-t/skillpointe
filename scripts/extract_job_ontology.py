"""Classify every job's seniority and extract its required credentials.

Two deterministic passes over the posting's OWN text — no LLM, fully
rerunnable, every decision auditable:

1. Seniority (packages/matching/seniority.py): normalizes the messy scraped
   experience_level vocabulary ("Experienced", "Fresh Graduate", NULL, ...)
   into entry | mid | senior | management with recorded evidence, an explicit
   years-required extraction, and an entry_friendly flag ("we will train").

2. Credentials: scans title + description + requirements for word-boundary
   mentions of the 127 canonical credential definitions
   (apps/api/app/skilled_pro/taxonomy.py). Guards against false positives:
   only aliases >= 3 chars; all-caps aliases (EPA, CDL, AWS) must match
   case-sensitively; longest-alias-wins so "CDL Class A" beats "CDL".
   Each hit is classified required vs preferred from its sentence context.

Writes: jobs.experience_level, years_experience_required, entry_friendly,
seniority_evidence, required_credentials (canonical display names),
required_credentials_canonical ([{raw, slug, name, confidence, requirement}]).

Usage: python scripts/extract_job_ontology.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.skilled_pro.taxonomy import all_definitions
from matching.seniority import classify_seniority

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"

_PREFERRED_CTX = re.compile(
    r"(preferred|a plus|nice to have|bonus|is desirable|would be an asset|"
    r"not required|helpful but)", re.IGNORECASE,
)
_REQUIRED_CTX = re.compile(
    r"(required|must (have|hold|possess)|need to (have|hold)|valid|current|"
    r"active|requirement)", re.IGNORECASE,
)


def build_alias_index():
    """[(compiled_pattern, alias, definition)] longest alias first."""
    entries = []
    for d in all_definitions():
        for alias in {d.name, *d.aliases}:
            a = alias.strip()
            if len(a) < 3:
                continue                       # 2-char aliases are noise in prose
            flags = 0 if (a.isupper() and " " not in a) else re.IGNORECASE
            pat = re.compile(rf"(?<![\w-]){re.escape(a)}(?![\w-])", flags)
            entries.append((pat, a, d))
    entries.sort(key=lambda t: -len(t[1]))     # longest-alias-wins
    return entries


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?:;])\s+|\n+", text)


def extract_credentials(alias_index, *texts: str | None) -> list[dict]:
    found: dict[str, dict] = {}
    for text in texts:
        if not text:
            continue
        for sent in sentences(text):
            consumed: list[tuple[int, int]] = []
            for pat, alias, d in alias_index:
                m = pat.search(sent)
                if not m:
                    continue
                span = (m.start(), m.end())
                # Skip if inside an already-matched longer alias.
                if any(s <= span[0] and span[1] <= e for s, e in consumed):
                    continue
                consumed.append(span)
                requirement = (
                    "preferred" if _PREFERRED_CTX.search(sent)
                    else "required" if _REQUIRED_CTX.search(sent)
                    else "mentioned"
                )
                prev = found.get(d.code)
                rank = {"required": 2, "preferred": 1, "mentioned": 0}
                if prev is None or rank[requirement] > rank[prev["requirement"]]:
                    found[d.code] = {
                        "raw": alias,
                        "slug": d.code.lower(),
                        "name": d.name,
                        "confidence": 0.95,
                        "confident": True,
                        "requirement": requirement,
                    }
    return list(found.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    alias_index = build_alias_index()
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, title_raw, description_raw, requirements_raw, experience_level
             FROM public.jobs WHERE is_active"""
    )
    rows = cur.fetchall()

    level_counts: Counter = Counter()
    cred_jobs = 0
    cred_total = 0
    entry_friendly_ct = 0

    for jid, title, desc, reqs, old_level in rows:
        sen = classify_seniority(title, desc, reqs)
        creds = extract_credentials(alias_index, title, desc, reqs)
        level_counts[sen.level] += 1
        if sen.entry_friendly:
            entry_friendly_ct += 1
        if creds:
            cred_jobs += 1
            cred_total += len(creds)

        if not args.dry_run:
            names = [c["name"] for c in creds if c["requirement"] != "preferred"]
            cur.execute(
                """UPDATE public.jobs SET
                       experience_level = %s,
                       years_experience_required = %s,
                       entry_friendly = %s,
                       seniority_evidence = %s::jsonb,
                       required_credentials = %s,
                       required_credentials_canonical = %s::jsonb,
                       updated_at = NOW()
                     WHERE id = %s""",
                (
                    sen.level,
                    sen.years_required,
                    sen.entry_friendly,
                    json.dumps({"job_zone": sen.job_zone, "evidence": sen.evidence,
                                "previous_label": old_level}),
                    names,
                    json.dumps(creds),
                    jid,
                ),
            )

    if not args.dry_run:
        conn.commit()

    total = len(rows)
    print(f"Classified {total} active jobs{' (dry run)' if args.dry_run else ''}:")
    for lvl in ("entry", "mid", "senior", "management"):
        n = level_counts.get(lvl, 0)
        print(f"  {lvl:11} {n:4}  ({n * 100 // max(total, 1)}%)")
    print(f"  entry_friendly flag on {entry_friendly_ct} jobs")
    print(f"Credentials: {cred_jobs} jobs carry >=1 canonical credential "
          f"({cred_total} total mentions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
