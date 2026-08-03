"""
geo.py — pure geodesic distance helpers for the matching engine.

No DB I/O, no network. Coordinates are pre-resolved upstream (profile save,
job import, or the recompute script's geocode-cache backfill) and passed in
on the applicant/job input structs as plain ``lat`` / ``lng`` floats.

The commute-radius rule (product requirement):
  Jobs are posted against a *city*. A job is in range iff the geodesic
  distance between the applicant's home coordinates and the job's city
  coordinates is <= the applicant's chosen radius — i.e. the radius circle
  covering the job's city counts. Never bare city/state string equality.
"""
from __future__ import annotations

import math

# Mean Earth radius (IUGG) in miles.
_EARTH_RADIUS_MILES = 3958.7613

# Product default when the applicant has not chosen a radius yet.
DEFAULT_COMMUTE_RADIUS_MILES = 50

# Distances at or under this are treated as "in your city" — city centroids
# for the same metro can be a few miles apart.
SAME_CITY_MILES = 5.0

# Beyond the radius but within radius * this factor counts as "just beyond" —
# a near-fit rather than a hard geography failure.
NEAR_RADIUS_FACTOR = 1.5


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two (lat, lng) points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def coords_of(entity: dict) -> tuple[float, float] | None:
    """Extract pre-resolved (lat, lng) from an applicant/job input struct.

    Returns None unless both coordinates are present and numeric — the
    engine then falls back to state/region logic (backward compatible).
    """
    lat = entity.get("lat")
    lng = entity.get("lng")
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def distance_between(applicant: dict, job: dict) -> float | None:
    """Geodesic miles between applicant home and job city, or None if either
    side is missing coordinates."""
    a = coords_of(applicant)
    j = coords_of(job)
    if a is None or j is None:
        return None
    return haversine_miles(a[0], a[1], j[0], j[1])


def effective_radius_miles(commute_radius_miles: int | float | None) -> float:
    """The applicant's chosen radius, falling back to the product default."""
    try:
        r = float(commute_radius_miles) if commute_radius_miles is not None else 0.0
    except (TypeError, ValueError):
        r = 0.0
    return r if r > 0 else float(DEFAULT_COMMUTE_RADIUS_MILES)
