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
  _email            → email field, lowercased (rejected if not a real address)
  _review_status    → review_status ('Folder - Name' in SPF exports is a
                      scholarship REVIEW STATUS like 'Internal Review',
                      never a person's name)
  _linked_account   → extra only ('Linked Personalized Account' is the literal
                      placeholder string 'First Last' in SPF exports — it is
                      NOT an email and NOT unique; never used as identity)
  _school_state     → strip "US-" prefix, then → state
  _completion_month → stored for month+year combination at end of map_row
  _completion_year  → stored for month+year combination at end of map_row
  _start_month      → stored for available_from_date combination
  _start_year       → stored for available_from_date combination
  _activities       → appended to experience_raw with separator
  _program_supplement → fills program_name_raw only if currently empty

Synthetic identity:
  Rows with no usable name/email (the SPF scholarship export is anonymized)
  get a deterministic synthetic identity derived from the row ordinal:
  first_name='Scholar', last_name='0007', email='scholar-0007@scholarship-import.local'.
  This is stable across re-imports of the same file, so the DB upsert on
  email makes re-imports idempotent (no duplicate applicants).

Run `python scripts/import_applicants.py --file <file> --inspect-headers`
to see which columns in your file are not yet mapped.
"""
from __future__ import annotations

import re
from typing import Any

from .coerce import coerce_date, coerce_state, coerce_text, split_full_name
from .models import MappedApplicant

# Domain for deterministic synthetic identities (anonymized scholarship rows).
# Clearly non-routable and clearly synthetic.
SYNTHETIC_EMAIL_DOMAIN = "scholarship-import.local"
SYNTHETIC_FIRST_NAME = "Scholar"

# ---------------------------------------------------------------------------
# Column map: normalized_file_header → target_field (or _special)
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {

    # ---- Scholarship review status ----
    # SPF exports put the application's REVIEW STATUS in 'Folder - Name'
    # (values: 'Internal Review', 'Accepted Award - Pending Payment',
    # 'Selected - Pending Acceptance').  It is NOT a person's name.
    "folder_name":                              "_review_status",
    "folder___name":                            "_review_status",   # alt normalisation

    # ---- Full name (only genuine name columns) ----
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

    # ---- Email ----
    # 'Linked Personalized Account' in SPF exports is the literal string
    # 'First Last' on every row — a placeholder, not an email, not unique.
    # It is preserved in extra but NEVER used as identity.
    "linked_personalized_account":              "_linked_account",
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
    # Both city/state AND the dedicated school_city/school_state columns
    # are populated so the profile shows where the value came from.
    "school_city":                              "_school_city",
    "school_city_":                             "_school_city",  # trailing colon gets normalised to _
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
    "program_field_of_study":                   "_program_field",       # → program_name_raw + program_field
    "program_field_of_study_other":             "_program_supplement",  # fills if raw is blank/"Other"
    "specific_career_field_of_study":           "_specific_career",     # → specific_career column
    "career_path":                              "_career_path",          # → career_path column
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
    # Essay 1 → bio_raw + essay_background (background, passion)
    # Essay 2 → career_goals_raw + essay_impact (post-graduation vision)
    "essay_1___background___driving_passion":   "_essay_background",
    "essay_1_background_driving_passion":       "_essay_background",
    "essay_1":                                  "_essay_background",
    "bio":                                      "bio_raw",
    "essay":                                    "bio_raw",
    "personal_statement":                       "bio_raw",
    "about_me":                                 "bio_raw",
    "statement":                                "bio_raw",
    "background":                               "bio_raw",

    "essay_2___post_graduation___scholarship_impact":  "_essay_impact",
    "essay_2_post_graduation_scholarship_impact":      "_essay_impact",
    "essay_2":                                         "_essay_impact",
    "career_goals":                                    "career_goals_raw",
    "goals":                                           "career_goals_raw",
    "career_objective":                                "career_goals_raw",
    "career_interests":                                "career_goals_raw",

    # ---- Experience (internship + activities combined into experience_raw) ----
    "internship_details":                       "_internship_details",
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

# Keys that go into extra with their clean label.
# Several of these ALSO populate a dedicated typed column on MappedApplicant
# (handled explicitly in map_row); the extra copy preserves the raw value.
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
    "_linked_account":              "linked_personalized_account",
    "_review_status":               "scholarship_review_status",
    "_school_city":                 "school_city",
    "_program_field":               "program_field",
}


# ---------------------------------------------------------------------------
# Enum mappings for expanded profile columns (Postgres enum values)
# ---------------------------------------------------------------------------

ENROLLMENT_STATUS_MAP = {
    "high school (seniors or upcoming seniors eligible only)":  "high_school",
    "community college/technical school":                       "community_college",
    "community college or trade school":                        "community_college",
    "skilled trades certificate/vocational program":            "vocational_certificate",
    "currently enrolled in a training program/vocational program": "vocational_certificate",
    "apprenticeship program":                                   "apprenticeship",
    "currently enrolled in an apprenticeship":                  "apprenticeship",
    "early college/high school dual enrollment program":        "dual_enrollment",
    "i am not currently attending school.":                     "not_enrolled",
    "4-year college student (major in skilled trades)":         "bachelors_plus",
    # The export truncates the closing paren on this one sometimes:
    "4 or more year college program (bachelors, master's or graduate degree)": "bachelors_plus",
    "4 or more year college program (bachelors, master's or graduate degree":  "bachelors_plus",
}

DEGREE_TYPE_MAP = {
    "associate's degree":                            "associates",
    "bachelor's degree":                             "bachelors",
    "skilled trades certificate/vocational program": "skilled_trades_certificate",
    "apprenticeship":                                "apprenticeship",
    "dual enrollment":                               "dual_enrollment",
    "other":                                         "other",
}


def _map_enrollment_status(value: str | None) -> str | None:
    if not value:
        return None
    return ENROLLMENT_STATUS_MAP.get(value.strip().lower(), "other")


def _map_degree_type(value: str | None) -> str | None:
    if not value:
        return None
    return DEGREE_TYPE_MAP.get(value.strip().lower(), "other")


def _parse_gpa(value: str | None) -> tuple[float | None, str | None]:
    """
    Parse GPA robustly.  Returns (gpa, warning).
    Handles '3.51', '4', '2,67' (EU decimal comma), '3.8 GPA'.
    Values that are not on a 0–5 scale ('92/100', '91.5 GPA', 'GED', 'N/A')
    are stored as None — we never invent a rescaled number.
    """
    if not value:
        return None, None
    v = str(value).strip()
    if not v or v.lower() in ("n/a", "na", "none", "-", "ged", "tbd", "unknown"):
        return None, None
    v = re.sub(r"\s*gpa\s*$", "", v, flags=re.IGNORECASE).strip()
    if "/" in v:  # e.g. '92/100' — different scale, do not guess
        return None, f"GPA on a non-4.0 scale left unset: {value!r}"
    v = v.replace(",", ".")
    try:
        g = float(v)
    except ValueError:
        return None, f"Could not parse GPA: {value!r}"
    if 0.0 <= g <= 5.0:
        return round(g, 2), None
    return None, f"GPA out of 0–5 range left unset: {value!r}"


def _parse_honor_societies(*values: str | None) -> list[str]:
    """Split newline/comma-separated honor society strings into a clean list."""
    out: list[str] = []
    for v in values:
        if not v:
            continue
        for part in re.split(r"[\n,]+", v):
            p = part.strip()
            if p and p.lower() not in ("none", "n/a", "na", "-"):
                if p not in out:
                    out.append(p)
    return out


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
    honor_society_values: list[str] = []

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
            # Only accept values that look like an actual email address.
            # SPF exports contain placeholder strings here; treating them as
            # emails would collide 335 rows onto one identity.
            if v and "@" in v and "." in v.split("@")[-1]:
                applicant.email = v.lower()
            elif v:
                applicant.extra["invalid_email_raw"] = v
                warnings.append(
                    f"Row {row_number}: email column value {v!r} is not an "
                    "email address — ignored (synthetic identity will be used)"
                )
            continue

        if target == "_review_status":
            # Scholarship review status — NEVER a name.
            applicant.review_status = v
            if v is not None:
                applicant.extra["scholarship_review_status"] = v
            continue

        if target == "_linked_account":
            # Placeholder column ('First Last' on every row) — preserve only.
            if v is not None:
                applicant.extra["linked_personalized_account"] = v
            continue

        if target == "_school_state":
            # Values like "US-TX" → "TX"
            if v:
                state = coerce_state(v.replace("US-", "").replace("us-", ""))
                applicant.state = state
                applicant.school_state = state
            continue

        if target == "_school_city":
            if v:
                applicant.city = v
                applicant.school_city = v
            continue

        if target == "_program_field":
            if v:
                applicant.program_name_raw = v
                applicant.program_field = v
            continue

        if target == "_essay_background":
            if v:
                applicant.bio_raw = v
                applicant.essay_background = v
            continue

        if target == "_essay_impact":
            if v:
                applicant.career_goals_raw = v
                applicant.essay_impact = v
            continue

        if target == "_internship_details":
            if v:
                applicant.internship_details = v
                applicant.experience_raw = v
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

            # Typed column population (in addition to the extra copy)
            if target == "_internship_flag":
                from .coerce import coerce_bool
                bool_val, warn = coerce_bool(raw_value, "internship")
                if warn:
                    warnings.append(f"Row {row_number}: {warn}")
                applicant.has_internship = bool_val
                applicant.extra[extra_key] = bool_val
                continue

            if target == "_career_path" and v:
                applicant.career_path = v
            elif target == "_specific_career" and v:
                applicant.specific_career = v
            elif target == "_enrollment_type" and v:
                applicant.enrollment_status = _map_enrollment_status(v)
            elif target == "_degree_type" and v:
                # 'Degree/Program', 'Degree Type', and 'Degree Type - Other'
                # all land here; first recognised (non-'other') value wins.
                mapped = _map_degree_type(v)
                if applicant.degree_type in (None, "other"):
                    applicant.degree_type = mapped
            elif target == "_school_name" and v:
                applicant.school_name = v
            elif target == "_campus_name" and v:
                applicant.school_campus = v
            elif target == "_demographic_age" and v:
                applicant.age_range = v
            elif target == "_demographic_gender" and v:
                applicant.gender = v
            elif target == "_demographic_military" and v:
                from .coerce import coerce_bool
                applicant.military_status, _ = coerce_bool(raw_value, "military")
            elif target == "_demographic_military_spouse" and v:
                from .coerce import coerce_bool
                applicant.military_dependent, _ = coerce_bool(raw_value, "military_spouse_dependent")
            elif target == "_demographic_household_income" and v:
                applicant.household_income = v
            elif target == "_demographic_current_wages" and v:
                applicant.current_wages = v
            elif target == "_financial_program_cost" and v:
                applicant.remaining_program_costs = v
            elif target == "_extra_gpa" and v:
                gpa_val, warn = _parse_gpa(v)
                if warn:
                    warnings.append(f"Row {row_number}: {warn}")
                applicant.gpa = gpa_val
            elif target == "_extra_honor_society" and v:
                honor_society_values.append(v)

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

    # Combine start month + year → program_start_date.
    # NOTE: the programme START date is when training begins, not when the
    # applicant is available for work — availability comes from the
    # completion date, so available_from_date is NOT set from these fields.
    start_month = pending.get("_start_month")
    start_year = pending.get("_start_year")
    if start_year and str(start_year).strip() not in ("Currently Enrolled", "", "None"):
        date_str = f"{start_month or 'September'} {start_year}"
        val, warn = coerce_date(date_str, "program_start_date")
        if val and not applicant.program_start_date:
            applicant.program_start_date = val

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

    # Append activities to experience_raw + dedicated column
    if activities_parts:
        activities_text = "\n\n".join(activities_parts)
        applicant.activities = activities_text
        if applicant.experience_raw:
            applicant.experience_raw = applicant.experience_raw + "\n\n--- Activities/Extracurriculars ---\n" + activities_text
        else:
            applicant.experience_raw = activities_text

    # Honor societies → clean list
    if honor_society_values:
        societies = _parse_honor_societies(*honor_society_values)
        applicant.honor_societies = societies or None

    # ---- Synthetic identity for anonymized rows ----
    # Deterministic in row order: re-importing the same file produces the
    # same identities, so the email upsert keeps re-imports idempotent.
    if not applicant.first_name and not applicant.last_name:
        applicant.first_name = SYNTHETIC_FIRST_NAME
        applicant.last_name = f"{row_number:04d}"
        applicant.synthetic_identity = True
    if not applicant.email:
        applicant.email = f"scholar-{row_number:04d}@{SYNTHETIC_EMAIL_DOMAIN}"
        applicant.synthetic_identity = True

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
