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

from pydantic import BaseModel as _BaseModel

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

    # Fire-and-forget: recompute matches for the new job
    import asyncio as _asyncio
    from app.worker.scheduler import trigger_recompute_for_job
    _asyncio.create_task(trigger_recompute_for_job(row["id"]))

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
        # Admin can view any job's applicants; employers are scoped to their own jobs.
        is_admin = current_user.is_admin
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        # Fetch total counts (pre-filter) for dashboard display
        if is_admin:
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
                GROUP BY j.id, j.title_normalized, j.title_raw, e.name
                """,
                job_id,
            )
        else:
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
        if is_admin:
            conditions = [
                "j.id = $1::uuid",
                "m.is_visible_to_employer = TRUE",
            ]
            params: list[Any] = [job_id]
            idx = 2
        else:
            conditions = [
                "j.id = $1::uuid",
                "j.employer_id = $2",           # CRITICAL: employer scoping
                "m.is_visible_to_employer = TRUE",
            ]
            params = [job_id, employer_id]
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
                j.work_setting::text AS job_work_setting,
                sj.interest_level AS applicant_interest
            FROM public.matches m
            JOIN public.applicants a  ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            LEFT JOIN public.canonical_job_families jf
                ON jf.id = a.canonical_job_family_id
            LEFT JOIN public.saved_jobs sj
                ON sj.applicant_id = a.id AND sj.job_id = j.id
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
        applicant_interest=row.get("applicant_interest"),
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


# ---------------------------------------------------------------------------
# POST /employer/me/outreach/draft  — AI-draft a message to a candidate
# POST /employer/me/outreach/send   — Record that the message was sent
# ---------------------------------------------------------------------------

class OutreachDraftRequest(_BaseModel):
    match_id: str
    applicant_id: str
    job_id: str


class OutreachDraftResponse(_BaseModel):
    subject: str
    body: str


class OutreachSendRequest(_BaseModel):
    match_id: str
    applicant_id: str
    job_id: str
    subject: str
    body: str
    ai_generated: bool = False


class OutreachSendResponse(_BaseModel):
    outreach_id: str
    sent_at: str


@router.post("/me/outreach/draft", response_model=OutreachDraftResponse)
async def draft_outreach(
    body: OutreachDraftRequest,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> OutreachDraftResponse:
    """
    Generate an AI-drafted outreach message for a matched candidate.
    Employer must own the job referenced in the match.
    """
    from app.services.chat import generate_outreach_draft

    async with get_db() as conn:
        is_admin = current_user.is_admin
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        # Fetch match details for context
        if is_admin:
            match_row = await conn.fetchrow(
                """
                SELECT
                    a.first_name, a.last_name,
                    j.title_normalized AS job_title,
                    e.name AS employer_name,
                    m.top_strengths,
                    m.recommended_next_step
                FROM public.matches m
                JOIN public.applicants a ON a.id = m.applicant_id
                JOIN public.jobs j ON j.id = m.job_id
                JOIN public.employers e ON e.id = j.employer_id
                WHERE m.id = $1::uuid AND a.id = $2::uuid AND j.id = $3::uuid
                """,
                body.match_id, body.applicant_id, body.job_id,
            )
        else:
            match_row = await conn.fetchrow(
                """
                SELECT
                    a.first_name, a.last_name,
                    j.title_normalized AS job_title,
                    e.name AS employer_name,
                    m.top_strengths,
                    m.recommended_next_step
                FROM public.matches m
                JOIN public.applicants a ON a.id = m.applicant_id
                JOIN public.jobs j ON j.id = m.job_id
                JOIN public.employers e ON e.id = j.employer_id
                WHERE m.id = $1::uuid
                  AND a.id = $2::uuid
                  AND j.id = $3::uuid
                  AND j.employer_id = $4
                """,
                body.match_id, body.applicant_id, body.job_id, employer_id,
            )

    if not match_row:
        raise HTTPException(status_code=404, detail="Match not found")

    applicant_name = " ".join(
        filter(None, [match_row["first_name"], match_row["last_name"]])
    ) or "Candidate"
    strengths = _safe_list(match_row.get("top_strengths"))

    draft = await generate_outreach_draft(
        job_title=match_row["job_title"] or "position",
        employer_name=match_row["employer_name"] or "our company",
        applicant_name=applicant_name,
        top_strengths=strengths,
        recommended_next_step=match_row.get("recommended_next_step"),
    )
    return OutreachDraftResponse(**draft)


@router.post("/me/outreach/send", response_model=OutreachSendResponse, status_code=201)
async def send_outreach(
    body: OutreachSendRequest,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> OutreachSendResponse:
    """Record that an outreach message was sent to a candidate."""
    async with get_db() as conn:
        is_admin = current_user.is_admin
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        if is_admin:
            emp_id_row = await conn.fetchval(
                "SELECT employer_id FROM public.jobs WHERE id = $1::uuid", body.job_id
            )
            employer_id = emp_id_row

        if not employer_id:
            raise HTTPException(status_code=404, detail="Employer not found")

        row = await conn.fetchrow(
            """
            INSERT INTO public.employer_outreach
              (employer_id, job_id, applicant_id, match_id, subject, body, ai_generated, status, sent_at)
            VALUES ($1, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, 'sent', NOW())
            RETURNING id::text, sent_at::text
            """,
            employer_id,
            body.job_id,
            body.applicant_id,
            body.match_id,
            body.subject,
            body.body,
            body.ai_generated,
        )

        # Log engagement event
        await conn.execute(
            """
            INSERT INTO public.engagement_events
              (employer_id, job_id, applicant_id, match_id, event_type, event_data)
            VALUES ($1, $2::uuid, $3::uuid, $4::uuid, 'outreach_sent', $5::jsonb)
            """,
            employer_id,
            body.job_id,
            body.applicant_id,
            body.match_id,
            {"ai_generated": body.ai_generated, "subject": body.subject},
        )

    return OutreachSendResponse(
        outreach_id=row["id"],
        sent_at=row["sent_at"],
    )


# ---------------------------------------------------------------------------
# POST /employer/me/jobs/{job_id}/candidates/{applicant_id}/hire
# ---------------------------------------------------------------------------

class HireOutcomeRequest(_BaseModel):
    outcome_type: str = "hired"  # 'hired' | 'declined' | 'withdrew'
    match_id: str | None = None
    hire_date: str | None = None
    notes: str | None = None


class HireOutcomeResponse(_BaseModel):
    outcome_id: str
    outcome_type: str
    created_at: str


@router.post(
    "/me/jobs/{job_id}/candidates/{applicant_id}/hire",
    response_model=HireOutcomeResponse,
    status_code=201,
)
async def report_hire_outcome(
    job_id: str,
    applicant_id: str,
    body: HireOutcomeRequest,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> HireOutcomeResponse:
    """
    Report a hire outcome (hired / declined / withdrew) for a candidate.
    Employers may only report for their own jobs.
    """
    valid_outcomes = {"hired", "declined", "withdrew"}
    if body.outcome_type not in valid_outcomes:
        raise HTTPException(
            status_code=422,
            detail=f"outcome_type must be one of: {', '.join(sorted(valid_outcomes))}",
        )

    from datetime import date as _date

    async with get_db() as conn:
        is_admin = current_user.is_admin
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        # Verify job belongs to employer (or is admin)
        if is_admin:
            emp_id = await conn.fetchval(
                "SELECT employer_id FROM public.jobs WHERE id = $1::uuid", job_id
            )
            employer_id = emp_id

        if not employer_id:
            raise HTTPException(status_code=404, detail="Job not found")

        if not is_admin:
            owns = await conn.fetchval(
                "SELECT id FROM public.jobs WHERE id = $1::uuid AND employer_id = $2",
                job_id, employer_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Job not found")

        hire_date = None
        if body.hire_date:
            try:
                hire_date = _date.fromisoformat(body.hire_date)
            except ValueError:
                pass

        row = await conn.fetchrow(
            """
            INSERT INTO public.hire_outcomes
              (applicant_id, job_id, employer_id, match_id, outcome_type, hire_date, notes, reported_by)
            VALUES ($1::uuid, $2::uuid, $3, $4::uuid, $5, $6, $7, $8)
            ON CONFLICT (applicant_id, job_id) DO UPDATE
              SET outcome_type = EXCLUDED.outcome_type,
                  hire_date    = EXCLUDED.hire_date,
                  notes        = EXCLUDED.notes,
                  reported_by  = EXCLUDED.reported_by,
                  updated_at   = NOW()
            RETURNING id::text, outcome_type, created_at::text
            """,
            applicant_id,
            job_id,
            employer_id,
            body.match_id,
            body.outcome_type,
            hire_date,
            body.notes,
            current_user.user_id,
        )

        # Log engagement event
        await conn.execute(
            """
            INSERT INTO public.engagement_events
              (employer_id, job_id, applicant_id, event_type, event_data)
            VALUES ($1, $2::uuid, $3::uuid, 'hire_reported', $4::jsonb)
            """,
            employer_id,
            job_id,
            applicant_id,
            {"outcome_type": body.outcome_type},
        )

    return HireOutcomeResponse(
        outcome_id=row["id"],
        outcome_type=row["outcome_type"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# GET /employer/me/analytics
# ---------------------------------------------------------------------------

class EmployerAnalytics(_BaseModel):
    outreach_sent: int
    candidates_interested: int
    candidates_applied: int
    hired_count: int
    declined_count: int
    recent_outreach: list[dict]


@router.get("/me/analytics", response_model=EmployerAnalytics)
async def get_employer_analytics(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> EmployerAnalytics:
    """Return engagement and outcome analytics for this employer."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        outreach_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.employer_outreach WHERE employer_id = $1 AND status = 'sent'",
            employer_id,
        )

        interested_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT sj.applicant_id)
            FROM public.saved_jobs sj
            JOIN public.jobs j ON j.id = sj.job_id
            WHERE j.employer_id = $1 AND sj.interest_level = 'interested'
            """,
            employer_id,
        )

        applied_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT sj.applicant_id)
            FROM public.saved_jobs sj
            JOIN public.jobs j ON j.id = sj.job_id
            WHERE j.employer_id = $1 AND sj.interest_level = 'applied'
            """,
            employer_id,
        )

        hired_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes WHERE employer_id = $1 AND outcome_type = 'hired'",
            employer_id,
        )

        declined_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.hire_outcomes WHERE employer_id = $1 AND outcome_type = 'declined'",
            employer_id,
        )

        recent_rows = await conn.fetch(
            """
            SELECT
                eo.id::text,
                eo.subject,
                eo.sent_at::text,
                a.first_name,
                a.last_name,
                j.title_normalized AS job_title
            FROM public.employer_outreach eo
            JOIN public.applicants a ON a.id = eo.applicant_id
            JOIN public.jobs j ON j.id = eo.job_id
            WHERE eo.employer_id = $1 AND eo.status = 'sent'
            ORDER BY eo.sent_at DESC NULLS LAST
            LIMIT 10
            """,
            employer_id,
        )

    return EmployerAnalytics(
        outreach_sent=int(outreach_count or 0),
        candidates_interested=int(interested_count or 0),
        candidates_applied=int(applied_count or 0),
        hired_count=int(hired_count or 0),
        declined_count=int(declined_count or 0),
        recent_outreach=[
            {
                "id": r["id"],
                "subject": r["subject"],
                "sent_at": r["sent_at"],
                "applicant_name": " ".join(filter(None, [r["first_name"], r["last_name"]])),
                "job_title": r["job_title"],
            }
            for r in recent_rows
        ],
    )


# ---------------------------------------------------------------------------
# GET /employer/me/jobs/{job_id}/applicants/ai-priority
# ---------------------------------------------------------------------------

class AIPriorityCandidate(_BaseModel):
    match_id: str
    applicant_id: str
    name: str
    score: float | None
    eligibility_status: str
    reason: str


class AIPriorityResponse(_BaseModel):
    job_title: str
    priorities: list[AIPriorityCandidate]
    generated: bool  # False when API key missing (returns score-based order only)


@router.get(
    "/me/jobs/{job_id}/applicants/ai-priority",
    response_model=AIPriorityResponse,
)
async def ai_prioritize_candidates(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> AIPriorityResponse:
    """
    Use AI to rank the top matched candidates for a job and explain
    why each is worth reaching out to first.

    Falls back to score order (no LLM reason) when OPENAI_API_KEY is absent.
    """
    from app.config import get_settings

    async with get_db() as conn:
        is_admin = current_user.role == "admin"
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        # Fetch the job title + employer scope check
        job_row = await conn.fetchrow(
            """
            SELECT COALESCE(j.title_normalized, j.title_raw) AS title
            FROM public.jobs j
            WHERE j.id = $1::uuid AND ($2 OR j.employer_id = $3)
            """,
            job_id, is_admin, employer_id,
        )
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        # Fetch top 10 eligible/near-fit candidates
        rows = await conn.fetch(
            """
            SELECT
                m.id::text AS match_id,
                a.id::text AS applicant_id,
                CONCAT(a.first_name, ' ', a.last_name) AS name,
                m.policy_adjusted_score,
                m.eligibility_status::text,
                m.top_strengths,
                m.top_gaps,
                m.recommended_next_step
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            WHERE m.job_id = $1::uuid
              AND m.is_visible_to_employer = TRUE
              AND m.eligibility_status IN ('eligible', 'near_fit')
            ORDER BY m.policy_adjusted_score DESC NULLS LAST
            LIMIT 10
            """,
            job_id,
        )

    if not rows:
        return AIPriorityResponse(
            job_title=job_row["title"], priorities=[], generated=False
        )

    candidates = [dict(r) for r in rows]
    job_title = job_row["title"]
    api_key = get_settings().openai_api_key

    # Build AI reasons if key is available
    ai_reasons: dict[str, str] = {}
    if api_key:
        try:
            import httpx, json as _json

            candidate_lines = []
            for i, c in enumerate(candidates, 1):
                strengths = "; ".join((c.get("top_strengths") or [])[:2]) or "—"
                gaps = "; ".join((c.get("top_gaps") or [])[:2]) or "—"
                score = round(float(c["policy_adjusted_score"])) if c.get("policy_adjusted_score") else "?"
                candidate_lines.append(
                    f"{i}. {c['name'].strip()} | Score: {score} | {c['eligibility_status']} | "
                    f"Strengths: {strengths} | Gaps: {gaps}"
                )

            prompt = (
                f"You are helping an employer prioritize which candidates to contact first "
                f"for the '{job_title}' role. For each candidate below, write ONE sentence "
                f"(max 20 words) explaining why they stand out or should be contacted first. "
                f"Focus on their unique strengths, readiness, or fit.\n\n"
                + "\n".join(candidate_lines)
                + '\n\nReturn JSON: {"reasons": [{"rank": 1, "reason": "..."}, ...]}'
            )

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                        "max_tokens": 400,
                        "response_format": {"type": "json_object"},
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                parsed = _json.loads(data["choices"][0]["message"]["content"])
                for i, item in enumerate(parsed.get("reasons", [])):
                    if i < len(candidates):
                        ai_reasons[candidates[i]["applicant_id"]] = item.get("reason", "")
        except Exception as exc:
            logger.warning("AI priority generation failed: %s", exc)

    priorities = [
        AIPriorityCandidate(
            match_id=c["match_id"],
            applicant_id=c["applicant_id"],
            name=c["name"].strip(),
            score=float(c["policy_adjusted_score"]) if c.get("policy_adjusted_score") is not None else None,
            eligibility_status=c["eligibility_status"],
            reason=ai_reasons.get(c["applicant_id"], "Ranked by match score."),
        )
        for c in candidates
    ]

    return AIPriorityResponse(
        job_title=job_title,
        priorities=priorities,
        generated=bool(ai_reasons),
    )
