"""
SKILLED Foundation impact & outcomes analytics (admin).

- GET  /admin/foundation/summary              headline WIOA-style numbers
- GET  /admin/foundation/outcomes?group_by=   cohort breakdown (full, admin-only)
- GET  /admin/foundation/feed?group_by=&k=     k-anonymized, publish-safe feed
- POST /admin/foundation/impact-report         deterministic numbers + AI narrative
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, require_admin
from app.db import get_db
from app.skilled_pro import outcomes
from app.skilled_pro.ai import generate_impact_report

router = APIRouter(prefix="/admin/foundation", tags=["foundation"])

GROUP_DIMS = {"program", "region", "cohort_year"}

_ROWS_SQL = """
    SELECT program, region, cohort_year, placed, wage, time_to_hire_days,
           credential_count, verified_credential_count
    FROM public.applicant_outcomes
"""


async def _load_rows(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in await conn.fetch(_ROWS_SQL)]


class Cohort(BaseModel):
    cohort: str
    n: int
    placed: int | None = None
    employment_rate: float | None = None
    median_wage: int | None = None
    attainment_rate: float | None = None
    median_time_to_hire_days: int | None = None
    suppressed: bool | None = None


class Summary(BaseModel):
    total_served: int
    placed: int
    employment_rate: float | None
    median_wage: int | None
    attainment_rate: float | None
    median_time_to_hire_days: int | None


class ImpactReport(BaseModel):
    narrative: str
    source: str
    summary: Summary
    top_programs: list[Cohort]


@router.get("/summary", response_model=Summary)
async def summary(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rows = await _load_rows(conn)
    return Summary(**outcomes.overall_summary(rows))


@router.get("/outcomes", response_model=list[Cohort])
async def cohorts(
    user: Annotated[CurrentUser, Depends(require_admin)],
    group_by: str = Query("program"),
):
    if group_by not in GROUP_DIMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"group_by must be one of {sorted(GROUP_DIMS)}")
    async with get_db() as conn:
        rows = await _load_rows(conn)
    return [Cohort(**c) for c in outcomes.aggregate_cohorts(rows, group_by)]


@router.get("/feed", response_model=list[Cohort])
async def public_feed(
    user: Annotated[CurrentUser, Depends(require_admin)],
    group_by: str = Query("program"),
    k: int = Query(outcomes.DEFAULT_K, ge=2, le=100),
):
    """Publish-safe: cohorts with n < k are suppressed (k-anonymity)."""
    if group_by not in GROUP_DIMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"group_by must be one of {sorted(GROUP_DIMS)}")
    async with get_db() as conn:
        rows = await _load_rows(conn)
    agg = outcomes.aggregate_cohorts(rows, group_by)
    return [Cohort(**c) for c in outcomes.apply_k_anonymity(agg, k)]


@router.post("/impact-report", response_model=ImpactReport)
async def impact_report(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rows = await _load_rows(conn)

    summ = outcomes.overall_summary(rows)
    programs = outcomes.aggregate_cohorts(rows, "program")
    # Lead with the strongest sufficiently-sized programs.
    top = sorted(
        [c for c in programs if c["n"] >= 5 and c["employment_rate"] is not None],
        key=lambda c: c["employment_rate"], reverse=True,
    )[:3]

    numbers = {"summary": summ, "top_programs": top}
    narrative, src = await generate_impact_report(numbers)
    return ImpactReport(
        narrative=narrative, source=src,
        summary=Summary(**summ), top_programs=[Cohort(**c) for c in top],
    )
