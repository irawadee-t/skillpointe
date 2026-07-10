"""
Free-tier geocoding via OpenStreetMap Nominatim.

Nominatim requires a descriptive User-Agent and enforces a 1 req/sec rate limit,
so we aggressively cache in geocode_cache (unique on normalized query string).
Same-city/state pairs collapse to one lookup for the whole app.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

import asyncpg
import httpx

logger = logging.getLogger(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = "SkillPointe-Match/0.1 (trades-workforce-platform; support@skillpointe.local)"

# Serialize outgoing Nominatim hits so we respect the 1 req/sec fair-use policy.
_lock = asyncio.Lock()
_last_hit = 0.0


def _normalize(city: str = "", state: str = "", zip_code: str = "") -> str:
    parts: list[str] = []
    if zip_code and zip_code.strip():
        parts.append(zip_code.strip())
    if city and city.strip():
        parts.append(city.strip().lower())
    if state and state.strip():
        parts.append(state.strip().upper()[:2])
    return ", ".join(parts)


async def geocode(
    conn: asyncpg.Connection,
    *,
    city: str = "",
    state: str = "",
    zip_code: str = "",
) -> Optional[Tuple[float, float]]:
    """Return (lat, lng) or None if we can't resolve. Caches on success."""
    query = _normalize(city, state, zip_code)
    if not query:
        return None

    row = await conn.fetchrow(
        "SELECT lat, lng FROM public.geocode_cache WHERE query = $1", query,
    )
    if row:
        return float(row["lat"]), float(row["lng"])

    result = await _nominatim_lookup(query)
    if result is None:
        return None
    lat, lng, display = result
    await conn.execute(
        """
        INSERT INTO public.geocode_cache (query, lat, lng, display_name, provider)
        VALUES ($1, $2, $3, $4, 'nominatim')
        ON CONFLICT (query) DO NOTHING
        """,
        query, lat, lng, display,
    )
    return lat, lng


async def _nominatim_lookup(query: str) -> Optional[Tuple[float, float, str]]:
    global _last_hit
    async with _lock:
        # Rate-limit: no more than 1 outbound request per second.
        import time
        elapsed = time.monotonic() - _last_hit
        if elapsed < 1.05:
            await asyncio.sleep(1.05 - elapsed)
        _last_hit = time.monotonic()

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
        "addressdetails": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": _UA}) as c:
            r = await c.get(_NOMINATIM, params=params)
        if r.status_code != 200:
            logger.warning(f"Nominatim status {r.status_code} for {query!r}")
            return None
        arr = r.json()
        if not arr:
            return None
        hit = arr[0]
        return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", "")
    except Exception as e:
        logger.warning(f"Nominatim lookup failed for {query!r}: {e}")
        return None
