"""
db.py — database write helpers for the import pipeline.

Uses psycopg2 (direct Postgres connection, bypasses RLS).
The DATABASE_URL defaults to the local Supabase Postgres port.

All writes happen inside the caller-supplied transaction; callers
should conn.commit() or conn.rollback().
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

_DB_URL = None


def get_db_url() -> str:
    global _DB_URL
    if _DB_URL:
        return _DB_URL
    env_file = Path(__file__).parent.parent.parent / "apps" / "api" / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or "postgresql://postgres:postgres@localhost:54322/postgres"
    )
    _DB_URL = url
    return url


def get_connection():
    """Return a psycopg2 connection.  Caller is responsible for close()."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        raise ImportError(
            "psycopg2-binary is required.  Run: pip install psycopg2-binary"
        ) from e
    conn = psycopg2.connect(get_db_url())
    psycopg2.extras.register_uuid(conn)
    return conn


# ---------------------------------------------------------------------------
# Import run
# ---------------------------------------------------------------------------

def create_import_run(
    conn,
    import_type: str,
    source_file: str,
    row_count: int | None,
    initiated_by: str | None = None,
) -> str:
    """Create an import_runs row and return its id (UUID string)."""
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.import_runs
              (id, import_type, source_file, row_count, status, initiated_by)
            VALUES (%s, %s, %s, %s, 'processing', %s)
            """,
            (run_id, import_type, source_file, row_count, initiated_by),
        )
    return run_id


def complete_import_run(
    conn,
    run_id: str,
    success_count: int,
    error_count: int,
    warning_count: int,
    status: str = "complete",
    error_summary: dict | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public.import_runs SET
              status        = %s,
              success_count = %s,
              error_count   = %s,
              warning_count = %s,
              error_summary = %s,
              completed_at  = NOW()
            WHERE id = %s
            """,
            (
                status,
                success_count,
                error_count,
                warning_count,
                json.dumps(error_summary) if error_summary else None,
                run_id,
            ),
        )


# ---------------------------------------------------------------------------
# Import rows
# ---------------------------------------------------------------------------

def insert_import_row(
    conn,
    run_id: str,
    row_number: int,
    raw_data: dict[str, Any],
    status: str,
    error_message: str | None = None,
    warning_message: str | None = None,
    entity_id: str | None = None,
    entity_type: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.import_rows
              (import_run_id, row_number, raw_data, status,
               error_message, warning_message, entity_id, entity_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                row_number,
                json.dumps(_serialize_raw(raw_data)),
                status,
                error_message,
                warning_message,
                entity_id,
                entity_type,
            ),
        )


def _serialize_raw(data: dict) -> dict:
    """Make a raw row JSON-serializable (handles dates, None, etc.)."""
    out = {}
    for k, v in data.items():
        if v is None:
            out[str(k)] = None
        elif isinstance(v, (date, datetime)):
            out[str(k)] = v.isoformat()
        else:
            out[str(k)] = str(v) if v is not None else None
    return out


# ---------------------------------------------------------------------------
# Employers
# ---------------------------------------------------------------------------

def find_or_create_employer(conn, name: str, import_run_id: str) -> str:
    """
    Look up an employer by name (case-insensitive).
    Creates a new row if not found.
    Returns the employer id (UUID string).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.employers WHERE lower(name) = lower(%s) LIMIT 1",
            (name,),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])

        emp_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO public.employers (id, name, source, import_run_id)
            VALUES (%s, %s, 'import', %s)
            """,
            (emp_id, name, import_run_id),
        )
        return emp_id


# ---------------------------------------------------------------------------
# Applicants
# ---------------------------------------------------------------------------

def insert_applicant(
    conn,
    applicant: "MappedApplicant",  # noqa: F821  (avoid circular import in type hint)
    import_run_id: str,
) -> str:
    """
    Insert a new applicant row and return its id (UUID string).

    Each imported row is treated as a distinct applicant — no deduplication
    by email or name.  The 'folder_name' / 'linked_personalized_account' fields
    from the SkillPointe export are mapped and stored but are not used as
    identity keys.  Sign-up linking (email → user_id) is handled in Phase 5/6.
    """
    applicant_id = str(uuid.uuid4())
    params = {
        "id":                           applicant_id,
        "first_name":                   applicant.first_name,
        "last_name":                    applicant.last_name,
        "preferred_name":               applicant.preferred_name,
        "email":                        applicant.email,
        "phone":                        applicant.phone,
        "city":                         applicant.city,
        "state":                        applicant.state,
        "zip_code":                     applicant.zip_code,
        "country":                      applicant.country,
        "willing_to_relocate":          applicant.willing_to_relocate,
        "willing_to_travel":            applicant.willing_to_travel,
        "commute_radius_miles":         applicant.commute_radius_miles,
        "relocation_willingness_notes": applicant.relocation_willingness_notes,
        "travel_willingness_notes":     applicant.travel_willingness_notes,
        "program_name_raw":             applicant.program_name_raw,
        "career_goals_raw":             applicant.career_goals_raw,
        "experience_raw":               applicant.experience_raw,
        "bio_raw":                      applicant.bio_raw,
        "expected_completion_date":     applicant.expected_completion_date,
        "available_from_date":          applicant.available_from_date,
        "timing_notes":                 applicant.timing_notes,
        "source":                       "import",
        "import_run_id":                import_run_id,
    }
    with conn.cursor() as cur:
        cols = ", ".join(params.keys())
        vals = ", ".join(f"%({k})s" for k in params.keys())
        cur.execute(
            f"INSERT INTO public.applicants ({cols}) VALUES ({vals})",
            params,
        )
    return applicant_id


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_job(
    conn,
    job: "MappedJob",  # noqa: F821
    employer_id: str,
    import_run_id: str,
) -> str:
    """Insert a job row and return its id."""
    job_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.jobs (
              id, employer_id,
              title_raw, description_raw, requirements_raw,
              preferred_qualifications_raw, responsibilities_raw,
              city, state, zip_code, country,
              work_setting, travel_requirement,
              pay_raw,
              is_active, posted_date,
              source, import_run_id
            ) VALUES (
              %(id)s, %(employer_id)s,
              %(title_raw)s, %(description_raw)s, %(requirements_raw)s,
              %(preferred_qualifications_raw)s, %(responsibilities_raw)s,
              %(city)s, %(state)s, %(zip_code)s, %(country)s,
              %(work_setting)s, %(travel_requirement)s,
              %(pay_raw)s,
              %(is_active)s, %(posted_date)s,
              'import', %(import_run_id)s
            )
            """,
            {
                "id":                           job_id,
                "employer_id":                  employer_id,
                "title_raw":                    job.title_raw,
                "description_raw":              job.description_raw,
                "requirements_raw":             job.requirements_raw,
                "preferred_qualifications_raw": job.preferred_qualifications_raw,
                "responsibilities_raw":         job.responsibilities_raw,
                "city":                         job.city,
                "state":                        job.state,
                "zip_code":                     job.zip_code,
                "country":                      job.country,
                "work_setting":                 _coerce_work_setting(job.work_setting),
                "travel_requirement":           job.travel_requirement,
                "pay_raw":                      job.pay_raw,
                "is_active":                    job.is_active,
                "posted_date":                  job.posted_date,
                "import_run_id":                import_run_id,
            },
        )
    return job_id


def _coerce_work_setting(value: str | None) -> str | None:
    """Map raw work_setting strings to our enum values."""
    if value is None:
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "remote":       "remote",
        "fully_remote": "remote",
        "work_from_home": "remote",
        "wfh":          "remote",
        "hybrid":       "hybrid",
        "on_site":      "on_site",
        "onsite":       "on_site",
        "on_premise":   "on_site",
        "in_person":    "on_site",
        "in_office":    "on_site",
        "flexible":     "flexible",
    }
    return mapping.get(v)  # None if not recognized → will be stored as NULL
