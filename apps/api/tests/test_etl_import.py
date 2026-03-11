"""
test_etl_import.py — Unit tests for Phase 4 ETL import pipeline.

These tests cover the mapping and coercion logic WITHOUT a database connection.
They run quickly in CI without Supabase running.

Test coverage:
  - applicant_mapper: column mapping, coercions, validation warnings
  - job_mapper: column mapping, validation errors
  - coerce: bool, date, int, text, state
  - loader: header normalization
  - models: ImportResult counting
"""
import sys
from datetime import date
from pathlib import Path

import pytest

# Allow importing from packages/etl
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from etl.coerce import (
    coerce_bool,
    coerce_date,
    coerce_int,
    coerce_state,
    coerce_text,
    split_full_name,
)
from etl.applicant_mapper import map_row as map_applicant, validate as validate_applicant, COLUMN_MAP as APPLICANT_COLUMN_MAP
from etl.job_mapper import map_row as map_job, validate as validate_job, COLUMN_MAP as JOB_COLUMN_MAP
from etl.models import ImportResult, ImportRowResult


# ============================================================
# coerce helpers
# ============================================================

class TestCoerceBool:
    def test_yes_variants(self):
        for v in ("Y", "y", "yes", "Yes", "YES", "true", "True", "1", "✓"):
            val, warn = coerce_bool(v, "field")
            assert val is True, f"Expected True for {v!r}"
            assert warn is None

    def test_no_variants(self):
        for v in ("N", "n", "no", "No", "false", "False", "0", ""):
            val, warn = coerce_bool(v, "field")
            assert val is False, f"Expected False for {v!r}"

    def test_none_input(self):
        val, warn = coerce_bool(None)
        assert val is None
        assert warn is None

    def test_unrecognised_returns_false_with_warning(self):
        val, warn = coerce_bool("maybe", "relocation")
        assert val is False
        assert warn is not None
        assert "maybe" in warn


class TestCoerceDate:
    def test_iso_date(self):
        val, warn = coerce_date("2025-06-01", "completion")
        assert val == date(2025, 6, 1)
        assert warn is None

    def test_us_format(self):
        val, warn = coerce_date("06/01/2025", "completion")
        assert val is not None
        assert warn is None

    def test_month_year(self):
        val, warn = coerce_date("May 2025", "completion")
        assert val is not None

    def test_none_input(self):
        val, warn = coerce_date(None)
        assert val is None

    def test_blank(self):
        val, warn = coerce_date("", "field")
        assert val is None
        assert warn is None

    def test_na_values(self):
        for v in ("n/a", "N/A", "-", "none"):
            val, warn = coerce_date(v, "field")
            assert val is None, f"Expected None for {v!r}"

    def test_unparseable_returns_warning(self):
        val, warn = coerce_date("not-a-date-at-all-xyz", "field")
        assert val is None
        assert warn is not None


class TestCoerceInt:
    def test_plain_number(self):
        val, warn = coerce_int("25", "commute")
        assert val == 25
        assert warn is None

    def test_with_unit(self):
        val, warn = coerce_int("25 miles", "commute")
        assert val == 25

    def test_none(self):
        val, warn = coerce_int(None)
        assert val is None


class TestCoerceText:
    def test_strips_whitespace(self):
        assert coerce_text("  hello  ") == "hello"

    def test_blank_returns_none(self):
        assert coerce_text("") is None
        assert coerce_text("   ") is None

    def test_none_returns_none(self):
        assert coerce_text(None) is None


class TestCoerceState:
    def test_uppercases(self):
        assert coerce_state("ny") == "NY"
        assert coerce_state("California") == "CALIFORNIA"

    def test_none(self):
        assert coerce_state(None) is None


class TestSplitFullName:
    def test_first_last(self):
        first, last = split_full_name("Jane Smith")
        assert first == "Jane"
        assert last == "Smith"

    def test_last_comma_first(self):
        first, last = split_full_name("Smith, Jane")
        assert first == "Jane"
        assert last == "Smith"

    def test_single_word(self):
        first, last = split_full_name("Jane")
        assert first == "Jane"
        assert last is None

    def test_none(self):
        first, last = split_full_name(None)
        assert first is None
        assert last is None


# ============================================================
# applicant_mapper
# ============================================================

class TestApplicantMapper:
    def _make_row(self, **kwargs):
        return kwargs

    def test_basic_identity_fields(self):
        row = self._make_row(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="555-1234",
        )
        applicant, warnings = map_applicant(row)
        assert applicant.first_name == "Jane"
        assert applicant.last_name == "Smith"
        assert applicant.email == "jane@example.com"
        assert applicant.phone == "555-1234"
        assert warnings == []

    def test_full_name_split(self):
        row = self._make_row(name="Jane Smith")
        applicant, _ = map_applicant(row)
        assert applicant.first_name == "Jane"
        assert applicant.last_name == "Smith"

    def test_email_lowercased(self):
        row = self._make_row(email="Jane@EXAMPLE.COM")
        applicant, _ = map_applicant(row)
        assert applicant.email == "jane@example.com"

    def test_willing_to_relocate_coerced(self):
        row = self._make_row(willing_to_relocate="Y", willing_to_travel="No")
        applicant, _ = map_applicant(row)
        assert applicant.willing_to_relocate is True
        assert applicant.willing_to_travel is False

    def test_date_coercion(self):
        row = self._make_row(expected_completion_date="2025-08-01")
        applicant, _ = map_applicant(row)
        assert applicant.expected_completion_date == date(2025, 8, 1)

    def test_state_uppercased(self):
        row = self._make_row(state="ny")
        applicant, _ = map_applicant(row)
        assert applicant.state == "NY"

    def test_program_name_preserved_raw(self):
        row = self._make_row(program="Electrical Apprenticeship Program - IBEW")
        applicant, _ = map_applicant(row)
        assert applicant.program_name_raw == "Electrical Apprenticeship Program - IBEW"

    def test_unmapped_column_goes_to_extra(self):
        row = self._make_row(some_unknown_column="some value")
        applicant, _ = map_applicant(row)
        assert "some_unknown_column" in applicant.extra
        assert applicant.extra["some_unknown_column"] == "some value"

    def test_alternate_header_names(self):
        """Verify a few alternate header names all map correctly."""
        # programme → program_name_raw
        row = self._make_row(programme="Plumbing Certificate")
        applicant, _ = map_applicant(row)
        assert applicant.program_name_raw == "Plumbing Certificate"

        # essay → bio_raw
        row = self._make_row(essay="I want to work in the trades.")
        applicant, _ = map_applicant(row)
        assert applicant.bio_raw == "I want to work in the trades."

    def test_validate_warns_missing_program(self):
        row = self._make_row(first_name="Jane", last_name="Smith", city="NYC", state="NY")
        applicant, _ = map_applicant(row)
        warnings = validate_applicant(applicant, 1)
        assert any("program" in w.lower() or "trade" in w.lower() for w in warnings)

    def test_validate_warns_missing_location(self):
        row = self._make_row(first_name="Jane", program="Electrical")
        applicant, _ = map_applicant(row)
        warnings = validate_applicant(applicant, 1)
        assert any("city" in w.lower() or "state" in w.lower() or "location" in w.lower() for w in warnings)

    def test_validate_no_warnings_for_complete_row(self):
        row = self._make_row(
            first_name="Jane",
            last_name="Smith",
            program="Electrical",
            city="New York",
            state="NY",
            expected_completion_date="2025-06-01",
        )
        applicant, map_warn = map_applicant(row)
        warnings = validate_applicant(applicant, 1)
        assert not map_warn
        assert not warnings

    # ---- Real SkillPointe column names ----

    def test_folder_name_splits_to_first_last(self):
        """'Folder - Name' column (normalized: folder_name) → first/last name."""
        row = self._make_row(folder_name="Smith, Jane")
        applicant, _ = map_applicant(row)
        assert applicant.first_name == "Jane"
        assert applicant.last_name == "Smith"

    def test_linked_personalized_account_to_email(self):
        """'Linked Personalized Account' (normalized: linked_personalized_account) → email."""
        row = self._make_row(linked_personalized_account="Jane@Example.COM")
        applicant, _ = map_applicant(row)
        assert applicant.email == "jane@example.com"

    def test_school_state_strips_us_prefix(self):
        """'School State:' column returns 'US-TX' in the export; strip 'US-' → 'TX'."""
        row = self._make_row(school_state_="US-TX")
        applicant, _ = map_applicant(row)
        assert applicant.state == "TX"

    def test_school_city_trailing_colon(self):
        """'School City:' column (trailing colon normalised to _) → city."""
        row = self._make_row(school_city_="Detroit")
        applicant, _ = map_applicant(row)
        assert applicant.city == "Detroit"

    def test_completion_month_year_combined(self):
        """program_completion_month + program_completion_year → expected_completion_date."""
        row = self._make_row(
            program_completion_month="June",
            program_completion_year="2025",
        )
        applicant, _ = map_applicant(row)
        assert applicant.expected_completion_date is not None
        assert applicant.expected_completion_date.year == 2025

    def test_completion_currently_enrolled_skipped(self):
        """'Currently Enrolled' year should not produce a date."""
        row = self._make_row(
            program_completion_month="",
            program_completion_year="Currently Enrolled",
        )
        applicant, _ = map_applicant(row)
        assert applicant.expected_completion_date is None

    def test_program_double_spaces_normalised(self):
        """Double spaces in program name (SkillPointe export artifact) are collapsed."""
        row = self._make_row(program_field_of_study="Transportation  - Auto Technician")
        applicant, _ = map_applicant(row)
        assert applicant.program_name_raw == "Transportation - Auto Technician"

    def test_program_supplement_fills_when_other(self):
        """program_field_of_study_other fills program_name_raw if main field is 'Other'."""
        row = self._make_row(
            program_field_of_study="Other",
            program_field_of_study_other="Custom Trade Program",
        )
        applicant, _ = map_applicant(row)
        assert applicant.program_name_raw == "Custom Trade Program"

    def test_activities_appended_to_experience(self):
        """activities_extracurriculars appended to experience_raw with separator."""
        row = self._make_row(
            internship_details="Worked at HVAC company.",
            activities_extracurriculars="SkillsUSA member.",
        )
        applicant, _ = map_applicant(row)
        assert "Worked at HVAC company." in applicant.experience_raw
        assert "SkillsUSA member." in applicant.experience_raw
        assert "Activities" in applicant.experience_raw

    def test_essay_1_to_bio_raw(self):
        """essay_1_background_driving_passion → bio_raw."""
        row = self._make_row(essay_1_background_driving_passion="I love the trades.")
        applicant, _ = map_applicant(row)
        assert applicant.bio_raw == "I love the trades."

    def test_essay_2_to_career_goals_raw(self):
        """essay_2_post_graduation_scholarship_impact → career_goals_raw."""
        row = self._make_row(essay_2_post_graduation_scholarship_impact="I plan to open a shop.")
        applicant, _ = map_applicant(row)
        assert applicant.career_goals_raw == "I plan to open a shop."


# ============================================================
# job_mapper
# ============================================================

class TestJobMapper:
    def test_basic_job_fields(self):
        row = dict(
            company="Acme Electric",
            title="Electrician",
            description="Install electrical systems",
            city="New York",
            state="NY",
            pay="$25-$35/hr",
        )
        job, warnings = map_job(row)
        assert job.employer_name == "Acme Electric"
        assert job.title_raw == "Electrician"
        assert job.description_raw == "Install electrical systems"
        assert job.city == "New York"
        assert job.state == "NY"
        assert job.pay_raw == "$25-$35/hr"

    def test_default_employer_name_used_when_no_company_column(self):
        row = dict(title="Plumber", description="Install pipes")
        job, _ = map_job(row, default_employer_name="Demo Corp")
        assert job.employer_name == "Demo Corp"

    def test_company_column_overrides_default(self):
        row = dict(company="Real Corp", title="Welder")
        job, _ = map_job(row, default_employer_name="Default Corp")
        assert job.employer_name == "Real Corp"

    def test_validate_fails_without_employer(self):
        row = dict(title="Electrician", description="desc")
        job, _ = map_job(row)
        is_valid, issues = validate_job(job, 1)
        assert is_valid is False
        assert any("employer" in i.lower() for i in issues)

    def test_validate_warns_missing_title(self):
        row = dict(company="Acme", description="desc")
        job, _ = map_job(row)
        is_valid, issues = validate_job(job, 1)
        assert is_valid is True  # not a hard error
        assert any("title" in i.lower() for i in issues)

    def test_unmapped_column_goes_to_extra(self):
        row = dict(company="Acme", some_extra_field="value123")
        job, _ = map_job(row)
        assert "some_extra_field" in job.extra

    def test_pay_preserved_raw(self):
        row = dict(company="Acme", salary="$60,000 - $80,000 annually")
        job, _ = map_job(row)
        assert job.pay_raw == "$60,000 - $80,000 annually"

    # ---- Real SkillPointe job column names ----

    def test_locations_parsed_to_city_state(self):
        """Semicolon-delimited 'Detroit, MI; Dallas, TX' → city='Detroit', state='MI'."""
        row = dict(
            company="Acme",
            job_id="J001",
            locations="Detroit, MI; Dallas, TX; Raleigh, NC",
        )
        job, _ = map_job(row)
        assert job.city == "Detroit"
        assert job.state == "MI"
        assert job.extra.get("all_locations_raw") == "Detroit, MI; Dallas, TX; Raleigh, NC"

    def test_remote_status_no_maps_to_on_site(self):
        """Remote_Status 'No' → work_setting 'on_site'."""
        row = dict(company="Acme", remote_status="No")
        job, _ = map_job(row)
        assert job.work_setting == "on_site"

    def test_remote_status_hybrid_maps_correctly(self):
        """Remote_Status 'Hybrid (field-based)' → work_setting 'hybrid'."""
        row = dict(company="Acme", remote_status="Hybrid (field-based)")
        job, _ = map_job(row)
        assert job.work_setting == "hybrid"

    def test_career_pathway_stored_in_extra(self):
        """career_pathway stored in extra['career_pathway_raw']."""
        row = dict(company="Acme", career_pathway="Electrician")
        job, _ = map_job(row)
        assert job.extra.get("career_pathway_raw") == "Electrician"

    def test_career_pathway_used_as_title_fallback(self):
        """career_pathway is used as title_raw when no explicit title column present."""
        row = dict(company="Acme", career_pathway="HVAC Technician")
        job, _ = map_job(row)
        assert job.title_raw == "HVAC Technician"

    def test_career_pathway_not_overrides_explicit_title(self):
        """Explicit title takes precedence over career_pathway fallback."""
        row = dict(company="Acme", job_title="Lead Electrician", career_pathway="Electrician")
        job, _ = map_job(row)
        assert job.title_raw == "Lead Electrician"

    def test_job_summary_to_description_raw(self):
        """job_summary → description_raw (SkillPointe jobs file column name)."""
        row = dict(company="Acme", job_summary="Install and maintain electrical systems.")
        job, _ = map_job(row)
        assert job.description_raw == "Install and maintain electrical systems."

    def test_pay_range_usd_preserved_raw(self):
        """pay_range_usd (e.g. '$22/hr–$33/hr') stored as pay_raw without parsing."""
        row = dict(company="Acme", pay_range_usd="$22/hr\u2013$33/hr")
        job, _ = map_job(row)
        assert job.pay_raw == "$22/hr\u2013$33/hr"

    def test_job_id_stored_in_extra(self):
        """job_id → extra['source_job_id']."""
        row = dict(company="Acme", job_id="SKP-042")
        job, _ = map_job(row)
        assert job.extra.get("source_job_id") == "SKP-042"


# ============================================================
# ImportResult counting
# ============================================================

class TestImportResult:
    def test_counts(self):
        result = ImportResult(import_type="applicants", source_file="test.csv")
        result.add_row(ImportRowResult(row_number=1, status="success", raw_data={}))
        result.add_row(ImportRowResult(row_number=2, status="warning", raw_data={}))
        result.add_row(ImportRowResult(row_number=3, status="error", raw_data={}))
        result.add_row(ImportRowResult(row_number=4, status="skipped", raw_data={}))
        assert result.total_rows == 4
        assert result.success_count == 1
        assert result.warning_count == 1
        assert result.error_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1


# ============================================================
# loader — header normalization
# ============================================================

class TestHeaderNormalization:
    def test_normalize_header(self):
        from etl.loader import _normalize_header
        assert _normalize_header("First Name") == "first_name"
        assert _normalize_header("  Last-Name  ") == "last_name"
        assert _normalize_header("ZIP") == "zip"
        assert _normalize_header("Expected Completion Date") == "expected_completion_date"
        assert _normalize_header("E-Mail") == "e_mail"

    def test_normalize_real_skillpointe_headers(self):
        """Real SkillPointe export headers with leading spaces, colons, slashes."""
        from etl.loader import _normalize_header
        # Trailing colons → trailing underscore, then stripped by h.strip("_")
        assert _normalize_header(" School City:") == "school_city"
        assert _normalize_header(" School State:") == "school_state"
        assert _normalize_header(" Program Completion Month") == "program_completion_month"
        assert _normalize_header(" Program Completion Year") == "program_completion_year"
        # Slash in "Program/Field Of Study" → underscore
        assert _normalize_header(" Program/Field Of Study") == "program_field_of_study"
        assert _normalize_header("Essay 1 - Background & Driving Passion") == "essay_1_background_driving_passion"
        assert _normalize_header("Folder - Name") == "folder_name"
        assert _normalize_header("Linked Personalized Account") == "linked_personalized_account"

    def test_load_csv_from_string(self, tmp_path):
        """Test that load_file handles a real CSV correctly."""
        from etl.loader import load_file
        csv_content = "First Name,Last Name,Program Name,City,State\nJane,Smith,Electrical,New York,NY\n"
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        rows, raw_headers, norm_headers = load_file(csv_file)
        assert len(rows) == 1
        assert rows[0]["first_name"] == "Jane"
        assert rows[0]["last_name"] == "Smith"
        assert rows[0]["program_name"] == "Electrical"
        assert raw_headers[0] == "First Name"
        assert norm_headers[0] == "first_name"
