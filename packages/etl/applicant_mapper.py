"""
applicant_mapper.py — maps a raw CSV/XLSX row to a MappedApplicant.

Built for the real SkillPointe scholarship applicant export format.
Header normalization has already been applied by loader.py before
this mapper is called (leading/trailing whitespace stripped, lowercase,
special chars → underscores).

Column mapping philosophy:
  - All raw text fields are preserved verbatim
  - Essays → bio_raw (Essay 1) and career_goals_raw (Essay 2)
  - Internship details + activities → experience_raw (combined)
  - School location is used as applicant location proxy (no home address in data)
  - School state strips the "US-" prefix from values like "US-TX"
  - Completion month + year are combined into expected_completion_date
  - Everything not explicitly mapped goes to MappedApplicant.extra
    (preserved in import_rows.raw_data; available for future normalisation)

Special targets (start with "_"):
  _full_name        → split into first_name / last_name
  _email            → email field, lowercased
  _school_state     → strip "US-" prefix, then → state
  _completion_month → stored for month+year combination at end of map_row
  _completion_year  → stored for month+year combination at end of map_row
  _start_month      → stored for available_from_date combination
  _start_year       → stored for available_from_date combination
  _activities       → appended to experience_raw with separator
  _program_supplement → fills program_name_raw only if currently empty

Run `python scripts/import_applicants.py --file <file> --inspect-headers`
to see which columns in your file are not yet mapped.
"""
from __future__ import annotations

from typing import Any

from .coerce import coerce_date, coerce_state, coerce_text, split_full_name
from .models import MappedApplicant

# ---------------------------------------------------------------------------
# Column map: normalized_file_header → target_field (or _special)
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {

    # ---- Full name (SkillPointe exports use 'Folder - Name') ----
    "folder_name":                              "_full_name",
    "folder___name":                            "_full_name",   # alt normalisation
    "name":                                     "_full_name",
    "full_name":                                "_full_name",
    "applicant_name":                           "_full_name",
    "student_name":                             "_full_name",
    "participant_name":                         "_full_name",
    "first_name":                               "first_name",
    "firstname":                                "first_name",
    "last_name":                                "last_name",
    "lastname":                                 "last_name",
    "preferred_name":                           "preferred_name",

    # ---- Email (SkillPointe uses 'Linked Personalized Account') ----
    "linked_personalized_account":              "_email",
    "email":                                    "_email",
    "email_address":                            "_email",
    "student_email":                            "_email",
    "applicant_email":                          "_email",

    # ---- Phone ----
    "phone":                                    "phone",
    "phone_number":                             "phone",
    "cell":                                     "phone",
    "mobile":                                   "phone",

    # ---- School location (used as applicant location proxy) ----
    # Real applicant home address is not present in the export.
    # School city/state is the best available geography signal.
    "school_city":                              "city",
    "school_city_":                             "city",       # trailing colon gets normalised to _
    "school_state":                             "_school_state",
    "school_state_":                            "_school_state",
    "home_city":                                "city",
    "home_state":                               "state",
    "city":                                     "city",
    "state":                                    "state",
    "zip":                                      "zip_code",
    "zip_code":                                 "zip_code",

    # Geography preferences (not in current export; kept for future imports)
    "willing_to_relocate":                      "willing_to_relocate",
    "willing_to_travel":                        "willing_to_travel",
    "relocation":                               "willing_to_relocate",
    "travel":                                   "willing_to_travel",
    "commute_radius_miles":                     "commute_radius_miles",
    "commute_radius":                           "commute_radius_miles",

    # ---- Programme / trade (raw — normalised in Phase 4.3) ----
    # ' Program/Field Of Study' normalises to program_field_of_study
    "program_field_of_study":                   "program_name_raw",
    "program_field_of_study_other":             "_program_supplement",  # fills if raw is blank/"Other"
    "specific_career_field_of_study":           "_specific_career",     # → extra['specific_career']
    "career_path":                              "_career_path",          # → extra['career_path_raw']
    "program":                                  "program_name_raw",
    "programme":                                "program_name_raw",
    "program_name":                             "program_name_raw",
    "trade_program":                            "program_name_raw",
    "trade":                                    "program_name_raw",
    "pathway":                                  "program_name_raw",
    "career_pathway":                           "program_name_raw",
    "major":                                    "program_name_raw",
    "field_of_study":                           "program_name_raw",
    "course":                                   "program_name_raw",

    # ---- Degree / enrollment type ----
    "degree_program":                           "_degree_type",   # → extra
    "degree_type":                              "_degree_type",
    "degree_type_other":                        "_degree_type",   # override if set
    "current_enrollment":                       "_enrollment_type",  # → extra

    # ---- School info ----
    "school_name":                              "_school_name",   # → extra
    "school_name_":                             "_school_name",
    "campus_name_if_relevant":                  "_campus_name",   # → extra

    # ---- Timing ----
    # SkillPointe stores completion as two separate fields: month + year
    "program_completion_month":                 "_completion_month",
    "program_completion_year":                  "_completion_year",
    "program_start_month":                      "_start_month",
    "program_start_year":                       "_start_year",
    "expected_completion_date":                 "expected_completion_date",
    "expected_completion":                      "expected_completion_date",
    "graduation_date":                          "expected_completion_date",
    "available_from_date":                      "available_from_date",
    "availability":                             "timing_notes",
    "timing_notes":                             "timing_notes",

    # ---- Career goals / essays ----
    # Essay 1 → bio_raw (background, passion)
    # Essay 2 → career_goals_raw (post-graduation vision)
    "essay_1___background___driving_passion":   "bio_raw",
    "essay_1_background_driving_passion":       "bio_raw",
    "essay_1":                                  "bio_raw",
    "bio":                                      "bio_raw",
    "essay":                                    "bio_raw",
    "personal_statement":                       "bio_raw",
    "about_me":                                 "bio_raw",
    "statement":                                "bio_raw",
    "background":                               "bio_raw",

    "essay_2___post_graduation___scholarship_impact":  "career_goals_raw",
    "essay_2_post_graduation_scholarship_impact":      "career_goals_raw",
    "essay_2":                                         "career_goals_raw",
    "career_goals":                                    "career_goals_raw",
    "goals":                                           "career_goals_raw",
    "career_objective":                                "career_goals_raw",
    "career_interests":                                "career_goals_raw",

    # ---- Experience (internship + activities combined into experience_raw) ----
    "internship_details":                       "experience_raw",
    "experience":                               "experience_raw",
    "work_experience":                          "experience_raw",
    "internship":                               "_internship_flag",   # Y/N bool → extra
    "activities_extracurriculars":              "_activities",         # appended to experience_raw
    "extracurriculars":                         "_activities",
    "extracurricular":                          "_activities",
    "activities":                               "_activities",
    "volunteer_experience":                     "_activities",

    # ---- Financial (all go to extra — not used in matching) ----
    "remaining_program_costs":                  "_financial_program_cost",
    "remaining_unmet_need":                     "_financial_unmet_need",
    "additional_financial_details":             "_financial_details",
    "receiving_outside_financial_assistance":   "_financial_other_assistance",
    "household_income":                         "_demographic_household_income",
    "current_wages":                            "_demographic_current_wages",

    # ---- Demographics (all go to extra — not used in matching score) ----
    "age":                                      "_demographic_age",
    "gender":                                   "_demographic_gender",
    "military":                                 "_demographic_military",
    "military_spouse_dependent":                "_demographic_military_spouse",

    # ---- Academic / other ----
    "gpa":                                      "_extra_gpa",
    "honor_society":                            "_extra_honor_society",
    "honor_society_other":                      "_extra_honor_society",
    "recent_photograph":                        "_extra_photo",
    "video_upload":                             "_extra_video",
    "submission_date":                          "_submission_date",
    "i_found_out_about_this_scholarship_through": "_referral_source",
}

# Keys that go into extra with their clean label
_EXTRA_KEY_MAP = {
    "_career_path":                 "career_path_raw",
    "_specific_career":             "specific_career_field",
    "_degree_type":                 "degree_type",
    "_enrollment_type":             "enrollment_type",
    "_school_name":                 "school_name",
    "_campus_name":                 "campus_name",
    "_internship_flag":             "internship_completed",
    "_financial_program_cost":      "financial_program_cost",
    "_financial_unmet_need":        "financial_unmet_need",
    "_financial_details":           "financial_details",
    "_financial_other_assistance":  "financial_other_assistance",
    "_demographic_age":             "age",
    "_demographic_gender":          "gender",
    "_demographic_household_income":"household_income",
    "_demographic_current_wages":   "current_wages",
    "_demographic_military":        "military",
    "_demographic_military_spouse": "military_spouse_dependent",
    "_extra_gpa":                   "gpa",
    "_extra_honor_society":         "honor_society",
    "_extra_photo":                 "photo_url",
    "_extra_video":                 "video_url",
    "_submission_date":             "submission_date",
    "_referral_source":             "referral_source",
}


def map_row(
    raw_row: dict[str, Any],
    row_number: int = 0,
) -> tuple[MappedApplicant, list[str]]:
    """
    Map a single normalised CSV/XLSX row to a MappedApplicant.

    Returns (MappedApplicant, warnings).  Never raises.
    """
    warnings: list[str] = []
    applicant = MappedApplicant()

    # Pending special fields — resolved at end of function
    pending: dict[str, str | None] = {}
    activities_parts: list[str] = []

    for raw_key, raw_value in raw_row.items():
        norm_key = str(raw_key).strip()
        target = COLUMN_MAP.get(norm_key)

        if target is None:
            applicant.extra[raw_key] = raw_value
            continue

        v = coerce_text(raw_value)  # strip whitespace; None if blank

        # ---- Special targets ----

        if target == "_full_name":
            first, last = split_full_name(v)
            if first and not applicant.first_name:
                applicant.first_name = first
            if last and not applicant.last_name:
                applicant.last_name = last
            continue

        if target == "_email":
            applicant.email = v.lower() if v else None
            continue

        if target == "_school_state":
            # Values like "US-TX" → "TX"
            if v:
                applicant.state = coerce_state(v.replace("US-", "").replace("us-", ""))
            continue

        if target == "_completion_month":
            pending["_completion_month"] = v
            continue

        if target == "_completion_year":
            pending["_completion_year"] = v
            continue

        if target == "_start_month":
            pending["_start_month"] = v
            continue

        if target == "_start_year":
            pending["_start_year"] = v
            continue

        if target == "_program_supplement":
            # Only use if program_name_raw is empty or "Other"
            pending["_program_supplement"] = v
            continue

        if target == "_activities":
            if v:
                activities_parts.append(v)
            continue

        if target in _EXTRA_KEY_MAP:
            extra_key = _EXTRA_KEY_MAP[target]
            if target == "_internship_flag":
                # Coerce to bool for the extra dict
                from .coerce import coerce_bool
                bool_val, warn = coerce_bool(raw_value, "internship")
                if warn:
                    warnings.append(f"Row {row_number}: {warn}")
                applicant.extra[extra_key] = bool_val
            else:
                if v is not None:
                    applicant.extra[extra_key] = v
            continue

        # ---- Typed direct targets ----

        if target in ("willing_to_relocate", "willing_to_travel"):
            from .coerce import coerce_bool
            val, warn = coerce_bool(raw_value, target)
            if warn:
                warnings.append(f"Row {row_number}: {warn}")
            setattr(applicant, target, val if val is not None else False)
            continue

        if target in ("expected_completion_date", "available_from_date"):
            val, warn = coerce_date(raw_value, target)
            if warn:
                warnings.append(f"Row {row_number}: {warn}")
            setattr(applicant, target, val)
            continue

        if target == "commute_radius_miles":
            from .coerce import coerce_int
            val, warn = coerce_int(raw_value, target)
            if warn:
                warnings.append(f"Row {row_number}: {warn}")
            applicant.commute_radius_miles = val
            continue

        if target == "state":
            applicant.state = coerce_state(raw_value)
            continue

        # ---- Plain text ----
        if v is not None:
            setattr(applicant, target, v)

    # ---- Post-processing: resolve pending fields ----

    # Combine completion month + year
    comp_month = pending.get("_completion_month")
    comp_year = pending.get("_completion_year")
    if comp_year and str(comp_year).strip() not in ("Currently Enrolled", "", "None"):
        date_str = f"{comp_month or 'June'} {comp_year}"
        val, warn = coerce_date(date_str, "expected_completion_date")
        if val:
            applicant.expected_completion_date = val
        elif warn:
            warnings.append(f"Row {row_number}: {warn}")

    # Combine start month + year → available_from_date
    start_month = pending.get("_start_month")
    start_year = pending.get("_start_year")
    if start_year and str(start_year).strip() not in ("Currently Enrolled", "", "None"):
        date_str = f"{start_month or 'September'} {start_year}"
        val, warn = coerce_date(date_str, "available_from_date")
        if val and not applicant.available_from_date:
            applicant.available_from_date = val

    # Use program_supplement if program_name_raw is empty or "Other"
    prog_sup = pending.get("_program_supplement")
    if prog_sup and (
        not applicant.program_name_raw
        or applicant.program_name_raw.strip().lower() in ("other", "other skilled trade career pathway", "")
    ):
        applicant.program_name_raw = prog_sup

    # Normalise program_name_raw: collapse double spaces from SkillPointe export
    # e.g. "Transportation  - Auto Technician" → "Transportation - Auto Technician"
    if applicant.program_name_raw:
        import re
        applicant.program_name_raw = re.sub(r" {2,}", " ", applicant.program_name_raw).strip()

    # Append activities to experience_raw
    if activities_parts:
        activities_text = "\n\n".join(activities_parts)
        if applicant.experience_raw:
            applicant.experience_raw = applicant.experience_raw + "\n\n--- Activities/Extracurriculars ---\n" + activities_text
        else:
            applicant.experience_raw = activities_text

    return applicant, warnings


def validate(applicant: MappedApplicant, row_number: int) -> list[str]:
    """Return a list of data quality warnings (non-fatal)."""
    warnings: list[str] = []
    if not applicant.first_name and not applicant.last_name:
        warnings.append(f"Row {row_number}: no name found")
    if not applicant.program_name_raw:
        warnings.append(
            f"Row {row_number}: no program/trade name — trade and career path matching will be weak"
        )
    if not applicant.city and not applicant.state:
        warnings.append(
            f"Row {row_number}: no location (school or home) — geography scoring will use defaults"
        )
    if not applicant.expected_completion_date:
        warnings.append(
            f"Row {row_number}: no completion date — timing gate cannot evaluate"
        )
    return warnings
