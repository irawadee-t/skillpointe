"""
config.py — scoring configuration loader for SkillPointe Match.

Priority order:
  1. If a yaml_path is supplied, load from that file.
  2. Default: repo-root SCORING_CONFIG.yaml
  3. Fallback: built-in hardcoded defaults (for unit tests with no file access)

The ScoringConfig dataclass is the canonical in-memory representation
used by normalizer, gates, scorer, and engine.  All other modules accept
ScoringConfig as a parameter so they never read the filesystem directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Path from packages/matching/config.py → repo root / SCORING_CONFIG.yaml
_CONFIG_PATH = Path(__file__).parent.parent.parent / "SCORING_CONFIG.yaml"


# ---------------------------------------------------------------------------
# Sub-config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EligibilityCapConfig:
    eligible: float = 1.0
    near_fit: float = 0.75
    ineligible: float = 0.35


@dataclass
class StructuredWeights:
    trade_program_alignment: float = 25.0
    geography_alignment: float = 20.0
    credential_readiness: float = 15.0
    timing_readiness: float = 10.0
    experience_internship_alignment: float = 10.0
    industry_alignment: float = 5.0
    compensation_alignment: float = 5.0
    work_style_signal_alignment: float = 5.0
    employer_soft_pref_alignment: float = 5.0


@dataclass
class NullHandlingConfig:
    compensation_alignment_unknown: float = 70.0
    employer_soft_pref_alignment_unknown: float = 50.0
    work_style_signal_alignment_unknown: float = 50.0
    geography_partially_known: float = 50.0
    geography_fully_unknown: float = 35.0
    credentials_unknown_nonrequired: float = 50.0
    experience_unknown: float = 50.0


@dataclass
class PolicyModifiers:
    partner_employer: float = 5.0
    funded_direct: float = 6.0
    funded_adjacent: float = 3.0
    geo_local: float = 6.0
    geo_same_state: float = 4.0
    geo_relocation_willing: float = 1.0
    geo_travel_willing: float = 1.0
    readiness_ready_now: float = 5.0
    readiness_near_completion: float = 3.0
    opportunity_upside: float = 2.0
    penalty_missing_mandatory_credential: float = -12.0
    penalty_missing_important_skill: float = -6.0
    penalty_missing_minor: float = -2.0
    max_partner_override_gap: float = 12.0


@dataclass
class ScoringConfig:
    version: str = "v1"
    eligibility_caps: EligibilityCapConfig = field(default_factory=EligibilityCapConfig)
    structured_weights: StructuredWeights = field(default_factory=StructuredWeights)
    null_handling: NullHandlingConfig = field(default_factory=NullHandlingConfig)
    policy_modifiers: PolicyModifiers = field(default_factory=PolicyModifiers)
    structured_weight: float = 0.75   # base_fit formula weight for structured score
    semantic_weight: float = 0.25     # base_fit formula weight for semantic score


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(yaml_path: str | Path | None = None) -> ScoringConfig:
    """
    Load ScoringConfig from YAML.  Falls back to built-in defaults if
    the file is missing or unreadable.
    """
    path = Path(yaml_path) if yaml_path else _CONFIG_PATH
    if path.exists():
        try:
            import yaml  # type: ignore
            with open(path) as f:
                raw = yaml.safe_load(f)
            return _from_yaml(raw)
        except Exception:
            pass  # fall through to defaults
    return ScoringConfig()


def _from_yaml(raw: dict[str, Any]) -> ScoringConfig:
    cfg = ScoringConfig()
    cfg.version = raw.get("version", "v1")

    # Eligibility caps
    elig = raw.get("eligibility", {}).get("labels", {})
    if elig:
        cfg.eligibility_caps = EligibilityCapConfig(
            eligible=elig.get("eligible", {}).get("hard_gate_cap", 1.0),
            near_fit=elig.get("near_fit", {}).get("hard_gate_cap", 0.75),
            ineligible=elig.get("ineligible", {}).get("hard_gate_cap", 0.35),
        )

    # Structured weights
    weights = raw.get("structured_score", {}).get("weights", {})
    if weights:
        cfg.structured_weights = StructuredWeights(
            trade_program_alignment=weights.get("trade_program_alignment", 25),
            geography_alignment=weights.get("geography_alignment", 20),
            credential_readiness=weights.get("credential_readiness", 15),
            timing_readiness=weights.get("timing_readiness", 10),
            experience_internship_alignment=weights.get("experience_internship_alignment", 10),
            industry_alignment=weights.get("industry_alignment", 5),
            compensation_alignment=weights.get("compensation_alignment", 5),
            work_style_signal_alignment=weights.get("work_style_signal_alignment", 5),
            employer_soft_pref_alignment=weights.get("employer_soft_pref_alignment", 5),
        )

    # Null handling defaults
    null = raw.get("null_handling", {}).get("defaults", {})
    if null:
        cfg.null_handling = NullHandlingConfig(
            compensation_alignment_unknown=null.get("compensation_alignment_unknown", 70),
            employer_soft_pref_alignment_unknown=null.get("employer_soft_pref_alignment_unknown", 50),
            work_style_signal_alignment_unknown=null.get("work_style_signal_alignment_unknown", 50),
            geography_partially_known=null.get("geography_partially_known", 50),
            geography_fully_unknown=null.get("geography_fully_unknown", 35),
            credentials_unknown_nonrequired=null.get("credentials_unknown_nonrequired", 50),
            experience_unknown=null.get("experience_unknown", 50),
        )

    # Policy modifiers
    policy = raw.get("policy_reranking", {}).get("policies", {})
    if policy:
        pm = PolicyModifiers()

        partner = policy.get("partner_employer_preference", {})
        pm.partner_employer = partner.get("modifiers", {}).get("partner_employer", 5)
        pm.max_partner_override_gap = partner.get("constraints", {}).get("max_override_gap", 12)

        funded = policy.get("funded_training_pathway_alignment", {}).get("modifiers", {})
        pm.funded_direct = funded.get("direct_alignment", 6)
        pm.funded_adjacent = funded.get("adjacent_alignment", 3)

        geo = policy.get("geography_preference", {}).get("modifiers", {})
        pm.geo_local = geo.get("local_feasible", 6)
        pm.geo_same_state = geo.get("same_state_or_regional", 4)
        pm.geo_relocation_willing = geo.get("relocation_required_and_willing", 1)
        pm.geo_travel_willing = geo.get("travel_heavy_and_willing", 1)

        ready = policy.get("readiness_preference", {}).get("modifiers", {})
        pm.readiness_ready_now = ready.get("ready_now_or_timing_aligned", 5)
        pm.readiness_near_completion = ready.get("near_completion", 3)

        upside = policy.get("opportunity_upside", {}).get("modifiers", {})
        pm.opportunity_upside = upside.get("meaningful_upside_and_near_fit_or_better", 2)

        penalty = policy.get("missing_critical_requirement_penalty", {}).get("modifiers", {})
        pm.penalty_missing_mandatory_credential = penalty.get("missing_mandatory_credential", -12)
        pm.penalty_missing_important_skill = penalty.get("missing_important_nonmandatory_skill_cluster", -6)
        pm.penalty_missing_minor = penalty.get("missing_minor_requirements_only", -2)

        cfg.policy_modifiers = pm

    return cfg
