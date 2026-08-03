"""
packages/matching — SkillPointe Match deterministic ranking engine.

Implements Phases 4.3, 5.1, 5.2 (normalization, hard gates, structured scoring).
Phase 5.3 (semantic scoring) and 5.4 (policy reranking full pass) are next.

Public API:
  from matching.config import load_config, ScoringConfig
  from matching.normalizer import (
      normalize_program_to_job_family,
      normalize_job_title_to_family,
      normalize_pay_range,
      normalize_location,
      normalize_timing,
  )
  from matching.gates import compute_eligibility, evaluate_*
  from matching.scorer import compute_structured_score
  from matching.engine import compute_match, MatchResult
"""

from .config import ScoringConfig, load_config
from .engine import MatchResult, compute_match
from .gates import EligibilityResult, compute_eligibility
from .normalizer import (
    NormResult,
    TimingResult,
    normalize_job_title_to_family,
    normalize_location,
    normalize_pay_range,
    normalize_program_to_job_family,
    normalize_timing,
)
from .scorer import DimensionScore, compute_structured_score

__all__ = [
    "load_config",
    "ScoringConfig",
    "compute_match",
    "MatchResult",
    "normalize_program_to_job_family",
    "normalize_job_title_to_family",
    "normalize_pay_range",
    "normalize_location",
    "normalize_timing",
    "NormResult",
    "TimingResult",
    "compute_eligibility",
    "EligibilityResult",
    "compute_structured_score",
    "DimensionScore",
]
