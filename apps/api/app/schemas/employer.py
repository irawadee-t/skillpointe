"""
Pydantic schemas for employer-facing API endpoints.
Mirrors the employer-side DB shape.

Safety rules (DECISIONS.md):
  - ApplicantMatchSummary exposes only safe summary fields (no user_id, no email,
    no admin-only notes, no other employers' data)
  - employer_global_candidate_search_default: false
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# Enum-ish string fields validated at the schema edge so bad values 422
# instead of exploding inside SQL casts.
_WORK_SETTINGS = {"remote", "hybrid", "on_site", "flexible"}
_TRAVEL_REQS = {"none", "light", "moderate", "frequent"}
_PAY_TYPES = {"hourly", "annual", "contract"}
_EXPERIENCE_LEVELS = {"entry", "mid", "senior"}
# Profile-sourced groups an employer may require at internal apply time.
_PROFILE_FIELD_GROUPS = {"contact", "location", "program", "availability", "credentials", "resume"}


def _check_choice(value: str | None, allowed: set[str], field_name: str) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
    return v

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
    # Company-wide default for jobs that don't set their own flag.
    accepts_internal_applications_default: bool = False


class CompanySettingsPatch(BaseModel):
    """Employer-editable company settings (partial update)."""
    accepts_internal_applications_default: bool | None = None


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
    # Granular-filter columns (additive; defaults keep old consumers working)
    family_code: str | None = None
    family_name: str | None = None
    employment_type: str | None = None
    pay_min: float | None = None
    pay_max: float | None = None
    pay_type: str | None = None
    pay_raw: str | None = None
    source: str | None = None
    source_site: str | None = None
    is_stale: bool = False
    apply_link_status: str | None = None
    # Lifecycle (additive): active | paused | filled | closed. is_active stays
    # the machine truth for visibility (status='active' ⇔ is_active=TRUE).
    status: str = "active"
    previous_status: str | None = None
    # Activity gate for Delete (else Close is the honest action).
    has_activity: bool = False
    # Career-source freshness (source-synced jobs only): when the posting was
    # last seen on the employer's own careers site, and when it vanished.
    source_last_seen_at: str | None = None
    source_vanished_at: str | None = None


class EmployerJobFacets(BaseModel):
    """Option lists drawn from THIS employer's own jobs only."""
    families: list[dict[str, str]] = []      # {value, label}
    states: list[str] = []
    sources: list[str] = []
    employment_types: list[str] = []


class EmployerJobsListResponse(BaseModel):
    employer_id: str
    company_name: str
    jobs: list[EmployerJobSummary]
    total_jobs: int
    # Filtered-list metadata (additive)
    unfiltered_total: int | None = None
    supports_internal_apply: bool = False
    facets: EmployerJobFacets = EmployerJobFacets()


class _JobFieldRules(BaseModel):
    """Shared cross-field/enum rules for job create + update payloads."""

    @field_validator("title_raw", check_fields=False)
    @classmethod
    def _title_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("title_raw must not be blank")
        return v

    @field_validator("work_setting", check_fields=False)
    @classmethod
    def _work_setting_valid(cls, v: str | None) -> str | None:
        return _check_choice(v, _WORK_SETTINGS, "work_setting")

    @field_validator("travel_requirement", check_fields=False)
    @classmethod
    def _travel_valid(cls, v: str | None) -> str | None:
        return _check_choice(v, _TRAVEL_REQS, "travel_requirement")

    @field_validator("pay_type", check_fields=False)
    @classmethod
    def _pay_type_valid(cls, v: str | None) -> str | None:
        return _check_choice(v, _PAY_TYPES, "pay_type")

    @field_validator("experience_level", check_fields=False)
    @classmethod
    def _experience_valid(cls, v: str | None) -> str | None:
        return _check_choice(v, _EXPERIENCE_LEVELS, "experience_level")

    @field_validator("required_profile_fields", check_fields=False)
    @classmethod
    def _profile_fields_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for item in v:
            key = item.strip().lower()
            if key not in _PROFILE_FIELD_GROUPS:
                raise ValueError(
                    f"required_profile_fields entries must be one of: {', '.join(sorted(_PROFILE_FIELD_GROUPS))}"
                )
            if key not in cleaned:
                cleaned.append(key)
        return cleaned

    @model_validator(mode="after")
    def _pay_range_ordered(self):
        pay_min = getattr(self, "pay_min", None)
        pay_max = getattr(self, "pay_max", None)
        if pay_min is not None and pay_max is not None and pay_min > pay_max:
            raise ValueError("pay_min cannot be greater than pay_max")
        return self


class JobCreateRequest(_JobFieldRules):
    title_raw: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=50)
    work_setting: str | None = None   # remote | hybrid | on_site | flexible
    travel_requirement: str | None = None  # none | light | moderate | frequent
    pay_min: float | None = Field(default=None, ge=0)
    pay_max: float | None = Field(default=None, ge=0)
    pay_type: str | None = None       # hourly | annual | contract
    description_raw: str | None = Field(default=None, max_length=20000)
    requirements_raw: str | None = Field(default=None, max_length=20000)
    experience_level: str | None = None   # entry | mid | senior
    # Internal-apply configuration
    accepts_internal_applications: bool | None = None
    required_profile_fields: list[str] | None = Field(default=None, max_length=6)


class JobUpdateRequest(_JobFieldRules):
    """All fields optional — only provided fields are updated (PATCH semantics)."""
    title_raw: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=50)
    work_setting: str | None = None
    travel_requirement: str | None = None
    pay_min: float | None = Field(default=None, ge=0)
    pay_max: float | None = Field(default=None, ge=0)
    pay_type: str | None = None
    description_raw: str | None = Field(default=None, max_length=20000)
    requirements_raw: str | None = Field(default=None, max_length=20000)
    experience_level: str | None = None
    is_active: bool | None = None
    accepts_internal_applications: bool | None = None
    required_profile_fields: list[str] | None = Field(default=None, max_length=6)


class JobCreateResponse(BaseModel):
    job_id: str
    title_raw: str
    is_active: bool
    created_at: str


class JobDetail(BaseModel):
    """Full job detail — used to pre-fill the edit form."""
    job_id: str
    title_raw: str
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
    is_active: bool
    # Internal-apply configuration. `accepts_internal_applications` is the raw
    # per-job flag (None = inherit); `internal_apply_effective` folds in the
    # company default so the UI shows the truth.
    accepts_internal_applications: bool | None = None
    required_profile_fields: list[str] = Field(default_factory=list)
    internal_apply_effective: bool = False


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
    # Pagination over the FILTERED list (defaults keep old clients working)
    filtered_total: int = 0
    page: int = 1
    per_page: int = 25
    total_pages: int = 1
