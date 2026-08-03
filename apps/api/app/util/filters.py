"""
Shared helpers for granular list-endpoint filters.

Multi-select filters arrive as comma-separated query params (matching the
URL-synced frontend primitives). AND semantics across facets, OR within one
multi-select — every builder here returns a predicate that composes with
`" AND ".join(conditions)`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException


def csv_values(raw: Optional[str], *, upper: bool = False, max_items: int = 60) -> list[str]:
    """Parse a comma-separated multi-select param into a clean value list."""
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        v = part.strip()
        if not v:
            continue
        out.append(v.upper() if upper else v)
        if len(out) >= max_items:
            break
    return out


def parse_iso_date(raw: Optional[str], param: str) -> Optional[date]:
    """Parse YYYY-MM-DD; 422 on garbage instead of a silent no-op filter."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{param} must be YYYY-MM-DD")
