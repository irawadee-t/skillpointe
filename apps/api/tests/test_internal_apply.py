"""
test_internal_apply.py — in-platform one-click applications.

Covers the internal-apply configuration + the hardened apply flow:

  Employer config
    - company default toggle round-trip (PATCH /employer/me/company)
    - job create/patch carry accepts_internal_applications + required_profile_fields
    - invalid profile-field keys 422 at the schema edge
    - screening question limit (max 5)

  Apply guards
    - inactive job → 409, no insert, no event
    - internal apply disabled → 409
    - unanswered required question → 422 (client/server parity)
    - missing required profile group → 422 naming the group
    - inline profile updates saved back to the profile and satisfying the check

  Idempotency + re-apply
    - already applied → friendly 409
    - concurrent race (insert returns no row) → 409, event NOT fired
    - withdrawn → exactly one re-apply (row reactivated, event fired with reapply)
    - second re-apply → 409

  Events
    - application_submitted fired exactly once per successful submit
    - external self-report path logs apply_click, never application_submitted

  Snapshot / employer view
    - snapshot INSERT carries shared_fields + inline-updated values (consent record)
    - employer detail returns decrypted screening answers from the stored row

Mock-DB style (same approach as test_engagement_instrumentation.py): patch
get_db in the router module, override the auth dependency, then assert on the
SQL the endpoint executed. fetch/fetchrow/fetchval are routed on SQL substrings
so the tests don't break on incidental query reordering.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_applicant, require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
JOB_ID = "33333333-0000-0000-0000-333333333333"
APPLICATION_ID = "44444444-0000-0000-0000-444444444444"
QUESTION_ID = "55555555-0000-0000-0000-555555555555"

from uuid import UUID as _UUID  # noqa: E402

QUESTION_UUID = _UUID(QUESTION_ID)


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=APPLICANT_USER_ID, email="applicant@test.local",
        role="applicant", onboarding_complete=True,
    )


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=EMPLOYER_USER_ID, email="employer@test.local",
        role="employer", onboarding_complete=True,
    )


def _applicant_row(**overrides: Any) -> dict:
    row = {
        "id": APPLICANT_ID, "first_name": "Jane", "last_name": "Doe",
        "phone": "512-555-0100", "email": "applicant@test.local",
        "city": "Austin", "state": "TX", "program_name_raw": "Welding",
        "program_field": None, "career_path": None,
        "available_from_date": None, "expected_completion_date": None,
        "career_goals_raw": None, "experience_raw": None, "bio_raw": None,
    }
    row.update(overrides)
    return row


def _job_row(**overrides: Any) -> dict:
    row = {
        "id": JOB_ID, "title_raw": "Welder", "employer_id": EMPLOYER_ID,
        "is_active": True, "source_url": "https://jobs.example.com/1",
        "required_profile_fields": [], "employer_name": "Acme",
        "internal_apply_enabled": True,
    }
    row.update(overrides)
    return row


class RoutedConn:
    """AsyncMock-ish conn whose fetch* calls dispatch on SQL substrings."""

    def __init__(self) -> None:
        self.fetchrow_routes: list[tuple[str, Any]] = []
        self.fetch_routes: list[tuple[str, Any]] = []
        self.fetchval_routes: list[tuple[str, Any]] = []
        self.executed: list[tuple[str, tuple]] = []
        self.fetchrow_calls: list[tuple[str, tuple]] = []

    def route_fetchrow(self, needle: str, result: Any) -> None:
        self.fetchrow_routes.append((needle, result))

    def route_fetch(self, needle: str, result: Any) -> None:
        self.fetch_routes.append((needle, result))

    def route_fetchval(self, needle: str, result: Any) -> None:
        self.fetchval_routes.append((needle, result))

    async def fetchrow(self, sql: str, *args: Any):
        self.fetchrow_calls.append((sql, args))
        for needle, result in self.fetchrow_routes:
            if needle in sql:
                return result() if callable(result) else result
        return None

    async def fetch(self, sql: str, *args: Any):
        for needle, result in self.fetch_routes:
            if needle in sql:
                return result
        return []

    async def fetchval(self, sql: str, *args: Any):
        for needle, result in self.fetchval_routes:
            if needle in sql:
                return result
        return None

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        return "UPDATE 1"

    def transaction(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    def executed_sql(self) -> str:
        return " ".join(sql for sql, _ in self.executed)

    def event_calls(self) -> list[tuple[str, tuple]]:
        return [(s, a) for s, a in self.executed if "application_submitted" in s]


def _patch_db(module: str, conn: RoutedConn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"app.routers.{module}.get_db", return_value=ctx)


def _std_apply_conn(
    applicant: dict | None = None,
    job: dict | None = None,
    existing: dict | None = None,
    insert_row: dict | None = "default",
    questions: list[dict] | None = None,
) -> RoutedConn:
    conn = RoutedConn()
    conn.route_fetchrow("FROM public.applicants", applicant or _applicant_row())
    conn.route_fetchrow("FROM public.jobs j", job or _job_row())
    conn.route_fetchrow("FROM public.applications WHERE applicant_id", existing)
    conn.route_fetchrow("extracted_applicant_signals", None)
    conn.route_fetchrow("FROM public.matches", None)
    if insert_row == "default":
        insert_row = {"id": APPLICATION_ID, "submitted_at": "2026-08-01T00:00:00"}
    conn.route_fetchrow("INSERT INTO public.applications", insert_row)
    conn.route_fetchrow("UPDATE public.applications", insert_row)
    conn.route_fetchrow("employer_contacts", None)
    conn.route_fetch("job_screening_questions", questions or [])
    conn.route_fetch("FROM public.credentials", [])
    return conn


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _dummy_application_out():
    from app.routers.applications import ApplicationOut
    return ApplicationOut(
        id=APPLICATION_ID, job_id=JOB_ID, job_title="Welder",
        employer_id=EMPLOYER_ID, applicant_id=APPLICANT_ID,
        status="submitted", knockout_failed=False,
        submitted_at="2026-08-01T00:00:00", days_since_submitted=0,
    )


def _post_apply(client: TestClient, payload: dict | None = None):
    return client.post(
        f"/applicant/me/jobs/{JOB_ID}/apply",
        json=payload or {"answers": [], "cover_note": None},
        headers={"Authorization": "Bearer fake"},
    )


def _apply_ctx(conn: RoutedConn):
    """Patch db + auth + the trailing get_my_application re-read."""
    from app.routers import applications as apps_mod
    app.dependency_overrides[require_applicant] = _applicant_user
    return (
        _patch_db("applications", conn),
        patch.object(apps_mod, "get_my_application", AsyncMock(return_value=_dummy_application_out())),
    )


# ---------------------------------------------------------------------------
# Employer configuration
# ---------------------------------------------------------------------------

class TestEmployerConfig:
    def test_company_default_toggle_roundtrip(self, client: TestClient) -> None:
        conn = RoutedConn()
        conn.route_fetchval("employer_contacts", EMPLOYER_ID)
        company_row = {
            "id": EMPLOYER_ID, "name": "Acme", "industry": None, "city": None,
            "state": None, "is_partner": False, "total_jobs": 1, "active_jobs": 1,
            "accepts_internal_applications_default": True,
        }
        conn.route_fetchrow("FROM public.employers e", company_row)

        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("employers", conn):
            res = client.patch(
                "/employer/me/company",
                json={"accepts_internal_applications_default": True},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        assert res.json()["accepts_internal_applications_default"] is True
        upd = next(s for s, _ in conn.executed if "UPDATE public.employers" in s)
        assert "accepts_internal_applications_default" in upd
        # The new value travels as a bound param, not string-interpolated SQL.
        args = next(a for s, a in conn.executed if "UPDATE public.employers" in s)
        assert True in args

    def test_company_patch_requires_a_field(self, client: TestClient) -> None:
        conn = RoutedConn()
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("employers", conn):
            res = client.patch(
                "/employer/me/company", json={},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 422

    def test_job_create_carries_internal_apply_config(self, client: TestClient) -> None:
        conn = RoutedConn()
        conn.route_fetchval("employer_contacts", EMPLOYER_ID)
        conn.route_fetchrow(
            "INSERT INTO public.jobs",
            {"id": JOB_ID, "title_raw": "Welder", "is_active": True, "created_at": "2026-08-01"},
        )
        app.dependency_overrides[require_employer_only] = _employer_user
        with (
            _patch_db("employers", conn),
            patch("app.worker.scheduler.trigger_recompute_for_job", AsyncMock()),
        ):
            res = client.post(
                "/employer/me/jobs",
                json={
                    "title_raw": "Welder — night shift",
                    "accepts_internal_applications": True,
                    "required_profile_fields": ["contact", "resume", "CONTACT"],
                },
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 201, res.text
        sql, args = next(
            (s, a) for s, a in conn.fetchrow_calls if "INSERT INTO public.jobs" in s
        )
        assert "accepts_internal_applications" in sql
        assert True in args
        # De-duplicated + lower-cased by the schema validator.
        assert ["contact", "resume"] in [list(a) if isinstance(a, list) else a for a in args]

    def test_job_patch_rejects_unknown_profile_field(self, client: TestClient) -> None:
        conn = RoutedConn()
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("employers", conn):
            res = client.patch(
                f"/employer/me/jobs/{JOB_ID}",
                json={"required_profile_fields": ["shoe_size"]},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 422
        assert "required_profile_fields" in res.text

    def test_screening_question_limit(self, client: TestClient) -> None:
        conn = RoutedConn()
        app.dependency_overrides[require_employer_only] = _employer_user
        questions = [
            {"kind": "yes_no", "prompt": f"Question number {i}?", "options": [],
             "required_answer": "Yes", "is_knockout": True, "position": i}
            for i in range(6)
        ]
        with _patch_db("applications", conn):
            res = client.put(
                f"/employer/me/jobs/{JOB_ID}/screening",
                json={"questions": questions},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 400
        assert "At most 5" in res.text


# ---------------------------------------------------------------------------
# Apply guards
# ---------------------------------------------------------------------------

class TestApplyGuards:
    def test_inactive_job_rejected_no_orphan_row(self, client: TestClient) -> None:
        conn = _std_apply_conn(job=_job_row(is_active=False))
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 409
        assert "no longer accepting" in res.json()["detail"]
        assert "INSERT INTO public.applications" not in " ".join(s for s, _ in conn.fetchrow_calls if "INSERT" in s)
        assert conn.event_calls() == []

    def test_internal_apply_disabled_rejected(self, client: TestClient) -> None:
        conn = _std_apply_conn(job=_job_row(internal_apply_enabled=False))
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 409
        assert "SKILLED Nation" in res.json()["detail"]
        assert conn.event_calls() == []

    def test_unanswered_required_question_422(self, client: TestClient) -> None:
        questions = [{
            "id": QUESTION_UUID, "kind": "yes_no", "prompt": "Do you have a CDL?",
            "required_answer": "Yes", "is_knockout": True,
        }]
        conn = _std_apply_conn(questions=questions)
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 422
        assert "Do you have a CDL?" in res.json()["detail"]
        assert conn.event_calls() == []

    def test_wrong_knockout_answer_still_submits_flagged(self, client: TestClient) -> None:
        questions = [{
            "id": QUESTION_UUID, "kind": "yes_no", "prompt": "Do you have a CDL?",
            "required_answer": "Yes", "is_knockout": True,
        }]
        conn = _std_apply_conn(questions=questions)
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client, {
                "answers": [{"question_id": QUESTION_ID, "answer": "No"}],
            })
        assert res.status_code == 200, res.text
        _, args = next(
            (s, a) for s, a in conn.fetchrow_calls if "INSERT INTO public.applications" in s
        )
        assert True in [a for a in args if isinstance(a, bool)]  # knockout_failed=True bound

    def test_missing_required_profile_group_422(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            applicant=_applicant_row(phone=None, email=None),
            job=_job_row(required_profile_fields=["contact"]),
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 422
        assert "contact info" in res.json()["detail"]
        assert conn.event_calls() == []

    def test_inline_profile_updates_saved_and_satisfy_requirement(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            applicant=_applicant_row(phone=None, email=None),
            job=_job_row(required_profile_fields=["contact"]),
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client, {
                "answers": [],
                "profile_updates": {"phone": "512-555-0199"},
            })
        assert res.status_code == 200, res.text
        upd_sql, upd_args = next(
            (s, a) for s, a in conn.executed if "UPDATE public.applicants" in s
        )
        assert "phone" in upd_sql
        assert "512-555-0199" in upd_args
        assert len(conn.event_calls()) == 1

    def test_missing_resume_required_422(self, client: TestClient) -> None:
        conn = _std_apply_conn(job=_job_row(required_profile_fields=["resume"]))
        # fetchval for applicant_resume_uploads returns None (no route) → missing
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 422
        assert "resume" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Idempotency + re-apply
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_already_applied_friendly_409(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            existing={"id": APPLICATION_ID, "status": "submitted", "reapply_count": 0},
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 409
        assert "already applied" in res.json()["detail"]
        assert conn.event_calls() == []

    def test_concurrent_race_no_event(self, client: TestClient) -> None:
        # Read-check saw nothing, but ON CONFLICT DO NOTHING returned no row.
        conn = _std_apply_conn(insert_row=None)
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 409
        assert conn.event_calls() == []

    def test_withdrawn_allows_one_reapply(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            existing={"id": APPLICATION_ID, "status": "withdrawn", "reapply_count": 0},
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 200, res.text
        # Reactivated in place — UPDATE, not a second INSERT.
        upd = next(
            (s for s, _ in conn.fetchrow_calls if "UPDATE public.applications" in s), None
        )
        assert upd is not None
        assert "reapply_count = reapply_count + 1" in upd
        assert "status = 'withdrawn'" in upd  # guarded against double re-apply races
        events = conn.event_calls()
        assert len(events) == 1
        assert events[0][1][3]["reapply"] is True

    def test_second_reapply_blocked(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            existing={"id": APPLICATION_ID, "status": "withdrawn", "reapply_count": 1},
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 409
        assert "limit" in res.json()["detail"]
        assert conn.event_calls() == []


# ---------------------------------------------------------------------------
# Events — exactly once, and separated from the external path
# ---------------------------------------------------------------------------

class TestEvents:
    def test_event_fired_exactly_once_on_happy_path(self, client: TestClient) -> None:
        conn = _std_apply_conn()
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client)
        assert res.status_code == 200, res.text
        events = conn.event_calls()
        assert len(events) == 1
        assert events[0][1][3]["application_id"] == APPLICATION_ID
        # The internal path must never also log the legacy external apply_click.
        assert "apply_click" not in conn.executed_sql()

    def test_external_self_report_logs_apply_click_not_application_submitted(
        self, client: TestClient
    ) -> None:
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.matches m",
            {"job_id": JOB_ID, "applicant_id": APPLICANT_ID},
        )
        conn.route_fetchrow(
            "INSERT INTO public.saved_jobs",
            {"interest_level": "applied", "updated_at": "2026-08-01T00:00:00"},
        )
        conn.route_fetchval("SELECT interest_level", None)

        app.dependency_overrides[require_applicant] = _applicant_user
        match_id = "66666666-0000-0000-0000-666666666666"
        with _patch_db("applicants", conn):
            res = client.post(
                f"/applicant/me/matches/{match_id}/interest",
                json={"interest_level": "applied"},
                headers={"Authorization": "Bearer fake"},
            )

        assert res.status_code == 200, res.text
        sql = conn.executed_sql()
        assert "apply_click" in sql
        assert "application_submitted" not in sql


# ---------------------------------------------------------------------------
# Snapshot immutability / employer view
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_records_shared_fields_and_inline_values(self, client: TestClient) -> None:
        conn = _std_apply_conn(
            applicant=_applicant_row(phone=None),
            job=_job_row(required_profile_fields=["contact", "location"]),
        )
        db, reread = _apply_ctx(conn)
        with db, reread:
            res = _post_apply(client, {
                "answers": [],
                "profile_updates": {"phone": "512-555-0123"},
            })
        assert res.status_code == 200, res.text
        _, args = next(
            (s, a) for s, a in conn.fetchrow_calls if "INSERT INTO public.applications" in s
        )
        snapshot = next(a for a in args if isinstance(a, dict) and "first_name" in a)
        # The consent record: what was shared, frozen at submit time.
        assert snapshot["shared_fields"] == ["contact", "location"]
        assert snapshot["phone"] == "512-555-0123"
        # shared_fields is ALSO bound as its own column for querying.
        assert ["contact", "location"] in [list(a) if isinstance(a, list) else None for a in args]

    def test_profile_edit_never_touches_applications(self, client: TestClient) -> None:
        """PATCH /applicant/me/profile must not write the applications table —
        the snapshot is immutable history."""
        conn = RoutedConn()
        conn.route_fetchrow("UPDATE public.applicants", {"id": APPLICANT_ID})
        conn.route_fetchval("SELECT COUNT(*)", 0)
        app.dependency_overrides[require_applicant] = _applicant_user
        with _patch_db("applicants", conn):
            res = client.patch(
                "/applicant/me/profile",
                json={"phone": "512-555-0777"} if False else {"first_name": "Janet"},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200, res.text
        all_sql = conn.executed_sql() + " ".join(s for s, _ in conn.fetchrow_calls)
        assert "public.applications" not in all_sql

    def test_employer_sees_decrypted_answers(self, client: TestClient) -> None:
        from datetime import datetime, timezone

        from app.routers.applications import _row_to_out
        from app.util.crypto import encrypt_str

        row = {
            "id": APPLICATION_ID, "job_id": JOB_ID, "employer_id": EMPLOYER_ID,
            "applicant_id": APPLICANT_ID, "match_id": None,
            "status": "submitted", "knockout_failed": False, "cover_note": None,
            "submitted_at": datetime.now(timezone.utc), "employer_viewed_at": None,
            "reviewed_at": None, "decision_at": None,
            "resume_snapshot": {"first_name": "Jane", "shared_fields": ["contact"]},
            "screening_answers": [{
                "question_id": QUESTION_ID, "prompt": "Do you have a CDL?",
                "answer": encrypt_str("Yes"), "knockout_pass": True,
            }],
            "job_title": "Welder", "employer_name": "Acme",
            "applicant_first": "Jane", "applicant_last": "Doe",
        }
        out = _row_to_out(row)
        assert out.screening_answers[0]["answer"] == "Yes"
        assert out.resume_snapshot["shared_fields"] == ["contact"]


# ---------------------------------------------------------------------------
# Apply context
# ---------------------------------------------------------------------------

class TestApplyContext:
    def test_context_reports_missing_groups_and_flags(self, client: TestClient) -> None:
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.jobs j", _job_row(
            required_profile_fields=["contact", "resume", "location"],
        ))
        conn.route_fetchrow("FROM public.applicants", _applicant_row(phone=None, email=None))
        conn.route_fetchrow("FROM public.applications", None)
        conn.route_fetch("job_screening_questions", [{
            "id": QUESTION_ID, "position": 0, "kind": "yes_no",
            "prompt": "Do you have a CDL?", "options": [],
            "required_answer": "Yes", "is_knockout": True,
        }])
        app.dependency_overrides[require_applicant] = _applicant_user
        with _patch_db("applications", conn):
            res = client.get(
                f"/applicant/me/jobs/{JOB_ID}/apply-context",
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["internal_apply_enabled"] is True
        assert body["job_active"] is True
        assert body["external_url"] == "https://jobs.example.com/1"
        assert set(body["missing_required"]) == {"contact", "resume"}  # location complete
        assert body["already_applied"] is None
        assert len(body["questions"]) == 1
        # SECURITY: the employer's expected knockout answer must never be
        # shipped to the applicant (would defeat the screening gate).
        assert "required_answer" not in body["questions"][0]

    def test_context_reports_reapply_eligibility(self, client: TestClient) -> None:
        from datetime import datetime, timezone
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.jobs j", _job_row())
        conn.route_fetchrow("FROM public.applicants", _applicant_row())
        conn.route_fetchrow("FROM public.applications", {
            "id": APPLICATION_ID, "status": "withdrawn",
            "submitted_at": datetime.now(timezone.utc), "reapply_count": 0,
        })
        app.dependency_overrides[require_applicant] = _applicant_user
        with _patch_db("applications", conn):
            res = client.get(
                f"/applicant/me/jobs/{JOB_ID}/apply-context",
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["already_applied"]["status"] == "withdrawn"
        assert body["already_applied"]["can_reapply"] is True
