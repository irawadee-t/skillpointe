"""
models.py — data models for the import pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class MappedApplicant:
    """Applicant row after column mapping and basic coercion."""
    # Identity
    first_name: str | None = None
    last_name: str | None = None
    preferred_name: str | None = None
    email: str | None = None
    phone: str | None = None

    # Location
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str = "US"

    # Geography preferences
    willing_to_relocate: bool = False
    willing_to_travel: bool = False
    commute_radius_miles: int | None = None
    relocation_willingness_notes: str | None = None
    travel_willingness_notes: str | None = None

    # Raw text fields — preserved verbatim
    program_name_raw: str | None = None
    career_goals_raw: str | None = None
    experience_raw: str | None = None
    bio_raw: str | None = None

    # Timing
    expected_completion_date: date | None = None
    available_from_date: date | None = None
    timing_notes: str | None = None

    # Unmapped columns — stored in raw_data
    extra: dict[str, Any] = field(default_factory=dict)

    def display_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.email or "(no name)"


@dataclass
class MappedJob:
    """Job row after column mapping and basic coercion."""
    # Employer (special: resolved to employer_id at DB write time)
    employer_name: str | None = None

    # Raw text fields — preserved verbatim
    title_raw: str | None = None
    description_raw: str | None = None
    requirements_raw: str | None = None
    preferred_qualifications_raw: str | None = None
    responsibilities_raw: str | None = None

    # Location
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str = "US"
    work_setting: str | None = None      # raw string; normalised in Phase 4.3
    travel_requirement: str | None = None

    # Compensation — raw only; parsing is Phase 4.3 normalization
    pay_raw: str | None = None

    # Status
    is_active: bool = True
    posted_date: date | None = None

    # Unmapped columns
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportRowResult:
    """Result for a single import row."""
    row_number: int
    status: str           # 'success', 'warning', 'error', 'skipped'
    raw_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    warning_message: str | None = None
    entity_id: str | None = None
    entity_type: str | None = None


@dataclass
class ImportResult:
    """Aggregate result for an entire import run."""
    import_type: str
    source_file: str
    run_id: str | None = None
    total_rows: int = 0
    success_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    row_results: list[ImportRowResult] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def failed_count(self) -> int:
        return self.error_count

    def add_row(self, result: ImportRowResult) -> None:
        self.row_results.append(result)
        self.total_rows += 1
        if result.status == "success":
            self.success_count += 1
        elif result.status == "warning":
            self.warning_count += 1
        elif result.status == "error":
            self.error_count += 1
        elif result.status == "skipped":
            self.skipped_count += 1
