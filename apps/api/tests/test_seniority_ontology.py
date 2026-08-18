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
