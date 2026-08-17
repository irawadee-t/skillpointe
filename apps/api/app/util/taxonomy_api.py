"""SKILLED Nation taxonomy validation for API writes.

The DB trigger (check_sector_matches_field) is the last line of defense; this
module is the first: it turns an invalid sector/field pair into a clean 422
with a human explanation instead of a 500 from a trigger exception, and it
does so in-process with no DB round trip.
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

# packages/ import path — walk only existing parents (deploy layouts differ).
for _parent in Path(__file__).resolve().parents:
    _pkg = _parent / "packages"
    if _pkg.is_dir():
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        break

try:
    from matching import sn_taxonomy  # noqa: E402
    TAXONOMY_AVAILABLE = True
except ImportError:  # pragma: no cover - deploy-layout dependent
    sn_taxonomy = None  # type: ignore[assignment]
    TAXONOMY_AVAILABLE = False


def validate_sector_field(sector_code: str | None, field_code: str | None) -> None:
    """Raise 422 unless the (sector, field) pair is coherent.

    Rules:
      * an unknown sector code is rejected outright;
      * an unknown field code is rejected outright;
      * a field given WITH a sector must belong to that sector
        (multi-sector fields accept any of their sectors);
      * either value alone is fine — sector-only is a coarse label,
        field-only implies its sector set.
    """
    if not TAXONOMY_AVAILABLE or (sector_code is None and field_code is None):
        return

    if sector_code is not None and sector_code not in sn_taxonomy.SECTORS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown sector '{sector_code}'. "
                   f"Valid sectors: {', '.join(sorted(sn_taxonomy.SECTORS))}.",
        )
    resolved = sn_taxonomy.resolve_field_code(field_code) if field_code else None
    if field_code is not None and resolved is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown career field '{field_code}'.",
        )
    if sector_code is not None and resolved is not None:
        allowed = sn_taxonomy.FIELDS[resolved]["sectors"]
        if sector_code not in allowed:
            names = ", ".join(sn_taxonomy.SECTORS[s]["name"] for s in allowed)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{sn_taxonomy.FIELDS[resolved]['name']}' belongs to "
                    f"{names}, not {sn_taxonomy.SECTORS[sector_code]['name']}. "
                    "Pick a field from the selected sector."
                ),
            )


async def resolve_family_uuid(conn, field_code: str) -> UUID | None:
    """Field code -> canonical_job_families.id (legacy codes resolve first)."""
    resolved = sn_taxonomy.resolve_field_code(field_code) if TAXONOMY_AVAILABLE else field_code
    if resolved is None:
        return None
    row = await conn.fetchrow(
        "SELECT id FROM public.canonical_job_families WHERE code = $1 AND is_active",
        resolved,
    )
    return row["id"] if row else None


def default_sector_for_field(field_code: str | None) -> str | None:
    """Single-sector fields imply their sector; multi-sector fields do not."""
    if not TAXONOMY_AVAILABLE or not field_code:
        return None
    resolved = sn_taxonomy.resolve_field_code(field_code)
    if resolved is None:
        return None
    sectors = sn_taxonomy.FIELDS[resolved]["sectors"]
    return sectors[0] if len(sectors) == 1 else None
