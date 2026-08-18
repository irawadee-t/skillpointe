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
from pydantic import Field as _Field
from pydantic import field_validator as _field_validator

from app.auth.dependencies import require_employer_only, require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.schemas.employer import (
    ApplicantMatchSummary,
    CompanySettingsPatch,
    EmployerCompanySummary,
    EmployerJobFacets,
    EmployerJobsListResponse,
    EmployerJobSummary,
    JobCreateRequest,
    JobCreateResponse,
    JobDetail,
    JobUpdateRequest,
    RankedApplicantsResponse,
)
from app.services.explanation_voice import (
    fallback_priority_reason,
    next_step_for_employer,
    to_employer_voice,
    validate_priority_reason,
)
from app.util.audit import write_audit
from app.util.filters import csv_values, parse_iso_date
from app.util.job_filters import (
    STALE_PRED,
    JobFilterParams,
    build_job_conditions,
    resolve_sort,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employer", tags=["employer"])


# ---------------------------------------------------------------------------
# POST /employer/me/company/create — self-serve employer onboarding
# ---------------------------------------------------------------------------

class CompanyCreateRequest(_BaseModel):
    name: str = _Field(min_length=1, max_length=200)
    industry: str | None = _Field(default=None, max_length=120)
    city: str | None = _Field(default=None, max_length=120)
    state: str | None = _Field(default=None, max_length=50)
    website: str | None = _Field(default=None, max_length=500)
    description: str | None = _Field(default=None, max_length=5000)
    # Optional contact fields captured from Step 2 (stored on the contact row's title
    # slot where useful; email/phone live on auth.users and account settings).
    contact_title: str | None = _Field(default=None, max_length=120)

    @_field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class CompanyCreateResponse(_BaseModel):
    employer_id: str
    name: str


@router.post(
    "/me/company/create",
    response_model=CompanyCreateResponse,
    status_code=201,
)
async def create_my_company(
    body: CompanyCreateRequest,
    # Admins never onboard as an employer themselves; this endpoint links the
    # caller's user_id to a new employer_contacts row.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> CompanyCreateResponse:
    """
    Self-serve employer company creation.

    Creates an employers row and links the current user via employer_contacts.
    Idempotent-ish: if the user already has a linked employer, returns 409 so
    the client can redirect back to the dashboard.

    Wizard fields:
      Step 1 — name, industry, city, state, website, description
      Step 2 — contact_title (hiring lead title)
      Step 3 — no fields; user either clicks "Post job" (routes to /employer/jobs/new)
               or "Skip for now" (routes to /employer).
    """
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail="Company name is required.")

    description = body.description
    if description and len(description) > 400:
        description = description[:400]

    async with get_db() as conn:
        existing = await conn.fetchval(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
            current_user.user_id,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You're already linked to a company.",
            )

        emp_row = await conn.fetchrow(
            """
            INSERT INTO public.employers
              (name, industry, city, state, website, description, source)
            VALUES ($1, $2, $3, $4, $5, $6, 'self_serve_onboarding')
            RETURNING id::text, name
            """,
            body.name.strip(),
            body.industry,
            body.city,
            body.state,
            body.website,
            description,
        )

        await conn.execute(
            """
            INSERT INTO public.employer_contacts
              (user_id, employer_id, is_primary, title)
            VALUES ($1, $2::uuid, TRUE, $3)
            ON CONFLICT (user_id) DO UPDATE
              SET employer_id = EXCLUDED.employer_id,
                  is_primary  = EXCLUDED.is_primary,
                  title       = COALESCE(EXCLUDED.title, public.employer_contacts.title),
                  updated_at  = NOW()
            """,
            current_user.user_id,
            emp_row["id"],
            body.contact_title,
        )

    return CompanyCreateResponse(
        employer_id=emp_row["id"],
        name=emp_row["name"],
    )


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
                e.accepts_internal_applications_default,
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
        accepts_internal_applications_default=bool(row["accepts_internal_applications_default"]),
    )


# ---------------------------------------------------------------------------
# PATCH /employer/me/company — employer-editable settings
# ---------------------------------------------------------------------------

@router.patch("/me/company", response_model=EmployerCompanySummary)
async def patch_my_company(
    body: CompanySettingsPatch,
    # Company settings are an employer decision — admin never flips them
    # on an employer's behalf (CLAUDE.md "admin cannot act as employer").
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> EmployerCompanySummary:
    """
    Update employer-editable company settings. Currently:
      - accepts_internal_applications_default: company-wide default for
        "Accept applications on SKILLED Nation" on jobs that don't set
        their own per-job flag.
    """
    if body.accepts_internal_applications_default is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No settings provided to update.",
        )

    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        await conn.execute(
            """
            UPDATE public.employers
               SET accepts_internal_applications_default = $2,
                   updated_at = NOW()
             WHERE id = $1
            """,
            employer_id,
            body.accepts_internal_applications_default,
        )

    return await get_my_company(current_user=current_user)


# ---------------------------------------------------------------------------
# GET /employer/me/jobs
# ---------------------------------------------------------------------------

@router.get("/me/jobs", response_model=EmployerJobsListResponse)
async def list_my_jobs(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    q: str | None = Query(None, max_length=160, description="Title search"),
    families: str | None = Query(None, description="Comma-separated family codes"),
    states: str | None = Query(None, description="Comma-separated state codes"),
    city: str | None = Query(None, max_length=120),
    employment_types: str | None = Query(None),
    sources: str | None = Query(None),
    job_status: str | None = Query(None, alias="status", description="active | inactive | stale"),
    apply_link: str | None = Query(None, description="ok | broken | unchecked"),
    has_pay: bool | None = Query(None),
    pay_gte: float | None = Query(None, ge=0),
    internal_apply: bool | None = Query(None),
    posted_from: str | None = Query(None),
    posted_to: str | None = Query(None),
    candidates: str | None = Query(None, description="none | 1_9 | 10_49 | over_50"),
    sort: str = Query("newest", description="newest | posted | title | pay"),
) -> EmployerJobsListResponse:
    """
    Return this employer's jobs with per-job applicant counts, optionally
    narrowed by the same granular filters as the admin jobs console.

    Employer isolation: `j.employer_id = $1` is bound FIRST, outside the
    filter builder — no filter combination can widen visibility beyond the
    caller's own jobs (see tests/test_granular_job_filters.py).
    """
    fp = JobFilterParams(
        q=q or None,
        families=csv_values(families),
        states=csv_values(states, upper=True),
        city=city or None,
        employment_types=csv_values(employment_types),
        sources=csv_values(sources),
        status=job_status or None,
        apply_link=apply_link or None,
        has_pay=has_pay,
        pay_gte=pay_gte,
        internal_apply=internal_apply,
        posted_from=parse_iso_date(posted_from, "posted_from"),
        posted_to=parse_iso_date(posted_to, "posted_to"),
        candidates=candidates or None,
    )
    order_by = resolve_sort(sort)

    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        supports_internal = bool(await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'jobs' "
            "  AND column_name = 'accepts_internal_applications'"
        ))

        # Isolation predicate first; filters can only narrow within it.
        params: list[Any] = [employer_id]
        conditions = ["j.employer_id = $1"] + build_job_conditions(
            fp, params, internal_apply_supported=supports_internal
        )
        where = " AND ".join(conditions)

        rows = await conn.fetch(
            f"""
            SELECT
                j.id,
                j.title_normalized,
                j.title_raw,
                j.city,
                j.state,
                j.work_setting::text,
                j.is_active,
                (j.is_active = TRUE AND {STALE_PRED}) AS is_stale,
                j.posted_date::text,
                j.created_at::text,
                jf.code AS family_code,
                jf.name AS family_name,
                j.employment_type,
                j.pay_min, j.pay_max, j.pay_type, j.pay_raw,
                j.source, j.source_site,
                j.apply_link_status,
                j.status AS job_status, j.previous_status,
                -- Delete is only honest for jobs with zero recorded activity.
                (EXISTS (SELECT 1 FROM public.applications ap WHERE ap.job_id = j.id)
                 OR EXISTS (SELECT 1 FROM public.saved_jobs sj WHERE sj.job_id = j.id)
                 OR EXISTS (SELECT 1 FROM public.hire_outcomes ho WHERE ho.job_id = j.id)
                 OR EXISTS (SELECT 1 FROM public.employer_outreach eo WHERE eo.job_id = j.id)
                ) AS has_activity,
                fresh.last_seen_at AS source_last_seen_at,
                fresh.vanished_at AS source_vanished_at,
                -- total_visible must carry the SAME eligibility predicate as the
                -- candidate list endpoint (eligible/near_fit only) — otherwise
                -- "View matched candidates (N)" counts ineligible matches the
                -- list never shows.
                COUNT(m.id) FILTER (
                    WHERE m.is_visible_to_employer = TRUE
                      AND m.eligibility_status IN ('eligible', 'near_fit')
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
            LEFT JOIN public.employers e ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            LEFT JOIN public.matches m ON m.job_id = j.id
            -- Freshness from career-source fingerprint memory: when this
            -- exact posting URL was last seen on the employer's own site.
            LEFT JOIN LATERAL (
                SELECT csj.last_seen_at, csj.vanished_at
                  FROM public.career_source_jobs csj
                  JOIN public.employer_career_sources cs ON cs.id = csj.source_id
                 WHERE cs.employer_id = j.employer_id
                   AND csj.source_url = j.source_url
                 ORDER BY csj.last_seen_at DESC
                 LIMIT 1
            ) fresh ON j.source_url IS NOT NULL
            WHERE {where}
            GROUP BY j.id, jf.code, jf.name, fresh.last_seen_at, fresh.vanished_at
            ORDER BY {order_by}
            """,
            *params,
        )

        name_row = await conn.fetchval(
            "SELECT name FROM public.employers WHERE id = $1", employer_id
        )
        unfiltered_total = await conn.fetchval(
            "SELECT COUNT(*) FROM public.jobs j WHERE j.employer_id = $1", employer_id
        )
        facet_rows = await conn.fetch(
            """
            SELECT DISTINCT jf.code AS family_code, jf.name AS family_name,
                   UPPER(TRIM(j.state)) AS state, j.source, j.employment_type
            FROM public.jobs j
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE j.employer_id = $1
            """,
            employer_id,
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
            family_code=r["family_code"],
            family_name=r["family_name"],
            employment_type=r["employment_type"],
            pay_min=float(r["pay_min"]) if r["pay_min"] is not None else None,
            pay_max=float(r["pay_max"]) if r["pay_max"] is not None else None,
            pay_type=r["pay_type"],
            pay_raw=r["pay_raw"],
            source=r["source"],
            source_site=r["source_site"],
            is_stale=bool(r["is_stale"]),
            apply_link_status=r["apply_link_status"],
            status=r["job_status"] or "active",
            previous_status=r["previous_status"],
            has_activity=bool(r["has_activity"]),
            source_last_seen_at=(
                r["source_last_seen_at"].isoformat() if r["source_last_seen_at"] else None
            ),
            source_vanished_at=(
                r["source_vanished_at"].isoformat() if r["source_vanished_at"] else None
            ),
        )
        for r in rows
    ]

    families_seen: dict[str, str] = {}
    states_seen: set[str] = set()
    sources_seen: set[str] = set()
    et_seen: set[str] = set()
    for r in facet_rows:
        if r["family_code"]:
            families_seen[r["family_code"]] = r["family_name"] or r["family_code"]
        if r["state"]:
            states_seen.add(r["state"])
        if r["source"]:
            sources_seen.add(r["source"])
        if r["employment_type"]:
            et_seen.add(r["employment_type"])

    return EmployerJobsListResponse(
        employer_id=str(employer_id),
        company_name=name_row or "",
        jobs=jobs,
        total_jobs=len(jobs),
        unfiltered_total=int(unfiltered_total or 0),
        supports_internal_apply=supports_internal,
        facets=EmployerJobFacets(
            families=[
                {"value": c, "label": n}
                for c, n in sorted(families_seen.items(), key=lambda kv: kv[1])
            ],
            states=sorted(states_seen),
            sources=sorted(sources_seen),
            employment_types=sorted(et_seen),
        ),
    )


# ---------------------------------------------------------------------------
# GET /employer/me/jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get("/me/jobs/{job_id}", response_model=JobDetail)
async def get_job_detail(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> JobDetail:
    """
    Return full detail for a single job — used to pre-fill the edit form.
    Employers may only fetch jobs they own. Admin can fetch any job.
    """
    async with get_db() as conn:
        is_admin = current_user.is_admin
        if is_admin:
            row = await conn.fetchrow(
                """
                SELECT j.id::text, j.title_raw, j.city, j.state,
                    j.work_setting::text, j.travel_requirement,
                    j.pay_min, j.pay_max, j.pay_type,
                    j.description_raw, j.requirements_raw, j.experience_level,
                    j.is_active,
                    j.accepts_internal_applications,
                    j.required_profile_fields,
                    j.sector_code,
                    jf.code AS field_code,
                    COALESCE(j.accepts_internal_applications,
                             e.accepts_internal_applications_default,
                             FALSE) AS internal_apply_effective
                FROM public.jobs j
                LEFT JOIN public.employers e ON e.id = j.employer_id
                LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
                WHERE j.id = $1::uuid
                """,
                job_id,
            )
        else:
            employer_id = await _resolve_employer_id(conn, current_user.user_id)
            row = await conn.fetchrow(
                """
                SELECT j.id::text, j.title_raw, j.city, j.state,
                    j.work_setting::text, j.travel_requirement,
                    j.pay_min, j.pay_max, j.pay_type,
                    j.description_raw, j.requirements_raw, j.experience_level,
                    j.is_active,
                    j.accepts_internal_applications,
                    j.required_profile_fields,
                    j.sector_code,
                    jf.code AS field_code,
                    COALESCE(j.accepts_internal_applications,
                             e.accepts_internal_applications_default,
                             FALSE) AS internal_apply_effective
                FROM public.jobs j
                LEFT JOIN public.employers e ON e.id = j.employer_id
                LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
                WHERE j.id = $1::uuid AND j.employer_id = $2
                """,
                job_id,
                employer_id,
            )

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

    return JobDetail(
        job_id=row["id"],
        title_raw=row["title_raw"],
        city=row["city"],
        state=row["state"],
        work_setting=row["work_setting"],
        travel_requirement=row["travel_requirement"],
        sector_code=row.get("sector_code"),
        field_code=row.get("field_code"),
        pay_min=float(row["pay_min"]) if row["pay_min"] is not None else None,
        pay_max=float(row["pay_max"]) if row["pay_max"] is not None else None,
        pay_type=row["pay_type"],
        description_raw=row["description_raw"],
        requirements_raw=row["requirements_raw"],
        experience_level=row["experience_level"],
        is_active=bool(row["is_active"]),
        accepts_internal_applications=row["accepts_internal_applications"],
        required_profile_fields=list(row["required_profile_fields"] or []),
        internal_apply_effective=bool(row["internal_apply_effective"]),
    )


# ---------------------------------------------------------------------------
# POST /employer/me/jobs
# ---------------------------------------------------------------------------

@router.post("/me/jobs", response_model=JobCreateResponse, status_code=201)
async def create_job(
    request: JobCreateRequest,
    # Admin cannot post jobs on behalf of an employer.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> JobCreateResponse:
    """
    Create a new job posting for this employer.
    New jobs are active by default (is_active = TRUE).
    """
    from app.util.taxonomy_api import (
        default_sector_for_field,
        resolve_family_uuid,
        validate_sector_field,
    )
    validate_sector_field(request.sector_code, request.field_code)
    sector_code = request.sector_code or default_sector_for_field(request.field_code)

    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        family_id = None
        if request.field_code:
            family_id = await resolve_family_uuid(conn, request.field_code)
            if family_id is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown career field '{request.field_code}'.",
                )

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
                sector_code,
                canonical_job_family_id,
                accepts_internal_applications,
                required_profile_fields,
                source
            ) VALUES (
                $1, $2, $3, $4,
                CASE WHEN $5::text IS NOT NULL
                     THEN $5::public.work_setting_enum
                     ELSE NULL
                END,
                $6, $7, $8, $9, $10, $11, $12,
                $13, $14,
                $15,
                COALESCE($16::text[], '{contact,location,program}'::text[]),
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
            sector_code,
            family_id,
            request.accepts_internal_applications,
            request.required_profile_fields,
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
    # Admin cannot edit an employer's job posting.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> JobCreateResponse:
    """
    Update an existing job. Only provided (non-None) fields are updated.
    Returns 404 if job doesn't exist or doesn't belong to this employer.
    """
    from app.util.taxonomy_api import (
        default_sector_for_field,
        resolve_family_uuid,
        validate_sector_field,
    )
    validate_sector_field(request.sector_code, request.field_code)
    effective_sector = request.sector_code or default_sector_for_field(request.field_code)

    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        family_id = None
        if request.field_code:
            family_id = await resolve_family_uuid(conn, request.field_code)
            if family_id is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown career field '{request.field_code}'.",
                )

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
            "sector_code": effective_sector,
            "canonical_job_family_id": family_id,
            "is_active": request.is_active,
            "accepts_internal_applications": request.accepts_internal_applications,
            "required_profile_fields": request.required_profile_fields,
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

    # Fire-and-forget recompute — a title/description/req/pay/location edit
    # can change ranking, so keep matches in sync without blocking the response.
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
# Job lifecycle: PATCH …/status, POST …/status/revert, DELETE …/{job_id}
# ---------------------------------------------------------------------------

# Allowed transitions. Every non-active status hides the job from applicants
# (browse + matching) via the status↔is_active trigger; 'active' restores it.
#   pause   — temporary, resumable
#   filled  — position hired (optionally through the SKILLED hire flow)
#   closed  — terminal but reopenable (the honest alternative to delete)
JOB_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "active": {"paused", "filled", "closed"},
    "paused": {"active", "filled", "closed"},
    "filled": {"active"},
    "closed": {"active"},
}


class JobStatusPatch(_BaseModel):
    status: str = _Field(pattern="^(active|paused|filled|closed)$")


class JobStatusOut(_BaseModel):
    job_id: str
    status: str
    previous_status: str | None
    is_active: bool


def _job_status_out(row: Any) -> JobStatusOut:
    return JobStatusOut(
        job_id=str(row["id"]), status=row["status"],
        previous_status=row["previous_status"], is_active=bool(row["is_active"]),
    )


async def _recompute_if_visibility_changed(was_active: bool, now_active: bool, job_id: str) -> None:
    """Any transition that flips applicant visibility re-ranks this job
    (fire-and-forget, debounced — same path as job create/edit)."""
    if was_active == now_active:
        return
    import asyncio as _asyncio

    from app.worker.scheduler import trigger_recompute_for_job
    _asyncio.create_task(trigger_recompute_for_job(job_id))


@router.patch("/me/jobs/{job_id}/status", response_model=JobStatusOut)
async def set_job_status(
    job_id: str,
    request: JobStatusPatch,
    # Lifecycle decisions are employer acts; admin views are read-only.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> JobStatusOut:
    """Move a job through its lifecycle (active | paused | filled | closed).

    Guarded by the transition matrix; every change stores previous_status for
    the revert endpoint, writes audit_logs, and re-ranks matches when
    applicant visibility flipped. Engagement/analytics history is untouched —
    filled and closed jobs keep their full record.
    """
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        row = await conn.fetchrow(
            "SELECT id, status, is_active FROM public.jobs "
            "WHERE id = $1::uuid AND employer_id = $2",
            job_id, employer_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        current = row["status"] or "active"
        target = request.status
        if target == current:
            # Idempotent no-op — the UI's optimistic state is already right.
            full = await conn.fetchrow(
                "SELECT id, status, previous_status, is_active FROM public.jobs WHERE id = $1::uuid",
                job_id,
            )
            return _job_status_out(full)
        if target not in JOB_STATUS_TRANSITIONS.get(current, set()):
            raise HTTPException(
                status_code=409,
                detail=f"A {current} job can't move to {target}.",
            )

        updated = await conn.fetchrow(
            """
            UPDATE public.jobs
               SET status = $3, previous_status = $4
             WHERE id = $1::uuid AND employer_id = $2 AND status = $4
            RETURNING id, status, previous_status, is_active
            """,
            job_id, employer_id, target, current,
        )
        if not updated:
            raise HTTPException(
                status_code=409,
                detail="This job changed underneath you. Refresh and try again.",
            )
        await write_audit(
            conn, action="job_status_changed",
            actor_id=current_user.user_id, actor_role=current_user.role,
            entity_type="job", entity_id=job_id,
            before={"status": current}, after={"status": target},
            metadata={"employer_id": str(employer_id)},
        )

    await _recompute_if_visibility_changed(
        bool(row["is_active"]), bool(updated["is_active"]), job_id,
    )
    return _job_status_out(updated)


@router.post("/me/jobs/{job_id}/status/revert", response_model=JobStatusOut)
async def revert_job_status(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> JobStatusOut:
    """REAL undo for the last lifecycle transition: restores previous_status
    (race-safe, single-shot — previous_status clears on revert). Audited."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        row = await conn.fetchrow(
            "SELECT id, status, previous_status, is_active FROM public.jobs "
            "WHERE id = $1::uuid AND employer_id = $2",
            job_id, employer_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        prev = row["previous_status"]
        if not prev or prev == row["status"]:
            raise HTTPException(status_code=409, detail="Nothing to revert on this job.")

        updated = await conn.fetchrow(
            """
            UPDATE public.jobs
               SET status = $3, previous_status = NULL
             WHERE id = $1::uuid AND employer_id = $2 AND status = $4
            RETURNING id, status, previous_status, is_active
            """,
            job_id, employer_id, prev, row["status"],
        )
        if not updated:
            raise HTTPException(
                status_code=409,
                detail="This job changed underneath you. Refresh and try again.",
            )
        await write_audit(
            conn, action="job_status_reverted",
            actor_id=current_user.user_id, actor_role=current_user.role,
            entity_type="job", entity_id=job_id,
            before={"status": row["status"]}, after={"status": prev},
            metadata={"employer_id": str(employer_id)},
        )

    await _recompute_if_visibility_changed(
        bool(row["is_active"]), bool(updated["is_active"]), job_id,
    )
    return _job_status_out(updated)


@router.delete("/me/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> dict[str, bool]:
    """Delete a posting — ONLY when it has zero recorded activity (no
    applications, saved-job interest, outreach, or hire outcomes). A job with
    history keeps that history honest: Close it instead. Audited."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        row = await conn.fetchrow(
            """
            SELECT j.id, j.title_raw, j.status,
                   (EXISTS (SELECT 1 FROM public.applications a WHERE a.job_id = j.id)
                    OR EXISTS (SELECT 1 FROM public.saved_jobs s WHERE s.job_id = j.id)
                    OR EXISTS (SELECT 1 FROM public.hire_outcomes h WHERE h.job_id = j.id)
                    OR EXISTS (SELECT 1 FROM public.employer_outreach o WHERE o.job_id = j.id)
                   ) AS has_activity
              FROM public.jobs j
             WHERE j.id = $1::uuid AND j.employer_id = $2
            """,
            job_id, employer_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["has_activity"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This job has candidate activity, so its record stays. "
                    "Close it instead of deleting."
                ),
            )
        await write_audit(
            conn, action="job_deleted",
            actor_id=current_user.user_id, actor_role=current_user.role,
            entity_type="job", entity_id=job_id,
            before={"status": row["status"], "title": row["title_raw"]},
            metadata={"employer_id": str(employer_id)},
        )
        await conn.execute(
            "DELETE FROM public.jobs WHERE id = $1::uuid AND employer_id = $2",
            job_id, employer_id,
        )
    return {"ok": True}


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
    q: Annotated[
        str | None,
        Query(max_length=120, description="Search applicant name (partial, case-insensitive)"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page")] = 25,
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

        # Instrument the employer-activation funnel ("reviewed applicants") —
        # server-side, deduped to one event per employer/job/day. Admin views
        # deliberately do NOT count as employer activity.
        if not is_admin and employer_id:
            await conn.execute(
                """
                INSERT INTO public.engagement_events (employer_id, job_id, event_type, event_data)
                SELECT $1, j.id, 'candidate_viewed', '{}'::jsonb
                FROM public.jobs j
                WHERE j.id = $2::uuid AND j.employer_id = $1
                  AND NOT EXISTS (
                    SELECT 1 FROM public.engagement_events ee
                    WHERE ee.employer_id = $1 AND ee.job_id = $2::uuid
                      AND ee.event_type = 'candidate_viewed'
                      AND ee.created_at >= date_trunc('day', now())
                  )
                """,
                employer_id,
                job_id,
            )

        # Fetch total counts (pre-filter) for dashboard display.
        # CRITICAL: the LEFT JOIN predicates here must match the base predicates
        # of the list query below (visible to employer AND eligible/near_fit),
        # otherwise the header counts disagree with the rendered list.
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
                    ON m.job_id = j.id
                   AND m.is_visible_to_employer = TRUE
                   AND m.eligibility_status IN ('eligible', 'near_fit')
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
                    ON m.job_id = j.id
                   AND m.is_visible_to_employer = TRUE
                   AND m.eligibility_status IN ('eligible', 'near_fit')
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

        if q and q.strip():
            conditions.append(
                f"(a.first_name ILIKE ${idx} OR a.last_name ILIKE ${idx} "
                f"OR (COALESCE(a.first_name, '') || ' ' || COALESCE(a.last_name, '')) ILIKE ${idx})"
            )
            params.append(f"%{q.strip()}%")
            idx += 1

        where_clause = " AND ".join(conditions)

        # Count of the FILTERED list (pagination denominator). Predicate parity:
        # exactly the same where_clause as the list query below.
        filtered_total = int(
            await conn.fetchval(
                f"""
                SELECT COUNT(*)
                FROM public.matches m
                JOIN public.applicants a  ON a.id = m.applicant_id
                JOIN public.jobs j        ON j.id = m.job_id
                WHERE {where_clause}
                """,
                *params,
            )
            or 0
        )

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
                m.distance_miles,
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
            ORDER BY m.n_gaps ASC NULLS LAST, m.policy_adjusted_score DESC NULLS LAST
            LIMIT ${ idx } OFFSET ${ idx + 1 }
            """,
            *params,
            per_page,
            (page - 1) * per_page,
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
        filtered_total=filtered_total,
        page=page,
        per_page=per_page,
        total_pages=max(1, (filtered_total + per_page - 1) // per_page),
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
    """Convert a DB row to an ApplicantMatchSummary (safe fields only).

    Stored explanations are written in the applicant's voice; everything an
    employer reads is re-voiced deterministically (same facts, employer
    perspective) via services/explanation_voice.
    """
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
        top_strengths=[
            to_employer_voice(s) for s in _safe_list(row.get("top_strengths"))
        ],
        top_gaps=[to_employer_voice(g) for g in _safe_list(row.get("top_gaps"))],
        recommended_next_step=next_step_for_employer(row.get("recommended_next_step")),
        confidence_level=row.get("confidence_level"),
        requires_review=bool(row.get("requires_review", False)),
        geography_note=_derive_applicant_geography_note(row),
        applicant_interest=row.get("applicant_interest"),
    )


def _derive_applicant_geography_note(row: dict[str, Any]) -> str | None:
    """
    Human-readable geography note from the employer's perspective:
    applicant's location relative to the job.

    "Local" is a factual proximity claim — only made with a verified
    distance (matches.distance_miles, geodesic home → job city). Same-state
    alone is NOT local: El Paso → Dallas is 570 mi. Without a distance we
    say "same state", never "Local".
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

    dist = _safe_float(row.get("distance_miles"))
    mobility: list[str] = []
    if willing_to_relocate:
        mobility.append("open to relocate")
    if willing_to_travel:
        mobility.append("open to travel")
    mobility_str = f" ({', '.join(mobility)})" if mobility else ""

    # Fold mobility into the same parenthetical as the distance so the note
    # never renders back-to-back paren groups.
    mobility_inline = f", {', '.join(mobility)}" if mobility else ""

    if dist is not None:
        d = round(dist)
        if d <= 25:
            return f"Local: {location_str} (~{d} mi from job)"
        if d <= 75:
            return f"{location_str} (~{d} mi from job{mobility_inline})"
        return f"{location_str} (~{d} mi away{mobility_inline})"

    # No verified distance: same city+state string match still supports a
    # "Local" claim (mirrors the engine's same-city gate rule); same state
    # alone does not.
    job_city = row.get("job_city")
    if (
        job_state and app_state.upper() == job_state.upper()
        and app_city and job_city
        and str(app_city).strip().lower() == str(job_city).strip().lower()
    ):
        return f"Local: {location_str}"

    if job_state and app_state.upper() == job_state.upper():
        return f"{location_str} (same state as job)"

    if mobility:
        return f"{location_str}{mobility_str}"
    return f"{location_str} (different state)"


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
    subject: str = _Field(min_length=1, max_length=200)
    body: str = _Field(min_length=1, max_length=5000)
    ai_generated: bool = False

    @_field_validator("subject", "body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


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
    # Admin must not send outreach on behalf of an employer — CLAUDE.md guardrail.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> OutreachSendResponse:
    """Record that an outreach message was sent to a candidate."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        if not employer_id:
            raise HTTPException(status_code=404, detail="Employer not found")

        # Employer isolation: the job/match being outreached on MUST belong to
        # this employer (mirrors the draft endpoint). Without this, any employer
        # could record outreach — and pollute analytics — against another
        # employer's job and candidates.
        owns = await conn.fetchval(
            """
            SELECT 1
            FROM public.matches m
            JOIN public.jobs j ON j.id = m.job_id
            WHERE m.id = $1::uuid AND j.id = $2::uuid
              AND m.applicant_id = $3::uuid AND j.employer_id = $4
            """,
            body.match_id, body.job_id, body.applicant_id, employer_id,
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Match not found")

        # Business row + its analytics event commit atomically: an outreach with
        # a lost event (or vice versa) permanently skews the funnel.
        async with conn.transaction():
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

            # Log engagement event. outreach_id lets the undo path retract this
            # exact event, so analytics never count an undone outreach.
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
                {"ai_generated": body.ai_generated, "subject": body.subject,
                 "outreach_id": str(row["id"])},
            )

    return OutreachSendResponse(
        outreach_id=row["id"],
        sent_at=row["sent_at"],
    )


# ---------------------------------------------------------------------------
# GET /employer/me/outreach/history — prior outreach to a candidate for a job
# ---------------------------------------------------------------------------

class OutreachHistoryItem(_BaseModel):
    outreach_id: str
    sent_at: str | None
    subject: str | None


class OutreachHistoryResponse(_BaseModel):
    items: list[OutreachHistoryItem]


@router.get("/me/outreach/history", response_model=OutreachHistoryResponse)
async def get_outreach_history(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    applicant_id: str = Query(..., description="Applicant to check history for"),
    job_id: str | None = Query(None, description="Optional job filter"),
) -> OutreachHistoryResponse:
    """Return prior outreach records to a candidate — most recent first."""
    async with get_db() as conn:
        is_admin = current_user.is_admin
        employer_id = None if is_admin else await _resolve_employer_id(conn, current_user.user_id)

        if is_admin and job_id:
            emp_id = await conn.fetchval(
                "SELECT employer_id FROM public.jobs WHERE id = $1::uuid", job_id
            )
            employer_id = emp_id

        if not employer_id:
            return OutreachHistoryResponse(items=[])

        if job_id:
            rows = await conn.fetch(
                """
                SELECT id::text AS outreach_id, sent_at::text, subject
                FROM public.employer_outreach
                WHERE employer_id = $1 AND applicant_id = $2::uuid AND job_id = $3::uuid
                  AND status = 'sent'
                ORDER BY sent_at DESC NULLS LAST LIMIT 20
                """,
                employer_id, applicant_id, job_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id::text AS outreach_id, sent_at::text, subject
                FROM public.employer_outreach
                WHERE employer_id = $1 AND applicant_id = $2::uuid AND status = 'sent'
                ORDER BY sent_at DESC NULLS LAST LIMIT 20
                """,
                employer_id, applicant_id,
            )

    return OutreachHistoryResponse(
        items=[
            OutreachHistoryItem(
                outreach_id=r["outreach_id"],
                sent_at=r["sent_at"],
                subject=r["subject"],
            )
            for r in rows
        ]
    )


# ---------------------------------------------------------------------------
# DELETE /employer/me/outreach/{outreach_id} — undo a recent send
# ---------------------------------------------------------------------------

@router.delete("/me/outreach/{outreach_id}")
async def delete_outreach(
    outreach_id: str,
    # Admin must not undo an employer's outreach — CLAUDE.md guardrail.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
) -> dict:
    """Delete an outreach record — used by the 10-second undo toast."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        await conn.execute(
            "DELETE FROM public.employer_outreach WHERE id = $1::uuid AND employer_id = $2",
            outreach_id, employer_id,
        )
        # Retract the analytics event too — an undone outreach must not keep
        # inflating the "outreach sent" tiles (one truth per metric).
        await conn.execute(
            "DELETE FROM public.engagement_events "
            "WHERE event_type = 'outreach_sent' AND employer_id = $2 "
            "AND event_data->>'outreach_id' = $1",
            outreach_id, employer_id,
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /employer/me/jobs/{job_id}/candidates/{applicant_id}/hire
# ---------------------------------------------------------------------------

class HireOutcomeRequest(_BaseModel):
    outcome_type: str = "hired"  # 'hired' | 'declined' | 'withdrew'
    match_id: str | None = None
    hire_date: str | None = None
    notes: str | None = _Field(default=None, max_length=5000)

    @_field_validator("hire_date")
    @classmethod
    def _hire_date_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("hire_date must be an ISO date (YYYY-MM-DD)") from exc
        return v
    # Annualized placement wage (USD) — feeds Foundation outcome analytics
    # (median wage). Optional; sane bounds guard against typos.
    reported_wage_annual: int | None = _Field(default=None, ge=1000, le=2_000_000)


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
    # Admin must not report hires on behalf of an employer — CLAUDE.md guardrail.
    current_user: Annotated[CurrentUser, Depends(require_employer_only)],
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
        employer_id = await _resolve_employer_id(conn, current_user.user_id)
        if not employer_id:
            raise HTTPException(status_code=404, detail="Employer not found")

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
        # Time-to-hire analytics require a hire_date; when the employer reports
        # a hire without one, the report date is the best available proxy.
        if hire_date is None and body.outcome_type == "hired":
            hire_date = _date.today()

        row = await conn.fetchrow(
            """
            INSERT INTO public.hire_outcomes
              (applicant_id, job_id, employer_id, match_id, outcome_type, hire_date,
               notes, reported_by, reported_wage_annual)
            VALUES ($1::uuid, $2::uuid, $3, $4::uuid, $5, $6, $7, $8, $9)
            ON CONFLICT (applicant_id, job_id) DO UPDATE
              SET outcome_type = EXCLUDED.outcome_type,
                  hire_date    = EXCLUDED.hire_date,
                  notes        = EXCLUDED.notes,
                  reported_by  = EXCLUDED.reported_by,
                  reported_wage_annual = COALESCE(
                      EXCLUDED.reported_wage_annual,
                      public.hire_outcomes.reported_wage_annual),
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
            body.reported_wage_annual,
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

        # A hired candidate must hear about it no matter which path recorded
        # the hire — this endpoint has no application row requirement, so it
        # notifies directly (same kind as the application-status path; the
        # shared dedupe key keeps double-reports quiet). Notification trouble
        # must never 500 the hire report itself.
        if body.outcome_type == "hired":
            try:
                info = await conn.fetchrow(
                    """
                    SELECT ap.user_id,
                           COALESCE(j.title_normalized, j.title_raw) AS job_title,
                           e.name AS employer_name,
                           (SELECT a.id FROM public.applications a
                             WHERE a.applicant_id = ap.id AND a.job_id = j.id
                             LIMIT 1) AS application_id
                      FROM public.applicants ap
                      JOIN public.jobs j      ON j.id = $2::uuid
                      LEFT JOIN public.employers e ON e.id = j.employer_id
                     WHERE ap.id = $1::uuid
                    """,
                    applicant_id, job_id,
                )
                if info and info["user_id"]:
                    from app.skilled_pro.notifications import notify
                    job_title = info["job_title"] or "the job"
                    employer_name = info["employer_name"] or "The employer"
                    link = (
                        f"/applicant/applications/{info['application_id']}"
                        if info["application_id"] else "/applicant/applications"
                    )
                    await notify(
                        conn,
                        recipient_user_id=str(info["user_id"]),
                        kind="application_hired",
                        title=f"You were hired for {job_title}",
                        body=f"{employer_name} marked you as hired. Congratulations.",
                        link_href=link,
                        payload={
                            "job_id": str(job_id),
                            **({"application_id": str(info["application_id"])} if info["application_id"] else {}),
                        },
                        dedupe_key=(
                            f"application_status:{info['application_id']}:hired"
                            if info["application_id"]
                            else f"hire_outcome:{applicant_id}:{job_id}"
                        ),
                    )
            except Exception as exc:
                logger.warning("Hire notification failed for %s/%s: %s", applicant_id, job_id, exc)

    return HireOutcomeResponse(
        outcome_id=row["id"],
        outcome_type=row["outcome_type"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# GET /employer/me/analytics
# ---------------------------------------------------------------------------

class EmployerAnalytics(_BaseModel):
    """Employer analytics.

    Two distinct, clearly-labeled families of numbers (finding: one surface,
    one truth):
      - applications_*: the REAL pipeline, derived from public.applications —
        the same table the /employer/applications inbox reads. "Applied" on
        the analytics page means an application row, matching the inbox.
      - candidates_interested / candidates_applied: self-reported interest
        signals from saved_jobs (kept for continuity + invariant tests; the
        page presents them as interest signals, never as the pipeline).
    """
    outreach_sent: int
    candidates_interested: int
    candidates_applied: int
    hired_count: int
    declined_count: int
    # Application pipeline (public.applications — same predicates as the inbox
    # buckets: new=submitted, in_review=reviewed|shortlisted,
    # interviewing=interviewing|offered, hired=hired).
    applications_total: int
    applications_new: int
    applications_in_review: int
    applications_interviewing: int
    applications_hired: int
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

        # Application pipeline — identical bucket predicates to the
        # /employer/applications inbox, so both surfaces tell one story.
        pipeline = await conn.fetchrow(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE status = 'submitted') AS new_count,
              COUNT(*) FILTER (WHERE status IN ('reviewed','shortlisted')) AS in_review,
              COUNT(*) FILTER (WHERE status IN ('interviewing','offered')) AS interviewing,
              COUNT(*) FILTER (WHERE status = 'hired') AS hired
            FROM public.applications
            WHERE employer_id = $1
            """,
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
        applications_total=int(pipeline["total"] or 0),
        applications_new=int(pipeline["new_count"] or 0),
        applications_in_review=int(pipeline["in_review"] or 0),
        applications_interviewing=int(pipeline["interviewing"] or 0),
        applications_hired=int(pipeline["hired"] or 0),
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
# GET /employer/me/analytics/insights  (time-to-fill, quality, wage benchmark, AI)
# ---------------------------------------------------------------------------

class EmployerInsights(_BaseModel):
    hires: int
    time_to_fill_days: int | None
    median_wage: int | None
    platform_median_wage: int | None
    wage_vs_platform_pct: int | None
    avg_match_fit: float | None
    strong_matches: int
    surfaced: int
    narrative: str
    narrative_source: str


@router.get("/me/analytics/insights", response_model=EmployerInsights)
async def get_employer_insights(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> EmployerInsights:
    """Hiring intelligence: time-to-fill, match quality, wage benchmarking vs the
    platform median, and an AI-written insight (template fallback)."""
    from app.skilled_pro.ai import generate_employer_insights

    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        ttf = await conn.fetchval(
            """
            SELECT percentile_disc(0.5) WITHIN GROUP (
                ORDER BY (ho.hire_date - j.created_at::date))
            FROM public.hire_outcomes ho JOIN public.jobs j ON j.id = ho.job_id
            WHERE ho.employer_id = $1 AND ho.outcome_type IN ('placed','hired')
              AND ho.hire_date IS NOT NULL
            """,
            employer_id,
        )
        hires = await conn.fetchval(
            "SELECT count(*) FROM public.hire_outcomes "
            "WHERE employer_id = $1 AND outcome_type IN ('placed','hired')",
            employer_id,
        )
        median_wage = await conn.fetchval(
            "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY reported_wage_annual) "
            "FROM public.hire_outcomes WHERE employer_id = $1 AND reported_wage_annual IS NOT NULL",
            employer_id,
        )
        platform_wage = await conn.fetchval(
            "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY reported_wage_annual) "
            "FROM public.hire_outcomes WHERE reported_wage_annual IS NOT NULL"
        )
        fit = await conn.fetchrow(
            """
            SELECT avg(m.base_fit_score) / 100.0 AS avg_fit,
                   count(*) FILTER (WHERE m.base_fit_score >= 70) AS strong,
                   count(*) AS surfaced
            FROM public.matches m JOIN public.jobs j ON j.id = m.job_id
            WHERE j.employer_id = $1
            """,
            employer_id,
        )

    ttf_days = int(ttf) if ttf is not None else None
    mw = int(median_wage) if median_wage is not None else None
    pm = int(platform_wage) if platform_wage is not None else None
    wage_delta = round((mw - pm) / pm * 100) if (mw and pm) else None
    avg_fit = round(float(fit["avg_fit"]), 3) if fit and fit["avg_fit"] is not None else None

    numbers = {
        "hires": int(hires or 0),
        "time_to_fill_days": ttf_days,
        "median_wage": mw,
        "platform_median_wage": pm,
        "avg_match_fit": avg_fit,
        "strong_matches": int(fit["strong"]) if fit else 0,
    }
    narrative, source = await generate_employer_insights(numbers)

    return EmployerInsights(
        hires=int(hires or 0),
        time_to_fill_days=ttf_days,
        median_wage=mw,
        platform_median_wage=pm,
        wage_vs_platform_pct=wage_delta,
        avg_match_fit=avg_fit,
        strong_matches=int(fit["strong"]) if fit else 0,
        surfaced=int(fit["surfaced"]) if fit else 0,
        narrative=narrative,
        narrative_source=source,
    )


# ---------------------------------------------------------------------------
# GET /employer/me/analytics/next-actions  (what should this employer DO next)
# ---------------------------------------------------------------------------

class WaitingCandidate(_BaseModel):
    applicant_id: str
    name: str
    job_id: str
    job_title: str
    interest_level: str  # 'interested' | 'applied'
    since: str | None


class EmployerNextActions(_BaseModel):
    """Action queue for the employer analytics page.

    waiting_candidates: candidates who marked interested/applied on this
    employer's jobs but have received neither a sent outreach nor a DM
    conversation from this employer. unviewed_applications: submitted
    applications the employer has never opened (same predicate family as the
    admin SLA metric, without the 5-day dormancy threshold).
    open_applications: applications still awaiting an employer decision
    (status submitted/reviewed) — the honest "caught up" predicate is
    waiting_candidates == 0 AND open_applications == 0, so a page can never
    say "you're caught up" while the applications inbox holds work.
    """
    waiting_candidates_total: int
    waiting_candidates: list[WaitingCandidate]
    unviewed_applications: int
    open_applications: int


@router.get("/me/analytics/next-actions", response_model=EmployerNextActions)
async def get_employer_next_actions(
    current_user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
) -> EmployerNextActions:
    """Employer-scoped action queue: who is waiting on this employer right now."""
    async with get_db() as conn:
        employer_id = await _resolve_employer_id(conn, current_user.user_id)

        waiting_rows = await conn.fetch(
            """
            SELECT
                sj.applicant_id::text AS applicant_id,
                CONCAT(a.first_name, ' ', a.last_name) AS name,
                j.id::text AS job_id,
                COALESCE(j.title_normalized, j.title_raw) AS job_title,
                sj.interest_level,
                sj.updated_at::text AS since
            FROM public.saved_jobs sj
            JOIN public.jobs j ON j.id = sj.job_id AND j.employer_id = $1
            JOIN public.applicants a ON a.id = sj.applicant_id
            WHERE sj.interest_level IN ('interested', 'applied')
              AND NOT EXISTS (
                  SELECT 1 FROM public.employer_outreach eo
                  WHERE eo.employer_id = $1
                    AND eo.applicant_id = sj.applicant_id
                    AND eo.status = 'sent')
              AND NOT EXISTS (
                  SELECT 1 FROM public.conversations c
                  WHERE c.employer_id = $1
                    AND c.applicant_id = sj.applicant_id)
            ORDER BY sj.updated_at DESC NULLS LAST
            """,
            employer_id,
        )

        unviewed = await conn.fetchval(
            """
            SELECT COUNT(*) FROM public.applications ap
            WHERE ap.employer_id = $1
              AND ap.employer_viewed_at IS NULL
              AND ap.status IN ('submitted', 'reviewed')
            """,
            employer_id,
        )

        open_apps = await conn.fetchval(
            """
            SELECT COUNT(*) FROM public.applications ap
            WHERE ap.employer_id = $1
              AND ap.status IN ('submitted', 'reviewed')
            """,
            employer_id,
        )

    return EmployerNextActions(
        waiting_candidates_total=len(waiting_rows),
        waiting_candidates=[
            WaitingCandidate(
                applicant_id=r["applicant_id"],
                name=(r["name"] or "").strip() or "Unknown",
                job_id=r["job_id"],
                job_title=r["job_title"] or "Untitled job",
                interest_level=r["interest_level"],
                since=r["since"],
            )
            for r in waiting_rows[:5]
        ],
        unviewed_applications=int(unviewed or 0),
        open_applications=int(open_apps or 0),
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
            ORDER BY m.n_gaps ASC NULLS LAST, m.policy_adjusted_score DESC NULLS LAST
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
    if not api_key:
        # The UI shows a generic "AI ranking is temporarily unavailable" —
        # the actual cause is logged here, server-side only.
        logger.info(
            "AI priority unavailable for job %s: OPENAI_API_KEY not configured — returning score order",
            job_id,
        )

    # Grounded input per candidate: ONLY stored match data (score, status,
    # engine-derived strengths/gaps re-voiced for the employer). The model
    # sees nothing it could not honestly restate, and every returned sentence
    # is deterministically validated against this exact line — a reason with
    # a number that isn't in the line is dropped (invented facts guard).
    candidate_lines = []
    for i, c in enumerate(candidates, 1):
        strengths = "; ".join(
            to_employer_voice(s) for s in (c.get("top_strengths") or [])[:2]
        ) or "—"
        gaps = "; ".join(
            to_employer_voice(g) for g in (c.get("top_gaps") or [])[:2]
        ) or "—"
        score = round(float(c["policy_adjusted_score"])) if c.get("policy_adjusted_score") else "?"
        candidate_lines.append(
            f"{i}. {c['name'].strip()} | Score: {score} | {c['eligibility_status']} | "
            f"Strengths: {strengths} | Gaps: {gaps}"
        )

    # Build AI reasons if key is available
    ai_reasons: dict[str, str] = {}
    if api_key:
        try:
            import json as _json

            import httpx

            from app.util.openai_client import interactive_http_timeout

            prompt = (
                f"You are helping an employer prioritize which candidates to contact first "
                f"for the '{job_title}' role. For each candidate below, write ONE sentence "
                f"(max 20 words) explaining why they stand out or should be contacted first.\n"
                "GROUNDING RULES: Use ONLY the data given on that candidate's line. "
                "Do not invent skills, certifications, employers, distances, pay, or any "
                "number that is not on the line. Never promise or predict hiring outcomes. "
                "If a candidate's line is sparse, say they rank on overall match score.\n\n"
                + "\n".join(candidate_lines)
                + '\n\nReturn JSON: {"reasons": [{"rank": 1, "reason": "..."}, ...]}'
            )

            async with httpx.AsyncClient(timeout=interactive_http_timeout()) as client:
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
                # Attach reasons by the model's declared `rank`, not array
                # position — an out-of-order response must not put the wrong
                # sentence on the wrong candidate. Invalid ranks are dropped,
                # and every sentence passes deterministic validation against
                # the exact grounded line it was generated from (invented
                # numbers / promise language → fall back to the honest
                # deterministic reason).
                for item in parsed.get("reasons", []):
                    try:
                        idx = int(item.get("rank")) - 1
                    except (TypeError, ValueError):
                        continue
                    if 0 <= idx < len(candidates) and item.get("reason"):
                        validated = validate_priority_reason(
                            str(item["reason"]),
                            f"{candidate_lines[idx]} | {job_title}",
                        )
                        if validated:
                            ai_reasons[candidates[idx]["applicant_id"]] = validated
        except Exception as exc:
            logger.warning("AI priority generation failed: %s", exc)

    priorities = [
        AIPriorityCandidate(
            match_id=c["match_id"],
            applicant_id=c["applicant_id"],
            name=c["name"].strip(),
            score=float(c["policy_adjusted_score"]) if c.get("policy_adjusted_score") is not None else None,
            eligibility_status=c["eligibility_status"],
            reason=ai_reasons.get(
                c["applicant_id"],
                fallback_priority_reason(list(c.get("top_strengths") or [])),
            ),
        )
        for c in candidates
    ]

    return AIPriorityResponse(
        job_title=job_title,
        priorities=priorities,
        generated=bool(ai_reasons),
    )
