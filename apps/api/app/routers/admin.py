"""
admin.py — Admin analytics and dashboard API endpoints.

Provides aggregate statistics, job distribution data, match quality metrics,
and data quality insights for SkillPointe staff.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OverviewStats(BaseModel):
    total_applicants: int
    total_active_jobs: int
    total_employers: int
    total_matches: int
    eligible_matches: int
    near_fit_matches: int
    ineligible_matches: int


class JobFamilyCount(BaseModel):
    family_code: str
    family_name: str
    count: int


class SourceCount(BaseModel):
    source_site: str
    count: int


class StateCount(BaseModel):
    state: str
    count: int


class CityJobCluster(BaseModel):
    city: str
    state: str
    lat: float
    lon: float
    count: int
    families: list[str]


class MatchQualityBucket(BaseModel):
    label: str
    count: int


class ExperienceLevelCount(BaseModel):
    level: str
    count: int


class DataQualityMetric(BaseModel):
    metric: str
    value: int
    total: int
    pct: float


class ClusterJob(BaseModel):
    id: str
    title: str
    employer: str
    family_code: str | None
    experience_level: str | None
    source_url: str | None


class AdminDashboard(BaseModel):
    overview: OverviewStats
    jobs_by_family: list[JobFamilyCount]
    jobs_by_source: list[SourceCount]
    jobs_by_state: list[StateCount]
    job_clusters: list[CityJobCluster]
    match_quality: list[MatchQualityBucket]
    experience_levels: list[ExperienceLevelCount]
    data_quality: list[DataQualityMetric]


# ---------------------------------------------------------------------------
# US city coordinate lookup (covers major cities in our dataset)
# ---------------------------------------------------------------------------

_CITY_COORDS: dict[str, tuple[float, float]] = {
    "san jose, ca": (37.3382, -121.8863), "san francisco, ca": (37.7749, -122.4194),
    "los angeles, ca": (33.9425, -118.2551), "palo alto, ca": (37.4419, -122.1430),
    "long beach, ca": (33.7701, -118.1937), "chino, ca": (34.0122, -117.6889),
    "austin, tx": (30.2672, -97.7431), "houston, tx": (29.7604, -95.3698),
    "dallas, tx": (32.7767, -96.7970), "denton, tx": (33.2148, -97.1331),
    "el paso, tx": (31.7619, -106.4850), "red oak, tx": (32.5174, -96.8044),
    "conroe, tx": (30.3119, -95.4561), "atlanta, ga": (33.7490, -84.3880),
    "carrollton, ga": (33.5801, -85.0766), "charlotte, nc": (35.2271, -80.8431),
    "raleigh, nc": (35.7796, -78.6382), "columbia, sc": (34.0007, -81.0348),
    "greenville, sc": (34.8526, -82.3940), "detroit, mi": (42.3314, -83.0458),
    "dearborn, mi": (42.3223, -83.1763), "flat rock, mi": (42.0955, -83.2833),
    "cleveland, oh": (41.4993, -81.6944), "columbus, oh": (39.9612, -82.9988),
    "lima, oh": (40.7425, -84.1053), "new york, ny": (40.7128, -74.0060),
    "boston, ma": (42.3601, -71.0589), "pittsburgh, pa": (40.4406, -79.9959),
    "philadelphia, pa": (39.9526, -75.1652), "seattle, wa": (47.6062, -122.3321),
    "vancouver, wa": (45.6387, -122.6615), "nashville, tn": (36.1627, -86.7816),
    "knoxville, tn": (35.9606, -83.9207), "louisville, ky": (38.2527, -85.7585),
    "indianapolis, in": (39.7684, -86.1581), "kansas city, mo": (39.0997, -94.5786),
    "st. louis, mo": (38.6270, -90.1994), "milwaukee, wi": (43.0389, -87.9065),
    "fargo, nd": (46.8772, -96.7898), "richmond, va": (37.5407, -77.4360),
    "newark, nj": (40.7357, -74.1724), "chicago, il": (41.8781, -87.6298),
    "denver, co": (39.7392, -104.9903), "portland, or": (45.5152, -122.6784),
    "millersburg, or": (44.6787, -123.0623), "goodyear, az": (33.4353, -112.3581),
    "waddell, az": (33.5714, -112.4618), "scottsdale, az": (33.4942, -111.9261),
    "horsham, pa": (40.1776, -75.1321), "west chester, pa": (39.9601, -75.6055),
}

# State centroid fallback
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.806671, -86.791130), "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221), "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564), "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371), "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783), "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337), "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137), "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526), "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067), "LA": (31.169546, -91.867805),
    "ME": (44.693947, -69.381927), "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106), "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192), "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368), "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082), "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896), "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482), "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419), "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915), "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938), "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780), "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828), "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461), "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686), "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494), "WV": (38.491226, -80.954456),
    "WI": (44.268543, -89.616508), "WY": (42.755966, -107.302490),
}


def _geocode(city: str | None, state: str | None) -> tuple[float, float] | None:
    """Look up coordinates for a city/state pair."""
    if city and state:
        key = f"{city.lower().strip()}, {state.lower().strip()}"
        if key in _CITY_COORDS:
            return _CITY_COORDS[key]
    if state:
        coords = _STATE_CENTROIDS.get(state.upper().strip())
        if coords:
            return coords
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/analytics/dashboard", response_model=AdminDashboard)
async def admin_dashboard(user=Depends(require_admin)):
    """Comprehensive admin dashboard data — all analytics in one call."""
    async with get_db() as conn:
        # Overview
        total_applicants = await conn.fetchval("SELECT COUNT(*) FROM public.applicants")
        total_active_jobs = await conn.fetchval("SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE")
        total_employers = await conn.fetchval("SELECT COUNT(*) FROM public.employers")
        total_matches = await conn.fetchval("SELECT COUNT(*) FROM public.matches")
        elig_ct = await conn.fetchval(
            "SELECT COUNT(*) FROM public.matches WHERE eligibility_status = 'eligible'"
        )
        near_ct = await conn.fetchval(
            "SELECT COUNT(*) FROM public.matches WHERE eligibility_status = 'near_fit'"
        )
        inelig_ct = await conn.fetchval(
            "SELECT COUNT(*) FROM public.matches WHERE eligibility_status = 'ineligible'"
        )

        overview = OverviewStats(
            total_applicants=total_applicants,
            total_active_jobs=total_active_jobs,
            total_employers=total_employers,
            total_matches=total_matches,
            eligible_matches=elig_ct,
            near_fit_matches=near_ct,
            ineligible_matches=inelig_ct,
        )

        # Jobs by family
        rows = await conn.fetch("""
            SELECT COALESCE(jf.code, 'unknown') as code,
                   COALESCE(jf.name, 'Unknown') as name,
                   COUNT(*) as ct
            FROM public.jobs j
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.is_active = TRUE
            GROUP BY jf.code, jf.name ORDER BY ct DESC
        """)
        jobs_by_family = [
            JobFamilyCount(family_code=r["code"], family_name=r["name"], count=r["ct"])
            for r in rows
        ]

        # Jobs by source
        rows = await conn.fetch("""
            SELECT COALESCE(source_site, source, 'manual') as src, COUNT(*) as ct
            FROM public.jobs WHERE is_active = TRUE
            GROUP BY src ORDER BY ct DESC
        """)
        jobs_by_source = [SourceCount(source_site=r["src"], count=r["ct"]) for r in rows]

        # Jobs by state
        rows = await conn.fetch("""
            SELECT COALESCE(state::text, 'Unknown') as st, COUNT(*) as ct
            FROM public.jobs WHERE is_active = TRUE
            GROUP BY st ORDER BY ct DESC
        """)
        jobs_by_state = [StateCount(state=r["st"], count=r["ct"]) for r in rows]

        # Job clusters (city-level with geocoding)
        rows = await conn.fetch("""
            SELECT j.city, j.state, COUNT(*) as ct,
                   ARRAY_AGG(DISTINCT jf.code) FILTER (WHERE jf.code IS NOT NULL) as families
            FROM public.jobs j
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.is_active = TRUE AND j.city IS NOT NULL AND j.state IS NOT NULL
            GROUP BY j.city, j.state
            ORDER BY ct DESC
        """)
        job_clusters = []
        for r in rows:
            coords = _geocode(r["city"], r["state"])
            if coords:
                job_clusters.append(CityJobCluster(
                    city=r["city"], state=r["state"],
                    lat=coords[0], lon=coords[1], count=r["ct"],
                    families=r["families"] or [],
                ))

        # Match quality distribution
        rows = await conn.fetch("""
            SELECT COALESCE(match_label::text, 'unscored') as label, COUNT(*) as ct
            FROM public.matches
            GROUP BY label ORDER BY ct DESC
        """)
        match_quality = [MatchQualityBucket(label=r["label"], count=r["ct"]) for r in rows]

        # Experience levels
        rows = await conn.fetch("""
            SELECT COALESCE(experience_level::text, 'unspecified') as level, COUNT(*) as ct
            FROM public.jobs WHERE is_active = TRUE
            GROUP BY level ORDER BY ct DESC
        """)
        experience_levels = [ExperienceLevelCount(level=r["level"], count=r["ct"]) for r in rows]

        # Data quality metrics
        dq: list[DataQualityMetric] = []
        total_j = total_active_jobs

        missing_desc = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE AND (description_raw IS NULL OR description_raw = '')"
        )
        dq.append(DataQualityMetric(
            metric="Jobs missing description", value=missing_desc,
            total=total_j, pct=round(missing_desc / max(total_j, 1) * 100, 1),
        ))

        missing_state = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE AND state IS NULL"
        )
        dq.append(DataQualityMetric(
            metric="Jobs missing state", value=missing_state,
            total=total_j, pct=round(missing_state / max(total_j, 1) * 100, 1),
        ))

        missing_family = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE AND canonical_job_family_id IS NULL"
        )
        dq.append(DataQualityMetric(
            metric="Jobs missing trade family", value=missing_family,
            total=total_j, pct=round(missing_family / max(total_j, 1) * 100, 1),
        ))

        missing_exp = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE AND experience_level IS NULL"
        )
        dq.append(DataQualityMetric(
            metric="Jobs missing experience level", value=missing_exp,
            total=total_j, pct=round(missing_exp / max(total_j, 1) * 100, 1),
        ))

        broken_links = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs WHERE is_active = TRUE AND source_url IS NULL AND source = 'scraper'"
        )
        dq.append(DataQualityMetric(
            metric="Scraped jobs missing URL", value=broken_links,
            total=total_j, pct=round(broken_links / max(total_j, 1) * 100, 1),
        ))

        sparse_applicants = await conn.fetchval("""
            SELECT COUNT(*) FROM public.applicants
            WHERE (experience_raw IS NULL OR experience_raw = '')
              AND (bio_raw IS NULL OR bio_raw = '')
              AND (essay_background IS NULL OR essay_background = '')
        """)
        total_a = total_applicants
        dq.append(DataQualityMetric(
            metric="Applicants with sparse profiles", value=sparse_applicants,
            total=total_a, pct=round(sparse_applicants / max(total_a, 1) * 100, 1),
        ))

    return AdminDashboard(
        overview=overview,
        jobs_by_family=jobs_by_family,
        jobs_by_source=jobs_by_source,
        jobs_by_state=jobs_by_state,
        job_clusters=job_clusters,
        match_quality=match_quality,
        experience_levels=experience_levels,
        data_quality=dq,
    )


@router.get("/analytics/cluster-jobs", response_model=list[ClusterJob])
async def cluster_jobs(city: str, state: str, user=Depends(require_admin)):
    """Fetch jobs at a specific city/state for map drill-down."""
    async with get_db() as conn:
        rows = await conn.fetch("""
            SELECT j.id, j.title_raw, COALESCE(j.title_normalized, j.title_raw) as title,
                   e.name as employer, jf.code as family_code,
                   j.experience_level::text, j.source_url
            FROM public.jobs j
            LEFT JOIN public.employers e ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.is_active = TRUE AND j.city = $1 AND j.state = $2
            ORDER BY j.title_raw
        """, city, state)
    return [
        ClusterJob(
            id=str(r["id"]), title=r["title"], employer=r["employer"] or "Unknown",
            family_code=r["family_code"], experience_level=r["experience_level"],
            source_url=r["source_url"],
        )
        for r in rows
    ]


@router.get("/analytics/job-map", response_model=list[CityJobCluster])
async def job_map_data(user=Depends(require_admin)):
    """Job distribution data for map visualization."""
    async with get_db() as conn:
        rows = await conn.fetch("""
            SELECT j.city, j.state, COUNT(*) as ct,
                   ARRAY_AGG(DISTINCT jf.code) FILTER (WHERE jf.code IS NOT NULL) as families
            FROM public.jobs j
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.is_active = TRUE AND j.city IS NOT NULL AND j.state IS NOT NULL
            GROUP BY j.city, j.state
            ORDER BY ct DESC
        """)
    clusters = []
    for r in rows:
        coords = _geocode(r["city"], r["state"])
        if coords:
            clusters.append(CityJobCluster(
                city=r["city"], state=r["state"],
                lat=coords[0], lon=coords[1], count=r["ct"],
                families=r["families"] or [],
            ))
    return clusters
