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

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "apps" / "api"))

import asyncpg  # noqa: E402

DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"


async def _run(dry: bool) -> int:
    # Delegates to the live pipeline stage so batch and pipeline can't drift.
    from app.skilled_pro.job_enrichment import enrich_jobs
    conn = await asyncpg.connect(DSN)
    # Match the app pool's jsonb codec so enrich_jobs can pass Python objects.
    import json as _json
    await conn.set_type_codec("jsonb", encoder=_json.dumps, decoder=_json.loads, schema="pg_catalog")
    ids = [str(r["id"]) for r in await conn.fetch(
        "SELECT id FROM public.jobs WHERE is_active")]
    if dry:
        print(f"(dry run) would enrich {len(ids)} active jobs")
        await conn.close()
        return 0
    audit = await enrich_jobs(conn, ids)
    rows = await conn.fetch(
        """SELECT experience_level AS lvl, count(*) AS n FROM public.jobs
            WHERE is_active GROUP BY lvl ORDER BY n DESC""")
    cred = await conn.fetchval(
        """SELECT count(*) FROM public.jobs WHERE is_active
            AND jsonb_array_length(COALESCE(required_credentials_canonical,'[]'::jsonb)) > 0""")
    await conn.close()
    print(f"Enriched {audit['enriched']} active jobs "
          f"(family stamped: {audit['family_stamped']}, no trade match: {audit['no_trade_match']})")
    for r in rows:
        print(f"  {r['lvl'] or '-':11} {r['n']}")
    print(f"Jobs with canonical credentials: {cred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run("--dry-run" in sys.argv)))
