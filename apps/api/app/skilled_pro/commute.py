"""
Drive-time estimation with a Postgres cache.

Preference order:
  1. Cache hit (nearby lat/lng snapped to 3 decimals)
  2. Google Maps Distance Matrix (if google_maps_api_key set)
  3. Mapbox Directions Matrix (if mapbox_access_token set)
  4. Haversine + rural-road fudge (35 mph average → minutes)

The matching engine already gates on geography via `region` + haversine. This
adds a *drive-time signal* attached to each match row — it doesn't replace the
existing gate. Downstream UI can render "27 min drive" instead of "18 mi away".
"""
from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

import asyncpg
import httpx

logger = logging.getLogger(__name__)

# Snap to ~110m precision for cache — trades workers care about "20 vs. 40 minutes",
# not curb-level precision.
_CACHE_PRECISION = 3
_FALLBACK_MPH = 35.0


async def drive_minutes(
    conn: asyncpg.Connection,
    *,
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    google_key: str = "",
    mapbox_token: str = "",
) -> Tuple[int, str]:
    """Return (drive_minutes, provider). Provider is one of google|mapbox|haversine."""
    olat, olng = _round(origin[0]), _round(origin[1])
    dlat, dlng = _round(destination[0]), _round(destination[1])

    cached = await conn.fetchrow(
        """
        SELECT drive_minutes, provider FROM public.commute_cache
         WHERE ROUND(origin_lat::numeric, 3) = $1
           AND ROUND(origin_lng::numeric, 3) = $2
           AND ROUND(dest_lat::numeric,   3) = $3
           AND ROUND(dest_lng::numeric,   3) = $4
      ORDER BY computed_at DESC LIMIT 1
        """,
        olat, olng, dlat, dlng,
    )
    if cached:
        return int(cached["drive_minutes"]), cached["provider"]

    minutes: Optional[int] = None
    provider = "haversine"
    distance_m: Optional[int] = None

    if google_key:
        result = await _google_matrix(origin, destination, google_key)
        if result:
            minutes, distance_m, provider = result[0], result[1], "google"
    if minutes is None and mapbox_token:
        result = await _mapbox_matrix(origin, destination, mapbox_token)
        if result:
            minutes, distance_m, provider = result[0], result[1], "mapbox"

    if minutes is None:
        # Haversine fallback with rural-road fudge.
        km = _haversine_km(origin, destination)
        distance_m = int(km * 1_000)
        miles = km * 0.621_371
        minutes = int(round((miles / _FALLBACK_MPH) * 60.0 * 1.25))  # +25% for surface streets
        provider = "haversine"

    await conn.execute(
        """
        INSERT INTO public.commute_cache
          (origin_lat, origin_lng, dest_lat, dest_lng, drive_minutes, distance_meters, provider)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        origin[0], origin[1], destination[0], destination[1],
        int(minutes), distance_m, provider,
    )
    return int(minutes), provider


# ---------------------------------------------------------------------------
def _round(v: float) -> float:
    return round(v, _CACHE_PRECISION)


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


async def _google_matrix(
    origin: Tuple[float, float], dest: Tuple[float, float], key: str,
) -> Optional[Tuple[int, int]]:
    """Returns (minutes, meters) or None on failure."""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{origin[0]},{origin[1]}",
        "destinations": f"{dest[0]},{dest[1]}",
        "mode": "driving",
        "units": "imperial",
        "key": key,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params=params)
        data = r.json()
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            return None
        seconds = int(el["duration"]["value"])
        meters = int(el["distance"]["value"])
        return max(1, seconds // 60), meters
    except Exception as e:
        logger.warning(f"Google Distance Matrix failed: {e}")
        return None


async def _mapbox_matrix(
    origin: Tuple[float, float], dest: Tuple[float, float], token: str,
) -> Optional[Tuple[int, int]]:
    url = f"https://api.mapbox.com/directions-matrix/v1/mapbox/driving/{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
    params = {"annotations": "duration,distance", "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params=params)
        data = r.json()
        dur = data.get("durations", [[None, None]])[0][1]
        dist = data.get("distances", [[None, None]])[0][1]
        if dur is None:
            return None
        return max(1, int(dur // 60)), int(dist or 0)
    except Exception as e:
        logger.warning(f"Mapbox matrix failed: {e}")
        return None
