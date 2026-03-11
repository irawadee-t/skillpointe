"""
gates.py — deterministic hard eligibility gate engine.

Implements the five gates from SCORING_CONFIG.yaml §eligibility.rules.
Each gate returns a GateDetail (PASS / NEAR_FIT / FAIL + rationale).
The final eligibility label is determined by the worst single-gate result.

Gate results per SCORING_CONFIG.yaml:
  PASS     → no issue
  NEAR_FIT → important gap, but pair is still worth surfacing
  FAIL     → critical mismatch

Final label aggregation (DECISIONS.md 1.11, 1.12):
  Any FAIL     → ineligible (cap 0.35)
  Any NEAR_FIT → near_fit   (cap 0.75)
  All PASS     → eligible   (cap 1.0)

DECISIONS.md 1.12 hard rule:
  No pair may be labeled high fit if a critical hard gate fails.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .normalizer import TimingResult, JOB_FAMILY_ADJACENCY

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASS = "pass"
NEAR_FIT = "near_fit"
FAIL = "fail"

ELIGIBLE = "eligible"
NEAR_FIT_LABEL = "near_fit"
INELIGIBLE = "ineligible"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GateDetail:
    gate_name: str
    result: str           # PASS, NEAR_FIT, or FAIL
    reason: str
    severity: str = "normal"   # 'critical', 'normal', 'advisory'
    needs_review: bool = False


@dataclass
class EligibilityResult:
    eligibility_status: str    # ELIGIBLE, NEAR_FIT_LABEL, INELIGIBLE
    hard_gate_cap: float
    gate_details: list[GateDetail] = field(default_factory=list)

    @property
    def hard_gate_failures(self) -> list[dict]:
        return [
            {"gate": g.gate_name, "reason": g.reason, "severity": g.severity}
            for g in self.gate_details if g.result == FAIL
        ]

    @property
    def hard_gate_rationale(self) -> dict:
        return {
            g.gate_name: {"result": g.result, "reason": g.reason}
            for g in self.gate_details
        }

    @property
    def requires_review(self) -> bool:
        return any(g.needs_review for g in self.gate_details)


# ---------------------------------------------------------------------------
# Gate 1: Job family compatibility
# ---------------------------------------------------------------------------

def evaluate_job_family_gate(
    applicant_family_code: str | None,
    job_family_code: str | None,
) -> GateDetail:
    """
    Gate 1: Does the applicant's trade/program match the job's family?

    Direct match → PASS
    Adjacent family → NEAR_FIT
    Unrelated → FAIL
    Either unknown → NEAR_FIT (null handling — cannot confirm incompatibility)
    """
    if applicant_family_code is None or job_family_code is None:
        return GateDetail(
            "job_family_compatibility", NEAR_FIT,
            "one or both family codes unknown — cannot confirm compatibility",
            needs_review=True,
        )

    if applicant_family_code == job_family_code:
        return GateDetail(
            "job_family_compatibility", PASS,
            f"direct match: {applicant_family_code}",
        )

    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code, set())
    if job_family_code in adjacent:
        return GateDetail(
            "job_family_compatibility", NEAR_FIT,
            f"adjacent families: applicant={applicant_family_code}, job={job_family_code}",
        )

    return GateDetail(
        "job_family_compatibility", FAIL,
        f"unrelated families: applicant={applicant_family_code}, job={job_family_code}",
        severity="critical",
    )


# ---------------------------------------------------------------------------
# Gate 2: Required credential compatibility
# ---------------------------------------------------------------------------

def evaluate_credential_gate(
    required_credentials: list[str] | None,
    applicant: dict[str, Any],
) -> GateDetail:
    """
    Gate 2: Does the applicant meet the job's required credentials/licenses?

    No required credentials on job → PASS.
    Required credentials present but applicant extraction not yet complete → NEAR_FIT + review.
    Phase 7 (LLM extraction) will make this gate more precise.

    Per SCORING_CONFIG.yaml null_handling.required_credential_behavior:
      if job requires credential and applicant data missing →
        eligibility_status: near_fit, auto_fail: false, requires_review_if_low_confidence: true
    """
    if not required_credentials:
        return GateDetail(
            "required_credential_compatibility", PASS,
            "no explicit credential requirements on job",
        )

    # Pre-Phase-7: required credentials exist but we haven't extracted applicant creds yet
    has_program = bool(
        applicant.get("program_name_raw") or applicant.get("canonical_job_family_code")
    )

    cred_list = ", ".join(required_credentials[:3])
    if not has_program:
        return GateDetail(
            "required_credential_compatibility", NEAR_FIT,
            f"requires [{cred_list}] — applicant profile incomplete, review needed",
            needs_review=True,
        )

    return GateDetail(
        "required_credential_compatibility", NEAR_FIT,
        f"requires [{cred_list}] — credential extraction pending (Phase 7)",
        needs_review=False,  # don't flood queue before extraction runs
    )


# ---------------------------------------------------------------------------
# Gate 3: Readiness / timing compatibility
# ---------------------------------------------------------------------------

def evaluate_timing_gate(timing: TimingResult) -> GateDetail:
    """
    Gate 3: Is the applicant's timeline compatible with the job?

    available_now        → PASS
    near_completion (<4m)→ NEAR_FIT
    in_progress (4–12m)  → NEAR_FIT
    future (>12m)        → FAIL
    unknown              → NEAR_FIT (null handling)
    """
    if timing.readiness_label == "unknown":
        return GateDetail(
            "readiness_timing_compatibility", NEAR_FIT,
            "no completion/availability date — timing cannot be confirmed",
            needs_review=True,
        )

    if timing.readiness_label == "available_now":
        return GateDetail(
            "readiness_timing_compatibility", PASS,
            "applicant is available now",
        )

    if timing.readiness_label in ("near_completion", "in_progress"):
        months = timing.months_to_available or 0
        return GateDetail(
            "readiness_timing_compatibility", NEAR_FIT,
            f"completing program in ~{months} months",
        )

    # future — materially delayed (>12 months)
    months = timing.months_to_available or 0
    return GateDetail(
        "readiness_timing_compatibility", FAIL,
        f"materially delayed: available in ~{months} months (threshold: 12)",
        severity="critical",
    )


# ---------------------------------------------------------------------------
# Gate 4: Geography feasibility
# ---------------------------------------------------------------------------

def evaluate_geography_gate(
    applicant_state: str | None,
    applicant_region: str | None,
    willing_to_relocate: bool,
    willing_to_travel: bool,
    job_state: str | None,
    job_region: str | None,
    job_work_setting: str | None,
) -> GateDetail:
    """
    Gate 4: Is the geography feasible?

    Remote job              → PASS (geography irrelevant)
    Same state              → PASS
    Same region + willing   → PASS
    Same region, unwilling  → NEAR_FIT
    Diff region + willing   → NEAR_FIT
    Diff region + unwilling → FAIL
    Unknown locations       → NEAR_FIT (null handling)
    """
    ws = (job_work_setting or "").lower()

    if ws == "remote":
        return GateDetail(
            "geography_feasibility", PASS,
            "fully remote job — geography not a constraint",
        )

    if not applicant_state and not job_state:
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            "no location data — geography feasibility unknown",
            needs_review=True,
        )

    if applicant_state and job_state and applicant_state.upper() == job_state.upper():
        return GateDetail(
            "geography_feasibility", PASS,
            f"same state: {applicant_state}",
        )

    if applicant_region and job_region and applicant_region == job_region:
        if willing_to_relocate or willing_to_travel:
            return GateDetail(
                "geography_feasibility", PASS,
                f"same region ({applicant_region}), willing to relocate/travel",
            )
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            f"same region ({applicant_region}), relocation willingness not confirmed",
        )

    # Different regions
    if willing_to_relocate:
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            f"different region but willing to relocate (applicant={applicant_state}/{applicant_region}, "
            f"job={job_state}/{job_region})",
        )

    if not applicant_state or not job_state:
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            "partial location data — feasibility uncertain",
            needs_review=True,
        )

    return GateDetail(
        "geography_feasibility", FAIL,
        f"geography mismatch: applicant={applicant_state}/{applicant_region}, "
        f"job={job_state}/{job_region} — not willing to relocate",
        severity="critical",
    )


# ---------------------------------------------------------------------------
# Gate 5: Explicit minimum requirement compatibility
# ---------------------------------------------------------------------------

def evaluate_min_req_gate(
    applicant: dict[str, Any],
    job_description_raw: str | None,
) -> GateDetail:
    """
    Gate 5: Does the applicant meet explicit minimum requirements?

    Pre-Phase-7: we cannot reliably evaluate without LLM extraction.
    This gate defaults to NEAR_FIT when description text exists, to avoid
    incorrectly marking pairs ineligible before extraction runs.
    Phase 7 will make this gate precise.
    """
    if not job_description_raw:
        return GateDetail(
            "explicit_minimum_requirement_compatibility", PASS,
            "no job description to evaluate against",
        )

    return GateDetail(
        "explicit_minimum_requirement_compatibility", NEAR_FIT,
        "minimum requirements exist in job description but not yet extracted (Phase 7 pending)",
        needs_review=False,  # don't flood review queue pre-extraction
    )


# ---------------------------------------------------------------------------
# Final eligibility aggregation
# ---------------------------------------------------------------------------

def compute_eligibility(
    gate_details: list[GateDetail],
    caps_config=None,
) -> EligibilityResult:
    """
    Aggregate all gate results into a final eligibility label and cap multiplier.

    Per DECISIONS.md 1.11:
      Any FAIL     → ineligible (cap 0.35)
      Any NEAR_FIT → near_fit   (cap 0.75)
      All PASS     → eligible   (cap 1.0)

    Per DECISIONS.md 1.12:
      No pair labeled high fit if a critical hard gate fails.
    """
    from .config import EligibilityCapConfig
    caps = caps_config or EligibilityCapConfig()

    has_fail = any(g.result == FAIL for g in gate_details)
    has_near_fit = any(g.result == NEAR_FIT for g in gate_details)

    if has_fail:
        return EligibilityResult(INELIGIBLE, caps.ineligible, gate_details)
    if has_near_fit:
        return EligibilityResult(NEAR_FIT_LABEL, caps.near_fit, gate_details)
    return EligibilityResult(ELIGIBLE, caps.eligible, gate_details)
