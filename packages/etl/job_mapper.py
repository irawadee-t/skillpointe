"""
job_mapper.py — maps a raw CSV/XLSX row to a MappedJob.

Built for the real SkillPointe jobs export (hypothetical_skilled_jobs_300.csv).
Header normalisation has already been applied by loader.py.

Key transformations:
  - 'Locations' (semicolon-delimited "City, ST; City, ST") → first location
    as primary city/state; full list stored in extra['all_locations']
  - 'Remote_Status' ("No" / "Hybrid (field-based)") → work_setting enum
  - 'Career_Pathway' → stored in extra['career_pathway_raw'] for Phase 4.3
    normalization; also used as title supplement
  - 'Pay_Range_USD' ("$22/hr–$33/hr") → stored as pay_raw; parsed in Phase 4.3
  - All employer/company data → employer_name (resolved to employer_id at write time)

Run `python scripts/import_jobs.py --file <file> --inspect-headers`
to see unmapped columns.
"""
from __future__ import annotations

import re
from typing import Any

from .coerce import coerce_bool, coerce_date, coerce_state, coerce_text
from .models import MappedJob

# ---------------------------------------------------------------------------
# Column map: normalized_file_header → target_field (or _special)
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {

    # ---- Employer ----
    "company":                          "_employer_name",
    "company_name":                     "_employer_name",
    "employer":                         "_employer_name",
    "employer_name":                    "_employer_name",
    "organization":                     "_employer_name",
    "hiring_company":                   "_employer_name",

    # ---- Job identifier ----
    "job_id":                           "_job_id",     # → extra['source_job_id']

    # ---- Title ----
    "job_title":                        "title_raw",
    "title":                            "title_raw",
    "position":                         "title_raw",
    "position_title":                   "title_raw",
    "role":                             "title_raw",

    # ---- Career pathway (role-level taxonomy from SkillPointe jobs file) ----
    "career_pathway":                   "_career_pathway",   # → extra + title supplement

    # ---- Job level (Entry / Level I / Level II / Early Career) ----
    "job_level":                        "_job_level",         # → extra

    # ---- Description / requirements (raw text) ----
    "job_summary":                      "description_raw",
    "description":                      "description_raw",
    "overview":                         "description_raw",
    "summary":                          "description_raw",

    "key_responsibilities":             "responsibilities_raw",
    "responsibilities":                 "responsibilities_raw",
    "duties":                           "responsibilities_raw",

    "required_qualifications":          "requirements_raw",
    "requirements":                     "requirements_raw",
    "qualifications":                   "requirements_raw",
    "minimum_qualifications":           "requirements_raw",
    "minimum_requirements":             "requirements_raw",

    "preferred_qualifications":         "preferred_qualifications_raw",
    "preferred":                        "preferred_qualifications_raw",
    "nice_to_have":                     "preferred_qualifications_raw",

    # ---- Pre-employment requirements → extra ----
    "pre_employment_requirements":      "_pre_employment_req",

    # ---- Location (SkillPointe jobs use semicolon-delimited multi-location) ----
    "locations":                        "_locations",         # special: parse "City, ST; City, ST"
    "location":                         "_locations",
    "city":                             "city",
    "state":                            "state",
    "zip":                              "zip_code",
    "zip_code":                         "zip_code",

    # ---- Work setting ----
    "remote_status":                    "_remote_status",     # special: map to enum
    "work_setting":                     "work_setting",
    "work_type":                        "work_setting",
    "job_type":                         "work_setting",
    "location_type":                    "work_setting",

    # ---- Travel ----
    "travel":                           "travel_requirement",
    "travel_requirement":               "travel_requirement",
    "travel_requirements":              "travel_requirement",

    # ---- Schedule / shift → extra ----
    "employment_type":                  "_employment_type",
    "shift":                            "_shift",
    "schedule":                         "_schedule",

    # ---- Pay (raw — parsed in Phase 4.3) ----
    "pay_range_usd":                    "pay_raw",
    "pay_range":                        "pay_raw",
    "pay":                              "pay_raw",
    "salary":                           "pay_raw",
    "compensation":                     "pay_raw",
    "wage":                             "pay_raw",
    "hourly_rate":                      "pay_raw",

    # ---- Status ----
    "posting_date":                     "posted_date",
    "date_posted":                      "posted_date",
    "is_active":                        "is_active",
    "active":                           "is_active",

    # ---- Other → extra ----
    "benefits":                         "_benefits",
    "how_to_apply":                     "_how_to_apply",
}


def map_row(
    raw_row: dict[str, Any],
    row_number: int = 0,
    default_employer_name: str | None = None,
) -> tuple[MappedJob, list[str]]:
    """
    Map a single normalised row to a MappedJob.

    Returns (MappedJob, warnings).  Never raises.
    """
    warnings: list[str] = []
    job = MappedJob()

    if default_employer_name:
        job.employer_name = default_employer_name

    for raw_key, raw_value in raw_row.items():
        norm_key = str(raw_key).strip()
        target = COLUMN_MAP.get(norm_key)

        if target is None:
            job.extra[raw_key] = raw_value
            continue

        v = coerce_text(raw_value)

        # ---- Special targets ----

        if target == "_employer_name":
            if v:
                job.employer_name = v
            continue

        if target == "_job_id":
            if v:
                job.extra["source_job_id"] = v
            continue

        if target == "_career_pathway":
            if v:
                job.extra["career_pathway_raw"] = v
                # Use as title_raw if no explicit title column
                if not job.title_raw:
                    job.title_raw = v
            continue

        if target == "_job_level":
            if v:
                job.extra["job_level"] = v
            continue

        if target == "_locations":
            if v:
                city, state = _parse_first_location(v)
                if city and not job.city:
                    job.city = city
                if state and not job.state:
                    job.state = state
                # Store all locations for normalization / multi-location matching
                job.extra["all_locations_raw"] = v
            continue

        if target == "_remote_status":
            job.work_setting = _coerce_remote_status(v)
            continue

        if target == "_employment_type":
            if v:
                job.extra["employment_type"] = v
            continue

        if target == "_shift":
            if v:
                job.extra["shift"] = v
            continue

        if target == "_schedule":
            if v:
                job.extra["schedule"] = v
            continue

        if target == "_pre_employment_req":
            if v:
                job.extra["pre_employment_requirements"] = v
            continue

        if target == "_benefits":
            if v:
                job.extra["benefits"] = v
            continue

        if target == "_how_to_apply":
            if v:
                job.extra["how_to_apply"] = v
            continue

        # ---- Typed direct targets ----

        if target == "is_active":
            val, warn = coerce_bool(raw_value, target)
            if warn:
                warnings.append(f"Row {row_number}: {warn}")
            job.is_active = val if val is not None else True
            continue

        if target == "posted_date":
            val, warn = coerce_date(raw_value, target)
            if warn:
                warnings.append(f"Row {row_number}: {warn}")
            job.posted_date = val
            continue

        if target == "state":
            job.state = coerce_state(raw_value)
            continue

        # ---- Plain text ----
        if v is not None:
            setattr(job, target, v)

    # ---- Post-processing ----

    # If title is still empty but career_pathway was set, use it
    if not job.title_raw and job.extra.get("career_pathway_raw"):
        job.title_raw = job.extra["career_pathway_raw"]

    return job, warnings


def validate(job: MappedJob, row_number: int) -> tuple[bool, list[str]]:
    """
    Returns (is_valid, issues).
    is_valid = False → row should be ERROR'd (cannot insert without employer).
    """
    issues: list[str] = []

    if not job.employer_name:
        issues.append(
            f"Row {row_number}: no employer/company name — use --employer-name flag if all jobs "
            f"belong to one employer"
        )
        return False, issues  # hard error

    if not job.title_raw or len(job.title_raw.strip()) < 2:
        issues.append(f"Row {row_number}: job title is missing or very short")

    if not job.description_raw and not job.requirements_raw:
        issues.append(
            f"Row {row_number}: no description or requirements — matching will be very weak"
        )

    if not job.city and not job.state and job.work_setting != "remote":
        issues.append(
            f"Row {row_number}: no location and not fully remote — geography scoring will use defaults"
        )

    return True, issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_first_location(locations_str: str) -> tuple[str | None, str | None]:
    """
    Parse the first entry from a semicolon-delimited locations string.
    Input:  "Detroit, MI; Dallas, TX; Raleigh, NC"
    Output: ("Detroit", "MI")
    """
    if not locations_str:
        return None, None
    first = locations_str.split(";")[0].strip()
    if "," in first:
        parts = [p.strip() for p in first.split(",", 1)]
        city = parts[0] or None
        state = coerce_state(parts[1]) if len(parts) > 1 else None
        return city, state
    # No comma — treat the whole thing as city-ish
    return first or None, None


def _coerce_remote_status(value: str | None) -> str | None:
    """
    Map SkillPointe Remote_Status values to work_setting enum.
    "No"                  → "on_site"
    "Hybrid (field-based)"→ "hybrid"
    "Yes"                 → "remote"
    """
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("no", "false", "0", "on-site", "on_site", "onsite"):
        return "on_site"
    if v.startswith("hybrid"):
        return "hybrid"
    if v in ("yes", "true", "1", "remote", "fully remote", "fully_remote"):
        return "remote"
    if v.startswith("flexible"):
        return "flexible"
    return None   # unrecognised — stored as NULL; Phase 4.3 can handle it
