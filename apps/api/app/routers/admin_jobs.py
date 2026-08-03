"""
admin_jobs.py — Admin structured-jobs console (GET /admin/jobs).

A filterable list over the ENTIRE job catalog (scraped + imported + manual),
with granular, composable facets: family, industry, geography, employment
type, pay, source, freshness, apply-link health, dates, and candidate bands.

Count and list share one WHERE clause (predicate parity — the analytics
soundness rule). Filter predicates live in app.util.job_filters and are shared
with the employer jobs list so both surfaces filter identically.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.db import get_db
from app.util.filters import csv_values, parse_iso_date
from app.util.job_filters import (
    CANDIDATES_EXPR,
    STALE_PRED,
    JobFilterParams,
    build_job_conditions,
    resolve_sort,
)
from app.util.suggest import SuggestResponse, cap_groups, fetch_label_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])

_JOB_JOINS = (
    "FROM public.jobs j "
    "LEFT JOIN public.employers e ON e.id = j.employer_id "
    "LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id"
)

# Feature detection: a concurrent workstream is adding
# jobs.accepts_internal_applications. Detect once per process and expose the
# capability to the frontend so the filter only renders when it can work.
_internal_apply_supported: Optional[bool] = None


async def _detect_internal_apply(conn) -> bool:
    global _internal_apply_supported
    if _internal_apply_supported is None:
        _internal_apply_supported = bool(await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'jobs' "
            "  AND column_name = 'accepts_internal_applications'"
        ))
    return _internal_apply_supported


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AdminJobRow(BaseModel):
    id: str
    title: str
    employer_id: str | None
    employer_name: str | None
    city: str | None
    state: str | None
    family_code: str | None
    family_name: str | None
    pay_min: float | None
    pay_max: float | None
    pay_type: str | None
    pay_raw: str | None
    employment_type: str | None
    source: str | None
    source_site: str | None
    is_active: bool
    is_stale: bool
    apply_link_status: str | None
    accepts_internal_applications: bool | None = None
    posted_date: str | None
    created_at: str | None
    candidate_count: int


class FacetOption(BaseModel):
    value: str
    label: str


class AdminJobFacets(BaseModel):
    families: list[FacetOption]
    industries: list[str]
    states: list[str]
    sources: list[str]
    source_sites: list[str]
    employment_types: list[str]


class AdminJobList(BaseModel):
    total: int
    page: int
    page_size: int
    supports_internal_apply: bool
    jobs: list[AdminJobRow]
    facets: AdminJobFacets


# ---------------------------------------------------------------------------
# GET /admin/jobs/suggest — as-you-type dropdown for the console search
# ---------------------------------------------------------------------------

@router.get("/suggest", response_model=SuggestResponse)
async def suggest_jobs(
    q: str = Query(..., min_length=1, max_length=120),
    user=Depends(require_admin),
):
    """Job titles + employer names matching `q`, prefix matches first.

    Sources mirror the console's own `q` predicate (title_normalized /
    title_raw / employer name over the ENTIRE catalog), so picking a
    suggestion narrows the list exactly as typing it would.
    """
    async with get_db() as conn:
        titles = await fetch_label_suggestions(
            conn,
            kind="job",
            label_expr="COALESCE(j.title_normalized, j.title_raw)",
            from_clause="FROM public.jobs j",
            q=q,
            limit=8,
        )
        employers = await fetch_label_suggestions(
            conn,
            kind="employer",
            label_expr="e.name",
            from_clause="FROM public.employers e",
            # Console q matches e.name via the jobs join — only employers
            # that actually have catalog jobs can narrow the list.
            where="EXISTS (SELECT 1 FROM public.jobs j WHERE j.employer_id = e.id)",
            q=q,
            limit=8,
        )
    return SuggestResponse(suggestions=cap_groups([titles, employers]))


# ---------------------------------------------------------------------------
# GET /admin/jobs
# ---------------------------------------------------------------------------

@router.get("", response_model=AdminJobList)
async def list_all_jobs(
    q: str | None = Query(None, max_length=160, description="Title or employer search"),
    families: str | None = Query(None, description="Comma-separated family codes"),
    industries: str | None = Query(None, description="Comma-separated industries"),
    states: str | None = Query(None, description="Comma-separated state codes"),
    city: str | None = Query(None, max_length=120),
    employment_types: str | None = Query(None, description="Comma-separated employment types"),
    sources: str | None = Query(None, description="Comma-separated sources (scraper, manual, ...)"),
    source_sites: str | None = Query(None, description="Comma-separated source sites"),
    status: str | None = Query(None, description="active | inactive | stale"),
    apply_link: str | None = Query(None, description="ok | broken | unchecked"),
    has_pay: bool | None = Query(None, description="Structured or raw pay present"),
    pay_gte: float | None = Query(None, ge=0, description="Structured pay ceiling at least this"),
    internal_apply: bool | None = Query(None, description="accepts_internal_applications (if supported)"),
    posted_from: str | None = Query(None),
    posted_to: str | None = Query(None),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    candidates: str | None = Query(None, description="none | 1_9 | 10_49 | over_50"),
    sort: str = Query("newest", description="newest | posted | title | pay"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_admin),
):
    fp = JobFilterParams(
        q=q or None,
        families=csv_values(families),
        industries=csv_values(industries),
        states=csv_values(states, upper=True),
        city=city or None,
        employment_types=csv_values(employment_types),
        sources=csv_values(sources),
        source_sites=csv_values(source_sites),
        status=status or None,
        apply_link=apply_link or None,
        has_pay=has_pay,
        pay_gte=pay_gte,
        internal_apply=internal_apply,
        posted_from=parse_iso_date(posted_from, "posted_from"),
        posted_to=parse_iso_date(posted_to, "posted_to"),
        created_from=parse_iso_date(created_from, "created_from"),
        created_to=parse_iso_date(created_to, "created_to"),
        candidates=candidates or None,
    )
    order_by = resolve_sort(sort)
    offset = (page - 1) * page_size

    async with get_db() as conn:
        supports_internal = await _detect_internal_apply(conn)

        params: list[Any] = []
        conditions = build_job_conditions(
            fp, params, internal_apply_supported=supports_internal
        )
        where = " AND ".join(conditions) if conditions else "1=1"

        total = await conn.fetchval(
            f"SELECT COUNT(*) {_JOB_JOINS} WHERE {where}", *params
        )

        internal_col = (
            "j.accepts_internal_applications" if supports_internal else "NULL::boolean"
        )
        rows = await conn.fetch(
            f"""
            SELECT
                j.id::text,
                COALESCE(j.title_normalized, j.title_raw) AS title,
                j.employer_id::text,
                e.name AS employer_name,
                j.city,
                j.state,
                jf.code AS family_code,
                jf.name AS family_name,
                j.pay_min, j.pay_max, j.pay_type, j.pay_raw,
                j.employment_type,
                j.source, j.source_site,
                j.is_active,
                (j.is_active = TRUE AND {STALE_PRED}) AS is_stale,
                j.apply_link_status,
                {internal_col} AS accepts_internal_applications,
                j.posted_date::text AS posted_date,
                j.created_at::text AS created_at,
                {CANDIDATES_EXPR} AS candidate_count
            {_JOB_JOINS}
            WHERE {where}
            ORDER BY {order_by}
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, page_size, offset,
        )

        # Facet option lists over the whole catalog (stable while narrowing).
        family_rows = await conn.fetch(
            "SELECT code, name FROM public.canonical_job_families "
            "WHERE is_active IS NOT FALSE ORDER BY name"
        )
        industry_rows = await conn.fetch(
            "SELECT DISTINCT TRIM(e2.industry) AS v FROM public.employers e2 "
            "WHERE e2.industry IS NOT NULL AND TRIM(e2.industry) <> '' "
            "UNION SELECT DISTINCT unnest(jf2.industries) "
            "FROM public.canonical_job_families jf2 ORDER BY 1"
        )
        state_rows = await conn.fetch(
            "SELECT DISTINCT UPPER(TRIM(j2.state)) AS v FROM public.jobs j2 "
            "WHERE j2.state IS NOT NULL AND TRIM(j2.state) <> '' ORDER BY 1"
        )
        source_rows = await conn.fetch(
            "SELECT DISTINCT j2.source AS v FROM public.jobs j2 "
            "WHERE j2.source IS NOT NULL ORDER BY 1"
        )
        site_rows = await conn.fetch(
            "SELECT DISTINCT j2.source_site AS v FROM public.jobs j2 "
            "WHERE j2.source_site IS NOT NULL ORDER BY 1"
        )
        et_rows = await conn.fetch(
            "SELECT DISTINCT j2.employment_type AS v FROM public.jobs j2 "
            "WHERE j2.employment_type IS NOT NULL ORDER BY 1"
        )

    jobs = [
        AdminJobRow(
            id=r["id"],
            title=r["title"] or "Untitled",
            employer_id=r["employer_id"],
            employer_name=r["employer_name"],
            city=r["city"],
            state=r["state"],
            family_code=r["family_code"],
            family_name=r["family_name"],
            pay_min=float(r["pay_min"]) if r["pay_min"] is not None else None,
            pay_max=float(r["pay_max"]) if r["pay_max"] is not None else None,
            pay_type=r["pay_type"],
            pay_raw=r["pay_raw"],
            employment_type=r["employment_type"],
            source=r["source"],
            source_site=r["source_site"],
            is_active=bool(r["is_active"]),
            is_stale=bool(r["is_stale"]),
            apply_link_status=r["apply_link_status"],
            accepts_internal_applications=r["accepts_internal_applications"],
            posted_date=r["posted_date"],
            created_at=r["created_at"],
            candidate_count=int(r["candidate_count"] or 0),
        )
        for r in rows
    ]
    return AdminJobList(
        total=int(total or 0),
        page=page,
        page_size=page_size,
        supports_internal_apply=supports_internal,
        jobs=jobs,
        facets=AdminJobFacets(
            families=[FacetOption(value=r["code"], label=r["name"] or r["code"]) for r in family_rows],
            industries=[r["v"] for r in industry_rows if r["v"]],
            states=[r["v"] for r in state_rows],
            sources=[r["v"] for r in source_rows],
            source_sites=[r["v"] for r in site_rows],
            employment_types=[r["v"] for r in et_rows],
        ),
    )
