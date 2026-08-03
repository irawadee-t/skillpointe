"""
geo.py — shared haversine helpers for API-side distance filtering.

Two forms of the SAME great-circle formula (kept provably in sync by
tests/test_browse_geo.py, which evaluates the SQL text with Python math):

  - haversine_miles():  pure-Python reference, used in tests and anywhere the
    API needs a distance without a round-trip to Postgres.
  - haversine_sql():    the SQL rendering, embedded in WHERE/SELECT clauses so
    Postgres does the filtering server-side (same pattern as the
    verified-workers `near_city` filter).

Deliberately dependency-free: the API must not import packages/matching
(see verified_workers.py — "no matching-package import").
"""
from __future__ import annotations

import math

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two (lat, lng) points."""
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def haversine_sql(
    lat_param: str,
    lng_param: str,
    lat_col: str = "j.lat",
    lng_col: str = "j.lng",
) -> str:
    """SQL expression for miles between a bound point and a row's coordinates.

    `lat_param` / `lng_param` are SQL placeholders ("$7") or literals; the
    columns default to the jobs table. Returns NULL when either column is NULL
    (SQL NULL propagation), so callers must guard with IS NOT NULL when the
    distance feeds a comparison.
    """
    return (
        f"2 * {EARTH_RADIUS_MILES} * asin(sqrt("
        f"power(sin(radians(({lat_col} - {lat_param}) / 2)), 2) + "
        f"cos(radians({lat_param})) * cos(radians({lat_col})) * "
        f"power(sin(radians(({lng_col} - {lng_param}) / 2)), 2)"
        f"))"
    )
