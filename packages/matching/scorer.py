"""
scorer.py — structured scoring engine.

Implements the 9 scoring dimensions from SCORING_CONFIG.yaml §structured_score.
All functions are pure — they receive normalized data and return DimensionScore objects.

Null handling follows DECISIONS.md §2.6 / SCORING_CONFIG.yaml §null_handling:
  - missing data defaults to NEUTRAL, not punitive
  - unknown compensation → 70
  - unknown credentials (non-required) → 50
  - unknown geography → 35 (fully) or 50 (partial)
  - unknown experience → 50

Dimension weights (defaulted, from SCORING_CONFIG.yaml):
  trade_program_alignment:         25
  geography_alignment:             20
  credential_readiness:            15
  timing_readiness:                10
  experience_internship_alignment: 10
  industry_alignment:               5
  compensation_alignment:           5
  work_style_signal_alignment:      5
  employer_soft_pref_alignment:     5
  Total = 100
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ScoringConfig
from .normalizer import TimingResult, JOB_FAMILY_ADJACENCY
from .text_scorer import _parse_education_required, _estimate_applicant_education


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    dimension: str
    weight: float
    raw_score: float         # 0–100 score for this dimension
    weighted_score: float    # weight * raw_score / 100
    rationale: str
    null_handling_applied: bool = False
    null_handling_default: float | None = None


# ---------------------------------------------------------------------------
# Individual dimension scorers
# ---------------------------------------------------------------------------

def score_trade_program_alignment(
    applicant_family_code: str | None,
    job_family_code: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Trade/program alignment (weight 25).
    Direct match → 100, adjacent → 60, unrelated → 20, unknown → null default.
    """
    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code or "", set())

    if applicant_family_code is None or job_family_code is None:
        return DimensionScore(
            "trade_program_alignment", weight,
            null_default, weight * null_default / 100,
            "program or job family not yet normalised — using null default",
            True, null_default,
        )

    if applicant_family_code == job_family_code:
        s, r = 100.0, f"direct family match: {applicant_family_code}"
    elif job_family_code in adjacent:
        s, r = 60.0, f"adjacent families: applicant={applicant_family_code}, job={job_family_code}"
    else:
        s, r = 20.0, f"unrelated families: applicant={applicant_family_code}, job={job_family_code}"

    return DimensionScore("trade_program_alignment", weight, s, weight * s / 100, r)


def score_geography_alignment(
    applicant_state: str | None,
    applicant_region: str | None,
    willing_to_relocate: bool,
    willing_to_travel: bool,
    job_state: str | None,
    job_region: str | None,
    job_work_setting: str | None,
    weight: float,
    null_handling,   # NullHandlingConfig
    travel_preference: str | None = None,
    relocation_preference: str | None = None,
    relocation_states: list[str] | None = None,
) -> DimensionScore:
    """
    Geography alignment (weight 20).
    Remote → 90, same state → 100, same region+willing → 80,
    diff region+willing → 55, infeasible → 20, unknown → config defaults.
    """
    dim = "geography_alignment"
    ws = (job_work_setting or "").lower()

    if ws == "remote":
        s, r = 90.0, "fully remote job — geography not a constraint"
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    if not applicant_state and not job_state:
        s = null_handling.geography_fully_unknown
        r = "no location data for either party — fully unknown"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    # Derive effective preferences from enums, falling back to booleans
    r_pref = relocation_preference or ("anywhere" if willing_to_relocate else "stay_current")
    t_pref = travel_preference or ("regional" if willing_to_travel else "no_travel")

    if applicant_state and job_state and applicant_state.upper() == job_state.upper():
        s, r = 100.0, f"same state: {applicant_state}"
    elif relocation_states and job_state and job_state.upper() in [rs.upper() for rs in relocation_states]:
        s, r = 90.0, f"job in explicitly chosen relocation state: {job_state}"
    elif applicant_region and job_region and applicant_region.lower() == job_region.lower():
        # Same region, different state — score depends on willingness
        if r_pref in ("anywhere", "within_region"):
            s, r = 85.0, f"same region ({applicant_region}), willing to relocate within region"
        elif t_pref in ("regional", "within_region", "nationwide", "anywhere"):
            s, r = 80.0, f"same region ({applicant_region}), willing to travel regionally"
        elif t_pref == "within_state" or r_pref == "within_state":
            s, r = 35.0, f"same region ({applicant_region}) but different state — prefers in-state"
        else:
            s, r = 20.0, f"same region ({applicant_region}) but different state — not willing to move"
    elif r_pref == "anywhere":
        s, r = 70.0, f"open to relocating anywhere (applicant={applicant_state}, job={job_state})"
    elif t_pref in ("nationwide", "anywhere"):
        s, r = 55.0, f"different region, willing to travel nationwide (applicant={applicant_state}, job={job_state})"
    elif not applicant_state or not job_state:
        s = null_handling.geography_partially_known
        r = "partial location data"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)
    else:
        s, r = 20.0, f"geography mismatch: {applicant_state}/{applicant_region} → {job_state}/{job_region}"

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_credential_readiness(
    required_credentials: list[str] | None,
    weight: float,
    null_default: float,
    applicant_certs: list[str] | None = None,
    job_min_education: str | None = None,
    applicant_education: str | None = None,
    job_required_experience_years: int | None = None,
    applicant_experience_years: int | None = None,
) -> DimensionScore:
    """
    Credential readiness (weight 15).

    Evaluates three sub-scores:
      A) Education level compatibility
      B) Specific credential/license match ratio
      C) Experience year fit

    The final score is a weighted average of available sub-scores.
    """
    dim = "credential_readiness"
    sub_scores: list[tuple[float, str, float]] = []  # (score, label, weight)

    _EDU_RANK = {"high_school": 1, "military": 2, "trade_cert": 3, "associates": 4, "bachelors": 5}

    # A) Education level
    if job_min_education and applicant_education:
        job_r = _EDU_RANK.get(job_min_education, 2)
        app_r = _EDU_RANK.get(applicant_education, 2)
        if app_r >= job_r:
            sub_scores.append((95.0, f"education: {applicant_education} meets {job_min_education}", 2.0))
        elif app_r >= job_r - 1:
            sub_scores.append((60.0, f"education: {applicant_education} close to {job_min_education}", 2.0))
        else:
            sub_scores.append((20.0, f"education gap: {applicant_education} vs {job_min_education}", 2.0))
    elif job_min_education:
        sub_scores.append((45.0, f"job requires {job_min_education} — applicant education unknown", 1.0))

    # B) Specific credentials
    if required_credentials:
        if applicant_certs is not None:
            app_certs_lower = {c.lower().strip() for c in applicant_certs}
            matched = sum(
                1 for req in required_credentials
                if any(req.lower().strip() in ac or ac in req.lower().strip() for ac in app_certs_lower)
            )
            total = len(required_credentials)
            ratio = matched / total if total > 0 else 1.0
            if ratio >= 1.0:
                sub_scores.append((95.0, f"all {total} credentials matched", 1.5))
            elif ratio >= 0.5:
                sub_scores.append((60.0 + ratio * 30.0, f"{matched}/{total} credentials matched", 1.5))
            else:
                sub_scores.append((25.0 + ratio * 20.0, f"{matched}/{total} credentials matched", 1.5))
        else:
            cred_list = ", ".join(required_credentials[:2])
            sub_scores.append((40.0, f"credentials [{cred_list}] not yet verified", 1.0))

    # C) Experience years
    if job_required_experience_years is not None and job_required_experience_years > 0:
        app_exp = applicant_experience_years or 0
        if app_exp >= job_required_experience_years:
            sub_scores.append((95.0, f"experience: {app_exp}+ yrs meets {job_required_experience_years} required", 1.0))
        elif job_required_experience_years <= 1:
            sub_scores.append((85.0, f"job prefers {job_required_experience_years} yr — trade training qualifies", 1.0))
        elif job_required_experience_years == 2:
            sub_scores.append((55.0, f"job needs {job_required_experience_years} yrs — stretch for new grad", 1.0))
        elif job_required_experience_years <= 4:
            sub_scores.append((20.0, f"job needs {job_required_experience_years} yrs — requires field time", 1.0))
        else:
            sub_scores.append((10.0, f"job needs {job_required_experience_years}+ yrs — significant gap", 1.0))

    if not sub_scores:
        s, r = 80.0, "no explicit credential, education, or experience requirements on job"
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    total_w = sum(ss[2] for ss in sub_scores)
    s = sum(ss[0] * ss[2] for ss in sub_scores) / total_w
    r = "; ".join(ss[1] for ss in sub_scores)
    return DimensionScore(dim, weight, round(s, 1), weight * round(s, 1) / 100, r)


def score_timing_readiness(
    timing: TimingResult,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Timing readiness (weight 10).
    available_now → 100, near_completion → 90, in_progress → scales 40–75,
    future → 20, unknown → null default.
    """
    dim = "timing_readiness"
    if timing.readiness_label == "available_now":
        s, r = 100.0, "applicant is available now"
    elif timing.readiness_label == "near_completion":
        s, r = 90.0, f"near completion (~{timing.months_to_available} months)"
    elif timing.readiness_label == "in_progress":
        months = timing.months_to_available or 0
        # Linear scale: 4 months → 75, 12 months → 40
        s = max(40.0, 75.0 - (months - 4) * (35.0 / 8.0))
        r = f"in progress (~{months} months to available)"
    elif timing.readiness_label == "future":
        s, r = 20.0, f"materially delayed (~{timing.months_to_available} months)"
    else:
        s = null_default
        r = "no timing information — null default"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_experience_alignment(
    experience_raw: str | None,
    bio_raw: str | None,
    internship_completed: bool | None,
    weight: float,
    null_default: float,
    experience_quality: str | None = None,
) -> DimensionScore:
    """
    Experience + internship alignment (weight 10).

    When experience_quality is provided (from LLM extraction):
      'strong' → 90, 'moderate' → 70, 'weak' → 50, 'none' → null default

    Fallback (no extraction): text-length heuristic.
    """
    dim = "experience_internship_alignment"

    # Phase 7 path: extracted experience quality available
    if experience_quality is not None:
        if experience_quality == "strong":
            s, r = 90.0, "strong experience signals (extracted)"
        elif experience_quality == "moderate":
            s, r = 70.0, "moderate experience signals (extracted)"
        elif experience_quality == "weak":
            s, r = 50.0, "weak experience signals (extracted)"
        else:
            s = null_default
            r = "no experience signals extracted"
            return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    # Fallback: text-length heuristic
    has_exp = bool(experience_raw and len(experience_raw.strip()) > 20)
    has_bio = bool(bio_raw and len(bio_raw.strip()) > 20)
    has_internship = internship_completed is True

    if has_exp and has_internship:
        s, r = 85.0, "experience details + completed internship"
    elif has_internship:
        s, r = 75.0, "completed internship (no detailed experience text)"
    elif has_exp:
        s, r = 65.0, "experience/internship details present"
    elif has_bio:
        s, r = 55.0, "personal statement / bio present (limited direct experience signal)"
    else:
        # For trade school students: the program IS their experience
        # Don't penalize them for not having a bio/experience text
        s, r = 55.0, "trade school training counts as foundational experience"
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_industry_alignment(
    applicant_family_code: str | None,
    job_family_code: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Industry-level alignment (weight 5).
    Coarser than trade_program_alignment — same or adjacent = good.
    Same family → 80, adjacent → 65, unrelated → 30, unknown → null default.
    """
    dim = "industry_alignment"
    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code or "", set())

    if applicant_family_code is None or job_family_code is None:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "unknown family — null default", True, null_default)

    if applicant_family_code == job_family_code:
        s, r = 80.0, f"same industry: {applicant_family_code}"
    elif job_family_code in adjacent:
        s, r = 65.0, f"adjacent industry: {applicant_family_code} / {job_family_code}"
    else:
        s, r = 30.0, f"different industry: applicant={applicant_family_code}, job={job_family_code}"

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_compensation_alignment(
    job_pay_min: float | None,
    job_pay_max: float | None,
    job_pay_type: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Compensation alignment (weight 5).
    Applicant expected salary is not in the SkillPointe import → default to neutral.
    If job has pay data, slight boost for competitive wages.
    Phase 7 may extract desired salary from essays.
    """
    dim = "compensation_alignment"
    if job_pay_min is None:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "no pay data on job — null default", True, null_default)

    avg = (job_pay_min + (job_pay_max or job_pay_min)) / 2
    pay_label = job_pay_type or "unknown"

    if job_pay_type == "hourly" and avg >= 20:
        s, r = 75.0, f"competitive hourly pay: ${job_pay_min}–${job_pay_max or job_pay_min}/hr"
    elif job_pay_type == "annual" and avg >= 40_000:
        s, r = 75.0, f"competitive salary: ${job_pay_min:,.0f}–${job_pay_max or job_pay_min:,.0f}/yr"
    else:
        s = null_default
        r = f"pay data present but below competitive threshold: {pay_label} avg ${avg:.0f}"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_work_style_alignment(
    job_work_setting: str | None,
    job_travel_requirement: str | None,
    willing_to_travel: bool,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Work style / setting alignment (weight 5).
    Remote → 80, hybrid → 72, on-site (no heavy travel) → 75,
    heavy travel + unwilling → 40, unknown → null default.
    """
    dim = "work_style_signal_alignment"
    ws = (job_work_setting or "").lower()
    travel = (job_travel_requirement or "").lower()

    if not ws:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "no work setting info — null default", True, null_default)

    if ws == "remote":
        s, r = 80.0, "fully remote"
    elif ws == "hybrid":
        s, r = 72.0, "hybrid work setting"
    elif ws == "on_site":
        if "frequent" in travel or "heavy" in travel:
            if willing_to_travel:
                s, r = 65.0, "on-site with frequent travel — willing"
            else:
                s, r = 40.0, "on-site with frequent travel — not willing"
        else:
            s, r = 75.0, "on-site (standard)"
    elif ws == "flexible":
        s, r = 75.0, "flexible work arrangement"
    else:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              f"unrecognised setting '{ws}' — null default", True, null_default)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


_SOFT_PREF_SIGNALS: dict[str, list[str]] = {
    "teamwork": ["team", "teamwork", "collaborate", "collaboration", "cooperative"],
    "self-motivated": ["self-motivated", "independent", "initiative", "self-starter", "proactive"],
    "communication": ["communication", "communicate", "interpersonal", "written and verbal"],
    "problem-solving": ["problem-solving", "problem solver", "troubleshoot", "analytical"],
    "detail-oriented": ["detail-oriented", "attention to detail", "meticulous", "precision"],
    "safety-conscious": ["safety", "safety-conscious", "osha", "ppe", "safe work"],
    "physical-fitness": ["physically", "lift", "standing", "climbing", "strenuous"],
    "flexibility": ["flexible", "adaptable", "shift", "overtime", "weekends"],
    "customer-service": ["customer", "client-facing", "customer service", "professional demeanor"],
    "leadership": ["leadership", "mentor", "train others", "lead"],
    "continuous-learning": ["learning", "continuous improvement", "eager to learn", "training"],
    "reliability": ["reliable", "dependable", "punctual", "attendance"],
}


def _extract_soft_signals(text: str) -> set[str]:
    """Extract soft-skill signals from free text using keyword matching."""
    if not text:
        return set()
    text_lower = text.lower()
    found = set()
    for signal, keywords in _SOFT_PREF_SIGNALS.items():
        for kw in keywords:
            if kw in text_lower:
                found.add(signal)
                break
    return found


def score_employer_soft_pref(
    weight: float,
    null_default: float,
    app_work_style: list[dict] | None = None,
    job_work_style: list[dict] | None = None,
    applicant_text: str | None = None,
    job_text: str | None = None,
) -> DimensionScore:
    """
    Employer soft preference alignment (weight 5).

    Priority:
      1. LLM-extracted work style signals (when available)
      2. Text-based soft signal extraction from descriptions/profiles
      3. Null default
    """
    dim = "employer_soft_pref_alignment"

    if app_work_style is not None and job_work_style is not None:
        if not job_work_style:
            s, r = 65.0, "no work style requirements from employer"
            return DimensionScore(dim, weight, s, weight * s / 100, r)

        app_signals = {s.get("signal", "").lower() for s in app_work_style if s.get("signal")}
        job_signals = {s.get("signal", "").lower() for s in job_work_style if s.get("signal")}

        if not job_signals:
            s, r = 65.0, "no specific work style signals from employer"
            return DimensionScore(dim, weight, s, weight * s / 100, r)

        overlap = app_signals & job_signals
        if overlap:
            ratio = len(overlap) / len(job_signals)
            s = 60.0 + ratio * 35.0
            r = f"work style match: {', '.join(list(overlap)[:3])}"
        else:
            s, r = 40.0, "no work style signal overlap"

        return DimensionScore(dim, weight, s, weight * s / 100, r)

    # Infer baseline soft skills for trade school students even with sparse text
    app_text = applicant_text or ""
    job_text_val = job_text or ""

    if job_text_val:
        app_signals = _extract_soft_signals(app_text)
        job_signals = _extract_soft_signals(job_text_val)

        # Trade school students have baseline soft skills from their training
        if not app_signals and not app_text.strip():
            app_signals = {"safety-conscious", "teamwork", "problem-solving", "reliability"}

        if not job_signals:
            s, r = 60.0, "no specific soft preferences detected in job posting"
            return DimensionScore(dim, weight, s, weight * s / 100, r)

        overlap = app_signals & job_signals
        if overlap:
            ratio = len(overlap) / len(job_signals)
            s = 55.0 + ratio * 40.0
            matched = sorted(overlap)[:3]
            r = f"soft skill alignment: {', '.join(matched)}"
        else:
            s, r = 45.0, "limited soft-skill overlap with employer preferences"

        return DimensionScore(dim, weight, s, weight * s / 100, r)

    return DimensionScore(
        dim, weight, null_default, weight * null_default / 100,
        "employer soft preferences not yet extracted",
        True, null_default,
    )


# ---------------------------------------------------------------------------
# Aggregate structured score
# ---------------------------------------------------------------------------

def compute_structured_score(
    applicant: dict[str, Any],
    job: dict[str, Any],
    timing: TimingResult,
    config: ScoringConfig,
    applicant_signals: dict[str, Any] | None = None,
    job_signals: dict[str, Any] | None = None,
) -> tuple[float, list[DimensionScore]]:
    """
    Compute the full weighted structured score (0–100) and per-dimension breakdown.

    applicant / job dicts must have the canonical_job_family_code field set
    (populated by normalize_data.py — joined from canonical_job_families table).

    applicant_signals / job_signals: optional extracted signal dicts from Phase 7.
    When provided, credential, experience, and employer_soft_pref dimensions
    use extracted data instead of heuristics.

    Returns:
        (weighted_structured_score, dimension_scores)
    """
    w = config.structured_weights
    nh = config.null_handling
    a_sig = applicant_signals or {}
    j_sig = job_signals or {}

    app_family = applicant.get("canonical_job_family_code")
    job_family = job.get("canonical_job_family_code")

    # Extract certs/skills/experience quality from signals if available
    applicant_certs = _extract_cert_names(a_sig) if a_sig else None
    experience_quality = _extract_experience_quality(a_sig) if a_sig else None
    app_work_style = a_sig.get("work_style_signals") if a_sig else None
    job_work_style = j_sig.get("work_style_signals") if j_sig else None
    # Use profile-level has_internship, falling back to extraction signals
    internship_completed = applicant.get("has_internship")
    if internship_completed is None:
        internship_completed = _has_internship(a_sig) if a_sig else None

    dimensions: list[DimensionScore] = [
        score_trade_program_alignment(
            app_family, job_family,
            w.trade_program_alignment, nh.credentials_unknown_nonrequired,
        ),
        score_geography_alignment(
            applicant.get("state"), applicant.get("region"),
            bool(applicant.get("willing_to_relocate")),
            bool(applicant.get("willing_to_travel")),
            job.get("state"), job.get("region"),
            job.get("work_setting"),
            w.geography_alignment, nh,
            travel_preference=applicant.get("travel_preference"),
            relocation_preference=applicant.get("relocation_preference"),
            relocation_states=applicant.get("relocation_states"),
        ),
        score_credential_readiness(
            job.get("required_credentials") or [],
            w.credential_readiness, nh.credentials_unknown_nonrequired,
            applicant_certs=applicant_certs,
            job_min_education=_get_job_education(job),
            applicant_education=_estimate_applicant_education(applicant),
            job_required_experience_years=job.get("required_experience_years"),
            applicant_experience_years=applicant.get("years_experience") or 0,
        ),
        score_timing_readiness(timing, w.timing_readiness, nh.experience_unknown),
        score_experience_alignment(
            applicant.get("experience_raw") or applicant.get("internship_details") or applicant.get("essay_background"),
            applicant.get("bio_raw") or applicant.get("essay_impact"),
            internship_completed,
            w.experience_internship_alignment, nh.experience_unknown,
            experience_quality=experience_quality,
        ),
        score_industry_alignment(
            app_family, job_family,
            w.industry_alignment, 50.0,
        ),
        score_compensation_alignment(
            job.get("pay_min"), job.get("pay_max"), job.get("pay_type"),
            w.compensation_alignment, nh.compensation_alignment_unknown,
        ),
        score_work_style_alignment(
            job.get("work_setting"), job.get("travel_requirement"),
            bool(applicant.get("willing_to_travel")),
            w.work_style_signal_alignment, nh.work_style_signal_alignment_unknown,
        ),
        score_employer_soft_pref(
            w.employer_soft_pref_alignment, nh.employer_soft_pref_alignment_unknown,
            app_work_style=app_work_style,
            job_work_style=job_work_style,
            applicant_text=" ".join(filter(None, [
                applicant.get("experience_raw"),
                applicant.get("bio_raw"),
                applicant.get("career_goals_raw"),
                applicant.get("essay_background"),
                applicant.get("internship_details"),
            ])),
            job_text=" ".join(filter(None, [
                job.get("description_raw"),
                job.get("requirements_raw"),
                job.get("preferred_qualifications_raw"),
            ])),
        ),
    ]

    total = sum(d.weighted_score for d in dimensions)
    weighted_structured_score = round(min(100.0, max(0.0, total)), 2)

    return weighted_structured_score, dimensions


# ---------------------------------------------------------------------------
# Helpers for extracting signals into scorer-compatible formats
# ---------------------------------------------------------------------------

def _get_job_education(job: dict) -> str | None:
    """Extract minimum education level from job text fields."""
    job_text = " ".join(filter(None, [
        job.get("description_raw"),
        job.get("requirements_raw"),
        job.get("preferred_qualifications_raw"),
    ]))
    if not job_text:
        return None
    edu = _parse_education_required(job_text)
    return edu["level"] if edu else None


def _extract_cert_names(signals: dict) -> list[str] | None:
    certs = signals.get("certifications_extracted")
    if certs is None:
        return None
    if isinstance(certs, list):
        return [c.get("name") or c.get("cert_name", "") for c in certs if isinstance(c, dict)]
    return None


def _extract_experience_quality(signals: dict) -> str | None:
    exp = signals.get("experience_signals")
    if exp is None:
        return None
    if not isinstance(exp, list) or not exp:
        return "none"
    high_rel = sum(1 for e in exp if isinstance(e, dict) and e.get("relevance") == "high")
    has_intern = any(
        "internship" in (e.get("description") or "").lower()
        for e in exp if isinstance(e, dict)
    )
    if high_rel >= 2 or (high_rel >= 1 and has_intern):
        return "strong"
    if exp:
        return "moderate"
    return "weak"


def _has_internship(signals: dict) -> bool | None:
    exp = signals.get("experience_signals")
    if exp is None:
        return None
    if isinstance(exp, list):
        return any(
            "internship" in (e.get("description") or "").lower()
            for e in exp if isinstance(e, dict)
        )
    return None
