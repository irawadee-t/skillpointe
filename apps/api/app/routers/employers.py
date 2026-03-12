"""
employers.py — Employer-facing API endpoints (Phase 6.2).

All routes require employer or admin role (require_employer_or_admin dep).
Data is fetched via asyncpg using raw SQL.

Endpoints:
  GET  /employer/me/company                           — company summary
  GET  /employer/me/jobs                              — list jobs for this employer
  POST /employer/me/jobs                              — create a new job
  PATCH /employer/me/jobs/{job_id}                    — update an existing job
  GET  /employer/me/jobs/{job_id}/applicants          — ranked applicant list for a job

DECISIONS.md guardrails enforced here:
  - Employer scoping: every job query is filtered by employer_id derived from
    employer_contacts (user_id → employer_id). Employers CANNOT see other employers' data.
  - is_visible_to_employer = TRUE is enforced on every match query.
  - Applicant email, user_id, and admin-only fields are never returned.
  - employer_global_candidate_search_default: false — no broad search endpoint.
  - Geography is included in every applicant response.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.schemas.employer import (
    ApplicantMatchSummary,
    EmployerCompanySummary,
    EmployerJobSummary,
    EmployerJobsListResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobUpdateRequest,
    RankedApplicantsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employer", tags=["employer"])

_MAX_APPLICANTS = 200


# ---------------------------------------------------------------------------
# GET /employer/me/company
# ---------------------------------------------------------------------------

@router.get("/me/company", response_model=EmployerCompanySummary)
async def get_my_company(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> EmployerCompanySummary:
    """
    Return the employer company summary for the authenticated user.
    Resolves via employer_contacts (user_id → employer_id).
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                e.id,
                e.name,
                e.industry,
                e.city,
                e.state,
                e.is_partner,
                COUNT(j.id)                         AS total_jobs,
                COUNT(j.id) FILTER (WHERE j.is_active = TRUE) AS active_jobs
            FROM public.employers e
            JOIN public.employer_contacts ec ON ec.employer_id = e.id
            LEFT JOIN public.jobs j ON j.employer_id = e.id
            WHERE ec.user_id = $1
            GROUP BY e.id
            """,
            current_user.user_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer not found. Contact admin to link your account.",
        )

    return EmployerCompanySummary(
        employer_id=str(row["id"]),
        name=row["name"],
        industry=row["industry"],
        city=row["city"],
        state=row["state"],
        is_partner=bool(row["is_partner"]),
        total_jobs=int(row["total_jobs"]),
        active_jobs=int(row["active_jobs"]),
    )


# ---------------------------------------------------------------------------
# GET /employer/me/jobs
# ---------------------------------------------------------------------------

@router.get("/me/jobs", response_model=EmployerJobsListResponse)
async def list_my_jobs(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> EmployerJobsListResponse:
    """
    Return all jobs for this employer with per-job applicant counts.
    Ordered by created_at DESC.
    """
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        rows = await conn.fetch(
            """
            SELECT
                j.id,
                j.title_normalized,
                j.title_raw,
                j.city,
                j.state,
                j.work_setting::text,
                j.is_active,
                j.posted_date::text,
                j.created_at::text,
                COUNT(m.id) FILTER (
                    WHERE m.is_visible_to_employer = TRUE
                ) AS total_visible,
                COUNT(m.id) FILTER (
                    WHERE m.is_visible_to_employer = TRUE
                      AND m.eligibility_status = 'eligible'
                ) AS eligible_count,
                COUNT(m.id) FILTER (
                    WHERE m.is_visible_to_employer = TRUE
                      AND m.eligibility_status = 'near_fit'
                ) AS near_fit_count
            FROM public.jobs j
            LEFT JOIN public.matches m ON m.job_id = j.id
            WHERE j.employer_id = $1
            GROUP BY j.id
            ORDER BY j.created_at DESC
            """,
            employer_id,
        )

        name_row = await conn.fetchval(
            "SELECT name FROM public.employers WHERE id = $1", employer_id
        )

    jobs = [
        EmployerJobSummary(
            job_id=str(r["id"]),
            title=r["title_normalized"] or r["title_raw"],
            city=r["city"],
            state=r["state"],
            work_setting=r["work_setting"],
            is_active=bool(r["is_active"]),
            posted_date=r["posted_date"],
            created_at=r["created_at"],
            total_visible=int(r["total_visible"] or 0),
            eligible_count=int(r["eligible_count"] or 0),
            near_fit_count=int(r["near_fit_count"] or 0),
        )
        for r in rows
    ]

    return EmployerJobsListResponse(
        employer_id=str(employer_id),
        company_name=name_row or "",
        jobs=jobs,
        total_jobs=len(jobs),
    )


# ---------------------------------------------------------------------------
# POST /employer/me/jobs
# ---------------------------------------------------------------------------

@router.post("/me/jobs", response_model=JobCreateResponse, status_code=201)
async def create_job(
    request: JobCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> JobCreateResponse:
    """
    Create a new job posting for this employer.
    New jobs are active by default (is_active = TRUE).
    """
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        row = await conn.fetchrow(
            """
            INSERT INTO public.jobs (
                employer_id,
                title_raw,
                city,
                state,
                work_setting,
                travel_requirement,
                pay_min,
                pay_max,
                pay_type,
                description_raw,
                requirements_raw,
                experience_level,
                source
            ) VALUES (
                $1, $2, $3, $4,
                CASE WHEN $5::text IS NOT NULL
                     THEN $5::public.work_setting_enum
                     ELSE NULL
                END,
                $6, $7, $8, $9, $10, $11, $12,
                'employer_created'
            )
            RETURNING id::text, title_raw, is_active, created_at::text
            """,
            employer_id,
            request.title_raw,
            request.city,
            request.state,
            request.work_setting,
            request.travel_requirement,
            request.pay_min,
            request.pay_max,
            request.pay_type,
            request.description_raw,
            request.requirements_raw,
            request.experience_level,
        )

    return JobCreateResponse(
        job_id=row["id"],
        title_raw=row["title_raw"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# PATCH /employer/me/jobs/{job_id}
# ---------------------------------------------------------------------------

@router.patch("/me/jobs/{job_id}", response_model=JobCreateResponse)
async def update_job(
    job_id: str,
    request: JobUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> JobCreateResponse:
    """
    Update an existing job. Only provided (non-None) fields are updated.
    Returns 404 if job doesn't exist or doesn't belong to this employer.
    """
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        # Build dynamic SET clause — only update provided fields
        updates: list[str] = []
        params: list[Any] = []
        param_idx = 3  # $1=job_id, $2=employer_id

        field_map = {
            "title_raw": request.title_raw,
            "city": request.city,
            "state": request.state,
            "travel_requirement": request.travel_requirement,
            "pay_min": request.pay_min,
            "pay_max": request.pay_max,
            "pay_type": request.pay_type,
            "description_raw": request.description_raw,
            "requirements_raw": request.requirements_raw,
            "experience_level": request.experience_level,
            "is_active": request.is_active,
        }

        for col, val in field_map.items():
            if val is not None:
                updates.append(f"{col} = ${param_idx}")
                params.append(val)
                param_idx += 1

        if request.work_setting is not None:
            updates.append(
                f"work_setting = CASE WHEN ${param_idx}::text IS NOT NULL "
                f"THEN ${param_idx}::public.work_setting_enum ELSE NULL END"
            )
            params.append(request.work_setting)
            param_idx += 1

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No fields provided to update.",
            )

        set_clause = ", ".join(updates)
        row = await conn.fetchrow(
            f"""
            UPDATE public.jobs
            SET {set_clause}
            WHERE id = $1::uuid
              AND employer_id = $2
            RETURNING id::text, title_raw, is_active, created_at::text
            """,
            job_id,
            employer_id,
            *params,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or does not belong to your account.",
        )

    return JobCreateResponse(
        job_id=row["id"],
        title_raw=row["title_raw"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# GET /employer/me/jobs/{job_id}/applicants
# ---------------------------------------------------------------------------

@router.get(
    "/me/jobs/{job_id}/applicants",
    response_model=RankedApplicantsResponse,
)
async def get_job_applicants(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    # Filters
    eligibility: Annotated[
        str,
        Query(description="Filter by eligibility: all | eligible | near_fit"),
    ] = "all",
    min_score: Annotated[
        float,
        Query(ge=0, le=100, description="Minimum policy_adjusted_score"),
    ] = 0.0,
    state: Annotated[
        str | None,
        Query(description="Filter by applicant state (2-letter code)"),
    ] = None,
    willing_to_relocate: Annotated[
        bool | None,
        Query(description="Filter to applicants willing to relocate"),
    ] = None,
) -> RankedApplicantsResponse:
    """
    Return ranked applicants for a specific job.

    Visibility rules (DECISIONS.md):
      - Job must belong to the authenticated employer (enforced via j.employer_id = $employer_id).
      - Only matches with is_visible_to_employer = TRUE are returned.
      - No admin-only fields (email, user_id, policy internals) are exposed.
      - Default shows eligible + near_fit; ineligible excluded unless explicitly filtered.

    Filters are additive (AND). All are optional.
    """
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        # Fetch total counts (pre-filter) for dashboard display
        count_row = await conn.fetchrow(
            """
            SELECT
                COUNT(m.id) AS total_visible,
                COUNT(m.id) FILTER (WHERE m.eligibility_status = 'eligible') AS eligible_count,
                COUNT(m.id) FILTER (WHERE m.eligibility_status = 'near_fit')  AS near_fit_count,
                j.title_normalized,
                j.title_raw,
                e.name AS employer_name
            FROM public.jobs j
            JOIN public.employers e ON e.id = j.employer_id
            LEFT JOIN public.matches m
                ON m.job_id = j.id AND m.is_visible_to_employer = TRUE
            WHERE j.id = $1::uuid
              AND j.employer_id = $2
            GROUP BY j.id, j.title_normalized, j.title_raw, e.name
            """,
            job_id,
            employer_id,
        )

        if not count_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or does not belong to your account.",
            )

        # Build filtered applicant query
        conditions = [
            "j.id = $1::uuid",
            "j.employer_id = $2",           # CRITICAL: employer scoping
            "m.is_visible_to_employer = TRUE",
        ]
        params: list[Any] = [job_id, employer_id]
        idx = 3

        if eligibility in ("eligible", "near_fit"):
            conditions.append(f"m.eligibility_status = ${idx}")
            params.append(eligibility)
            idx += 1
        else:
            # Default: exclude ineligible
            conditions.append("m.eligibility_status IN ('eligible', 'near_fit')")

        if min_score > 0:
            conditions.append(f"m.policy_adjusted_score >= ${idx}")
            params.append(min_score)
            idx += 1

        if state:
            conditions.append(f"a.state ILIKE ${idx}")
            params.append(state)
            idx += 1

        if willing_to_relocate is not None:
            conditions.append(f"a.willing_to_relocate = ${idx}")
            params.append(willing_to_relocate)
            idx += 1

        where_clause = " AND ".join(conditions)

        applicant_rows = await conn.fetch(
            f"""
            SELECT
                m.id          AS match_id,
                a.id          AS applicant_id,
                a.first_name,
                a.last_name,
                a.city,
                a.state,
                a.region,
                a.willing_to_relocate,
                a.willing_to_travel,
                a.program_name_raw,
                a.expected_completion_date::text,
                a.available_from_date::text,
                jf.code       AS canonical_job_family_code,
                m.eligibility_status::text,
                m.match_label::text,
                m.policy_adjusted_score,
                m.top_strengths,
                m.top_gaps,
                m.recommended_next_step,
                m.confidence_level::text,
                m.requires_review,
                j.city        AS job_city,
                j.state       AS job_state,
                j.region      AS job_region,
                j.work_setting::text AS job_work_setting
            FROM public.matches m
            JOIN public.applicants a  ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            LEFT JOIN public.canonical_job_families jf
                ON jf.id = a.canonical_job_family_id
            WHERE {where_clause}
            ORDER BY m.policy_adjusted_score DESC NULLS LAST
            LIMIT ${ idx }
            """,
            *params,
            _MAX_APPLICANTS,
        )

    applicants = [_row_to_applicant_summary(dict(r)) for r in applicant_rows]

    return RankedApplicantsResponse(
        job_id=job_id,
        job_title=count_row["title_normalized"] or count_row["title_raw"],
        employer_name=count_row["employer_name"],
        total_visible=int(count_row["total_visible"] or 0),
        eligible_count=int(count_row["eligible_count"] or 0),
        near_fit_count=int(count_row["near_fit_count"] or 0),
        applicants=applicants,
        filter_eligibility=eligibility if eligibility != "all" else None,
        filter_min_score=min_score if min_score > 0 else None,
        filter_state=state,
        filter_willing_to_relocate=willing_to_relocate,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _resolve_employer_id(conn: Any, user_id: str) -> Any:
    """
    Look up the employer_id for this authenticated user via employer_contacts.
    Raises HTTP 404 if no employer record is linked to the user.
    """
    employer_id = await conn.fetchval(
        """
        SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1
        """,
        user_id,
    )
    if not employer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer account not found. Contact admin to link your account.",
        )
    return employer_id


def _row_to_applicant_summary(row: dict[str, Any]) -> ApplicantMatchSummary:
    """Convert a DB row to an ApplicantMatchSummary (safe fields only)."""
    return ApplicantMatchSummary(
        match_id=str(row["match_id"]),
        applicant_id=str(row["applicant_id"]),
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        city=row.get("city"),
        state=row.get("state"),
        region=row.get("region"),
        willing_to_relocate=bool(row.get("willing_to_relocate", False)),
        willing_to_travel=bool(row.get("willing_to_travel", False)),
        program_name_raw=row.get("program_name_raw"),
        canonical_job_family_code=row.get("canonical_job_family_code"),
        expected_completion_date=row.get("expected_completion_date"),
        available_from_date=row.get("available_from_date"),
        eligibility_status=row.get("eligibility_status", "near_fit"),
        match_label=row.get("match_label"),
        policy_adjusted_score=_safe_float(row.get("policy_adjusted_score")),
        top_strengths=_safe_list(row.get("top_strengths")),
        top_gaps=_safe_list(row.get("top_gaps")),
        recommended_next_step=row.get("recommended_next_step"),
        confidence_level=row.get("confidence_level"),
        requires_review=bool(row.get("requires_review", False)),
        geography_note=_derive_applicant_geography_note(row),
    )


def _derive_applicant_geography_note(row: dict[str, Any]) -> str | None:
    """
    Human-readable geography note from the employer's perspective:
    applicant's location relative to the job.
    """
    job_ws = (row.get("job_work_setting") or "").lower()
    if job_ws == "remote":
        return None  # Location irrelevant for fully remote roles

    app_state = row.get("state")
    app_city = row.get("city")
    job_state = row.get("job_state")
    willing_to_relocate = row.get("willing_to_relocate", False)
    willing_to_travel = row.get("willing_to_travel", False)

    if not app_state:
        return "Location not set"

    location_str = ", ".join(filter(None, [app_city, app_state]))

    if job_state and app_state.upper() == job_state.upper():
        return f"Local — {location_str}"

    notes: list[str] = []
    if willing_to_relocate:
        notes.append("open to relocate")
    if willing_to_travel:
        notes.append("open to travel")

    if notes:
        return f"{location_str} ({', '.join(notes)})"
    return f"{location_str} — different state"


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    return []
