"""
test_explanation_accuracy.py — plain-language match explanations must be
provably derived from the pair's real data, on BOTH marketplace sides.

Covers the fixes from the explanation-accuracy audit:
  Engine (packages/matching):
    - no "Pay matches expectations" (we never collect pay expectations) —
      the job's real pay figures are surfaced instead
    - no "You have the credentials" when the job simply lists no requirements
    - soft skills assumed from an empty profile are never claimed as a
      verified "Matches employer preferences" strength
    - timing strengths state the real availability ("Available in ~4 months")
    - next_step never lowercases credential acronyms ("OSHA 10", not "osha 10")
    - geography-failure next_step is actionable, not a raw distance dump
    - "Related trade" tier wording requires BOTH family codes to be known
    - trade-mismatch gaps read plainly (no "unrelated families: applicant=…")
  Employer serving layer (apps/api):
    - stored applicant-voice sentences are re-voiced for employers
      (same facts, employer perspective, no "apply now" advice)
    - "Local:" geography note requires a verified distance, never
      same-state string equality alone
    - AI-priority reasons are deterministically validated against the exact
      grounded input (invented numbers / promise language rejected)

All tests are pure — no DB, no network.
"""
import sys
from datetime import date
from pathlib import Path

# Allow importing from packages/matching
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.config import ScoringConfig
from matching.engine import _strength_text, compute_match
from matching.scorer import DimensionScore

from app.routers.employers import _derive_applicant_geography_note
from app.services.explanation_voice import (
    fallback_priority_reason,
    next_step_for_employer,
    to_employer_voice,
    validate_priority_reason,
)

_TODAY = date(2026, 8, 1)


def _applicant(**kwargs) -> dict:
    base = {
        "id": "app-001",
        "first_name": "Jane",
        "last_name": "Smith",
        "canonical_job_family_code": "electrical",
        "city": "Shelton",
        "state": "CT",
        "region": "northeast",
        "lat": 41.30,
        "lng": -73.10,
        "willing_to_relocate": False,
        "willing_to_travel": False,
        "expected_completion_date": None,
        "available_from_date": date(2026, 1, 1),  # past → available_now
        "experience_raw": "Completed a 2-year electrical apprenticeship.",
        "bio_raw": "Ready for a first role on a service team.",
        "career_goals_raw": "Become a licensed journeyman electrician.",
        "program_name_raw": "Electrical Apprentice",
    }
    base.update(kwargs)
    return base


def _job(**kwargs) -> dict:
    base = {
        "id": "job-001",
        "employer_id": "emp-001",
        "title_raw": "Electrician",
        "title_normalized": "Electrician",
        "canonical_job_family_code": "electrical",
        "city": "Bridgeport",
        "state": "CT",
        "region": "northeast",
        "lat": 41.19,
        "lng": -73.20,
        "work_setting": "on_site",
        "travel_requirement": None,
        "pay_min": 25.0,
        "pay_max": 35.0,
        "pay_type": "hourly",
        "required_credentials": [],
        "description_raw": None,
        "experience_level": "entry",
    }
    base.update(kwargs)
    return base


_EMP = {"id": "emp-001", "name": "ACME Electric", "is_partner": False}


def _run(app=None, job=None, **kw):
    return compute_match(app or _applicant(), job or _job(), _EMP,
                         ScoringConfig(), today=_TODAY, **kw)


# ---------------------------------------------------------------------------
# Engine — grounded strength wording
# ---------------------------------------------------------------------------

class TestGroundedStrengths:
    def test_pay_strength_uses_real_figures_not_expectations(self):
        # Bad sentence reproduced: "Pay matches expectations" — the platform
        # never collects pay expectations, so that claim was unfounded.
        r = _run()
        assert "Pay matches expectations" not in r.top_strengths
        d = DimensionScore("compensation_alignment", 5, 75.0, 3.75,
                           "competitive hourly pay: $25–$35/hr")
        assert _strength_text(d) == "Competitive hourly pay: $25–$35/hr"

    def test_annual_pay_strength_uses_real_figures(self):
        d = DimensionScore("compensation_alignment", 5, 75.0, 3.75,
                           "competitive salary: $52,000–$64,000/yr")
        assert _strength_text(d) == "Competitive salary: $52,000–$64,000/yr"
        # non-competitive rationale never produces a pay strength
        d2 = DimensionScore("compensation_alignment", 5, 70.0, 3.5,
                            "pay data present but below competitive threshold")
        assert _strength_text(d2) is None

    def test_no_credential_claim_when_job_lists_no_requirements(self):
        # Bad sentence reproduced: "You have the credentials" on a job with
        # zero credential/education/experience requirements.
        r = _run()
        assert "You have the credentials" not in r.top_strengths
        assert "No extra credentials required" in r.top_strengths

    def test_credential_strength_kept_when_actually_matched(self):
        signals = {"certifications_extracted": [{"name": "OSHA 10"}]}
        r = _run(job=_job(required_credentials=["OSHA 10"]),
                 applicant_signals=signals)
        assert "You have the credentials" in r.top_strengths

    def test_assumed_soft_skills_never_claimed_as_strength(self):
        # Empty profile + soft-keyword job description → the scorer assumes
        # baseline trade-training soft skills. That assumption must not be
        # presented as "Matches employer preferences".
        app = _applicant(experience_raw="", bio_raw="", career_goals_raw="")
        job = _job(description_raw="Join our team. Safety first — reliable, "
                                   "dependable people who solve problems.")
        r = _run(app=app, job=job)
        assert "Matches employer preferences" not in r.top_strengths

    def test_real_soft_skill_overlap_still_a_strength(self):
        app = _applicant(
            bio_raw="I take safety seriously and love working on a team.",
        )
        job = _job(description_raw="We value safety and teamwork above all. "
                                   "Team players wanted.")
        r = _run(app=app, job=job)
        assert "Matches employer preferences" in r.top_strengths

    def test_available_now_strength_is_specific(self):
        r = _run()
        assert "Available now" in r.top_strengths
        assert "Timing is right" not in r.top_strengths

    def test_months_out_strength_states_real_availability(self):
        # Job with an unmet credential requirement pushes the credential
        # dimension out of the top-4, letting the timing strength surface.
        app = _applicant(available_from_date=None,
                         expected_completion_date=date(2026, 12, 15))
        r = _run(app=app,
                 job=_job(required_credentials=["EPA 608"]),
                 applicant_signals={"certifications_extracted": []})
        assert "Available in ~4 months" in r.top_strengths
        assert "Timing is right" not in r.top_strengths

    def test_strength_text_timing_variants(self):
        mk = lambda r: DimensionScore("timing_readiness", 10, 90.0, 9.0, r)
        assert _strength_text(mk("applicant is available now")) == "Available now"
        assert (_strength_text(mk("near completion (~2 months)"))
                == "Finishing your program in ~2 months")
        assert (_strength_text(mk("in progress (~5 months to available)"))
                == "Available in ~5 months")


# ---------------------------------------------------------------------------
# Engine — next step + gap wording
# ---------------------------------------------------------------------------

class TestNextStepAndGaps:
    def test_next_step_preserves_acronym_case(self):
        # Bad sentence reproduced: "Look into: required credentials [osha 10]…"
        # (old code lowercased the whole string). Since the attainability rule
        # (2026-08), a missing certification is a bridgeable near_fit, not an
        # ineligible — and the next step states the path with case intact.
        signals = {"certifications_extracted": []}
        r = _run(job=_job(required_credentials=["OSHA 10"]),
                 applicant_signals=signals)
        assert r.eligibility_status == "near_fit"
        assert "OSHA 10" in r.recommended_next_step
        assert "osha" not in r.recommended_next_step
        assert "earn" in r.recommended_next_step.lower()

    def test_geography_fail_next_step_is_actionable(self):
        # Bad sentence reproduced: "Look into: ~620 mi away — beyond your…"
        app = _applicant(commute_radius_miles=25, travel_preference="regional")
        job = _job(city="Louisville", state="KY", region="south",
                   lat=38.25, lng=-85.76)
        r = _run(app=app, job=job)
        assert r.eligibility_status == "ineligible"
        assert r.recommended_next_step.startswith("Outside your commute area")
        assert not r.recommended_next_step.startswith("Look into: ~")

    def test_trade_mismatch_gap_reads_plainly(self):
        # Bad sentence reproduced: "unrelated families: applicant=welding,
        # job=nursing" shown verbatim to a trainee. (Industrial trades are
        # all mutually adjacent, so cross into healthcare for a true FAIL.)
        app = _applicant(canonical_job_family_code="welding")
        job = _job(canonical_job_family_code="nursing")
        r = _run(app=app, job=job)
        assert r.eligibility_status == "ineligible"
        joined = " | ".join(r.top_gaps + r.required_missing_items)
        assert "unrelated families" not in joined
        # engine copy de-dashed (2026-08): comma instead of em dash
        assert "this is a nursing role, your training is in welding" in joined

    def test_trade_mismatch_not_restated_three_times(self):
        # The gate gap already explains the trade mismatch in full — the
        # generic "Different trade background" / "Different industry" chips
        # must not pile on as redundant restatements.
        app = _applicant(canonical_job_family_code="welding")
        job = _job(canonical_job_family_code="nursing")
        r = _run(app=app, job=job)
        assert any(g.startswith("Trade alignment") for g in r.top_gaps)
        assert "Different trade background" not in r.top_gaps
        assert "Different industry" not in r.top_gaps


# ---------------------------------------------------------------------------
# Engine — tier wording honesty
# ---------------------------------------------------------------------------

class TestTierWording:
    def test_unknown_family_never_claims_related_trade(self):
        # Bad sentence reproduced: tier_reason "Related trade, near you" for
        # an applicant whose program/family was never set.
        app = _applicant(canonical_job_family_code=None)
        r = _run(app=app)
        assert r.match_tier == "adjacent"
        assert "Related trade" not in (r.tier_reason or "")
        assert "Add your trade" in (r.tier_reason or "")

    def test_known_adjacent_family_still_says_related_trade(self):
        app = _applicant(canonical_job_family_code="welding")
        job = _job(canonical_job_family_code="manufacturing")
        r = _run(app=app, job=job)
        assert r.match_tier == "adjacent"
        assert (r.tier_reason or "").startswith("Related trade")


# ---------------------------------------------------------------------------
# Employer serving layer — perspective re-voicing
# ---------------------------------------------------------------------------

class TestEmployerVoice:
    def test_exact_labels_revoiced(self):
        assert to_employer_voice("Your trade matches this role") == "Trade matches this role"
        assert to_employer_voice("You have the credentials") == "Has the required credentials"
        assert to_employer_voice("Location works for you") == "Location works"
        assert (to_employer_voice("No extra credentials required")
                == "Meets the posted requirements")

    def test_distance_sentence_keeps_facts_changes_pronouns(self):
        # engine copy de-dashed (2026-08): comma instead of em dash
        out = to_employer_voice("~14 mi from Troy, inside your 50 mi radius")
        assert out == "~14 mi from Troy, within their 50 mi commute radius"

    def test_applicant_advice_clause_dropped(self):
        # engine copy de-dashed (2026-08): comma instead of em dash
        out = to_employer_voice(
            "Location: ~62 mi away, beyond your 25 mi radius; "
            "consider widening your radius or updating relocation settings"
        )
        assert out == "Location: ~62 mi away, beyond their 25 mi commute radius"
        assert "consider" not in out

    def test_unset_prefs_sentence_revoiced(self):
        # engine copy de-dashed (2026-08): comma instead of em dash
        out = to_employer_voice(
            "~57 mi away, beyond the default 50 mi radius; "
            "set your commute radius or relocation preferences to confirm"
        )
        assert "your" not in out
        assert "commute preferences not set yet" in out

    def test_next_step_apply_now_becomes_employer_action(self):
        # Bad sentence reproduced: employer card said
        # "Suggested: You're a strong match. Apply now.".
        # engine copy de-dashed (2026-08): sentence breaks instead of em dashes
        assert (next_step_for_employer("You're a strong match. Apply now.")
                == "Strong match. Consider reaching out.")
        assert (next_step_for_employer("Good fit. Review the description and apply.")
                == "Good fit. Review their profile.")
        assert next_step_for_employer(None) is None

    def test_legacy_dashed_rows_still_revoiced_dash_free(self):
        # Rows scored before the de-dash pass keep serving employer copy
        # without applicant-directed advice or em-dash next-steps.
        assert (next_step_for_employer("You're a strong match — apply now")
                == "Strong match. Consider reaching out.")
        assert (next_step_for_employer("Worth a look — location")
                == "Worth a look: location")

    def test_next_step_look_into_revoiced(self):
        out = next_step_for_employer("Look into: requires OSHA 10")
        assert out == "Gap to close: requires OSHA 10"


# ---------------------------------------------------------------------------
# Employer serving layer — geography note honesty
# ---------------------------------------------------------------------------

class TestEmployerGeographyNote:
    def _row(self, **kw):
        base = {
            "job_work_setting": "on_site",
            "state": "CA",
            "city": "Santa Ana",
            "job_state": "CA",
            "willing_to_relocate": False,
            "willing_to_travel": False,
            "distance_miles": None,
        }
        base.update(kw)
        return base

    def test_same_state_far_away_is_not_local(self):
        # Bad sentence reproduced: "Local: Santa Ana, CA" for a job 377 mi
        # away (same-state string equality is not proximity).
        note = _derive_applicant_geography_note(self._row(distance_miles=377.2))
        assert not note.startswith("Local")
        assert "~377 mi" in note

    def test_verified_short_distance_is_local(self):
        # geography note de-dashed (2026-08): colon/parens instead of em dash
        note = _derive_applicant_geography_note(self._row(distance_miles=12.0))
        assert note == "Local: Santa Ana, CA (~12 mi from job)"

    def test_same_state_without_distance_says_same_state(self):
        # geography note de-dashed (2026-08): colon/parens instead of em dash
        note = _derive_applicant_geography_note(self._row())
        assert note == "Santa Ana, CA (same state as job)"
        assert "Local" not in note

    def test_remote_job_has_no_note(self):
        assert _derive_applicant_geography_note(
            self._row(job_work_setting="remote")) is None


# ---------------------------------------------------------------------------
# AI-priority reason grounding guard
# ---------------------------------------------------------------------------

class TestPriorityReasonGuard:
    SOURCE = ("3. Maria Lopez | Score: 78 | eligible | "
              "Strengths: Trade matches this role; Available now | Gaps: — | "
              "HVAC Technician")

    def test_grounded_reason_accepted(self):
        out = validate_priority_reason(
            "Maria scores 78 and is available now with a matching trade.",
            self.SOURCE,
        )
        assert out is not None

    def test_invented_number_rejected(self):
        # e.g. a hallucinated "5 years of experience" that exists nowhere
        # in the grounded candidate data.
        assert validate_priority_reason(
            "Maria has 5 years of HVAC experience and scores 78.",
            self.SOURCE,
        ) is None

    def test_promise_language_rejected(self):
        assert validate_priority_reason(
            "Guaranteed to succeed — contact first.", self.SOURCE) is None

    def test_empty_and_overlong_rejected(self):
        assert validate_priority_reason("", self.SOURCE) is None
        assert validate_priority_reason("word " * 60, self.SOURCE) is None

    def test_fallback_reason_uses_real_strength(self):
        # Offline mode prints the candidate's OWN top strength — a real
        # per-candidate differentiator, not shared boilerplate.
        out = fallback_priority_reason(["Your trade matches this role"])
        assert out == "Trade matches this role."

    def test_fallback_reason_without_strengths_is_empty(self):
        # No candidate-specific signal → no reason line at all (the UI hides
        # it) rather than the same sentence repeated for every candidate.
        assert fallback_priority_reason([]) == ""
