"""
Pydantic schemas for employer-facing API endpoints.
Mirrors the employer-side DB shape.

Safety rules (DECISIONS.md):
  - ApplicantMatchSummary exposes only safe summary fields (no user_id, no email,
    no admin-only notes, no other employers' data)
  - employer_global_candidate_search_default: false
"""
from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Company / employer
# ---------------------------------------------------------------------------

class EmployerCompanySummary(BaseModel):
    employer_id: str
    name: str
    industry: str | None
    city: str | None
    state: str | None
    is_partner: bool
    total_jobs: int
    active_jobs: int


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class EmployerJobSummary(BaseModel):
    job_id: str
    title: str
    city: str | None
    state: str | None
    work_setting: str | None
    is_active: bool
    posted_date: str | None
    created_at: str
    total_visible: int     # visible-to-employer matches (pre-filter)
    eligible_count: int
    near_fit_count: int


class EmployerJobsListResponse(BaseModel):
    employer_id: str
    company_name: str
    jobs: list[EmployerJobSummary]
    total_jobs: int


class JobCreateRequest(BaseModel):
    title_raw: str
    city: str | None = None
    state: str | None = None
    work_setting: str | None = None   # remote | hybrid | on_site | flexible
    travel_requirement: str | None = None  # none | light | moderate | frequent
    pay_min: float | None = None
    pay_max: float | None = None
    pay_type: str | None = None       # hourly | annual | contract
    description_raw: str | None = None
    requirements_raw: str | None = None
    experience_level: str | None = None   # entry | mid | senior


class JobUpdateRequest(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""
    title_raw: str | None = None
    city: str | None = None
    state: str | None = None
    work_setting: str | None = None
    travel_requirement: str | None = None
    pay_min: float | None = None
    pay_max: float | None = None
    pay_type: str | None = None
    description_raw: str | None = None
    requirements_raw: str | None = None
    experience_level: str | None = None
    is_active: bool | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    title_raw: str
    is_active: bool
    created_at: str


# ---------------------------------------------------------------------------
# Applicant match summary (employer view)
# Safe fields only — no user_id, no email, no admin-only fields.
# ---------------------------------------------------------------------------

class ApplicantMatchSummary(BaseModel):
    match_id: str
    applicant_id: str          # internal applicant UUID (not auth user_id)
    first_name: str | None
    last_name: str | None
    city: str | None
    state: str | None
    region: str | None
    willing_to_relocate: bool
    willing_to_travel: bool
    program_name_raw: str | None
    canonical_job_family_code: str | None
    expected_completion_date: str | None
    available_from_date: str | None
    eligibility_status: str              # eligible | near_fit
    match_label: str | None              # strong_fit | good_fit | moderate_fit | low_fit
    policy_adjusted_score: float | None
    top_strengths: list[str]
    top_gaps: list[str]
    recommended_next_step: str | None
    confidence_level: str | None         # high | medium | low
    requires_review: bool
    geography_note: str | None
    applicant_interest: str | None       # interested | applied | not_interested | None


class RankedApplicantsResponse(BaseModel):
    job_id: str
    job_title: str
    employer_name: str
    # Total counts (pre-filter, for dashboard display)
    total_visible: int
    eligible_count: int
    near_fit_count: int
    # Filtered, ranked applicant list
    applicants: list[ApplicantMatchSummary]
    # Applied filter context (for UI to reflect active filters)
    filter_eligibility: str | None
    filter_min_score: float | None
    filter_state: str | None
    filter_willing_to_relocate: bool | None
