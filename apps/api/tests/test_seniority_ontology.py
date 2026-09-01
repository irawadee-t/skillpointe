"""Seniority ontology classifier — evidence-based level assignment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from matching.seniority import classify_seniority, extract_years_required  # noqa: E402


class TestYearsExtraction:
    def test_plain_years(self):
        assert extract_years_required("Requires 3 years of experience") == 3

    def test_plus_years(self):
        assert extract_years_required("5+ years experience in HVAC") == 5

    def test_minimum_of(self):
        assert extract_years_required("Minimum of 7 years of related experience") == 7

    def test_range_takes_lower_bound_via_first_number(self):
        assert extract_years_required("2-4 years of field experience") == 2

    def test_wordy_years(self):
        assert extract_years_required("three (3) years of relevant experience") == 3

    def test_highest_wins_across_mentions(self):
        text = "1 year of safety training. 6 years of industrial experience."
        assert extract_years_required(text) == 6

    def test_no_years(self):
        assert extract_years_required("Great attitude required") is None

    def test_absurd_years_ignored(self):
        assert extract_years_required("99 years of experience") is None


class TestClassify:
    def test_apprentice_title_is_entry(self):
        r = classify_seniority("Electrician Apprentice")
        assert r.level == "entry"
        assert r.job_zone == "1-2"

    def test_helper_is_entry(self):
        assert classify_seniority("HVAC Helper").level == "entry"

    def test_will_train_beats_neutral_title(self):
        r = classify_seniority(
            "Machine Operator",
            description="No experience necessary. We will train the right person.",
        )
        assert r.level == "entry"
        assert r.entry_friendly is True
        assert any("no experience" in e.lower() for e in r.evidence)

    def test_years_beats_title_vibes(self):
        r = classify_seniority(
            "Maintenance Technician",
            requirements="Requires 7 years of industrial maintenance experience.",
        )
        assert r.level == "senior"
        assert r.years_required == 7

    def test_two_to_four_years_is_mid(self):
        r = classify_seniority("Welder", requirements="3 years of MIG welding experience")
        assert r.level == "mid"
        assert r.job_zone == "3"

    def test_one_year_is_entry(self):
        assert classify_seniority("Assembler", requirements="1 year experience").level == "entry"

    def test_senior_title(self):
        r = classify_seniority("Senior Controls Technician")
        assert r.level == "senior"

    def test_supervisor_is_management_ladder(self):
        r = classify_seniority("Maintenance Supervisor")
        assert r.level == "management"
        assert r.job_zone == "supervisory"

    def test_foreman_is_management(self):
        assert classify_seniority("Electrical Foreman").level == "management"

    def test_management_not_overridden_by_will_train(self):
        # A supervisory role that offers training is still supervisory.
        r = classify_seniority("Plant Supervisor", description="training provided")
        assert r.level == "management"

    def test_journeyman_is_mid(self):
        assert classify_seniority("Journeyman Plumber").level == "mid"

    def test_will_train_with_high_years_defers_to_years(self):
        # Contradictory posting: "will train" but demands 6 years. The years
        # ask wins; trainability only decides at <= 1 year.
        r = classify_seniority(
            "Technician", description="We will train. Requires 6 years of experience."
        )
        assert r.level == "senior"

    def test_no_signals_defaults_mid_with_flag(self):
        r = classify_seniority("Team Member")
        assert r.level == "mid"
        assert any("defaulted" in e for e in r.evidence)

    def test_every_result_carries_evidence(self):
        for title in ("Apprentice Lineworker", "Senior Welder", "Shop Foreman", "Nurse"):
            assert classify_seniority(title).evidence


class TestGateOntologyWiring:
    """evaluate_seniority_gate consuming the ontology outputs."""

    def _gate(self, **kw):
        from matching.gates import evaluate_seniority_gate
        return evaluate_seniority_gate(
            kw.get("level"), kw.get("years"), is_trade_school=True,
            job_entry_friendly=kw.get("friendly"), job_years_required=kw.get("ask"),
        )

    def test_entry_friendly_passes_trainee_even_on_senior_label(self):
        g = self._gate(level="senior", years=None, friendly=True)
        assert g.result == "pass"
        assert "will train" in g.reason

    def test_entry_friendly_never_overrides_management(self):
        g = self._gate(level="management", years=None, friendly=True)
        assert g.result != "pass"

    def test_stated_ask_met_passes(self):
        g = self._gate(level="senior", years=6, ask=5)
        assert g.result == "pass"
        assert "asks for 5+" in g.reason

    def test_stated_ask_close_is_near_fit(self):
        g = self._gate(level="senior", years=4, ask=5)
        assert g.result == "near_fit"

    def test_stated_ask_far_falls_through_to_level_rules(self):
        g = self._gate(level="senior", years=1, ask=7)
        assert g.result == "fail"

    def test_unknown_years_with_ask_stays_uncertain_not_fail(self):
        g = self._gate(level="senior", years=None, ask=5)
        assert g.result == "near_fit"


class TestBridgeableGaps:
    """Attainable gaps keep doors open with a stated path."""

    def _creds(self, required, certs):
        from matching.gates import evaluate_credential_gate
        return evaluate_credential_gate(required, {}, applicant_certs=certs)

    def test_missing_certification_is_near_fit_not_fail(self):
        g = self._creds(["EPA 608 Certification"], ["OSHA 10"])
        assert g.result == "near_fit"
        assert "attainable" in g.reason

    def test_missing_cdl_is_near_fit(self):
        g = self._creds(["CDL Class A"], [])
        assert g.result == "near_fit"

    def test_missing_degree_still_fails(self):
        g = self._creds(["Bachelor's degree in Engineering"], ["OSHA 10"])
        assert g.result == "fail"

    def test_missing_rn_license_still_fails(self):
        # A nursing license is a program + board exam, not a weekend course.
        g = self._creds(["RN license"], [])
        assert g.result == "fail"

    def test_no_disclosed_certs_stays_near_fit(self):
        g = self._creds(["OSHA 10"], None)
        assert g.result == "near_fit"
        assert "not yet verified" in g.reason


class TestEntryFriendlyCredentialConsistency:
    def test_will_train_softens_degree_to_preference(self):
        from matching.gates import evaluate_credential_gate
        g = evaluate_credential_gate(
            ["Associate's degree", "EPA 608 Certification"], {},
            applicant_certs=["OSHA 10"], job_entry_friendly=True,
        )
        assert g.result == "near_fit"

    def test_degree_still_fails_without_trainability(self):
        from matching.gates import evaluate_credential_gate
        g = evaluate_credential_gate(
            ["Associate's degree"], {},
            applicant_certs=["OSHA 10"], job_entry_friendly=False,
        )
        assert g.result == "fail"


class TestZoneOneTwoTitlesAreEntryFriendly:
    """O*NET Zone 1-2 occupational titles carry no seniority qualifier, and an
    entry classification IS the entry-friendly signal (little preparation by
    definition) — the 2026-09 Home Depot audit found 1,741 Freight/Receiving
    postings defaulted to mid/not-friendly for lack of a "we will train"."""

    def _c(self, title, body=None):
        from matching.seniority import classify_seniority
        return classify_seniority(title, body)

    def test_freight_receiving_is_entry_and_friendly(self):
        s = self._c("Freight/Receiving")
        assert s.level == "entry"
        assert s.entry_friendly is True

    def test_material_mover_titles(self):
        for t in ("Warehouse Associate", "Material Handler", "Order Picker",
                  "Machine Operator", "Custodian", "Lot Associate"):
            s = self._c(t)
            assert s.level == "entry", t
            assert s.entry_friendly is True, t

    def test_one_year_ask_is_entry_friendly(self):
        s = self._c("Production Technician", "1 year of experience required")
        assert s.level == "entry"
        assert s.entry_friendly is True

    def test_bare_technician_still_defaults_mid_not_friendly(self):
        s = self._c("Repair and tool Technician")
        assert s.level == "mid"
        assert s.entry_friendly is False

    def test_senior_and_management_untouched(self):
        assert self._c("Senior Electrician").entry_friendly is False
        assert self._c("Warehouse Supervisor").level == "management"
