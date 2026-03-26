"""
admin.py — Admin analytics and dashboard API endpoints.

Provides aggregate statistics, job distribution data, match quality metrics,
and data quality insights for SkillPointe staff.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
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


# ---------------------------------------------------------------------------
# Admin applicant & employer directory endpoints
# ---------------------------------------------------------------------------

class AdminApplicantRow(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    city: str | None
    state: str | None
    program_name_raw: str | None
    job_family_code: str | None
    job_family_name: str | None
    available_from: str | None
    profile_completeness: int
    willing_to_relocate: bool
    eligible_count: int
    near_fit_count: int


class AdminApplicantList(BaseModel):
    total: int
    applicants: list[AdminApplicantRow]


class AdminEmployerRow(BaseModel):
    id: str
    name: str
    industry: str | None
    city: str | None
    state: str | None
    is_partner: bool
    total_jobs: int
    active_jobs: int
    contact_email: str | None
    contact_name: str | None


class AdminEmployerList(BaseModel):
    total: int
    employers: list[AdminEmployerRow]


class AdminEmployerJobRow(BaseModel):
    id: str
    title: str
    city: str | None
    state: str | None
    work_setting: str | None
    experience_level: str | None
    is_active: bool
    pay_min: float | None
    pay_max: float | None
    pay_type: str | None
    source_url: str | None
    eligible_count: int
    near_fit_count: int
    total_visible: int


class AdminEmployerDetail(BaseModel):
    id: str
    name: str
    industry: str | None
    description: str | None
    website: str | None
    city: str | None
    state: str | None
    is_partner: bool
    partner_since: str | None
    contact_email: str | None
    total_jobs: int
    active_jobs: int
    jobs: list[AdminEmployerJobRow]


@router.get("/employers/{employer_id}", response_model=AdminEmployerDetail)
async def get_employer_detail(employer_id: str, user=Depends(require_admin)):
    """Return full employer profile + job list for admin detail view."""
    async with get_db() as conn:
        emp = await conn.fetchrow(
            """
            SELECT e.id::text, e.name, e.industry, e.description, e.website,
                   e.city, e.state::text, e.is_partner, e.partner_since::text,
                   (
                       SELECT au.email
                       FROM public.employer_contacts ec2
                       JOIN auth.users au ON au.id = ec2.user_id
                       WHERE ec2.employer_id = e.id
                       ORDER BY ec2.created_at
                       LIMIT 1
                   ) AS contact_email
            FROM public.employers e
            WHERE e.id = $1::uuid
            """,
            employer_id,
        )
        if not emp:
            from fastapi import HTTPException, status as _status
            raise HTTPException(status_code=_status.HTTP_404_NOT_FOUND, detail="Employer not found")

        jobs = await conn.fetch(
            """
            SELECT
                j.id::text,
                COALESCE(j.title_normalized, j.title_raw) AS title,
                j.city, j.state::text,
                j.work_setting::text,
                j.experience_level::text,
                j.is_active,
                j.pay_min, j.pay_max,
                j.pay_type::text,
                j.source_url,
                COUNT(m.id) FILTER (WHERE m.is_visible_to_employer = TRUE) AS total_visible,
                COUNT(m.id) FILTER (WHERE m.is_visible_to_employer = TRUE AND m.eligibility_status = 'eligible') AS eligible_count,
                COUNT(m.id) FILTER (WHERE m.is_visible_to_employer = TRUE AND m.eligibility_status = 'near_fit') AS near_fit_count
            FROM public.jobs j
            LEFT JOIN public.matches m ON m.job_id = j.id
            WHERE j.employer_id = $1::uuid
            GROUP BY j.id
            ORDER BY j.is_active DESC, j.created_at DESC
            """,
            employer_id,
        )

    job_rows = [
        AdminEmployerJobRow(
            id=r["id"], title=r["title"],
            city=r["city"], state=r["state"],
            work_setting=r["work_setting"],
            experience_level=r["experience_level"],
            is_active=bool(r["is_active"]),
            pay_min=float(r["pay_min"]) if r["pay_min"] is not None else None,
            pay_max=float(r["pay_max"]) if r["pay_max"] is not None else None,
            pay_type=r["pay_type"],
            source_url=r["source_url"],
            total_visible=int(r["total_visible"] or 0),
            eligible_count=int(r["eligible_count"] or 0),
            near_fit_count=int(r["near_fit_count"] or 0),
        )
        for r in jobs
    ]

    active = sum(1 for j in job_rows if j.is_active)
    return AdminEmployerDetail(
        id=emp["id"], name=emp["name"],
        industry=emp["industry"], description=emp["description"],
        website=emp["website"], city=emp["city"], state=emp["state"],
        is_partner=bool(emp["is_partner"]), partner_since=emp["partner_since"],
        contact_email=emp["contact_email"],
        total_jobs=len(job_rows), active_jobs=active,
        jobs=job_rows,
    )


@router.get("/applicants", response_model=AdminApplicantList)
async def list_applicants(
    q: str | None = Query(None, description="Search by name or email"),
    state: str | None = Query(None),
    job_family: str | None = Query(None, description="Filter by job family code"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    """List all applicants with optional filtering for admin directory."""
    offset = (page - 1) * page_size

    conditions = ["1=1"]
    params: list[Any] = []
    p = 1

    if q:
        conditions.append(
            f"(a.first_name ILIKE ${p} OR a.last_name ILIKE ${p} OR a.email ILIKE ${p})"
        )
        params.append(f"%{q}%")
        p += 1
    if state:
        conditions.append(f"a.state = ${p}")
        params.append(state.upper())
        p += 1
    if job_family:
        conditions.append(f"jf.code = ${p}")
        params.append(job_family)
        p += 1

    where = " AND ".join(conditions)

    async with get_db() as conn:
        total = await conn.fetchval(
            f"""
            SELECT COUNT(DISTINCT a.id)
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            WHERE {where}
            """,
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT
                a.id::text,
                a.first_name,
                a.last_name,
                a.email,
                a.city,
                a.state::text,
                a.program_name_raw,
                -- completeness computed inline (no stored column)
                (
                  CASE WHEN a.first_name IS NOT NULL AND a.last_name IS NOT NULL THEN 10 ELSE 0 END +
                  CASE WHEN a.program_name_raw IS NOT NULL THEN 10 ELSE 0 END +
                  CASE WHEN a.canonical_job_family_id IS NOT NULL THEN 15 ELSE 0 END +
                  CASE WHEN a.state IS NOT NULL THEN 10 ELSE 0 END +
                  CASE WHEN a.city IS NOT NULL THEN 5 ELSE 0 END +
                  CASE WHEN a.available_from_date IS NOT NULL OR a.expected_completion_date IS NOT NULL THEN 15 ELSE 0 END +
                  CASE WHEN a.willing_to_relocate THEN 5 ELSE 0 END
                ) AS profile_completeness,
                a.willing_to_relocate,
                COALESCE(a.available_from_date::text, a.expected_completion_date::text) AS available_from,
                jf.code AS job_family_code,
                jf.name AS job_family_name,
                COUNT(m.id) FILTER (WHERE m.eligibility_status = 'eligible') AS eligible_count,
                COUNT(m.id) FILTER (WHERE m.eligibility_status = 'near_fit') AS near_fit_count
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            LEFT JOIN public.matches m ON m.applicant_id = a.id
            WHERE {where}
            GROUP BY a.id, jf.code, jf.name
            ORDER BY a.last_name NULLS LAST, a.first_name NULLS LAST
            LIMIT ${p} OFFSET ${p + 1}
            """,
            *params, page_size, offset,
        )

    applicants = [
        AdminApplicantRow(
            id=r["id"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            email=r["email"],
            city=r["city"],
            state=r["state"],
            program_name_raw=r["program_name_raw"],
            job_family_code=r["job_family_code"],
            job_family_name=r["job_family_name"],
            available_from=r["available_from"],
            profile_completeness=r["profile_completeness"] or 0,
            willing_to_relocate=bool(r["willing_to_relocate"]),
            eligible_count=int(r["eligible_count"] or 0),
            near_fit_count=int(r["near_fit_count"] or 0),
        )
        for r in rows
    ]
    return AdminApplicantList(total=total, applicants=applicants)


@router.get("/employers", response_model=AdminEmployerList)
async def list_employers(
    q: str | None = Query(None, description="Search by company name"),
    state: str | None = Query(None),
    is_partner: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    """List all employers with optional filtering for admin directory."""
    offset = (page - 1) * page_size

    conditions = ["1=1"]
    params: list[Any] = []
    p = 1

    if q:
        conditions.append(f"e.name ILIKE ${p}")
        params.append(f"%{q}%")
        p += 1
    if state:
        conditions.append(f"e.state = ${p}")
        params.append(state.upper())
        p += 1
    if is_partner is not None:
        conditions.append(f"e.is_partner = ${p}")
        params.append(is_partner)
        p += 1

    where = " AND ".join(conditions)

    async with get_db() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM public.employers e WHERE {where}",
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT
                e.id::text,
                e.name,
                e.industry,
                e.city,
                e.state::text,
                e.is_partner,
                COUNT(DISTINCT j.id) FILTER (WHERE j.is_active = TRUE) AS active_jobs,
                COUNT(DISTINCT j.id) AS total_jobs,
                (
                    SELECT au.email
                    FROM public.employer_contacts ec2
                    JOIN auth.users au ON au.id = ec2.user_id
                    WHERE ec2.employer_id = e.id
                    ORDER BY ec2.created_at
                    LIMIT 1
                ) AS contact_email,
                NULL::text AS contact_name
            FROM public.employers e
            LEFT JOIN public.jobs j ON j.employer_id = e.id
            WHERE {where}
            GROUP BY e.id
            ORDER BY e.name
            LIMIT ${p} OFFSET ${p + 1}
            """,
            *params, page_size, offset,
        )

    employers = [
        AdminEmployerRow(
            id=r["id"],
            name=r["name"],
            industry=r["industry"],
            city=r["city"],
            state=r["state"],
            is_partner=bool(r["is_partner"]),
            total_jobs=int(r["total_jobs"] or 0),
            active_jobs=int(r["active_jobs"] or 0),
            contact_email=r["contact_email"],
            contact_name=r["contact_name"],
        )
        for r in rows
    ]
    return AdminEmployerList(total=total, employers=employers)


# ---------------------------------------------------------------------------
# GET /admin/analytics/engagement
# ---------------------------------------------------------------------------

class EngagementEventCount(BaseModel):
    event_type: str
    count: int


class EngagementActivity(BaseModel):
    event_type: str
    actor_name: str
    detail: str | None
    created_at: str


class EngagementAnalytics(BaseModel):
    # Platform totals
    total_events: int
    total_dms_sent: int
    total_outreach_sent: int
    total_interest_signals: int
    total_apply_clicks: int
    total_hires_reported: int
    total_active_conversations: int
    # Breakdown by event type
    events_by_type: list[EngagementEventCount]
    # Recent activity feed (last 30 events)
    recent_activity: list[EngagementActivity]


@router.get("/analytics/engagement", response_model=EngagementAnalytics)
async def engagement_analytics(user=Depends(require_admin)):
    """Platform engagement metrics for admin: DMs, interest signals, outreach, hires."""
    async with get_db() as conn:
        total_events = await conn.fetchval("SELECT COUNT(*) FROM public.engagement_events") or 0

        # DMs (from direct_messages table — more accurate than engagement_events)
        total_dms = await conn.fetchval("SELECT COUNT(*) FROM public.direct_messages") or 0
        active_convos = await conn.fetchval(
            "SELECT COUNT(*) FROM public.conversations WHERE last_message_at > NOW() - INTERVAL '30 days'"
        ) or 0

        # Outreach emails sent
        total_outreach = await conn.fetchval(
            "SELECT COUNT(*) FROM public.employer_outreach WHERE status = 'sent'"
        ) or 0

        # Interest signals from applicants
        total_interest = await conn.fetchval(
            "SELECT COUNT(*) FROM public.engagement_events WHERE event_type = 'interest_set'"
        ) or 0

        # Apply clicks
        total_apply_clicks = await conn.fetchval(
            "SELECT COUNT(*) FROM public.engagement_events WHERE event_type = 'apply_click'"
        ) or 0

        # Hires reported
        total_hires = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes WHERE outcome_type = 'hired'"
        ) or 0

        # Events by type
        type_rows = await conn.fetch(
            """
            SELECT event_type, COUNT(*) AS cnt
            FROM public.engagement_events
            GROUP BY event_type
            ORDER BY cnt DESC
            LIMIT 20
            """
        )
        events_by_type = [
            EngagementEventCount(event_type=r["event_type"], count=int(r["cnt"]))
            for r in type_rows
        ]

        # Recent activity feed — combine engagement_events, outreach, DMs
        activity_rows = await conn.fetch(
            """
            SELECT
                ee.event_type,
                COALESCE(
                    CONCAT(a.first_name, ' ', a.last_name),
                    em.name,
                    'System'
                ) AS actor_name,
                ee.event_data::text AS detail,
                ee.created_at::text
            FROM public.engagement_events ee
            LEFT JOIN public.applicants a ON a.id = ee.applicant_id
            LEFT JOIN public.employers em ON em.id = ee.employer_id
            ORDER BY ee.created_at DESC
            LIMIT 30
            """
        )
        recent_activity = [
            EngagementActivity(
                event_type=r["event_type"],
                actor_name=(r["actor_name"] or "Unknown").strip(),
                detail=r["detail"],
                created_at=r["created_at"],
            )
            for r in activity_rows
        ]

    return EngagementAnalytics(
        total_events=int(total_events),
        total_dms_sent=int(total_dms),
        total_outreach_sent=int(total_outreach),
        total_interest_signals=int(total_interest),
        total_apply_clicks=int(total_apply_clicks),
        total_hires_reported=int(total_hires),
        total_active_conversations=int(active_convos),
        events_by_type=events_by_type,
        recent_activity=recent_activity,
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/engagement/applicants
# ---------------------------------------------------------------------------

class ApplicantEngagementRow(BaseModel):
    applicant_id: str
    name: str
    program: str | None
    state: str | None
    interest_signals: int
    apply_clicks: int
    chat_messages: int
    dms_sent: int
    total_events: int


class ApplicantEngagementList(BaseModel):
    total: int
    rows: list[ApplicantEngagementRow]


@router.get("/analytics/engagement/applicants", response_model=ApplicantEngagementList)
async def applicant_engagement(
    q: str | None = Query(None, description="Filter by name"),
    sort: str = Query("total_events", description="Sort column"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    """Per-applicant engagement breakdown for admin."""
    offset = (page - 1) * page_size

    name_filter = ""
    params_base: list[Any] = []
    if q:
        name_filter = "WHERE (a.first_name ILIKE $1 OR a.last_name ILIKE $1)"
        params_base = [f"%{q}%"]

    sort_col = {
        "total_events": "total_events",
        "interest_signals": "interest_signals",
        "apply_clicks": "apply_clicks",
        "chat_messages": "chat_messages",
        "dms_sent": "dms_sent",
        "name": "name",
    }.get(sort, "total_events")

    p = len(params_base) + 1

    async with get_db() as conn:
        total = await conn.fetchval(
            f"""
            SELECT COUNT(DISTINCT a.id)
            FROM public.applicants a
            {name_filter}
            """,
            *params_base,
        )

        rows = await conn.fetch(
            f"""
            SELECT
                a.id::text AS applicant_id,
                CONCAT(a.first_name, ' ', a.last_name) AS name,
                a.program_name_raw AS program,
                a.state::text AS state,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'interest_set')      AS interest_signals,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'apply_click')        AS apply_clicks,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'chat_message_sent')  AS chat_messages,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'dm_sent'
                    AND (ee.event_data->>'sender_role') = 'applicant')           AS dms_sent,
                COUNT(ee.id)                                                      AS total_events
            FROM public.applicants a
            LEFT JOIN public.engagement_events ee ON ee.applicant_id = a.id
            {name_filter}
            GROUP BY a.id
            ORDER BY {sort_col} DESC NULLS LAST, name
            LIMIT ${p} OFFSET ${p + 1}
            """,
            *params_base, page_size, offset,
        )

    return ApplicantEngagementList(
        total=int(total or 0),
        rows=[
            ApplicantEngagementRow(
                applicant_id=r["applicant_id"],
                name=(r["name"] or "").strip() or "Unknown",
                program=r["program"],
                state=r["state"],
                interest_signals=int(r["interest_signals"] or 0),
                apply_clicks=int(r["apply_clicks"] or 0),
                chat_messages=int(r["chat_messages"] or 0),
                dms_sent=int(r["dms_sent"] or 0),
                total_events=int(r["total_events"] or 0),
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# GET /admin/analytics/engagement/employers
# ---------------------------------------------------------------------------

class EmployerEngagementRow(BaseModel):
    employer_id: str
    name: str
    outreach_sent: int
    dms_sent: int
    hires_reported: int
    candidates_viewed: int
    total_actions: int


class EmployerEngagementList(BaseModel):
    total: int
    rows: list[EmployerEngagementRow]


@router.get("/analytics/engagement/employers", response_model=EmployerEngagementList)
async def employer_engagement(
    q: str | None = Query(None, description="Filter by employer name"),
    sort: str = Query("total_actions", description="Sort column"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    """Per-employer engagement breakdown for admin."""
    offset = (page - 1) * page_size

    name_filter = ""
    params_base: list[Any] = []
    if q:
        name_filter = "WHERE e.name ILIKE $1"
        params_base = [f"%{q}%"]

    sort_col = {
        "total_actions": "total_actions",
        "outreach_sent": "outreach_sent",
        "dms_sent": "dms_sent",
        "hires_reported": "hires_reported",
        "candidates_viewed": "candidates_viewed",
        "name": "e.name",
    }.get(sort, "total_actions")

    p = len(params_base) + 1

    async with get_db() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM public.employers e {name_filter}",
            *params_base,
        )

        rows = await conn.fetch(
            f"""
            SELECT
                e.id::text AS employer_id,
                e.name,
                COUNT(DISTINCT eo.id)                                            AS outreach_sent,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'dm_sent'
                    AND (ee.event_data->>'sender_role') = 'employer')            AS dms_sent,
                COUNT(DISTINCT ho.id)                                            AS hires_reported,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'candidate_viewed')  AS candidates_viewed,
                (
                    COUNT(DISTINCT eo.id)
                    + COUNT(ee.id) FILTER (WHERE ee.event_type = 'dm_sent'
                        AND (ee.event_data->>'sender_role') = 'employer')
                    + COUNT(DISTINCT ho.id)
                    + COUNT(ee.id) FILTER (WHERE ee.event_type = 'candidate_viewed')
                )                                                                AS total_actions
            FROM public.employers e
            LEFT JOIN public.employer_outreach eo ON eo.employer_id = e.id AND eo.status = 'sent'
            LEFT JOIN public.engagement_events ee ON ee.employer_id = e.id
            LEFT JOIN public.hire_outcomes ho ON ho.employer_id = e.id
            {name_filter}
            GROUP BY e.id
            ORDER BY total_actions DESC NULLS LAST, e.name
            LIMIT ${p} OFFSET ${p + 1}
            """,
            *params_base, page_size, offset,
        )

    return EmployerEngagementList(
        total=int(total or 0),
        rows=[
            EmployerEngagementRow(
                employer_id=r["employer_id"],
                name=r["name"] or "Unknown",
                outreach_sent=int(r["outreach_sent"] or 0),
                dms_sent=int(r["dms_sent"] or 0),
                hires_reported=int(r["hires_reported"] or 0),
                candidates_viewed=int(r["candidates_viewed"] or 0),
                total_actions=int(r["total_actions"] or 0),
            )
            for r in rows
        ],
    )
