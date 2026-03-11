"""
test_matching.py — Unit tests for Phase 4.3 / 5.1 / 5.2 matching engine.

All tests are pure (no DB, no filesystem, no Supabase required).
Tests cover:
  - matching.normalizer  — program/title normalization, pay, location, timing, work setting
  - matching.gates       — all 5 gate evaluators + compute_eligibility aggregation
  - matching.scorer      — all 9 dimension scorers + compute_structured_score
  - matching.engine      — compute_match integration, score formula, match labels

Run with:
  cd apps/api && pytest tests/test_matching.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest

# Allow importing from packages/matching
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.config import (
    ScoringConfig,
    EligibilityCapConfig,
    NullHandlingConfig,
    StructuredWeights,
    PolicyModifiers,
)
from matching.normalizer import (
    NormResult,
    TimingResult,
    normalize_program_to_job_family,
    normalize_job_title_to_family,
    normalize_pay_range,
    normalize_location,
    normalize_timing,
    normalize_work_setting,
    JOB_FAMILY_ADJACENCY,
)
from matching.gates import (
    PASS, NEAR_FIT, FAIL,
    ELIGIBLE, NEAR_FIT_LABEL, INELIGIBLE,
    GateDetail,
    EligibilityResult,
    evaluate_job_family_gate,
    evaluate_credential_gate,
    evaluate_timing_gate,
    evaluate_geography_gate,
    evaluate_min_req_gate,
    compute_eligibility,
)
from matching.scorer import (
    DimensionScore,
    score_trade_program_alignment,
    score_geography_alignment,
    score_credential_readiness,
    score_timing_readiness,
    score_experience_alignment,
    score_industry_alignment,
    score_compensation_alignment,
    score_work_style_alignment,
    score_employer_soft_pref,
    compute_structured_score,
)
from matching.engine import compute_match, MatchResult


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_FAMILIES = [
    {"id": "1", "code": "electrical", "name": "Electrical",
     "aliases": ["electrician", "electrical apprentice", "electrical technician"]},
    {"id": "2", "code": "hvac", "name": "HVAC",
     "aliases": ["hvac technician", "heating and cooling", "refrigeration"]},
    {"id": "3", "code": "plumbing", "name": "Plumbing",
     "aliases": ["plumber", "pipefitter", "plumbing apprentice"]},
    {"id": "4", "code": "automotive", "name": "Automotive",
     "aliases": ["auto technician", "automotive technician", "vehicle mechanic"]},
    {"id": "5", "code": "culinary", "name": "Culinary",
     "aliases": ["cook", "chef", "culinary arts"]},
]

_GEO_REGIONS = [
    {"id": "r1", "code": "midwest", "name": "Midwest",
     "states": ["IL", "IN", "MI", "OH", "WI", "MN", "IA", "MO", "ND", "SD", "NE", "KS"]},
    {"id": "r2", "code": "south", "name": "South",
     "states": ["TX", "OK", "AR", "LA", "MS", "AL", "TN", "KY", "FL", "GA", "SC", "NC", "VA", "WV"]},
    {"id": "r3", "code": "northeast", "name": "Northeast",
     "states": ["NY", "NJ", "PA", "CT", "MA", "RI", "VT", "NH", "ME", "DE", "MD", "DC"]},
    {"id": "r4", "code": "west", "name": "West",
     "states": ["CA", "OR", "WA", "NV", "AZ", "CO", "UT", "NM", "ID", "MT", "WY", "AK", "HI"]},
]


def _default_config() -> ScoringConfig:
    return ScoringConfig()


def _make_applicant(**kwargs) -> dict:
    """Minimal valid applicant dict. available_from_date defaults to the past so
    the timing gate passes by default in engine integration tests."""
    base = {
        "id": "app-001",
        "first_name": "Jane",
        "last_name": "Smith",
        "canonical_job_family_code": "electrical",
        "state": "IL",
        "region": "midwest",
        "willing_to_relocate": False,
        "willing_to_travel": False,
        "expected_completion_date": None,
        "available_from_date": date(2025, 1, 1),  # past → available_now timing gate PASS
        "experience_raw": "Completed 2-year electrical apprenticeship at ABC Electric.",
        "bio_raw": "Passionate about electrical work and seeking first role.",
        "career_goals_raw": "Want to become a licensed journeyman electrician.",
        "program_name_raw": "Electrical Apprentice",
    }
    base.update(kwargs)
    return base


def _make_job(**kwargs) -> dict:
    """Minimal valid job dict."""
    base = {
        "id": "job-001",
        "employer_id": "emp-001",
        "title_raw": "Electrician",
        "title_normalized": "Electrician",
        "canonical_job_family_code": "electrical",
        "state": "IL",
        "region": "midwest",
        "work_setting": "on_site",
        "travel_requirement": None,
        "pay_min": 25.0,
        "pay_max": 35.0,
        "pay_type": "hourly",
        "required_credentials": [],
        "description_raw": None,
    }
    base.update(kwargs)
    return base


def _make_employer(**kwargs) -> dict:
    base = {"id": "emp-001", "name": "ACME Electric", "is_partner": False}
    base.update(kwargs)
    return base


# ===========================================================================
# normalizer.py
# ===========================================================================

class TestNormalizeProgram:
    def test_exact_code_match(self):
        r = normalize_program_to_job_family("electrical", _FAMILIES)
        assert r.family_code == "electrical"
        assert r.confidence == "high"

    def test_exact_name_match_case_insensitive(self):
        r = normalize_program_to_job_family("HVAC", _FAMILIES)
        assert r.family_code == "hvac"
        assert r.confidence == "high"

    def test_alias_substring_match(self):
        r = normalize_program_to_job_family("electrician apprentice", _FAMILIES)
        assert r.family_code == "electrical"

    def test_keyword_overlap_match(self):
        r = normalize_program_to_job_family("Auto Technician Training", _FAMILIES)
        assert r.family_code == "automotive"

    def test_no_match_returns_none(self):
        r = normalize_program_to_job_family("underwater basket weaving", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True

    def test_empty_string_returns_none(self):
        r = normalize_program_to_job_family("", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True

    def test_none_input_returns_none(self):
        r = normalize_program_to_job_family(None, _FAMILIES)
        assert r.family_code is None

    def test_multiple_alias_matches_sets_needs_review(self):
        # "auto tech" is a substring of "auto technician training" AND
        # "auto technician" is also a substring of "auto technician training"
        # → two families both match via alias → needs_review = True
        families = [
            {"id": "a", "code": "x_family", "name": "X Family", "aliases": ["auto tech"]},
            {"id": "b", "code": "y_family", "name": "Y Family", "aliases": ["auto technician"]},
        ]
        r = normalize_program_to_job_family("auto technician training", families)
        assert r.needs_review is True
        assert len(r.alternative_families) >= 1


class TestNormalizeJobTitle:
    def test_pathway_used_when_high_confidence(self):
        r = normalize_job_title_to_family("Senior Tech", "Electrician", _FAMILIES)
        assert r.family_code == "electrical"
        assert "career_pathway" in r.match_reason

    def test_fallback_to_title_when_no_pathway(self):
        r = normalize_job_title_to_family("HVAC Technician", None, _FAMILIES)
        assert r.family_code == "hvac"

    def test_no_match_when_unrecognized(self):
        r = normalize_job_title_to_family("Yoga Instructor", "Wellness Coach", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True


class TestNormalizePayRange:
    def test_hourly_range_with_dash(self):
        # Note: "$22–$33/hr" works (number–number); "$22/hr–$33/hr" doesn't
        # because "/hr" sits between the number and the separator.
        lo, hi, pt = normalize_pay_range("$22 – $33/hr")
        assert (lo, hi, pt) == (22.0, 33.0, "hourly")

    def test_annual_range_with_keyword(self):
        lo, hi, pt = normalize_pay_range("$45,000 – $65,000 annually")
        assert (lo, hi, pt) == (45000.0, 65000.0, "annual")

    def test_single_hourly_value(self):
        lo, hi, pt = normalize_pay_range("$28/hr")
        assert lo == 28.0 and hi == 28.0 and pt == "hourly"

    def test_magnitude_heuristic_hourly(self):
        lo, hi, pt = normalize_pay_range("$18-$25")   # < 500 → hourly
        assert pt == "hourly"

    def test_magnitude_heuristic_annual(self):
        lo, hi, pt = normalize_pay_range("$50,000-$70,000")  # > 500 → annual
        assert pt == "annual"

    def test_none_returns_triple_none(self):
        assert normalize_pay_range(None) == (None, None, None)

    def test_empty_string_returns_triple_none(self):
        assert normalize_pay_range("") == (None, None, None)

    def test_non_numeric_returns_triple_none(self):
        assert normalize_pay_range("competitive") == (None, None, None)


class TestNormalizeLocation:
    def test_illinois_maps_to_midwest(self):
        code = normalize_location("Chicago", "IL", _GEO_REGIONS)
        assert code == "midwest"

    def test_texas_maps_to_south(self):
        code = normalize_location(None, "TX", _GEO_REGIONS)
        assert code == "south"

    def test_missing_state_returns_none(self):
        code = normalize_location("Chicago", None, _GEO_REGIONS)
        assert code is None

    def test_unknown_state_returns_none(self):
        code = normalize_location(None, "XX", _GEO_REGIONS)
        assert code is None

    def test_case_insensitive_state(self):
        code = normalize_location(None, "il", _GEO_REGIONS)
        assert code == "midwest"


class TestNormalizeTiming:
    _TODAY = date(2026, 3, 10)

    def test_past_date_is_available_now(self):
        r = normalize_timing(date(2025, 6, 1), None, self._TODAY)
        assert r.readiness_label == "available_now"
        assert r.months_to_available == 0

    def test_today_is_available_now(self):
        r = normalize_timing(self._TODAY, None, self._TODAY)
        assert r.readiness_label == "available_now"

    def test_near_completion(self):
        future = date(2026, 5, 10)  # 2 months out
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "near_completion"
        assert r.months_to_available < 4

    def test_in_progress(self):
        future = date(2026, 9, 10)  # ~6 months out
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "in_progress"

    def test_future(self):
        future = date(2027, 6, 1)  # >12 months
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "future"

    def test_no_dates_returns_unknown(self):
        r = normalize_timing(None, None, self._TODAY)
        assert r.readiness_label == "unknown"
        assert r.months_to_available is None

    def test_available_from_date_takes_priority(self):
        # available_from is in the past, completion is in the future
        r = normalize_timing(date(2026, 12, 1), date(2025, 1, 1), self._TODAY)
        assert r.readiness_label == "available_now"

    def test_is_enrolled_set_for_future_date(self):
        future = date(2026, 7, 1)
        r = normalize_timing(future, None, self._TODAY)
        assert r.is_currently_enrolled is True

    def test_is_enrolled_false_for_past_date(self):
        r = normalize_timing(date(2025, 1, 1), None, self._TODAY)
        assert r.is_currently_enrolled is False


class TestNormalizeWorkSetting:
    def test_no_returns_on_site(self):
        assert normalize_work_setting("No") == "on_site"

    def test_yes_returns_remote(self):
        assert normalize_work_setting("Yes") == "remote"

    def test_hybrid(self):
        assert normalize_work_setting("Hybrid") == "hybrid"

    def test_fully_remote(self):
        assert normalize_work_setting("Fully Remote") == "remote"

    def test_none_returns_none(self):
        assert normalize_work_setting(None) is None

    def test_unrecognised_returns_none(self):
        assert normalize_work_setting("occasional") is None


# ===========================================================================
# gates.py
# ===========================================================================

class TestJobFamilyGate:
    def test_direct_match_passes(self):
        g = evaluate_job_family_gate("electrical", "electrical")
        assert g.result == PASS

    def test_adjacent_families_near_fit(self):
        # electrical is adjacent to hvac
        g = evaluate_job_family_gate("electrical", "hvac")
        assert g.result == NEAR_FIT

    def test_unrelated_fails(self):
        g = evaluate_job_family_gate("electrical", "culinary")
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_null_applicant_family_near_fit(self):
        g = evaluate_job_family_gate(None, "electrical")
        assert g.result == NEAR_FIT
        assert g.needs_review is True

    def test_null_job_family_near_fit(self):
        g = evaluate_job_family_gate("electrical", None)
        assert g.result == NEAR_FIT

    def test_both_null_near_fit(self):
        g = evaluate_job_family_gate(None, None)
        assert g.result == NEAR_FIT


class TestCredentialGate:
    def test_no_required_credentials_passes(self):
        g = evaluate_credential_gate([], {"program_name_raw": "Electrician"})
        assert g.result == PASS

    def test_none_credentials_passes(self):
        g = evaluate_credential_gate(None, {})
        assert g.result == PASS

    def test_required_creds_with_program_near_fit(self):
        g = evaluate_credential_gate(["EPA 608"], {"program_name_raw": "HVAC Tech"})
        assert g.result == NEAR_FIT

    def test_required_creds_no_program_near_fit_with_review(self):
        g = evaluate_credential_gate(["EPA 608"], {})
        assert g.result == NEAR_FIT
        assert g.needs_review is True


class TestTimingGate:
    def test_available_now_passes(self):
        timing = TimingResult(0, "available_now", False)
        g = evaluate_timing_gate(timing)
        assert g.result == PASS

    def test_near_completion_near_fit(self):
        timing = TimingResult(2, "near_completion", True)
        g = evaluate_timing_gate(timing)
        assert g.result == NEAR_FIT

    def test_in_progress_near_fit(self):
        timing = TimingResult(6, "in_progress", True)
        g = evaluate_timing_gate(timing)
        assert g.result == NEAR_FIT

    def test_future_fails(self):
        timing = TimingResult(15, "future", True)
        g = evaluate_timing_gate(timing)
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_unknown_near_fit_with_review(self):
        timing = TimingResult(None, "unknown", False)
        g = evaluate_timing_gate(timing)
        assert g.result == NEAR_FIT
        assert g.needs_review is True


class TestGeographyGate:
    def test_remote_job_passes(self):
        g = evaluate_geography_gate("TX", "south", False, False,
                                    "CA", "west", "remote")
        assert g.result == PASS

    def test_same_state_passes(self):
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "IL", "midwest", "on_site")
        assert g.result == PASS

    def test_same_region_willing_to_relocate_passes(self):
        g = evaluate_geography_gate("IL", "midwest", True, False,
                                    "OH", "midwest", "on_site")
        assert g.result == PASS

    def test_same_region_not_willing_near_fit(self):
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "OH", "midwest", "on_site")
        assert g.result == NEAR_FIT

    def test_different_region_willing_near_fit(self):
        g = evaluate_geography_gate("IL", "midwest", True, False,
                                    "TX", "south", "on_site")
        assert g.result == NEAR_FIT

    def test_different_region_not_willing_fails(self):
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "TX", "south", "on_site")
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_no_location_data_near_fit(self):
        g = evaluate_geography_gate(None, None, False, False, None, None, "on_site")
        assert g.result == NEAR_FIT
        assert g.needs_review is True


class TestMinReqGate:
    def test_no_description_passes(self):
        g = evaluate_min_req_gate({}, None)
        assert g.result == PASS

    def test_description_present_near_fit(self):
        g = evaluate_min_req_gate({}, "Must have EPA 608 cert and 2 years experience.")
        assert g.result == NEAR_FIT


class TestComputeEligibility:
    def _config(self):
        return EligibilityCapConfig()

    def test_all_pass_returns_eligible(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", PASS, "ok"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == ELIGIBLE
        assert r.hard_gate_cap == 1.0

    def test_one_near_fit_returns_near_fit(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", NEAR_FIT, "gap"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == NEAR_FIT_LABEL
        assert r.hard_gate_cap == 0.75

    def test_one_fail_returns_ineligible(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", FAIL, "mismatch"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == INELIGIBLE
        assert r.hard_gate_cap == 0.35

    def test_fail_overrides_near_fit(self):
        gates = [
            GateDetail("g1", NEAR_FIT, "gap"),
            GateDetail("g2", FAIL, "critical mismatch", severity="critical"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == INELIGIBLE

    def test_hard_gate_failures_property(self):
        gates = [
            GateDetail("g1", FAIL, "bad mismatch", severity="critical"),
            GateDetail("g2", PASS, "ok"),
        ]
        r = compute_eligibility(gates, self._config())
        failures = r.hard_gate_failures
        assert len(failures) == 1
        assert failures[0]["gate"] == "g1"

    def test_requires_review_flag(self):
        gates = [
            GateDetail("g1", NEAR_FIT, "unknown", needs_review=True),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.requires_review is True


# ===========================================================================
# scorer.py
# ===========================================================================

class TestScoreTradeAlignment:
    def test_direct_match_100(self):
        d = score_trade_program_alignment("electrical", "electrical", 25, 50)
        assert d.raw_score == 100.0
        assert d.null_handling_applied is False

    def test_adjacent_match_60(self):
        d = score_trade_program_alignment("electrical", "hvac", 25, 50)
        assert d.raw_score == 60.0

    def test_unrelated_20(self):
        d = score_trade_program_alignment("electrical", "culinary", 25, 50)
        assert d.raw_score == 20.0

    def test_null_applicant_uses_default(self):
        d = score_trade_program_alignment(None, "electrical", 25, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0

    def test_weighted_score_formula(self):
        d = score_trade_program_alignment("electrical", "electrical", 25, 50)
        assert d.weighted_score == pytest.approx(25.0)  # 25 * 100 / 100


class TestScoreGeographyAlignment:
    def _nh(self):
        return NullHandlingConfig()

    def test_remote_job_90(self):
        d = score_geography_alignment("IL", "midwest", False, False,
                                      "CA", "west", "remote", 20, self._nh())
        assert d.raw_score == 90.0

    def test_same_state_100(self):
        d = score_geography_alignment("IL", "midwest", False, False,
                                      "IL", "midwest", "on_site", 20, self._nh())
        assert d.raw_score == 100.0

    def test_same_region_willing_80(self):
        d = score_geography_alignment("IL", "midwest", True, False,
                                      "OH", "midwest", "on_site", 20, self._nh())
        assert d.raw_score == 80.0

    def test_diff_region_willing_55(self):
        d = score_geography_alignment("IL", "midwest", True, False,
                                      "TX", "south", "on_site", 20, self._nh())
        assert d.raw_score == 55.0

    def test_no_location_uses_null_default(self):
        d = score_geography_alignment(None, None, False, False,
                                      None, None, "on_site", 20, self._nh())
        assert d.null_handling_applied is True
        assert d.raw_score == 35.0  # geography_fully_unknown default


class TestScoreCredentialReadiness:
    def test_no_creds_returns_80(self):
        d = score_credential_readiness([], 15, 50)
        assert d.raw_score == 80.0
        assert d.null_handling_applied is False

    def test_required_creds_pending_uses_null_default(self):
        d = score_credential_readiness(["EPA 608"], 15, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0


class TestScoreTimingReadiness:
    def test_available_now_100(self):
        timing = TimingResult(0, "available_now", False)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 100.0

    def test_near_completion_90(self):
        timing = TimingResult(2, "near_completion", True)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 90.0

    def test_in_progress_scales(self):
        timing = TimingResult(8, "in_progress", True)
        d = score_timing_readiness(timing, 10, 50)
        assert 40.0 <= d.raw_score <= 75.0

    def test_future_20(self):
        timing = TimingResult(15, "future", True)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 20.0

    def test_unknown_uses_null_default(self):
        timing = TimingResult(None, "unknown", False)
        d = score_timing_readiness(timing, 10, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0


class TestScoreExperienceAlignment:
    def test_experience_and_internship_85(self):
        d = score_experience_alignment("Completed electrical apprenticeship at XYZ.", None, True, 10, 50)
        assert d.raw_score == 85.0

    def test_experience_only_65(self):
        d = score_experience_alignment("Worked in electrical trade for 2 years.", None, None, 10, 50)
        assert d.raw_score == 65.0

    def test_bio_only_55(self):
        d = score_experience_alignment(None, "I am passionate about electrical work and learning.", None, 10, 50)
        assert d.raw_score == 55.0

    def test_no_data_null_default(self):
        d = score_experience_alignment(None, None, None, 10, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0

    def test_short_experience_treated_as_null(self):
        d = score_experience_alignment("Tech", None, None, 10, 50)
        assert d.null_handling_applied is True


class TestScoreCompensationAlignment:
    def test_no_pay_data_null_default(self):
        d = score_compensation_alignment(None, None, None, 5, 70)
        assert d.null_handling_applied is True
        assert d.raw_score == 70.0

    def test_competitive_hourly_75(self):
        d = score_compensation_alignment(22.0, 30.0, "hourly", 5, 70)
        assert d.raw_score == 75.0

    def test_competitive_annual_75(self):
        d = score_compensation_alignment(45000.0, 65000.0, "annual", 5, 70)
        assert d.raw_score == 75.0

    def test_low_hourly_uses_null_default(self):
        d = score_compensation_alignment(10.0, 14.0, "hourly", 5, 70)
        assert d.null_handling_applied is True


class TestComputeStructuredScore:
    def test_perfect_match_score_above_70(self):
        app = _make_applicant(
            state="IL", region="midwest",
            willing_to_relocate=False, willing_to_travel=False,
            experience_raw="2-year electrical apprenticeship completed at ACME.",
        )
        job = _make_job(
            state="IL", region="midwest",
            work_setting="on_site",
            pay_min=25.0, pay_max=35.0, pay_type="hourly",
            required_credentials=[],
        )
        timing = TimingResult(0, "available_now", False)
        config = _default_config()
        score, dims = compute_structured_score(app, job, timing, config)
        assert score > 70.0
        assert len(dims) == 9

    def test_mismatched_family_lowers_score(self):
        app = _make_applicant(canonical_job_family_code="culinary")
        job = _make_job(canonical_job_family_code="electrical")
        timing = TimingResult(0, "available_now", False)
        config = _default_config()
        score_bad, _ = compute_structured_score(app, job, timing, config)

        app2 = _make_applicant(canonical_job_family_code="electrical")
        score_good, _ = compute_structured_score(app2, job, timing, config)
        assert score_bad < score_good

    def test_dimension_count_always_nine(self):
        app = _make_applicant()
        job = _make_job()
        timing = TimingResult(None, "unknown", False)
        _, dims = compute_structured_score(app, job, timing, _default_config())
        assert len(dims) == 9

    def test_weighted_scores_sum_equals_total(self):
        app = _make_applicant()
        job = _make_job()
        timing = TimingResult(0, "available_now", False)
        total, dims = compute_structured_score(app, job, timing, _default_config())
        assert total == pytest.approx(sum(d.weighted_score for d in dims), abs=0.01)

    def test_score_bounded_0_to_100(self):
        for _ in range(3):
            app = _make_applicant()
            job = _make_job()
            timing = TimingResult(0, "available_now", False)
            score, _ = compute_structured_score(app, job, timing, _default_config())
            assert 0.0 <= score <= 100.0


# ===========================================================================
# engine.py — compute_match integration
# ===========================================================================

class TestComputeMatch:
    _TODAY = date(2026, 3, 10)

    def test_eligible_pair_produces_match_result(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result, MatchResult)
        assert result.eligibility_status == ELIGIBLE
        assert result.hard_gate_cap == 1.0

    def test_ineligible_pair_from_family_mismatch(self):
        app = _make_applicant(canonical_job_family_code="culinary")
        job = _make_job(canonical_job_family_code="electrical",
                        state="TX", region="south",
                        description_raw=None)
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY,
                               scoring_run_id="test-run-001")
        assert result.eligibility_status == INELIGIBLE
        assert result.hard_gate_cap == 0.35

    def test_ineligible_label_is_low_fit(self):
        app = _make_applicant(canonical_job_family_code="culinary",
                              state="IL", region="midwest",
                              willing_to_relocate=False)
        job = _make_job(canonical_job_family_code="electrical",
                        state="TX", region="south")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.match_label == "low_fit"

    def test_base_fit_score_formula(self):
        """base_fit = hard_gate_cap * (struct * 0.75 + semantic * 0.25)"""
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        expected_base = result.hard_gate_cap * (
            result.weighted_structured_score * 0.75
            + result.semantic_score * 0.25
        )
        assert result.base_fit_score == pytest.approx(expected_base, abs=0.01)

    def test_policy_adjusted_score_is_separate(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        # Partner modifier should push policy_adjusted above base (or at least stored separately)
        assert hasattr(result, "base_fit_score")
        assert hasattr(result, "policy_adjusted_score")

    def test_partner_employer_boosts_policy_score(self):
        app = _make_applicant()
        job = _make_job()
        emp_no = _make_employer(is_partner=False)
        emp_yes = _make_employer(is_partner=True)
        r_no = compute_match(app, job, emp_no, _default_config(), self._TODAY)
        r_yes = compute_match(app, job, emp_yes, _default_config(), self._TODAY)
        assert r_yes.policy_adjusted_score >= r_no.policy_adjusted_score

    def test_dimension_scores_length(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert len(result.dimension_scores) == 9

    def test_hard_gate_cap_applied_to_base_fit(self):
        # near_fit applicant (future timing)
        future_date = date(2027, 6, 1)
        app = _make_applicant(expected_completion_date=future_date, available_from_date=None)
        job = _make_job(state="TX", region="south")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        # With a future timing gate FAIL, pair should be ineligible
        # family mismatch (app=electrical, job=electrical state mismatch still near_fit)
        # geography mismatch TX vs IL no relocation → FAIL
        # timing > 12m → FAIL
        assert result.eligibility_status == INELIGIBLE

    def test_match_label_strong_fit_above_80(self):
        """Force a scenario where policy_adjusted_score should be >= 80."""
        # Same state, same family, available_now, partner, competitive pay
        app = _make_applicant(
            state="IL", region="midwest",
            willing_to_relocate=False, willing_to_travel=False,
            expected_completion_date=None,
            available_from_date=date(2025, 1, 1),
            experience_raw="Completed 2-year electrical apprenticeship at ACME Electric Co.",
        )
        job = _make_job(
            state="IL", region="midwest",
            work_setting="on_site",
            pay_min=28.0, pay_max=40.0, pay_type="hourly",
            required_credentials=[],
        )
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.eligibility_status == ELIGIBLE
        assert result.match_label == "strong_fit"

    def test_scoring_run_id_stored_on_result(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY,
                               scoring_run_id="fixed-run-id")
        assert result.scoring_run_id == "fixed-run-id"

    def test_confidence_level_set(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.confidence_level in ("high", "medium", "low")

    def test_top_strengths_and_gaps_are_lists(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result.top_strengths, list)
        assert isinstance(result.top_gaps, list)

    def test_recommended_next_step_is_string(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result.recommended_next_step, str)
        assert len(result.recommended_next_step) > 0

    def test_policy_score_capped_at_100(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.policy_adjusted_score <= 100.0

    def test_policy_score_not_below_zero(self):
        app = _make_applicant(canonical_job_family_code="culinary",
                              state="ME", region="northeast",
                              willing_to_relocate=False)
        job = _make_job(canonical_job_family_code="automotive",
                        state="CA", region="west")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.policy_adjusted_score >= 0.0


# ===========================================================================
# config.py
# ===========================================================================

class TestScoringConfig:
    def test_default_config_loads(self):
        cfg = ScoringConfig()
        assert cfg.version == "v1"
        assert cfg.structured_weight == 0.75
        assert cfg.semantic_weight == 0.25

    def test_default_weights_sum_to_100(self):
        w = StructuredWeights()
        total = (
            w.trade_program_alignment
            + w.geography_alignment
            + w.credential_readiness
            + w.timing_readiness
            + w.experience_internship_alignment
            + w.industry_alignment
            + w.compensation_alignment
            + w.work_style_signal_alignment
            + w.employer_soft_pref_alignment
        )
        assert total == pytest.approx(100.0)

    def test_structured_plus_semantic_weight_equals_1(self):
        cfg = ScoringConfig()
        assert cfg.structured_weight + cfg.semantic_weight == pytest.approx(1.0)

    def test_eligibility_caps_ordering(self):
        caps = EligibilityCapConfig()
        assert caps.eligible > caps.near_fit > caps.ineligible > 0


# ===========================================================================
# JOB_FAMILY_ADJACENCY integrity
# ===========================================================================

class TestJobFamilyAdjacency:
    def test_known_adjacencies_present(self):
        """Spot-check key adjacency relationships used by gate + scorer."""
        assert "hvac" in JOB_FAMILY_ADJACENCY["electrical"]
        assert "construction" in JOB_FAMILY_ADJACENCY["electrical"]
        assert "plumbing" in JOB_FAMILY_ADJACENCY["hvac"]
        assert "automotive" in JOB_FAMILY_ADJACENCY["welding"]

    def test_known_non_adjacencies(self):
        """Unrelated families must NOT appear in each other's adjacent set."""
        assert "culinary" not in JOB_FAMILY_ADJACENCY.get("electrical", set())
        assert "electrical" not in JOB_FAMILY_ADJACENCY.get("culinary", set())

    def test_no_self_adjacency(self):
        for family, adjacent_set in JOB_FAMILY_ADJACENCY.items():
            assert family not in adjacent_set, (
                f"{family} is listed as adjacent to itself"
            )
