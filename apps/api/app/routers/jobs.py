"""
jobs.py — Public job browsing endpoint.

Provides a paginated, filterable list of all active jobs for applicants
to browse. Includes both manually created and scraped job postings.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependencies import require_authenticated
from app.db import get_db
from app.skilled_pro.job_sections import (
    compute_content_hash,
    llm_reorganize_sections,
    parse_job_sections,
)
from app.util.cache import cache_key, cached_json
from app.util.geo import haversine_sql
from app.util.openai_client import get_openai_client
from app.util.suggest import SuggestResponse, cap_groups, fetch_label_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobBrowseItem(BaseModel):
    job_id: str
    title: str
    employer_name: str
    city: str | None
    state: str | None
    work_setting: str | None
    pay_min: float | None
    pay_max: float | None
    pay_type: str | None
    pay_raw: str | None
    source: str | None
    source_url: str | None
    source_site: str | None
    posted_date: str | None
    canonical_job_family_code: str | None
    description_preview: str | None
    description: str | None
    qualifications: str | None
    requirements: str | None
    experience_level: str | None
    employment_type: str | None
    # Effective "Apply on SKILLED Nation" flag (per-job override, else the
    # employer's company default). Defaults False so stale cached payloads
    # from before this field existed still validate.
    internal_apply: bool = False
    # Miles from the caller-supplied center (near_lat/near_lng). None when no
    # center was given OR the job has no coordinates — never fabricated.
    distance_miles: float | None = None


class JobBrowseResponse(BaseModel):
    jobs: list[JobBrowseItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class JobPin(BaseModel):
    """Light map-pin record — id + label + coordinates only."""

    job_id: str
    title: str
    employer_name: str
    city: str | None
    state: str | None
    lat: float
    lng: float
    pay_min: float | None
    pay_max: float | None
    pay_type: str | None
    pay_raw: str | None
    source_url: str | None
    internal_apply: bool = False
    distance_miles: float | None = None


class JobPinsResponse(BaseModel):
    pins: list[JobPin]
    # Jobs matching the filters that HAVE coordinates (before the pin cap).
    total: int
    # Jobs matching the filters with no coordinates — shown in the list only.
    without_coords: int


# Map payload cap — ~400 active jobs today; 500 keeps the pins response light
# even as the catalog grows, and the honest `total` count tells the UI when
# pins were capped.
_MAX_PINS = 500


@router.get("/employers")
async def list_job_employers(
    user=Depends(require_authenticated),
):
    """Return distinct employer names that have at least one active job."""
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT e.name
            FROM public.jobs j
            JOIN public.employers e ON e.id = j.employer_id
            WHERE j.is_active = TRUE AND e.name IS NOT NULL
            ORDER BY e.name
            """
        )
    return {"employers": [r["name"] for r in rows]}


@router.get("/trades")
async def list_job_trades(
    user=Depends(require_authenticated),
):
    """Return distinct canonical job families that have at least one active job.

    Powers the "Trade" filter on the applicant browse page — values are the
    family codes accepted by /jobs/browse?trade=.
    """
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT jf.code, jf.name
            FROM public.jobs j
            JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.is_active = TRUE
            ORDER BY jf.name
            """
        )
    return {"trades": [{"value": r["code"], "label": r["name"]} for r in rows]}


@router.get("/suggest", response_model=SuggestResponse)
async def suggest_browse(
    q: str = Query(..., min_length=1, max_length=120),
    user=Depends(require_authenticated),
):
    """As-you-type dropdown for the applicant browse search: job titles,
    employer names, and trade names over ACTIVE jobs only — the same
    `j.is_active = TRUE` base predicate as /jobs/browse, so a picked
    suggestion narrows the list exactly as typing it would.
    """
    async with get_db() as conn:
        titles = await fetch_label_suggestions(
            conn,
            kind="job",
            label_expr="j.title_raw",
            from_clause="FROM public.jobs j",
            where="j.is_active = TRUE",
            q=q,
            limit=8,
        )
        employers = await fetch_label_suggestions(
            conn,
            kind="employer",
            label_expr="e.name",
            from_clause="FROM public.employers e",
            where=(
                "EXISTS (SELECT 1 FROM public.jobs j "
                "WHERE j.employer_id = e.id AND j.is_active = TRUE)"
            ),
            q=q,
            limit=8,
        )
        trades = await fetch_label_suggestions(
            conn,
            kind="trade",
            label_expr="jf.name",
            from_clause="FROM public.canonical_job_families jf",
            where=(
                "EXISTS (SELECT 1 FROM public.jobs j "
                "WHERE j.canonical_job_family_id = jf.id AND j.is_active = TRUE)"
            ),
            q=q,
            limit=8,
        )
    return SuggestResponse(suggestions=cap_groups([titles, employers, trades]))


def _browse_filters(
    q: str, trade: str, state: str, employer: str, work_setting: str, source: str,
) -> tuple[list[str], list]:
    """Shared WHERE builder for /jobs/browse and /jobs/browse/pins.

    Both endpoints MUST filter identically — the map pins and the list are two
    views of the same result set (predicate parity, tested in
    tests/test_browse_geo.py).
    """
    where_clauses = ["j.is_active = TRUE"]
    params: list = []

    if q.strip():
        params.append(f"%{q.strip()}%")
        where_clauses.append(
            f"(j.title_raw ILIKE ${len(params)} OR j.description_raw ILIKE ${len(params)})"
        )
    if trade.strip():
        params.append(trade.strip())
        where_clauses.append(f"jf.code = ${len(params)}")
    if state.strip():
        params.append(state.strip())
        where_clauses.append(f"UPPER(j.state) = UPPER(${len(params)})")
    if employer.strip():
        params.append(f"%{employer.strip()}%")
        where_clauses.append(f"e.name ILIKE ${len(params)}")
    if work_setting.strip():
        params.append(work_setting.strip())
        where_clauses.append(f"j.work_setting::text = ${len(params)}")
    if source.strip():
        params.append(source.strip())
        where_clauses.append(f"j.source = ${len(params)}")

    return where_clauses, params


def _parse_bbox(bbox: str) -> tuple[float, float, float, float] | None:
    """Parse `bbox=minLng,minLat,maxLng,maxLat` (the map viewport) or 422.

    Returns None when the param is absent/empty. The bbox is a plain
    lat/lng-aligned rectangle — the same shape the frontend derives from the
    map viewport, so "what the list shows" is exactly "what the map frames".
    """
    if not bbox.strip():
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422,
            detail="bbox must be minLng,minLat,maxLng,maxLat",
        )
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="bbox must be four numbers: minLng,minLat,maxLng,maxLat",
        )
    if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180
            and -90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox is out of range")
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(
            status_code=422,
            detail="bbox min values must be less than max values",
        )
    return (min_lng, min_lat, max_lng, max_lat)


def _apply_bbox(
    where_clauses: list[str],
    params: list,
    bbox: tuple[float, float, float, float],
    include_unmapped: bool,
) -> None:
    """Append the shared viewport predicate (identical text on /browse and
    /browse/pins — predicate parity, tested in tests/test_browse_geo.py).

    The range comparisons are NULL-safe by SQL semantics: a job without
    coordinates fails every comparison, so a bbox-scoped list honestly shows
    only what the map can frame. `include_unmapped` re-admits those jobs via
    an explicit OR branch (the list's "Show them" affordance).
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    params.extend([min_lng, max_lng, min_lat, max_lat])
    n = len(params)
    clause = (
        f"(j.lng >= ${n - 3} AND j.lng <= ${n - 2} "
        f"AND j.lat >= ${n - 1} AND j.lat <= ${n})"
    )
    if include_unmapped:
        clause = f"({clause} OR j.lat IS NULL OR j.lng IS NULL)"
    where_clauses.append(clause)


def _validate_geo_params(
    near_lat: float | None, near_lng: float | None, radius_miles: float | None,
    bbox: tuple[float, float, float, float] | None = None,
) -> None:
    """near_lat/near_lng travel as a pair; a radius needs a center; the map
    viewport (bbox) and the radius circle are two exclusive scopes."""
    if (near_lat is None) != (near_lng is None):
        raise HTTPException(
            status_code=422,
            detail="near_lat and near_lng must be provided together",
        )
    if radius_miles is not None and near_lat is None:
        raise HTTPException(
            status_code=422,
            detail="radius_miles requires near_lat and near_lng",
        )
    if bbox is not None and (near_lat is not None or radius_miles is not None):
        raise HTTPException(
            status_code=422,
            detail="bbox and near_lat/near_lng/radius_miles are exclusive scopes",
        )


def _geo_sql(
    params: list, near_lat: float | None, near_lng: float | None,
) -> str | None:
    """Bind the center point and return the distance-miles SQL expression."""
    if near_lat is None or near_lng is None:
        return None
    params.append(near_lat)
    lat_ph = f"${len(params)}"
    params.append(near_lng)
    lng_ph = f"${len(params)}"
    return haversine_sql(lat_ph, lng_ph)


@router.get("/browse", response_model=JobBrowseResponse)
async def browse_jobs(
    user=Depends(require_authenticated),
    q: str = Query("", description="Search query for title or description"),
    trade: str = Query("", description="Filter by canonical job family code"),
    state: str = Query("", description="Filter by state (2-letter code)"),
    employer: str = Query("", description="Filter by employer name"),
    work_setting: str = Query("", description="Filter by work_setting enum"),
    source: str = Query("", description="Filter by source (manual, scraper)"),
    near_lat: float | None = Query(None, ge=-90, le=90,
                                   description="Center latitude for distance filtering/sorting"),
    near_lng: float | None = Query(None, ge=-180, le=180,
                                   description="Center longitude for distance filtering/sorting"),
    radius_miles: float | None = Query(None, gt=0, le=4000,
                                       description="Only jobs within this many miles of the center "
                                                   "(jobs without coordinates stay in the list)"),
    bbox: str = Query("", description="Map viewport scope: minLng,minLat,maxLng,maxLat. "
                                      "Exclusive with near_lat/near_lng/radius_miles. "
                                      "Jobs without coordinates are excluded unless "
                                      "include_unmapped is set."),
    include_unmapped: bool = Query(False, description="With bbox: also list jobs without "
                                                      "coordinates (appended after mapped jobs)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Browse all active job postings with search, filters, and one optional
    geographic scope: a radius around a center point (haversine) or the map
    viewport (bbox) — never both."""
    # Direct in-process calls (integration tests) bypass FastAPI's DI, so the
    # declared Query(...) sentinels arrive as-is — normalize to real defaults.
    if not isinstance(bbox, str):
        bbox = ""
    if not isinstance(include_unmapped, bool):
        include_unmapped = False
    bbox_t = _parse_bbox(bbox)
    _validate_geo_params(near_lat, near_lng, radius_miles, bbox_t)

    where_clauses, params = _browse_filters(q, trade, state, employer, work_setting, source)

    # Viewport scope: what the map frames is what the list shows. Jobs without
    # coordinates fail the range predicate (honest semantics — they cannot be
    # placed in or out of the viewport); include_unmapped re-admits them.
    if bbox_t is not None:
        _apply_bbox(where_clauses, params, bbox_t, include_unmapped)
    n_where_params = len(params)

    # Geography: distance is SELECTed whenever a center is given; the radius
    # predicate keeps jobs WITHOUT coordinates in the list (they can't be
    # distance-tested — the UI labels them "no mapped location" instead of
    # silently dropping them; the map excludes them with an honest count).
    distance_sql = _geo_sql(params, near_lat, near_lng)
    radius_in_where = distance_sql is not None and radius_miles is not None
    if radius_in_where:
        params.append(radius_miles)
        where_clauses.append(
            f"(j.lat IS NULL OR j.lng IS NULL OR {distance_sql} <= ${len(params)})"
        )

    where_sql = " AND ".join(where_clauses)
    param_idx = len(params)
    offset = (page - 1) * per_page
    # asyncpg rejects unused bound args: the count query only sees the geo
    # center placeholders when the radius predicate is in the WHERE clause.
    count_params = params if radius_in_where else params[:n_where_params]

    distance_select = (
        f"{distance_sql} AS distance_miles" if distance_sql is not None
        else "NULL::float AS distance_miles"
    )
    # Nearest-first when a center is given (Airbnb-style); in viewport scope
    # with unmapped jobs re-admitted, mapped jobs come first so the unmapped
    # tail reads as an appendix; otherwise newest.
    if distance_sql is not None:
        order_sql = (
            "ORDER BY distance_miles ASC NULLS LAST, "
            "j.posted_date DESC NULLS LAST, j.created_at DESC"
        )
    elif bbox_t is not None and include_unmapped:
        order_sql = (
            "ORDER BY (j.lat IS NULL OR j.lng IS NULL) ASC, "
            "j.posted_date DESC NULLS LAST, j.created_at DESC"
        )
    else:
        order_sql = "ORDER BY j.posted_date DESC NULLS LAST, j.created_at DESC"

    count_sql = f"""
        SELECT COUNT(*)
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE {where_sql}
    """

    data_sql = f"""
        SELECT
            j.id, j.title_raw, e.name AS employer_name,
            j.city, j.state, j.work_setting::text AS work_setting,
            j.pay_min, j.pay_max, j.pay_type, j.pay_raw,
            j.source, j.source_url, j.source_site,
            j.posted_date::text AS posted_date,
            jf.code AS canonical_job_family_code,
            -- Preview prefers the cleaned "About the role" text over raw scrape
            -- (which often opens with corporate mission boilerplate).
            LEFT(COALESCE(jds.sections->'about'->>0, j.description_raw), 200)
                AS description_preview,
            j.description_raw,
            j.preferred_qualifications_raw,
            j.requirements_raw,
            j.experience_level,
            COALESCE(j.accepts_internal_applications,
                     e.accepts_internal_applications_default,
                     FALSE) AS internal_apply,
            {distance_select}
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        LEFT JOIN public.job_display_sections jds ON jds.job_id = j.id
        WHERE {where_sql}
        {order_sql}
        LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
    """
    params_with_pagination = params + [per_page, offset]

    async def _produce() -> dict:
        async with get_db() as conn:
            total = await conn.fetchval(count_sql, *count_params)
            rows = await conn.fetch(data_sql, *params_with_pagination)

        total_pages = max(1, (total + per_page - 1) // per_page)

        jobs = [
            JobBrowseItem(
                job_id=str(row["id"]),
                title=row["title_raw"],
                employer_name=row["employer_name"] or "Unknown",
                city=row["city"],
                state=row["state"],
                work_setting=row["work_setting"],
                pay_min=float(row["pay_min"]) if row["pay_min"] else None,
                pay_max=float(row["pay_max"]) if row["pay_max"] else None,
                pay_type=row["pay_type"],
                pay_raw=row["pay_raw"],
                source=row["source"],
                source_url=row["source_url"],
                source_site=row["source_site"],
                posted_date=row["posted_date"],
                canonical_job_family_code=row["canonical_job_family_code"],
                description_preview=row["description_preview"],
                description=row["description_raw"],
                qualifications=row["preferred_qualifications_raw"],
                requirements=row["requirements_raw"],
                experience_level=row["experience_level"],
                employment_type=None,
                internal_apply=bool(row["internal_apply"]),
                distance_miles=(
                    round(float(row["distance_miles"]), 1)
                    if row["distance_miles"] is not None else None
                ),
            )
            for row in rows
        ]
        return JobBrowseResponse(
            jobs=jobs, total=total, page=page, per_page=per_page, total_pages=total_pages,
        ).model_dump()

    # Cache-aside: the job catalog changes slowly, and browse is the most
    # repeated expensive query (count + data scan). 30s TTL bounds staleness.
    # v4: adds near_lat/near_lng/radius_miles + distance_miles — new namespace
    # avoids serving stale distance-less payloads from cache.
    # v5: adds bbox + include_unmapped (viewport scope) — new namespace avoids
    # serving stale unscoped payloads from cache.
    key = cache_key(
        "jobs:browse:v5", q, trade, state, employer, work_setting, source,
        near_lat, near_lng, radius_miles, bbox, include_unmapped, page, per_page,
    )
    data = await cached_json(key, 30, _produce)
    return JobBrowseResponse(**data)


@router.get("/browse/pins", response_model=JobPinsResponse)
async def browse_job_pins(
    user=Depends(require_authenticated),
    q: str = Query("", description="Search query for title or description"),
    trade: str = Query("", description="Filter by canonical job family code"),
    state: str = Query("", description="Filter by state (2-letter code)"),
    employer: str = Query("", description="Filter by employer name"),
    work_setting: str = Query("", description="Filter by work_setting enum"),
    source: str = Query("", description="Filter by source (manual, scraper)"),
    near_lat: float | None = Query(None, ge=-90, le=90),
    near_lng: float | None = Query(None, ge=-180, le=180),
    radius_miles: float | None = Query(None, gt=0, le=4000),
    bbox: str = Query(""),
):
    """Map-pin variant of /jobs/browse: every job matching the SAME filters,
    unpaginated (capped at 500), coordinates required. Jobs without coordinates
    are counted in `without_coords` so the UI can say so honestly."""
    # Direct in-process calls bypass FastAPI's DI — normalize the Query
    # sentinel to a real default (mirrors browse_jobs).
    if not isinstance(bbox, str):
        bbox = ""
    bbox_t = _parse_bbox(bbox)
    _validate_geo_params(near_lat, near_lng, radius_miles, bbox_t)

    where_clauses, params = _browse_filters(q, trade, state, employer, work_setting, source)
    # Coverage (the without_coords count) deliberately ignores the bbox: a job
    # without coordinates is neither in nor out of any viewport, so the honest
    # count is "matching the filters, unmappable" — the same number whatever
    # the map frames.
    filter_params = list(params)
    base_where = " AND ".join(where_clauses)

    # Pins require coordinates; the viewport or radius (when given) applies on
    # top — same predicate text as /jobs/browse (shared helpers).
    pin_clauses = list(where_clauses) + ["j.lat IS NOT NULL", "j.lng IS NOT NULL"]
    if bbox_t is not None:
        _apply_bbox(pin_clauses, params, bbox_t, include_unmapped=False)
    n_where_params = len(params)
    distance_sql = _geo_sql(params, near_lat, near_lng)
    radius_in_where = distance_sql is not None and radius_miles is not None
    if radius_in_where:
        params.append(radius_miles)
        pin_clauses.append(f"{distance_sql} <= ${len(params)}")
    pin_where = " AND ".join(pin_clauses)
    # asyncpg rejects unused bound args — the pin-count WHERE references the
    # geo center placeholders only when the radius predicate was appended.
    pin_count_params = params if radius_in_where else params[:n_where_params]

    distance_select = (
        f"{distance_sql} AS distance_miles" if distance_sql is not None
        else "NULL::float AS distance_miles"
    )
    order_sql = (
        "ORDER BY distance_miles ASC, j.posted_date DESC NULLS LAST, j.created_at DESC"
        if distance_sql is not None
        else "ORDER BY j.posted_date DESC NULLS LAST, j.created_at DESC"
    )

    coverage_sql = f"""
        SELECT COUNT(*) FILTER (WHERE j.lat IS NULL OR j.lng IS NULL) AS without_coords
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE {base_where}
    """

    pin_count_sql = f"""
        SELECT COUNT(*)
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE {pin_where}
    """

    data_sql = f"""
        SELECT
            j.id, j.title_raw, e.name AS employer_name,
            j.city, j.state, j.lat, j.lng,
            j.pay_min, j.pay_max, j.pay_type, j.pay_raw, j.source_url,
            COALESCE(j.accepts_internal_applications,
                     e.accepts_internal_applications_default,
                     FALSE) AS internal_apply,
            {distance_select}
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE {pin_where}
        {order_sql}
        LIMIT {_MAX_PINS}
    """

    async def _produce() -> dict:
        async with get_db() as conn:
            without_coords = await conn.fetchval(coverage_sql, *filter_params)
            total = await conn.fetchval(pin_count_sql, *pin_count_params)
            rows = await conn.fetch(data_sql, *params)

        pins = [
            JobPin(
                job_id=str(row["id"]),
                title=row["title_raw"],
                employer_name=row["employer_name"] or "Unknown",
                city=row["city"],
                state=row["state"],
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                pay_min=float(row["pay_min"]) if row["pay_min"] else None,
                pay_max=float(row["pay_max"]) if row["pay_max"] else None,
                pay_type=row["pay_type"],
                pay_raw=row["pay_raw"],
                source_url=row["source_url"],
                internal_apply=bool(row["internal_apply"]),
                distance_miles=(
                    round(float(row["distance_miles"]), 1)
                    if row["distance_miles"] is not None else None
                ),
            )
            for row in rows
        ]
        return JobPinsResponse(
            pins=pins, total=int(total), without_coords=int(without_coords),
        ).model_dump()

    key = cache_key(
        "jobs:browse-pins:v2", q, trade, state, employer, work_setting, source,
        near_lat, near_lng, radius_miles, bbox,
    )
    data = await cached_json(key, 30, _produce)
    return JobPinsResponse(**data)


def _format_pay(pay_raw, pay_min, pay_max, pay_type, fact_pay) -> str | None:
    """Best available pay string: raw text > structured range > parsed fact."""
    if pay_raw and pay_raw.strip():
        # Scraped pay_raw can arrive snapped across lines ("$\n27.68\nper hour")
        # — collapse whitespace and re-attach the currency symbol.
        cleaned = re.sub(r"\s+", " ", pay_raw).strip()
        return re.sub(r"([$€£])\s+(?=\d)", r"\1", cleaned)
    if pay_min is not None:
        suffix = "/hr" if pay_type == "hourly" else "/yr" if pay_type == "annual" else ""
        fmt = (lambda n: f"${n / 1000:.0f}k") if pay_type == "annual" else (lambda n: f"${n:.2f}".rstrip("0").rstrip("."))
        lo = fmt(float(pay_min))
        if pay_max is not None and pay_max != pay_min:
            return f"{lo}–{fmt(float(pay_max))}{suffix}"
        return f"{lo}{suffix}"
    return fact_pay


def _clean_place(v: str | None) -> str | None:
    """Scraped feeds sometimes send literal 'Unspecified' — treat it as absent."""
    if v and v.strip() and v.strip().lower() != "unspecified":
        return v.strip()
    return None


@router.get("/{job_id}/sections")
async def get_job_sections(
    job_id: str,
    user=Depends(require_authenticated),
):
    """Clean, structured display sections for a job (cached; parser + LLM fallback)."""
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")

    async with get_db() as conn:
        job = await conn.fetchrow(
            """
            SELECT j.description_raw, j.requirements_raw, j.preferred_qualifications_raw,
                   j.responsibilities_raw, j.city, j.state, j.work_setting::text AS work_setting,
                   j.pay_min, j.pay_max, j.pay_type, j.pay_raw
            FROM public.jobs j
            WHERE j.id = $1 AND j.is_active = TRUE
            """,
            jid,
        )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Instrument "job view" — this endpoint fires exactly when a user opens a
    # job's detail view. Server-side, applicants only (employer/admin views are
    # not applicant demand), deduped to one event per applicant/job/day.
    if getattr(user, "role", None) == "applicant":
        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO public.engagement_events (applicant_id, job_id, event_type, event_data)
                SELECT a.id, $2::uuid, 'job_view', '{}'::jsonb
                FROM public.applicants a
                WHERE a.user_id = $1
                  AND NOT EXISTS (
                    SELECT 1 FROM public.engagement_events ee
                    WHERE ee.applicant_id = a.id AND ee.job_id = $2::uuid
                      AND ee.event_type = 'job_view'
                      AND ee.created_at >= date_trunc('day', now())
                  )
                """,
                user.user_id,
                jid,
            )

    raws = (
        job["description_raw"],
        job["requirements_raw"],
        job["preferred_qualifications_raw"],
        job["responsibilities_raw"],
    )
    content_hash = compute_content_hash(*raws)

    async with get_db() as conn:
        cached = await conn.fetchrow(
            "SELECT sections, source FROM public.job_display_sections "
            "WHERE job_id = $1 AND content_hash = $2",
            jid, content_hash,
        )

    if cached is not None:
        sections, source = cached["sections"], cached["source"]
    else:
        sections = parse_job_sections(*raws)
        source = "parser"
        if sections["quality"] == "messy" and get_openai_client() is not None:
            # Bounded reorganize-only call; returns the parser result on failure.
            llm_sections = await asyncio.to_thread(
                llm_reorganize_sections, *raws, deterministic_result=sections
            )
            if llm_sections is not sections:
                sections, source = llm_sections, "llm"
        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO public.job_display_sections
                    (job_id, sections, source, content_hash, updated_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (job_id) DO UPDATE SET
                    sections = EXCLUDED.sections,
                    source = EXCLUDED.source,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = now()
                """,
                jid, sections, source, content_hash,
            )

    facts = sections.get("facts") or {}
    location = ", ".join(
        p for p in (_clean_place(job["city"]), _clean_place(job["state"])) if p
    ) or facts.get("location_text")

    return {
        "job_id": str(jid),
        "source": source,
        "quality": sections.get("quality", "good"),
        "glance": {
            "location": location,
            "work_setting": job["work_setting"],
            "shift": facts.get("shift"),
            "pay": _format_pay(
                job["pay_raw"], job["pay_min"], job["pay_max"], job["pay_type"],
                facts.get("pay_text"),
            ),
        },
        "about": sections.get("about", []),
        "duties": sections.get("duties", []),
        "needs": sections.get("needs", []),
        "nice_to_have": sections.get("nice_to_have", []),
        "benefits": sections.get("benefits", []),
        "schedule": sections.get("schedule", []),
        "company": sections.get("company", []),
        "notices": sections.get("notices", []),
    }
