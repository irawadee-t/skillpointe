"""
test_engagement_instrumentation.py — event emitters behind admin analytics.

Every metric surfaced on the admin Command center / Engagement / Impact pages
must have a live writer. These tests pin the server-side emitters added for:

  - application_submitted  (POST /applicant/me/jobs/{job_id}/apply)
  - credential_added       (POST /credentials)
  - profile_completed      (PATCH /applicant/me/profile, once, at >= 80)
  - job_view               (GET /jobs/{job_id}/sections, applicants only)
  - reported_wage_annual   (POST /employer/me/.../hire writes the wage column)

Mock-DB style (same approach as test_employer_visibility.py): patch get_db in
the router module, override the auth dependency, then assert on the SQL the
endpoint executed.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    get_current_user,
    require_applicant,
    require_employer_only,
)
from app.auth.schemas import CurrentUser
from app.main import app

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
JOB_ID = "33333333-0000-0000-0000-333333333333"
APPLICATION_ID = "44444444-0000-0000-0000-444444444444"


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=APPLICANT_USER_ID,
        email="applicant@test.local",
        role="applicant",
        onboarding_complete=True,
    )


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=EMPLOYER_USER_ID,
        email="employer@test.local",
        role="employer",
        onboarding_complete=True,
    )


def _mock_conn(
    fetchval_side: list[Any] | None = None,
    fetchrow_side: list[Any] | None = None,
    fetch_side: list[Any] | None = None,
):
    conn = AsyncMock()
    if fetchval_side is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    if fetchrow_side is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    conn.fetch = AsyncMock(side_effect=fetch_side if fetch_side is not None else [[]] * 10)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    return conn


def _patch_db(module: str, conn: AsyncMock):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"app.routers.{module}.get_db", return_value=mock_ctx)


def _executed_sql(conn: AsyncMock) -> str:
    return " ".join(str(c.args[0]) for c in conn.execute.call_args_list)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# application_submitted
# ---------------------------------------------------------------------------

class TestApplicationSubmittedEvent:
    def test_apply_inserts_application_submitted_event(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        from app.routers.applications import ApplicationOut

        applicant_row = {
            "id": APPLICANT_ID, "first_name": "Jane", "last_name": "Doe",
            "phone": None, "email": "applicant@test.local", "city": "Austin",
            "state": "TX", "program_name_raw": "Welding",
            "program_field": None, "career_path": None,
            "available_from_date": None, "expected_completion_date": None,
            "career_goals_raw": None, "experience_raw": None, "bio_raw": None,
        }
        job_row = {
            "id": JOB_ID, "title_raw": "Welder", "employer_id": EMPLOYER_ID,
            "is_active": True, "source_url": None,
            "required_profile_fields": [], "employer_name": "Acme",
            "internal_apply_enabled": True,
        }
        insert_row = {"id": APPLICATION_ID, "submitted_at": "2026-07-21T00:00:00"}

        conn = _mock_conn(
            fetchrow_side=[
                applicant_row,   # applicant snapshot
                job_row,         # job lookup
                None,            # duplicate check
                None,            # extracted signals (_resume_extras)
                None,            # match lookup
                insert_row,      # INSERT INTO applications RETURNING
                None,            # employer contact (skips notify)
            ],
            fetch_side=[[], []],  # screening questions, credentials
        )

        app.dependency_overrides[require_applicant] = _applicant_user
        dummy_out = ApplicationOut(
            id=APPLICATION_ID, job_id=JOB_ID, job_title="Welder",
            employer_id=EMPLOYER_ID, applicant_id=APPLICANT_ID,
            status="submitted", knockout_failed=False,
            submitted_at="2026-07-21T00:00:00", days_since_submitted=0,
        )
        with (
            _patch_db("applications", conn),
            patch.object(apps_mod, "get_my_application", AsyncMock(return_value=dummy_out)),
        ):
            res = client.post(
                f"/applicant/me/jobs/{JOB_ID}/apply",
                json={"answers": [], "cover_note": None},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        sql = _executed_sql(conn)
        assert "application_submitted" in sql
        # Emitted with the business identifiers, not an empty payload.
        event_call = next(
            c for c in conn.execute.call_args_list
            if "application_submitted" in str(c.args[0])
        )
        assert event_call.args[1] == APPLICANT_ID
        assert event_call.args[4]["application_id"] == APPLICATION_ID


# ---------------------------------------------------------------------------
# credential_added
# ---------------------------------------------------------------------------

class TestCredentialAddedEvent:
    def test_add_credential_inserts_event(self, client: TestClient) -> None:
        from app.routers import credentials as creds_mod

        cred_row = {
            "id": "55555555-0000-0000-0000-555555555555",
            "raw_name": "OSHA 10", "canonical_code": None, "canonical_name": None,
            "credential_type": None, "issuer": None,
            "normalization_confidence": 0.2, "needs_review": True,
            "source": "self", "verification_level": 0,
            "issued_date": None, "expires_date": None, "document_url": None,
        }
        conn = _mock_conn(
            fetchrow_side=[
                {"id": APPLICANT_ID},  # _resolve_applicant_id
                {"id": "66666666-0000-0000-0000-666666666666"},  # _definition_id_for_slug
                cred_row,              # INSERT RETURNING *
            ],
        )

        app.dependency_overrides[require_applicant] = _applicant_user
        with (
            _patch_db("credentials", conn),
            patch.object(creds_mod, "append_credential_record", AsyncMock()),
        ):
            res = client.post(
                "/applicant/me/credentials",
                json={"raw_name": "OSHA 10"},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 201, res.text
        sql = _executed_sql(conn)
        assert "credential_added" in sql


# ---------------------------------------------------------------------------
# profile_completed
# ---------------------------------------------------------------------------

def _complete_profile_row() -> dict[str, Any]:
    """A row whose _compute_completeness score is >= 80."""
    return {
        "id": APPLICANT_ID,
        "first_name": "Jane", "last_name": "Doe",
        "program_name_raw": "Welding", "program_field": "Welding",
        "city": "Austin", "state": "TX",
        "expected_completion_date": "2026-08-01", "available_from_date": None,
        "school_name": "Austin Tech", "enrollment_status": "enrolled",
        "degree_type": None,
        "travel_preference": "regional", "relocation_preference": "open",
        "willing_to_relocate": True, "willing_to_travel": True,
        "has_internship": False, "gpa": None, "age_range": None, "gender": None,
        "canonical_job_family_code": "WLD",
    }


class TestProfileCompletedEvent:
    def test_patch_crossing_80_emits_once_guarded(self, client: TestClient) -> None:
        conn = _mock_conn(
            fetchrow_side=[
                {"id": APPLICANT_ID},          # UPDATE ... RETURNING id
                _complete_profile_row(),       # fresh completeness snapshot
                {"lat": 30.27, "lng": -97.74},  # geocode_cache hit (no network)
            ],
        )

        app.dependency_overrides[require_applicant] = _applicant_user
        with _patch_db("applicants", conn):
            res = client.patch(
                "/applicant/me/profile",
                json={"city": "Austin"},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        event_calls = [
            c for c in conn.execute.call_args_list
            if "profile_completed" in str(c.args[0])
        ]
        assert len(event_calls) == 1
        # Once-per-applicant guard lives in the SQL itself.
        assert "NOT EXISTS" in str(event_calls[0].args[0])

    def test_incomplete_profile_does_not_emit(self, client: TestClient) -> None:
        sparse = {k: None for k in _complete_profile_row()}
        sparse["id"] = APPLICANT_ID
        sparse["first_name"] = "Jane"
        conn = _mock_conn(fetchrow_side=[{"id": APPLICANT_ID}, None, sparse])

        app.dependency_overrides[require_applicant] = _applicant_user
        with _patch_db("applicants", conn):
            res = client.patch(
                "/applicant/me/profile",
                json={"city": "Austin"},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        assert "profile_completed" not in _executed_sql(conn)


# ---------------------------------------------------------------------------
# job_view
# ---------------------------------------------------------------------------

def _job_sections_rows() -> list[Any]:
    job_row = {
        "description_raw": "desc", "requirements_raw": None,
        "preferred_qualifications_raw": None, "responsibilities_raw": None,
        "city": "Austin", "state": "TX", "work_setting": "on_site",
        "pay_min": None, "pay_max": None, "pay_type": None, "pay_raw": None,
    }
    cached_row = {
        "sections": {
            "quality": "good", "facts": {}, "about": [], "duties": [],
            "needs": [], "nice_to_have": [], "benefits": [],
        },
        "source": "parser",
    }
    return [job_row, cached_row]


class TestJobViewEvent:
    def test_applicant_open_emits_deduped_job_view(self, client: TestClient) -> None:
        conn = _mock_conn(fetchrow_side=_job_sections_rows())

        app.dependency_overrides[get_current_user] = _applicant_user
        with _patch_db("jobs", conn):
            res = client.get(
                f"/jobs/{JOB_ID}/sections",
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        event_calls = [
            c for c in conn.execute.call_args_list
            if "job_view" in str(c.args[0])
        ]
        assert len(event_calls) == 1
        sql = str(event_calls[0].args[0])
        assert "NOT EXISTS" in sql                       # daily dedupe guard
        assert "date_trunc('day', now())" in sql

    def test_employer_open_does_not_emit(self, client: TestClient) -> None:
        conn = _mock_conn(fetchrow_side=_job_sections_rows())

        app.dependency_overrides[get_current_user] = _employer_user
        with _patch_db("jobs", conn):
            res = client.get(
                f"/jobs/{JOB_ID}/sections",
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        assert "job_view" not in _executed_sql(conn)


# ---------------------------------------------------------------------------
# hire wage — Foundation median-wage metric writer
# ---------------------------------------------------------------------------

class TestHireWageWriter:
    def test_hire_writes_reported_wage_annual(self, client: TestClient) -> None:
        conn = _mock_conn(
            fetchval_side=[EMPLOYER_ID, JOB_ID],  # contact lookup, job ownership
            fetchrow_side=[{
                "id": "66666666-0000-0000-0000-666666666666",
                "outcome_type": "hired",
                "created_at": "2026-07-21T00:00:00",
            }],
        )

        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("employers", conn):
            res = client.post(
                f"/employer/me/jobs/{JOB_ID}/candidates/{APPLICANT_ID}/hire",
                json={"outcome_type": "hired", "reported_wage_annual": 52000},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 201, res.text
        insert_call = conn.fetchrow.call_args_list[0]
        assert "reported_wage_annual" in str(insert_call.args[0])
        assert 52000 in insert_call.args
        # hire_date defaults to today when the employer omits it.
        from datetime import date
        assert date.today() in insert_call.args
        # And the existing hire_reported event still fires.
        assert "hire_reported" in _executed_sql(conn)

    def test_wage_out_of_bounds_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        res = client.post(
            f"/employer/me/jobs/{JOB_ID}/candidates/{APPLICANT_ID}/hire",
            json={"outcome_type": "hired", "reported_wage_annual": 12},
            headers={"Authorization": "Bearer fake"},
        )
        assert res.status_code == 422
