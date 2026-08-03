#!/usr/bin/env python3
"""
gen_credential_definitions_sql.py — emit the credential_definitions seed SQL
from the in-code taxonomy (apps/api/app/skilled_pro/taxonomy.py).

The Python module is the source of truth for the canonical credential
registry; this script keeps the DB mirror (credential_definitions) in sync.
Regenerate whenever the taxonomy changes, then paste the output into a new
migration (and keep seed behaviour idempotent — everything is ON CONFLICT
upserts keyed on canonical_code).

Usage:
    cd apps/api && source .venv/bin/activate && cd ../..
    python scripts/gen_credential_definitions_sql.py            # print to stdout
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from app.skilled_pro.taxonomy import TAXONOMY  # noqa: E402


def q(s):
    """SQL-quote a string (or NULL)."""
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def arr(items):
    if not items:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ",".join(q(i) for i in items) + "]"


def main() -> int:
    rows = []
    for c in TAXONOMY:
        rows.append(
            "  ({code}, {name}, {ctype}, {authority}, {aliases}, {families}, "
            "{validity}, {verify_url})".format(
                code=q(c.slug),
                name=q(c.name),
                ctype=q(c.type.value),
                authority=q(c.issuer),
                aliases=arr(list(c.aliases)),
                families=arr(list(c.job_families)),
                validity=q(c.validity),
                verify_url=q(c.verify_url),
            )
        )

    print(
        "INSERT INTO public.credential_definitions\n"
        "  (canonical_code, canonical_name, credential_type, authority, aliases,\n"
        "   job_families, validity_note, verification_url)\n"
        "VALUES\n" + ",\n".join(rows) + "\n"
        "ON CONFLICT (canonical_code) DO UPDATE SET\n"
        "  canonical_name   = EXCLUDED.canonical_name,\n"
        "  credential_type  = EXCLUDED.credential_type,\n"
        "  authority        = COALESCE(EXCLUDED.authority, credential_definitions.authority),\n"
        "  aliases          = EXCLUDED.aliases,\n"
        "  job_families     = EXCLUDED.job_families,\n"
        "  validity_note    = EXCLUDED.validity_note,\n"
        "  verification_url = EXCLUDED.verification_url,\n"
        "  active           = true,\n"
        "  updated_at       = now();"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
