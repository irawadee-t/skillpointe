"""
jobs.py — Public job browsing endpoint.

Provides a paginated, filterable list of all active jobs for applicants
to browse. Includes both manually created and scraped job postings.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import require_authenticated
from app.db import get_db

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


class JobBrowseResponse(BaseModel):
    jobs: list[JobBrowseItem]
    total: int
    page: int
    per_page: int
    total_pages: int


@router.get("/employers")
async def list_job_employers(
    user=Depends(require_authenticated),
    conn=Depends(get_db),
):
    """Return distinct employer names that have at least one active job."""
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


@router.get("/browse", response_model=JobBrowseResponse)
async def browse_jobs(
    user=Depends(require_authenticated),
    q: str = Query("", description="Search query for title or description"),
    trade: str = Query("", description="Filter by canonical job family code"),
    state: str = Query("", description="Filter by state (2-letter code)"),
    employer: str = Query("", description="Filter by employer name"),
    work_setting: str = Query("", description="Filter by work_setting enum"),
    source: str = Query("", description="Filter by source (manual, scraper)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Browse all active job postings with search and filters."""
    where_clauses = ["j.is_active = TRUE"]
    params: list = []
    param_idx = 0

    if q.strip():
        param_idx += 1
        where_clauses.append(
            f"(j.title_raw ILIKE ${param_idx} OR j.description_raw ILIKE ${param_idx})"
        )
        params.append(f"%{q.strip()}%")

    if trade.strip():
        param_idx += 1
        where_clauses.append(f"jf.code = ${param_idx}")
        params.append(trade.strip())

    if state.strip():
        param_idx += 1
        where_clauses.append(f"UPPER(j.state) = UPPER(${param_idx})")
        params.append(state.strip())

    if employer.strip():
        param_idx += 1
        where_clauses.append(f"e.name ILIKE ${param_idx}")
        params.append(f"%{employer.strip()}%")

    if work_setting.strip():
        param_idx += 1
        where_clauses.append(f"j.work_setting::text = ${param_idx}")
        params.append(work_setting.strip())

    if source.strip():
        param_idx += 1
        where_clauses.append(f"j.source = ${param_idx}")
        params.append(source.strip())

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * per_page

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
            LEFT(j.description_raw, 200) AS description_preview,
            j.description_raw,
            j.preferred_qualifications_raw,
            j.requirements_raw,
            j.experience_level
        FROM public.jobs j
        LEFT JOIN public.employers e ON e.id = j.employer_id
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        WHERE {where_sql}
        ORDER BY j.posted_date DESC NULLS LAST, j.created_at DESC
        LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
    """
    params_with_pagination = params + [per_page, offset]

    async with get_db() as conn:
        total = await conn.fetchval(count_sql, *params)
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
        )
        for row in rows
    ]

    return JobBrowseResponse(
        jobs=jobs,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )
