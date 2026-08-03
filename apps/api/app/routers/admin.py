"""
admin.py — Admin analytics and dashboard API endpoints.

Provides aggregate statistics, job distribution data, match quality metrics,
and data quality insights for SkillPointe staff.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_admin
from app.db import get_db
from app.util.filters import csv_values, parse_iso_date

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


@router.get("/analytics/overview")
async def admin_overview(user=Depends(require_admin)):
    """Granular, cross-domain platform metrics — the admin command center.
    One aggregation call covering acquisition, verification, consent, matching,
    marketplace, engagement, outcomes, SKILLED ID, and sync health."""
    async with get_db() as conn:
        async def v(q: str) -> int:
            return int(await conn.fetchval(q) or 0)

        W7 = "created_at >= now() - interval '7 days'"
        W30 = "created_at >= now() - interval '30 days'"

        # Single-pass aggregates over the big tables. Same numbers as the old
        # one-count-per-query version — just one scan instead of one per metric
        # (matches alone is 130k+ rows; six separate counts cost ~6 scans).
        cred_agg = await conn.fetchrow(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE verification_level = 0) AS self_reported, "
            "count(*) FILTER (WHERE verification_level = 1) AS inst, "
            "count(*) FILTER (WHERE verification_level >= 2) AS skilled, "
            "count(*) FILTER (WHERE needs_review = TRUE) AS needs_review, "
            f"count(*) FILTER (WHERE {W7}) AS new_7d, "
            f"count(*) FILTER (WHERE {W30}) AS new_30d "
            "FROM public.credentials"
        )
        creds = int(cred_agg["total"] or 0)
        inst = int(cred_agg["inst"] or 0)
        skilled = int(cred_agg["skilled"] or 0)

        match_agg = await conn.fetchrow(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE eligibility_status = 'eligible') AS eligible, "
            "count(*) FILTER (WHERE eligibility_status = 'near_fit') AS near_fit, "
            "count(*) FILTER (WHERE eligibility_status = 'ineligible') AS ineligible, "
            "avg(base_fit_score) AS avg_fit, "
            "count(*) FILTER (WHERE base_fit_score >= 70) AS strong "
            "FROM public.matches"
        )
        m_total = int(match_agg["total"] or 0)
        # Kept separate on purpose: a DISTINCT-inside-the-aggregate forces a
        # sort of the whole table (~245ms); this probe uses the eligibility
        # index (<1ms) since eligible rows are a tiny fraction of matches.
        applicants_matched = await v(
            "SELECT count(DISTINCT applicant_id) FROM public.matches WHERE eligibility_status = 'eligible'"
        )

        eng_agg = await conn.fetchrow(
            "SELECT count(*) AS total, "
            f"count(*) FILTER (WHERE {W7}) AS total_7d, "
            f"count(DISTINCT applicant_id) FILTER (WHERE applicant_id IS NOT NULL AND {W7}) AS active_applicants_7d, "
            f"count(DISTINCT employer_id) FILTER (WHERE employer_id IS NOT NULL AND {W7}) AS active_employers_7d, "
            "count(DISTINCT applicant_id) FILTER (WHERE applicant_id IS NOT NULL) AS active_applicants_total, "
            "count(DISTINCT employer_id) FILTER (WHERE employer_id IS NOT NULL) AS active_employers_total "
            "FROM public.engagement_events"
        )

        eng_rows = await conn.fetch(
            f"SELECT event_type, count(*) AS c, count(*) FILTER (WHERE {W7}) AS c7 "
            "FROM public.engagement_events GROUP BY event_type ORDER BY c DESC"
        )
        trade_rows = await conn.fetch(
            "SELECT jf.name AS name, count(*) AS c FROM public.jobs j "
            "JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id "
            "WHERE j.is_active = TRUE GROUP BY jf.name ORDER BY c DESC LIMIT 6"
        )
        med_wage = await conn.fetchval(
            "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY reported_wage_annual) "
            "FROM public.hire_outcomes WHERE reported_wage_annual IS NOT NULL"
        )

        # --- Marketplace funnel (the core conversion story) ---
        # Each stage is the CUMULATIVE subset of workers who reached every prior
        # stage too, so counts are monotonically non-increasing (a funnel that
        # widens mid-way is a lie — a worker matched without ever verifying is
        # off-path and must not inflate "Matched"). The independent per-signal
        # counts still live in the matching/marketplace sections above.
        funnel_row = await conn.fetchrow(
            """
            WITH stage AS (
                SELECT a.id,
                    EXISTS (SELECT 1 FROM public.credentials c
                            WHERE c.applicant_id = a.id) AS credentialed,
                    EXISTS (SELECT 1 FROM public.credentials c
                            WHERE c.applicant_id = a.id AND c.verification_level >= 1) AS verified,
                    EXISTS (SELECT 1 FROM public.consent_settings cs
                            WHERE cs.applicant_id = a.id AND cs.external_sharing ? 'employer') AS sharing,
                    EXISTS (SELECT 1 FROM public.matches m
                            WHERE m.applicant_id = a.id AND m.eligibility_status = 'eligible') AS matched,
                    EXISTS (SELECT 1 FROM public.saved_jobs sj
                            WHERE sj.applicant_id = a.id
                              AND sj.interest_level IN ('interested','applied')) AS interested,
                    EXISTS (SELECT 1 FROM public.hire_outcomes ho
                            WHERE ho.applicant_id = a.id
                              AND ho.outcome_type IN ('placed','hired')) AS placed
                FROM public.applicants a
            )
            SELECT
                count(*) AS learners,
                count(*) FILTER (WHERE credentialed) AS credentialed,
                count(*) FILTER (WHERE credentialed AND verified) AS verified,
                count(*) FILTER (WHERE credentialed AND verified AND sharing) AS discoverable,
                count(*) FILTER (WHERE credentialed AND verified AND sharing
                                   AND matched) AS matched,
                count(*) FILTER (WHERE credentialed AND verified AND sharing
                                   AND matched AND interested) AS interested,
                count(*) FILTER (WHERE credentialed AND verified AND sharing
                                   AND matched AND interested AND placed) AS placed
            FROM stage
            """
        )
        learners = int(funnel_row["learners"] or 0)
        with_credential = int(funnel_row["credentialed"] or 0)
        verified_workers = int(funnel_row["verified"] or 0)
        discoverable = int(funnel_row["discoverable"] or 0)
        matched = int(funnel_row["matched"] or 0)
        interested = int(funnel_row["interested"] or 0)
        placed = int(funnel_row["placed"] or 0)

        # --- Action-needed signals (what an operator should DO) ---
        unmatched = await v(
            "SELECT count(*) FROM public.applicants a WHERE a.onboarding_complete = TRUE AND NOT EXISTS ("
            "  SELECT 1 FROM public.matches m WHERE m.applicant_id = a.id AND m.eligibility_status = 'eligible')"
        )
        jobs_no_candidates = await v(
            "SELECT count(*) FROM public.jobs j WHERE j.is_active = TRUE AND NOT EXISTS ("
            "  SELECT 1 FROM public.matches m WHERE m.job_id = j.id AND m.eligibility_status = 'eligible')"
        )
        verified_not_sharing = await v(
            "SELECT count(DISTINCT a.id) FROM public.applicants a WHERE EXISTS ("
            "  SELECT 1 FROM public.credentials c WHERE c.applicant_id = a.id AND c.verification_level >= 1) "
            "AND NOT EXISTS (SELECT 1 FROM public.consent_settings cs WHERE cs.applicant_id = a.id AND cs.external_sharing ? 'employer')"
        )
        review_queue = await v("SELECT count(*) FROM public.credentials WHERE needs_review = TRUE")
        sync_pending = await v("SELECT count(*) FROM public.event_outbox WHERE published_at IS NULL")
        # Same definition as GET /admin/analytics/sla (5-day dormancy threshold).
        sla_breaches = await v(
            "SELECT count(*) FROM public.applications a "
            "WHERE a.employer_viewed_at IS NULL "
            "AND a.status IN ('submitted', 'reviewed') "
            "AND a.submitted_at < NOW() - INTERVAL '5 days'"
        )
        # Job import work awaiting admin review — the ONE shared definition
        # (app.util.review_queue): submitted batches AND careers-page pulls
        # with staged rows. The queue page and career sources count the same
        # way, so these numbers can never contradict each other.
        from app.util.review_queue import (
            count_awaiting_import_review,
            count_pending_review_items,
        )
        awaiting_imports = await count_awaiting_import_review(conn)
        import_batches_pending = awaiting_imports["batches"]
        import_jobs_pending = awaiting_imports["rows"]
        # Pending review_queue_items (chat guardrail trips, taxonomy
        # mismatches, broken apply links, ...) — the /admin/review feed.
        review_items = await count_pending_review_items(conn)

        return {
            "platform": {
                "users": await v("SELECT count(*) FROM public.user_profiles"),
                "applicants": await v("SELECT count(*) FROM public.applicants"),
                "employers": await v("SELECT count(*) FROM public.employers"),
                "institutions": await v("SELECT count(*) FROM public.institutions"),
                "partners": await v("SELECT count(*) FROM public.api_clients"),
            },
            "acquisition": {
                "new_applicants_7d": await v(f"SELECT count(*) FROM public.applicants WHERE {W7}"),
                "new_applicants_30d": await v(f"SELECT count(*) FROM public.applicants WHERE {W30}"),
                "new_jobs_7d": await v(f"SELECT count(*) FROM public.jobs WHERE {W7}"),
                "new_jobs_30d": await v(f"SELECT count(*) FROM public.jobs WHERE {W30}"),
                "new_credentials_7d": int(cred_agg["new_7d"] or 0),
                "new_credentials_30d": int(cred_agg["new_30d"] or 0),
            },
            "verification": {
                "credentials_total": creds,
                "self_reported": int(cred_agg["self_reported"] or 0),
                "institution_verified": inst,
                "skilled_verified": skilled,
                "verified_rate": round((inst + skilled) / creds * 100, 1) if creds else 0.0,
                "needs_review": int(cred_agg["needs_review"] or 0),
            },
            "consent": {
                "sharing_with_employers": await v(
                    "SELECT count(DISTINCT applicant_id) FROM public.consent_settings WHERE external_sharing ? 'employer'"
                ),
                "total_with_settings": await v("SELECT count(DISTINCT applicant_id) FROM public.consent_settings"),
            },
            "matching": {
                "total": m_total,
                "eligible": int(match_agg["eligible"] or 0),
                "near_fit": int(match_agg["near_fit"] or 0),
                "ineligible": int(match_agg["ineligible"] or 0),
                "avg_fit": round(float(match_agg["avg_fit"]), 1) if match_agg["avg_fit"] is not None else 0.0,
                "strong": int(match_agg["strong"] or 0),
                "applicants_matched": applicants_matched,
            },
            "marketplace": {
                "active_jobs": await v("SELECT count(*) FROM public.jobs WHERE is_active = TRUE"),
                "discoverable_workers": await v(
                    "SELECT count(DISTINCT a.id) FROM public.applicants a "
                    "JOIN public.consent_settings cs ON cs.applicant_id = a.id "
                    "WHERE cs.external_sharing ? 'employer' AND EXISTS ("
                    "  SELECT 1 FROM public.credentials c WHERE c.applicant_id = a.id AND c.verification_level >= 1)"
                ),
                "top_trades": [{"name": r["name"], "count": int(r["c"])} for r in trade_rows],
            },
            "engagement": {
                "total": int(eng_agg["total"] or 0),
                "total_7d": int(eng_agg["total_7d"] or 0),
                # Distinct actors, so the UI can say "N events from M people"
                # instead of implying broad activity that isn't there.
                "active_applicants_7d": int(eng_agg["active_applicants_7d"] or 0),
                "active_employers_7d": int(eng_agg["active_employers_7d"] or 0),
                "active_applicants_total": int(eng_agg["active_applicants_total"] or 0),
                "active_employers_total": int(eng_agg["active_employers_total"] or 0),
                "by_type": [{"type": r["event_type"], "count": int(r["c"]), "last_7d": int(r["c7"])} for r in eng_rows],
            },
            "outcomes": {
                "placements": await v("SELECT count(*) FROM public.hire_outcomes WHERE outcome_type IN ('placed','hired')"),
                "median_wage": int(med_wage) if med_wage is not None else None,
            },
            "skilled_id": {
                "partners": await v("SELECT count(*) FROM public.api_clients"),
                "active": await v("SELECT count(*) FROM public.api_clients WHERE active = TRUE"),
                "queries_total": await v("SELECT count(*) FROM public.api_request_logs"),
                "queries_7d": await v(f"SELECT count(*) FROM public.api_request_logs WHERE {W7}"),
            },
            "sync": {
                "outbox_total": await v("SELECT count(*) FROM public.event_outbox"),
                "outbox_unpublished": await v("SELECT count(*) FROM public.event_outbox WHERE published_at IS NULL"),
                "inbox_applied": await v("SELECT count(*) FROM public.sync_inbox"),
            },
            "funnel": [
                {"key": "learners", "label": "Learners", "count": learners},
                {"key": "credentialed", "label": "Added a credential", "count": with_credential},
                {"key": "verified", "label": "Verified", "count": verified_workers},
                {"key": "discoverable", "label": "Discoverable to employers", "count": discoverable},
                {"key": "matched", "label": "Matched to a job", "count": matched},
                {"key": "interested", "label": "Showed interest", "count": interested},
                {"key": "placed", "label": "Placed", "count": placed},
            ],
            "alerts": {
                "review_queue": review_queue,
                "unmatched_learners": unmatched,
                "jobs_no_candidates": jobs_no_candidates,
                "import_batches_pending": import_batches_pending,
                "import_jobs_pending": import_jobs_pending,
                "sla_breaches": sla_breaches,
                "verified_not_sharing": verified_not_sharing,
                "sync_pending": sync_pending,
                # /admin/review feed — total + per-type so the inbox can name
                # the work ("6 chat guardrail flags"), not just count it.
                "review_items_pending": review_items["total"],
                "review_items_by_type": review_items["by_type"],
            },
        }


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
# Geographic visualization: applicant map + application flows
# ---------------------------------------------------------------------------

class CityApplicantCluster(BaseModel):
    """City-level applicant aggregate — counts only, never individual rows (no PII)."""
    city: str
    state: str
    lat: float
    lng: float
    applicant_count: int


class FlowEndpoint(BaseModel):
    lat: float
    lng: float
    city: str
    state: str


class ApplicationFlow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: FlowEndpoint = Field(alias="from")
    to: FlowEndpoint
    count: int


async def _resolve_city_coords(
    conn, pairs: set[tuple[str, str]],
) -> dict[tuple[str, str], tuple[float, float]]:
    """Resolve (city, state) -> (lat, lng).

    Same mechanism the job map uses: the static `_CITY_COORDS` lookup first,
    then a single batched read of `geocode_cache` (keys normalized the same way
    as app.skilled_pro.geocode: "city, ST"). Never live-geocodes at request
    time — cities with no known coords are simply skipped by callers.
    """
    resolved: dict[tuple[str, str], tuple[float, float]] = {}
    cache_keys: dict[str, tuple[str, str]] = {}
    for city, state in pairs:
        if not city or not state:
            continue
        static_key = f"{city.lower().strip()}, {state.lower().strip()}"
        if static_key in _CITY_COORDS:
            resolved[(city, state)] = _CITY_COORDS[static_key]
        else:
            cache_keys[f"{city.strip().lower()}, {state.strip().upper()[:2]}"] = (city, state)
    if cache_keys:
        rows = await conn.fetch(
            "SELECT query, lat, lng FROM public.geocode_cache WHERE query = ANY($1::text[])",
            list(cache_keys),
        )
        for r in rows:
            pair = cache_keys.get(r["query"])
            if pair and pair not in resolved:
                resolved[pair] = (float(r["lat"]), float(r["lng"]))
    # Last resort: state centroid (same fallback job-map uses via _geocode).
    for city, state in pairs:
        if (city, state) not in resolved and state:
            centroid = _STATE_CENTROIDS.get(state.upper().strip())
            if centroid:
                resolved[(city, state)] = centroid
    return resolved


@router.get("/analytics/applicant-map", response_model=list[CityApplicantCluster])
async def applicant_map_data(user=Depends(require_admin)):
    """Applicant distribution for the admin map. City-level counts only — no PII."""
    async with get_db() as conn:
        rows = await conn.fetch("""
            SELECT city, state, COUNT(*) AS ct
            FROM public.applicants
            WHERE city IS NOT NULL AND state IS NOT NULL
            GROUP BY city, state
            ORDER BY ct DESC
            LIMIT 1000
        """)
        coords = await _resolve_city_coords(conn, {(r["city"], r["state"]) for r in rows})
    return [
        CityApplicantCluster(
            city=r["city"], state=r["state"],
            lat=coords[(r["city"], r["state"])][0],
            lng=coords[(r["city"], r["state"])][1],
            applicant_count=int(r["ct"]),
        )
        for r in rows
        if (r["city"], r["state"]) in coords
    ]


@router.get("/analytics/application-flows", response_model=list[ApplicationFlow])
async def application_flows(user=Depends(require_admin)):
    """Applicant-city -> job-city application flows, aggregated by city pair.

    Signal sources (deduped on applicant+job so one person applying through
    both paths counts once):
      1. public.applications — formal submitted applications (primary source).
      2. public.saved_jobs with interest_level IN ('applied', 'interested') —
         self-reported application/interest signals. Included because the
         applications table is sparse in local/demo environments; 'interested'
         rows are a weaker signal but keep the demo populated. Note the source
         mix here if this view ever drives real decisions.
    """
    async with get_db() as conn:
        rows = await conn.fetch("""
            WITH signals AS (
                SELECT ap.applicant_id, ap.job_id FROM public.applications ap
                UNION
                SELECT sj.applicant_id, sj.job_id
                FROM public.saved_jobs sj
                WHERE sj.interest_level IN ('applied', 'interested')
            )
            SELECT a.city AS from_city, a.state AS from_state,
                   j.city AS to_city, j.state AS to_state,
                   COUNT(*) AS ct
            FROM signals s
            JOIN public.applicants a ON a.id = s.applicant_id
            JOIN public.jobs j ON j.id = s.job_id
            WHERE a.city IS NOT NULL AND a.state IS NOT NULL
              AND j.city IS NOT NULL AND j.state IS NOT NULL
            GROUP BY 1, 2, 3, 4
            ORDER BY ct DESC
            LIMIT 500
        """)
        pairs = {(r["from_city"], r["from_state"]) for r in rows}
        pairs |= {(r["to_city"], r["to_state"]) for r in rows}
        coords = await _resolve_city_coords(conn, pairs)

    flows: list[ApplicationFlow] = []
    for r in rows:
        src = coords.get((r["from_city"], r["from_state"]))
        dst = coords.get((r["to_city"], r["to_state"]))
        if not src or not dst:
            continue  # no cached coords — skip rather than live-geocode
        flows.append(ApplicationFlow(
            from_=FlowEndpoint(lat=src[0], lng=src[1], city=r["from_city"], state=r["from_state"]),
            to=FlowEndpoint(lat=dst[0], lng=dst[1], city=r["to_city"], state=r["to_state"]),
            count=int(r["ct"]),
        ))
    return flows


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
    created_at: str | None = None
    has_career_source: bool = False
    hired_count: int = 0
    outreach_count: int = 0
    last_activity_at: str | None = None


class AdminEmployerFacets(BaseModel):
    """Data-backed option lists for the directory filter bar."""
    industries: list[str] = []
    states: list[str] = []


class AdminEmployerList(BaseModel):
    total: int
    employers: list[AdminEmployerRow]
    facets: AdminEmployerFacets = AdminEmployerFacets()


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
            from fastapi import HTTPException
            from fastapi import status as _status
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
                -- Predicate parity with the employer candidate list: visible
                -- AND eligible/near_fit only, so this count equals what the
                -- candidate page actually lists.
                COUNT(m.id) FILTER (WHERE m.is_visible_to_employer = TRUE AND m.eligibility_status IN ('eligible', 'near_fit')) AS total_visible,
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
            f"(a.first_name ILIKE ${p} OR a.last_name ILIKE ${p} OR a.email ILIKE ${p} "
            f"OR (COALESCE(a.first_name, '') || ' ' || COALESCE(a.last_name, '')) ILIKE ${p})"
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

        # Paginate FIRST, then count matches per returned applicant via a
        # LATERAL probe. The old join-then-GROUP-BY aggregated the entire
        # matches table (130k+ rows, ~300ms seq scan + hash agg) before
        # discarding all but one page; this touches only page_size applicants
        # and uses the (applicant_id, eligibility_status) index. Results are
        # identical — ordering does not depend on the aggregated counts.
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
                -- Completeness computed inline (no stored column). The weights
                -- below sum to 70, so scale to 100 -- rendering the raw sum as a
                -- percentage made 100% unreachable and pinned every fully-filled
                -- profile at 65%.
                ROUND(
                  (
                    CASE WHEN a.first_name IS NOT NULL AND a.last_name IS NOT NULL THEN 10 ELSE 0 END +
                    CASE WHEN a.program_name_raw IS NOT NULL THEN 10 ELSE 0 END +
                    CASE WHEN a.canonical_job_family_id IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN a.state IS NOT NULL THEN 10 ELSE 0 END +
                    CASE WHEN a.city IS NOT NULL THEN 5 ELSE 0 END +
                    CASE WHEN a.available_from_date IS NOT NULL OR a.expected_completion_date IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN a.willing_to_relocate THEN 5 ELSE 0 END
                  ) * 100.0 / 70
                )::int AS profile_completeness,
                a.willing_to_relocate,
                COALESCE(a.available_from_date::text, a.expected_completion_date::text) AS available_from,
                a.job_family_code,
                a.job_family_name,
                mc.eligible_count,
                mc.near_fit_count
            FROM (
                SELECT a.*, jf.code AS job_family_code, jf.name AS job_family_name
                FROM public.applicants a
                LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
                WHERE {where}
                ORDER BY a.last_name NULLS LAST, a.first_name NULLS LAST
                LIMIT ${p} OFFSET ${p + 1}
            ) a
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE m.eligibility_status = 'eligible') AS eligible_count,
                    COUNT(*) FILTER (WHERE m.eligibility_status = 'near_fit') AS near_fit_count
                FROM public.matches m
                WHERE m.applicant_id = a.id
            ) mc ON TRUE
            ORDER BY a.last_name NULLS LAST, a.first_name NULLS LAST
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


# ---------------------------------------------------------------------------
# POST /admin/view-as/{applicant_id}/start — begin a read-only view-as session
# ---------------------------------------------------------------------------

class ViewAsStartResponse(BaseModel):
    applicant_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    has_linked_account: bool


@router.post("/view-as/{applicant_id}/start", response_model=ViewAsStartResponse)
async def start_view_as_applicant(
    applicant_id: UUID,
    user=Depends(require_admin),
):
    """
    Start an admin "view as applicant" debug session (read-only impersonation).

    Writes ONE audit_logs row per session start — the per-request GETs that
    follow (carrying X-View-As-Applicant) are not individually logged.
    Guardrail (CLAUDE.md): all admin overrides are auditable.
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text AS id, user_id::text AS user_id,
                   first_name, last_name, email
            FROM public.applicants
            WHERE id = $1::uuid
            """,
            str(applicant_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Applicant not found")

        has_linked_account = bool(row["user_id"])
        await conn.execute(
            """
            INSERT INTO public.audit_logs
                (actor_id, actor_role, action, entity_type, entity_id, metadata)
            VALUES ($1::uuid, 'admin', 'admin_view_as_applicant', 'applicant', $2::uuid, $3::jsonb)
            """,
            user.user_id,
            str(applicant_id),
            {
                "applicant_email": row["email"],
                "has_linked_account": has_linked_account,
                "mode": "read_only_debug",
            },
        )

    return ViewAsStartResponse(
        applicant_id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        has_linked_account=has_linked_account,
    )


# Job-count bands for the employer directory filter. Expressed as predicates
# over a scalar subquery so the SAME where-clause drives count + list (parity).
_EMPLOYER_JOBS_EXPR = "(SELECT COUNT(*) FROM public.jobs jb WHERE jb.employer_id = e.id)"
_EMPLOYER_JOBS_BANDS = {
    "none": f"{_EMPLOYER_JOBS_EXPR} = 0",
    "1_10": f"{_EMPLOYER_JOBS_EXPR} BETWEEN 1 AND 10",
    "11_100": f"{_EMPLOYER_JOBS_EXPR} BETWEEN 11 AND 100",
    "over_100": f"{_EMPLOYER_JOBS_EXPR} > 100",
}

# Most-recent touch on the employer record: newest job, outreach, or hire
# report (falls back to the row's own updated_at). GREATEST ignores NULLs.
_EMPLOYER_LAST_ACTIVITY = """
GREATEST(
    e.updated_at,
    (SELECT MAX(jx.created_at) FROM public.jobs jx WHERE jx.employer_id = e.id),
    (SELECT MAX(ox.created_at) FROM public.employer_outreach ox WHERE ox.employer_id = e.id),
    (SELECT MAX(hx.created_at) FROM public.hire_outcomes hx WHERE hx.employer_id = e.id)
)
"""


@router.get("/employers", response_model=AdminEmployerList)
async def list_employers(
    q: str | None = Query(None, description="Search by company name"),
    state: str | None = Query(None, description="Single state (back-compat; prefer states)"),
    states: str | None = Query(None, description="Comma-separated state codes (multi-select)"),
    industry: str | None = Query(None, description="Comma-separated industries (multi-select)"),
    is_partner: bool | None = Query(None),
    has_active_jobs: bool | None = Query(None),
    jobs_band: str | None = Query(None, description="Total-jobs band: none | 1_10 | 11_100 | over_100"),
    has_hired: bool | None = Query(None, description="Has at least one reported hire"),
    has_outreach: bool | None = Query(None, description="Has sent at least one outreach"),
    has_career_source: bool | None = Query(None, description="Careers-page source connected"),
    created_from: str | None = Query(None, description="Added on/after YYYY-MM-DD"),
    created_to: str | None = Query(None, description="Added on/before YYYY-MM-DD"),
    sort: str = Query("name", description="name | jobs | recent"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    """List all employers with granular, composable filtering for the directory."""
    offset = (page - 1) * page_size

    conditions = ["1=1"]
    params: list[Any] = []

    def bind(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    if q:
        conditions.append(f"e.name ILIKE {bind(f'%{q}%')}")
    state_list = csv_values(states, upper=True) or ([state.upper()] if state else [])
    if state_list:
        conditions.append(f"e.state = ANY({bind(state_list)}::text[])")
    industry_list = csv_values(industry)
    if industry_list:
        conditions.append(f"TRIM(e.industry) = ANY({bind(industry_list)}::text[])")
    if is_partner is not None:
        conditions.append(f"e.is_partner = {bind(is_partner)}")
    if has_active_jobs is not None:
        pred = "EXISTS (SELECT 1 FROM public.jobs ja WHERE ja.employer_id = e.id AND ja.is_active = TRUE)"
        conditions.append(pred if has_active_jobs else f"NOT {pred}")
    if jobs_band:
        band = _EMPLOYER_JOBS_BANDS.get(jobs_band)
        if band is None:
            raise HTTPException(422, f"jobs_band must be one of: {', '.join(_EMPLOYER_JOBS_BANDS)}")
        conditions.append(band)
    if has_hired is not None:
        pred = ("EXISTS (SELECT 1 FROM public.hire_outcomes h "
                "WHERE h.employer_id = e.id AND h.outcome_type = 'hired')")
        conditions.append(pred if has_hired else f"NOT {pred}")
    if has_outreach is not None:
        pred = "EXISTS (SELECT 1 FROM public.employer_outreach o WHERE o.employer_id = e.id)"
        conditions.append(pred if has_outreach else f"NOT {pred}")
    if has_career_source is not None:
        pred = "EXISTS (SELECT 1 FROM public.employer_career_sources cs WHERE cs.employer_id = e.id)"
        conditions.append(pred if has_career_source else f"NOT {pred}")
    d_from = parse_iso_date(created_from, "created_from")
    if d_from:
        conditions.append(f"e.created_at >= {bind(d_from)}")
    d_to = parse_iso_date(created_to, "created_to")
    if d_to:
        conditions.append(f"e.created_at < {bind(d_to)} + INTERVAL '1 day'")

    where = " AND ".join(conditions)

    order_by = {
        "name": "e.name",
        "jobs": "total_jobs DESC, e.name",
        "recent": "last_activity_at DESC NULLS LAST, e.name",
    }.get(sort)
    if order_by is None:
        raise HTTPException(422, "sort must be one of: name, jobs, recent")

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
                e.created_at::text AS created_at,
                COUNT(DISTINCT j.id) FILTER (WHERE j.is_active = TRUE) AS active_jobs,
                COUNT(DISTINCT j.id) AS total_jobs,
                EXISTS (SELECT 1 FROM public.employer_career_sources cs
                        WHERE cs.employer_id = e.id) AS has_career_source,
                (SELECT COUNT(*) FROM public.hire_outcomes h
                 WHERE h.employer_id = e.id AND h.outcome_type = 'hired') AS hired_count,
                (SELECT COUNT(*) FROM public.employer_outreach o
                 WHERE o.employer_id = e.id) AS outreach_count,
                {_EMPLOYER_LAST_ACTIVITY}::text AS last_activity_at,
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
            ORDER BY {order_by}
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, page_size, offset,
        )

        # Facets — data-backed dropdown options over the whole directory
        # (unfiltered on purpose: options must not vanish as you narrow).
        industry_rows = await conn.fetch(
            "SELECT DISTINCT TRIM(industry) AS v FROM public.employers "
            "WHERE industry IS NOT NULL AND TRIM(industry) <> '' ORDER BY 1"
        )
        state_rows = await conn.fetch(
            "SELECT DISTINCT UPPER(TRIM(state)) AS v FROM public.employers "
            "WHERE state IS NOT NULL AND TRIM(state) <> '' ORDER BY 1"
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
            created_at=r["created_at"],
            has_career_source=bool(r["has_career_source"]),
            hired_count=int(r["hired_count"] or 0),
            outreach_count=int(r["outreach_count"] or 0),
            last_activity_at=r["last_activity_at"],
        )
        for r in rows
    ]
    return AdminEmployerList(
        total=total,
        employers=employers,
        facets=AdminEmployerFacets(
            industries=[r["v"] for r in industry_rows],
            states=[r["v"] for r in state_rows],
        ),
    )


# ---------------------------------------------------------------------------
# GET /admin/search — combined typeahead search for the admin top bar
# ---------------------------------------------------------------------------

class AdminSearchRow(BaseModel):
    id: str
    label: str
    subtitle: str | None = None
    href: str


class AdminSearchResponse(BaseModel):
    applicants: list[AdminSearchRow]
    employers: list[AdminSearchRow]
    credentials: list[AdminSearchRow]


@router.get("/search", response_model=AdminSearchResponse)
async def admin_search(
    q: str = Query(..., min_length=1, max_length=120, description="Partial name / email / title"),
    limit: int = Query(5, ge=1, le=10),
    user=Depends(require_admin),
):
    """
    Live type-ahead search across applicants, employers, and credentials.

    Case-insensitive partial matching (ILIKE %q%) on names, emails, company
    names, and credential titles. Each group is capped at `limit` rows so the
    dropdown stays scannable.
    """
    like = f"%{q.strip()}%"
    # Prefix matches rank first (Google-style: "ge" puts "GE Vernova" above
    # "Schneider — Georgia plant"); substring matches follow alphabetically.
    prefix = f"{q.strip()}%"

    async with get_db() as conn:
        applicant_rows = await conn.fetch(
            """
            SELECT a.id::text, a.first_name, a.last_name, a.email, a.city, a.state::text
            FROM public.applicants a
            WHERE a.first_name ILIKE $1 OR a.last_name ILIKE $1 OR a.email ILIKE $1
               OR (COALESCE(a.first_name, '') || ' ' || COALESCE(a.last_name, '')) ILIKE $1
            ORDER BY (a.first_name ILIKE $3 OR a.last_name ILIKE $3 OR a.email ILIKE $3) DESC,
                     a.last_name NULLS LAST, a.first_name NULLS LAST
            LIMIT $2
            """,
            like, limit, prefix,
        )
        employer_rows = await conn.fetch(
            """
            SELECT e.id::text, e.name, e.industry, e.city, e.state::text,
                   e.created_at,
                   (SELECT count(*) FROM public.jobs j
                     WHERE j.employer_id = e.id AND j.is_active = TRUE) AS job_count
            FROM public.employers e
            WHERE e.name ILIKE $1
            ORDER BY (e.name ILIKE $3) DESC, e.name
            LIMIT $2
            """,
            like, limit, prefix,
        )
        credential_rows = await conn.fetch(
            """
            SELECT c.id::text,
                   COALESCE(c.canonical_name, c.raw_name) AS name,
                   c.issuer,
                   a.first_name, a.last_name, a.email
            FROM public.credentials c
            JOIN public.applicants a ON a.id = c.applicant_id
            WHERE c.canonical_name ILIKE $1 OR c.raw_name ILIKE $1 OR c.issuer ILIKE $1
            ORDER BY (COALESCE(c.canonical_name, c.raw_name) ILIKE $3) DESC,
                     COALESCE(c.canonical_name, c.raw_name)
            LIMIT $2
            """,
            like, limit, prefix,
        )

    def _person(first: Any, last: Any, email: Any) -> str:
        return " ".join(s for s in (first, last) if s) or (email or "Unnamed")

    applicants = [
        AdminSearchRow(
            id=r["id"],
            label=_person(r["first_name"], r["last_name"], r["email"]),
            subtitle=", ".join(
                s for s in (r["email"], ", ".join(p for p in (r["city"], r["state"]) if p)) if s
            ) or None,
            href=f"/admin/applicants?q={quote_plus(r['email'] or _person(r['first_name'], r['last_name'], r['email']))}",
        )
        for r in applicant_rows
    ]
    # Secondary line disambiguates same-name rows: job count + created year
    # + id suffix, so "Ford" vs "Ford" is decidable from the dropdown.
    def _employer_subtitle(r: Any) -> str | None:
        keys = tuple(r.keys())
        job_count = int(r["job_count"] or 0) if "job_count" in keys else None
        created = r["created_at"] if "created_at" in keys else None
        bits = [
            r["industry"],
            ", ".join(p for p in (r["city"], r["state"]) if p) or None,
            f"{job_count} open job{'s' if job_count != 1 else ''}" if job_count is not None else None,
            f"since {created.year}" if created else None,
            f"id {r['id'][:8]}",
        ]
        return " · ".join(s for s in bits if s) or None

    employers = [
        AdminSearchRow(
            id=r["id"],
            label=r["name"],
            subtitle=_employer_subtitle(r),
            href=f"/admin/employers/{r['id']}",
        )
        for r in employer_rows
    ]
    credentials = [
        AdminSearchRow(
            id=r["id"],
            label=r["name"] or "Untitled credential",
            subtitle=", ".join(
                s for s in (r["issuer"], _person(r["first_name"], r["last_name"], r["email"])) if s
            ) or None,
            href=f"/admin/applicants?q={quote_plus(r['email'] or _person(r['first_name'], r['last_name'], r['email']))}",
        )
        for r in credential_rows
    ]
    return AdminSearchResponse(applicants=applicants, employers=employers, credentials=credentials)


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
    # How many of `total` have ANY recorded engagement event — the honest
    # denominator sentence for a population-heavy, activity-sparse platform.
    active_total: int = 0
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
        name_filter = (
            "WHERE (a.first_name ILIKE $1 OR a.last_name ILIKE $1 "
            "OR (COALESCE(a.first_name, '') || ' ' || COALESCE(a.last_name, '')) ILIKE $1)"
        )
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

        # Same population + name filter, restricted to applicants with at
        # least one engagement event (matches the LEFT JOIN counted below).
        active_total = await conn.fetchval(
            f"""
            SELECT COUNT(DISTINCT a.id)
            FROM public.applicants a
            JOIN public.engagement_events ee ON ee.applicant_id = a.id
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
        active_total=int(active_total or 0),
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
    # How many of `total` have ANY recorded action (outreach, DM,
    # candidate view, or hire) — denominator for the takeaway sentence.
    active_total: int = 0
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

        # Employers with ANY of the four counted actions — the same source
        # predicates as the lateral aggregates below.
        active_filter = "AND" if name_filter else "WHERE"
        active_total = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM public.employers e
            {name_filter}
            {active_filter} (
                EXISTS (SELECT 1 FROM public.employer_outreach o
                        WHERE o.employer_id = e.id AND o.status = 'sent')
                OR EXISTS (SELECT 1 FROM public.engagement_events ev
                           WHERE ev.employer_id = e.id
                             AND (ev.event_type = 'candidate_viewed'
                                  OR (ev.event_type = 'dm_sent'
                                      AND (ev.event_data->>'sender_role') = 'employer')))
                OR EXISTS (SELECT 1 FROM public.hire_outcomes h
                           WHERE h.employer_id = e.id)
            )
            """,
            *params_base,
        )

        # Each source table is aggregated in its OWN lateral before joining.
        # Joining three one-to-many tables simultaneously multiplies rows
        # (3 outreach × 2 hires = every event counted 6×), which silently
        # inflated dms_sent / candidates_viewed here before.
        rows = await conn.fetch(
            f"""
            SELECT
                e.id::text AS employer_id,
                e.name,
                COALESCE(eo.n, 0)  AS outreach_sent,
                COALESCE(ee.dms, 0)   AS dms_sent,
                COALESCE(ho.n, 0)  AS hires_reported,
                COALESCE(ee.views, 0) AS candidates_viewed,
                (COALESCE(eo.n, 0) + COALESCE(ee.dms, 0)
                 + COALESCE(ho.n, 0) + COALESCE(ee.views, 0)) AS total_actions
            FROM public.employers e
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS n FROM public.employer_outreach o
                WHERE o.employer_id = e.id AND o.status = 'sent'
            ) eo ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE ev.event_type = 'dm_sent'
                        AND (ev.event_data->>'sender_role') = 'employer') AS dms,
                    COUNT(*) FILTER (WHERE ev.event_type = 'candidate_viewed') AS views
                FROM public.engagement_events ev
                WHERE ev.employer_id = e.id
            ) ee ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS n FROM public.hire_outcomes h
                WHERE h.employer_id = e.id
            ) ho ON TRUE
            {name_filter}
            ORDER BY {sort_col} DESC NULLS LAST, e.name
            LIMIT ${p} OFFSET ${p + 1}
            """,
            *params_base, page_size, offset,
        )

    return EmployerEngagementList(
        total=int(total or 0),
        active_total=int(active_total or 0),
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


# ---------------------------------------------------------------------------
# GET /admin/analytics/engagement/summary
# The single aggregate endpoint for the redesigned engagement page.
# Returns everything: north-star metric with 12-week sparkline, AARRR-style
# supporting metrics, activation funnels for both sides, cohort retention
# curve for applicants, and time-to-hire percentiles.
# ---------------------------------------------------------------------------


class SparklinePoint(BaseModel):
    label: str          # ISO week-start date "YYYY-MM-DD"
    value: float


class NorthStar(BaseModel):
    value: int          # verified hires in last 30 days
    prev_value: int     # previous 30 days, for delta arrow
    all_time: int
    spark: list[SparklinePoint]  # 12 weeks of hires


class LensMetric(BaseModel):
    lens: str           # "acquisition" | "activation" | "engagement" | "retention" | "conversion"
    label: str
    value: str          # display string ("48", "62%", "3.2d")
    detail: str         # "vs 41 last 30d" or similar
    trend: float | None # signed % change; null if no baseline


class FunnelStep(BaseModel):
    label: str
    count: int
    pct_of_top: float   # 0.0 – 1.0


class RetentionCohort(BaseModel):
    week_offset: int    # 0 = signup week, 1 = week after, ...
    pct_returning: float
    n_users: int


class TimeToHire(BaseModel):
    p50_days: float | None
    p90_days: float | None
    sample_size: int


class ResponseSLA(BaseModel):
    median_hours: float | None
    p90_hours: float | None
    sample_size: int


class EngagementSummary(BaseModel):
    generated_at: str
    north_star: NorthStar
    lenses: list[LensMetric]
    applicant_funnel: list[FunnelStep]
    employer_funnel: list[FunnelStep]
    retention: list[RetentionCohort]
    time_to_hire: TimeToHire
    employer_response: ResponseSLA


@router.get("/analytics/engagement/summary", response_model=EngagementSummary)
async def engagement_summary(user=Depends(require_admin)):
    """
    Aggregate engagement snapshot for the admin engagement page.

    North star = Verified hires in last 30 days. Everything else supports
    that: acquisition, activation, engagement, retention, conversion, plus
    the two activation funnels and cohort retention curve.
    """
    from datetime import datetime, timezone

    async with get_db() as conn:
        # -------- North star: verified hires ----------
        ns_30 = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes "
            "WHERE outcome_type = 'hired' AND created_at > NOW() - INTERVAL '30 days'"
        ) or 0
        ns_prev = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes "
            "WHERE outcome_type = 'hired' "
            "AND created_at > NOW() - INTERVAL '60 days' "
            "AND created_at <= NOW() - INTERVAL '30 days'"
        ) or 0
        ns_all = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes WHERE outcome_type = 'hired'"
        ) or 0

        # 12-week sparkline of hires
        spark_rows = await conn.fetch(
            """
            SELECT
              date_trunc('week', gs)::date AS wk,
              COALESCE((
                SELECT COUNT(*) FROM public.hire_outcomes ho
                WHERE ho.outcome_type = 'hired'
                  AND ho.created_at >= date_trunc('week', gs)
                  AND ho.created_at <  date_trunc('week', gs) + INTERVAL '7 days'
              ), 0) AS n
            FROM generate_series(
              date_trunc('week', NOW() - INTERVAL '11 weeks'),
              date_trunc('week', NOW()),
              INTERVAL '1 week'
            ) AS gs
            ORDER BY wk
            """
        )
        spark = [SparklinePoint(label=r["wk"].isoformat(), value=float(r["n"])) for r in spark_rows]

        # -------- Supporting lenses (AARRR-flavoured, marketplace-tuned) ----------
        # Acquisition — new applicants + new employer contacts last 30d
        new_applicants_30 = await conn.fetchval(
            "SELECT COUNT(*) FROM public.applicants WHERE created_at > NOW() - INTERVAL '30 days'"
        ) or 0
        new_applicants_prev = await conn.fetchval(
            "SELECT COUNT(*) FROM public.applicants "
            "WHERE created_at > NOW() - INTERVAL '60 days' "
            "AND created_at <= NOW() - INTERVAL '30 days'"
        ) or 0

        # Activation — % of applicants (created last 30d) whose profile is complete
        act_num = await conn.fetchval(
            "SELECT COUNT(*) FROM public.applicants "
            "WHERE created_at > NOW() - INTERVAL '30 days' "
            "AND onboarding_complete = TRUE"
        ) or 0
        act_pct = (act_num / new_applicants_30 * 100) if new_applicants_30 > 0 else 0.0

        # Engagement — active applicants (any engagement event) last 7d
        active_7d = await conn.fetchval(
            "SELECT COUNT(DISTINCT applicant_id) FROM public.engagement_events "
            "WHERE created_at > NOW() - INTERVAL '7 days' AND applicant_id IS NOT NULL"
        ) or 0
        active_prev_7d = await conn.fetchval(
            "SELECT COUNT(DISTINCT applicant_id) FROM public.engagement_events "
            "WHERE created_at > NOW() - INTERVAL '14 days' "
            "AND created_at <= NOW() - INTERVAL '7 days' "
            "AND applicant_id IS NOT NULL"
        ) or 0

        # Employer activation — % of employers who posted a job AND reviewed at least one applicant
        emp_activated = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT e.id)
            FROM public.employers e
            JOIN public.jobs j ON j.employer_id = e.id
            JOIN public.engagement_events ee ON ee.employer_id = e.id
              AND ee.event_type = 'candidate_viewed'
            """
        ) or 0
        emp_with_jobs = await conn.fetchval(
            "SELECT COUNT(DISTINCT employer_id) FROM public.jobs WHERE employer_id IS NOT NULL"
        ) or 0
        emp_act_pct = (emp_activated / emp_with_jobs * 100) if emp_with_jobs > 0 else 0.0

        # Match-to-apply conversion — share of applicants who viewed a match in
        # the last 30d that also clicked apply in that window. Applicant-level
        # subset ratio, so it is bounded at 100% by construction. (Raw event
        # ratio apply_clicks/match_views could exceed 100% — one view, many
        # applies — which is meaningless as a "conversion".)
        conv_row = await conn.fetchrow(
            """
            WITH viewers AS (
                SELECT DISTINCT applicant_id
                FROM public.engagement_events
                WHERE event_type = 'match_view' AND applicant_id IS NOT NULL
                  AND created_at > NOW() - INTERVAL '30 days'
            )
            SELECT
                (SELECT COUNT(*) FROM viewers) AS viewers,
                (SELECT COUNT(*) FROM viewers v
                  WHERE EXISTS (
                    SELECT 1 FROM public.engagement_events ee
                    WHERE ee.event_type = 'apply_click'
                      AND ee.applicant_id = v.applicant_id
                      AND ee.created_at > NOW() - INTERVAL '30 days'
                  )) AS converters
            """
        )
        m_views = int(conv_row["viewers"] or 0)
        m_applies = int(conv_row["converters"] or 0)
        m_conv_pct = (m_applies / m_views * 100) if m_views > 0 else 0.0

        def pct_delta(a: int, b: int) -> float | None:
            if b == 0:
                return None
            return (a - b) / b * 100.0

        lenses = [
            LensMetric(
                lens="acquisition",
                label="New applicants (30d)",
                value=str(new_applicants_30),
                detail=f"vs {new_applicants_prev} prior 30d",
                trend=pct_delta(new_applicants_30, new_applicants_prev),
            ),
            LensMetric(
                lens="activation",
                label="Applicant activation rate",
                value=f"{act_pct:.0f}%",
                detail=f"{act_num} of {new_applicants_30} new signups complete profile",
                trend=None,
            ),
            LensMetric(
                lens="activation",
                label="Employer activation rate",
                value=f"{emp_act_pct:.0f}%",
                detail=f"{emp_activated} of {emp_with_jobs} posted-a-job employers reviewed candidates",
                trend=None,
            ),
            LensMetric(
                lens="engagement",
                label="Weekly active applicants",
                value=str(active_7d),
                detail=f"vs {active_prev_7d} prior week",
                trend=pct_delta(active_7d, active_prev_7d),
            ),
            LensMetric(
                lens="conversion",
                label="Match to apply",
                value=f"{m_conv_pct:.0f}%",
                detail=f"{m_applies} of {m_views} match viewers clicked apply (30d)",
                trend=None,
            ),
        ]

        # -------- Applicant activation funnel ----------
        # Cumulative subsets: every stage requires all previous stages, so the
        # funnel is monotonically non-increasing (an applicant who applied
        # without a complete profile is off-path and must not widen a later
        # stage past an earlier one).
        af = await conn.fetchrow(
            """
            WITH s AS (
                SELECT a.id,
                    a.onboarding_complete AS complete,
                    EXISTS (SELECT 1 FROM public.engagement_events ee
                            WHERE ee.applicant_id = a.id
                              AND ee.event_type = 'match_view') AS viewed,
                    EXISTS (SELECT 1 FROM public.engagement_events ee
                            WHERE ee.applicant_id = a.id
                              AND ee.event_type = 'apply_click') AS applied,
                    EXISTS (SELECT 1 FROM public.conversations c
                            JOIN public.direct_messages dm ON dm.conversation_id = c.id
                            WHERE c.applicant_id = a.id
                              AND dm.sender_role = 'employer') AS got_reply
                FROM public.applicants a
            )
            SELECT
                COUNT(*) AS signed_up,
                COUNT(*) FILTER (WHERE complete) AS complete,
                COUNT(*) FILTER (WHERE complete AND viewed) AS viewed,
                COUNT(*) FILTER (WHERE complete AND viewed AND applied) AS applied,
                COUNT(*) FILTER (WHERE complete AND viewed AND applied
                                   AND got_reply) AS got_reply
            FROM s
            """
        )
        total_applicants = int(af["signed_up"] or 0)
        complete_profiles = int(af["complete"] or 0)
        viewed_match = int(af["viewed"] or 0)
        applied = int(af["applied"] or 0)
        got_response = int(af["got_reply"] or 0)

        def steps(pairs: list[tuple[str, int]]) -> list[FunnelStep]:
            top = pairs[0][1] if pairs and pairs[0][1] > 0 else 0
            return [
                FunnelStep(
                    label=label,
                    count=count,
                    pct_of_top=(count / top) if top > 0 else 0.0,
                )
                for label, count in pairs
            ]

        applicant_funnel = steps([
            ("Signed up", total_applicants),
            ("Profile complete", complete_profiles),
            ("Viewed a match", viewed_match),
            ("Clicked apply", applied),
            ("Got employer reply", got_response),
        ])

        # -------- Employer activation funnel ----------
        # Cumulative subsets, same rationale as the applicant funnel: seeded
        # employers with jobs but no login account must not make "Posted first
        # job" wider than "Account created".
        ef = await conn.fetchrow(
            """
            WITH s AS (
                SELECT e.id,
                    EXISTS (SELECT 1 FROM public.employer_contacts ec
                            WHERE ec.employer_id = e.id) AS has_contact,
                    EXISTS (SELECT 1 FROM public.jobs j
                            WHERE j.employer_id = e.id) AS posted,
                    EXISTS (SELECT 1 FROM public.engagement_events ee
                            WHERE ee.employer_id = e.id
                              AND ee.event_type = 'candidate_viewed') AS reviewed,
                    EXISTS (SELECT 1 FROM public.hire_outcomes ho
                            WHERE ho.employer_id = e.id
                              AND ho.outcome_type = 'hired') AS hired
                FROM public.employers e
            )
            SELECT
                COUNT(*) AS onboarded,
                COUNT(*) FILTER (WHERE has_contact) AS has_contact,
                COUNT(*) FILTER (WHERE has_contact AND posted) AS posted,
                COUNT(*) FILTER (WHERE has_contact AND posted AND reviewed) AS reviewed,
                COUNT(*) FILTER (WHERE has_contact AND posted AND reviewed
                                   AND hired) AS hired
            FROM s
            """
        )
        total_employers = int(ef["onboarded"] or 0)
        emp_with_contact = int(ef["has_contact"] or 0)
        emp_posted_job = int(ef["posted"] or 0)
        emp_viewed_applicant = int(ef["reviewed"] or 0)
        emp_hired = int(ef["hired"] or 0)

        employer_funnel = steps([
            ("Onboarded", total_employers),
            ("Account created", emp_with_contact),
            ("Posted first job", emp_posted_job),
            ("Reviewed applicants", emp_viewed_applicant),
            ("Reported first hire", emp_hired),
        ])

        # -------- Applicant cohort retention (weeks since signup) ----------
        retention_rows = await conn.fetch(
            """
            WITH cohort AS (
              SELECT a.id, date_trunc('week', a.created_at) AS signup_wk
              FROM public.applicants a
              WHERE a.created_at > NOW() - INTERVAL '84 days'
            ),
            active AS (
              SELECT DISTINCT
                ee.applicant_id,
                date_trunc('week', ee.created_at) AS active_wk
              FROM public.engagement_events ee
              WHERE ee.applicant_id IS NOT NULL
                AND ee.created_at > NOW() - INTERVAL '84 days'
            )
            SELECT
              wk_off AS week_offset,
              COUNT(DISTINCT c.id) FILTER (WHERE c.id IS NOT NULL) AS n_users,
              COUNT(DISTINCT c.id) FILTER (WHERE a.applicant_id IS NOT NULL) AS n_active
            FROM generate_series(0, 8) AS wk_off
            LEFT JOIN cohort c ON c.signup_wk + (wk_off || ' weeks')::INTERVAL <= NOW()
            LEFT JOIN active a
              ON a.applicant_id = c.id
             AND a.active_wk = c.signup_wk + (wk_off || ' weeks')::INTERVAL
            GROUP BY wk_off
            ORDER BY wk_off
            """
        )
        retention = [
            RetentionCohort(
                week_offset=int(r["week_offset"]),
                n_users=int(r["n_users"] or 0),
                pct_returning=(
                    float(r["n_active"] or 0) / float(r["n_users"])
                    if r["n_users"] else 0.0
                ),
            )
            for r in retention_rows
        ]

        # -------- Time to hire percentiles ----------
        tth_rows = await conn.fetch(
            """
            SELECT EXTRACT(EPOCH FROM (ho.created_at - a.created_at)) / 86400.0 AS days
            FROM public.hire_outcomes ho
            JOIN public.applicants a ON a.id = ho.applicant_id
            WHERE ho.outcome_type = 'hired'
              AND ho.created_at > a.created_at
            """
        )
        days = sorted([float(r["days"]) for r in tth_rows if r["days"] is not None])

        def pct(vals: list[float], q: float) -> float | None:
            if not vals:
                return None
            k = int(round((len(vals) - 1) * q))
            return vals[k]

        time_to_hire = TimeToHire(
            p50_days=pct(days, 0.5),
            p90_days=pct(days, 0.9),
            sample_size=len(days),
        )

        # -------- Employer response SLA (median hours from applicant DM → employer reply) ----------
        sla_rows = await conn.fetch(
            """
            WITH first_applicant AS (
              SELECT conversation_id, MIN(created_at) AS applicant_at
              FROM public.direct_messages
              WHERE sender_role = 'applicant'
              GROUP BY conversation_id
            ),
            first_employer AS (
              SELECT conversation_id, MIN(created_at) AS employer_at
              FROM public.direct_messages
              WHERE sender_role = 'employer'
              GROUP BY conversation_id
            )
            SELECT EXTRACT(EPOCH FROM (fe.employer_at - fa.applicant_at)) / 3600.0 AS hours
            FROM first_applicant fa
            JOIN first_employer fe ON fe.conversation_id = fa.conversation_id
            WHERE fe.employer_at > fa.applicant_at
            """
        )
        hours = sorted([float(r["hours"]) for r in sla_rows if r["hours"] is not None])
        response_sla = ResponseSLA(
            median_hours=pct(hours, 0.5),
            p90_hours=pct(hours, 0.9),
            sample_size=len(hours),
        )

    return EngagementSummary(
        generated_at=datetime.now(timezone.utc).isoformat(),
        north_star=NorthStar(
            value=int(ns_30),
            prev_value=int(ns_prev),
            all_time=int(ns_all),
            spark=spark,
        ),
        lenses=lenses,
        applicant_funnel=applicant_funnel,
        employer_funnel=employer_funnel,
        retention=retention,
        time_to_hire=time_to_hire,
        employer_response=response_sla,
    )


# ---------------------------------------------------------------------------
# Test mode: applicant switcher (for development & QA)
# ---------------------------------------------------------------------------

class TestApplicantListItem(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    state: str | None
    program: str | None
    family_code: str | None
    eligible_count: int
    near_fit_count: int


@router.get("/test/applicants", response_model=list[TestApplicantListItem])
async def list_all_applicants_for_test(user=Depends(require_admin)):
    """List all applicants with match counts for the test switcher dropdown."""
    async with get_db() as conn:
        rows = await conn.fetch("""
            SELECT
                a.id::text,
                a.first_name,
                a.last_name,
                a.state,
                a.program_name_raw,
                jf.code AS family_code,
                COUNT(*) FILTER (WHERE m.eligibility_status = 'eligible') AS eligible_count,
                COUNT(*) FILTER (WHERE m.eligibility_status = 'near_fit') AS near_fit_count
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            LEFT JOIN public.matches m ON m.applicant_id = a.id
            GROUP BY a.id, a.first_name, a.last_name, a.state, a.program_name_raw, jf.code
            ORDER BY a.first_name, a.last_name
        """)

    return [
        TestApplicantListItem(
            id=r["id"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            state=r["state"],
            program=r["program_name_raw"],
            family_code=r["family_code"],
            eligible_count=int(r["eligible_count"] or 0),
            near_fit_count=int(r["near_fit_count"] or 0),
        )
        for r in rows
    ]


class TestApplicantProfile(BaseModel):
    applicant_id: str
    first_name: str | None
    last_name: str | None
    program: str | None
    family_code: str | None
    city: str | None
    state: str | None
    region: str | None
    expected_completion_date: str | None
    travel_preference: str | None
    relocation_preference: str | None


class TestMatchSummary(BaseModel):
    match_id: str
    job_id: str
    job_title: str
    employer_name: str
    job_city: str | None
    job_state: str | None
    work_setting: str | None
    eligibility_status: str
    match_label: str | None
    policy_adjusted_score: float | None
    top_strengths: list[str]
    top_gaps: list[str]
    recommended_next_step: str | None
    source_url: str | None
    family_code: str | None
    description_raw: str | None
    requirements_raw: str | None
    experience_level: str | None
    confidence_level: str | None


class TestApplicantMatches(BaseModel):
    profile: TestApplicantProfile
    eligible_matches: list[TestMatchSummary]
    near_fit_matches: list[TestMatchSummary]
    total_eligible: int
    total_near_fit: int


@router.get("/test/applicants/{applicant_id}/matches", response_model=TestApplicantMatches)
async def get_test_applicant_matches(
    applicant_id: str,
    user=Depends(require_admin),
):
    """Fetch profile + matches for any applicant (admin test mode)."""
    async with get_db() as conn:
        profile = await conn.fetchrow("""
            SELECT
                a.id::text, a.first_name, a.last_name,
                a.program_name_raw, a.city, a.state, a.region,
                a.expected_completion_date::text,
                a.travel_preference::text, a.relocation_preference::text,
                jf.code AS family_code
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            WHERE a.id = $1::uuid
        """, applicant_id)

        if not profile:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Applicant not found")

        rows = await conn.fetch("""
            SELECT
                m.id::text AS match_id,
                m.job_id::text,
                COALESCE(j.title_normalized, j.title_raw) AS job_title,
                e.name AS employer_name,
                j.city AS job_city, j.state AS job_state,
                j.work_setting::text,
                m.eligibility_status::text,
                m.match_label::text,
                m.policy_adjusted_score,
                m.top_strengths, m.top_gaps,
                m.recommended_next_step,
                j.source_url,
                jf.code AS family_code,
                j.description_raw, j.requirements_raw,
                j.experience_level::text,
                m.confidence_level::text
            FROM public.matches m
            JOIN public.jobs j ON j.id = m.job_id
            JOIN public.employers e ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE m.applicant_id = $1::uuid
              AND m.eligibility_status IN ('eligible', 'near_fit')
            ORDER BY m.policy_adjusted_score DESC NULLS LAST
            LIMIT 100
        """, applicant_id)

    prof = TestApplicantProfile(
        applicant_id=str(profile["id"]),
        first_name=profile["first_name"],
        last_name=profile["last_name"],
        program=profile["program_name_raw"],
        family_code=profile["family_code"],
        city=profile["city"],
        state=profile["state"],
        region=profile["region"],
        expected_completion_date=profile["expected_completion_date"],
        travel_preference=profile["travel_preference"],
        relocation_preference=profile["relocation_preference"],
    )

    def _to_match(r: Any) -> TestMatchSummary:
        return TestMatchSummary(
            match_id=r["match_id"],
            job_id=r["job_id"],
            job_title=r["job_title"] or "Untitled",
            employer_name=r["employer_name"] or "Unknown",
            job_city=r["job_city"],
            job_state=r["job_state"],
            work_setting=r["work_setting"],
            eligibility_status=r["eligibility_status"],
            match_label=r["match_label"],
            policy_adjusted_score=float(r["policy_adjusted_score"]) if r["policy_adjusted_score"] else None,
            top_strengths=r["top_strengths"] or [],
            top_gaps=r["top_gaps"] or [],
            recommended_next_step=r["recommended_next_step"],
            source_url=r["source_url"],
            family_code=r["family_code"],
            description_raw=r["description_raw"],
            requirements_raw=r["requirements_raw"],
            experience_level=r["experience_level"],
            confidence_level=r["confidence_level"],
        )

    eligible = [_to_match(r) for r in rows if r["eligibility_status"] == "eligible"]
    near_fit = [_to_match(r) for r in rows if r["eligibility_status"] == "near_fit"]

    return TestApplicantMatches(
        profile=prof,
        eligible_matches=eligible,
        near_fit_matches=near_fit,
        total_eligible=len(eligible),
        total_near_fit=len(near_fit),
    )
