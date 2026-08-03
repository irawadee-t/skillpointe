"""
test_application_revert.py — REAL undo for employer application decisions.

The one non-negotiable: an Undo affordance must actually undo. These tests
pin the whole revert contract:

  Transition matrix
    - shortlisted → its stored previous stage (previous_status)
    - shortlisted with no history (legacy row) → 'reviewed' fallback
    - rejected → reopened at previous stage, decision_note/decision_at cleared
    - hired → previous stage AND the hire is voided (hire_outcomes row
      deleted + original hire_reported engagement events deleted) so the
      employer/admin analytics stay TRUE
    - unsafe previous_status (e.g. 'hired') can never be a revert target
    - interviewing → 409 (owned by the interview supersede/cancel flow)
    - submitted / reviewed / withdrawn → 409 (nothing to revert)

  Bookkeeping
    - every revert writes audit_logs (action=application_status_reverted)
      with from/to state, archived decision note, and voided hire outcome
    - PATCH stores previous_status on every actual status transition
    - PATCH to 'hired' records hire_outcomes + hire_reported exactly once
      (no-op when the row is already hired)

  Guards
    - double revert → second call finds a non-revertible status → 409
    - concurrent flip (guarded UPDATE matches 0 rows) → 409, no side effects
    - non-owner employer → 404

Mock-DB style shared with test_internal_apply.py (RoutedConn).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app
from tests.test_internal_apply import (  # noqa: F401  (shared harness)
    APPLICANT_ID,
    APPLICATION_ID,
    EMPLOYER_ID,
    EMPLOYER_USER_ID,
    JOB_ID,
    RoutedConn,
    _patch_db,
)

MATCH_ID = "66666666-0000-0000-0000-666666666666"


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=EMPLOYER_USER_ID, email="employer@test.local",
        role="employer", onboarding_complete=True,
    )


def _app_row(status: str, previous_status: str | None = None, **overrides: Any) -> dict:
    row = {
        "employer_id": EMPLOYER_ID, "applicant_id": APPLICANT_ID,
        "job_id": JOB_ID, "match_id": MATCH_ID,
        "status": status, "previous_status": previous_status,
        "decision_note": None, "decision_at": None,
    }
    row.update(overrides)
    return row


def _conn_for_revert(
    row: dict | None,
    *,
    owns: bool = True,
    hire_outcome_row: dict | None = None,
) -> RoutedConn:
    conn = RoutedConn()
    conn.route_fetchrow("FROM public.applications", row)
    conn.route_fetchrow("employer_contacts", {"?column?": 1} if owns else None)
    conn.route_fetchrow("DELETE FROM public.hire_outcomes", hire_outcome_row)
    return conn


def _dummy_out(status: str = "reviewed"):
    from app.routers.applications import ApplicationOut
    return ApplicationOut(
        id=APPLICATION_ID, job_id=JOB_ID, job_title="Welder",
        employer_id=EMPLOYER_ID, applicant_id=APPLICANT_ID,
        status=status, knockout_failed=False,
        submitted_at="2026-08-01T00:00:00", days_since_submitted=0,
    )


def _ctx(conn: RoutedConn, out_status: str = "reviewed"):
    from app.routers import applications as apps_mod
    app.dependency_overrides[require_employer_only] = _employer_user
    return (
        _patch_db("applications", conn),
        patch.object(
            apps_mod, "get_employer_application",
            AsyncMock(return_value=_dummy_out(out_status)),
        ),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _post_revert(client: TestClient):
    return client.post(
        f"/employer/me/applications/{APPLICATION_ID}/revert",
        headers={"Authorization": "Bearer fake"},
    )


def _revert_update(conn: RoutedConn) -> tuple[str, tuple] | None:
    for sql, args in conn.executed:
        if "UPDATE public.applications" in sql and "previous_status = NULL" in sql:
            return sql, args
    return None


def _audit_insert(conn: RoutedConn) -> tuple[str, tuple] | None:
    for sql, args in conn.executed:
        if "INSERT INTO public.audit_logs" in sql:
            return sql, args
    return None


# ---------------------------------------------------------------------------
# Transition matrix
# ---------------------------------------------------------------------------

class TestRevertMatrix:
    def test_shortlisted_reverts_to_previous_stage(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row("shortlisted", previous_status="reviewed"))
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 200
        sql, args = _revert_update(conn)
        assert args[1] == "reviewed"          # target
        assert args[2] == "shortlisted"       # race guard: only from current

    def test_shortlisted_without_history_falls_back_to_reviewed(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row("shortlisted", previous_status=None))
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 200
        _, args = _revert_update(conn)
        assert args[1] == "reviewed"

    def test_rejected_reopens_and_clears_decision_note(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row(
            "rejected", previous_status="shortlisted",
            decision_note="Not a match right now.",
        ))
        db, out = _ctx(conn, out_status="shortlisted")
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 200
        sql, args = _revert_update(conn)
        assert args[1] == "shortlisted"
        assert "decision_note = NULL" in sql
        assert "decision_at = NULL" in sql
        # The note isn't lost — archived into the audit row's before_state.
        _, audit_args = _audit_insert(conn)
        assert audit_args[3]["decision_note"] == "Not a match right now."

    def test_hired_revert_voids_outcome_and_events(self, client: TestClient) -> None:
        conn = _conn_for_revert(
            _app_row("hired", previous_status="offered"),
            hire_outcome_row={"id": "77777777-0000-0000-0000-777777777777",
                              "outcome_type": "hired", "hire_date": None,
                              "reported_wage_annual": None},
        )
        db, out = _ctx(conn, out_status="offered")
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 200
        _, args = _revert_update(conn)
        assert args[1] == "offered"
        # The original hire_reported events are deleted — analytics stay true.
        assert any(
            "DELETE FROM public.engagement_events" in sql and "hire_reported" in sql
            for sql, _ in conn.executed
        )
        # Voided outcome is preserved in the audit trail.
        _, audit_args = _audit_insert(conn)
        assert audit_args[3]["hire_outcome"]["outcome_type"] == "hired"
        assert audit_args[3]["status"] == "hired"
        assert audit_args[4] == {"status": "offered"}

    def test_unsafe_previous_status_never_a_target(self, client: TestClient) -> None:
        # A rejected row whose previous stage was 'hired' must NOT resurrect
        # the hire — it lands on 'reviewed'.
        conn = _conn_for_revert(_app_row("rejected", previous_status="hired"))
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 200
        _, args = _revert_update(conn)
        assert args[1] == "reviewed"

    @pytest.mark.parametrize("status,detail_needle", [
        ("interviewing", "interview"),
        ("submitted", "Nothing to revert"),
        ("reviewed", "Nothing to revert"),
        ("withdrawn", "Nothing to revert"),
    ])
    def test_non_revertible_states_409(self, client: TestClient, status: str, detail_needle: str) -> None:
        conn = _conn_for_revert(_app_row(status))
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 409
        assert detail_needle.lower() in r.json()["detail"].lower()
        assert _revert_update(conn) is None      # no write happened
        assert _audit_insert(conn) is None


# ---------------------------------------------------------------------------
# Bookkeeping: audit + previous_status capture + hire recording
# ---------------------------------------------------------------------------

class TestBookkeeping:
    def test_every_revert_is_audited_with_from_to(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row("shortlisted", previous_status="reviewed"))
        db, out = _ctx(conn)
        with db, out:
            _post_revert(client)
        sql, args = _audit_insert(conn)
        assert "application_status_reverted" in sql
        assert args[0] == EMPLOYER_USER_ID and args[1] == "employer"
        assert args[3]["status"] == "shortlisted"     # before
        assert args[4] == {"status": "reviewed"}      # after

    def test_patch_transition_stores_previous_status(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications", _app_row("reviewed"))
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application", AsyncMock(return_value=_dummy_out("shortlisted")),
        ):
            r = client.patch(
                f"/employer/me/applications/{APPLICATION_ID}",
                json={"status": "shortlisted"},
                headers={"Authorization": "Bearer fake"},
            )
        assert r.status_code == 200
        update_sql = next(sql for sql, _ in conn.executed if "UPDATE public.applications" in sql)
        assert "previous_status = status" in update_sql

    def test_patch_same_status_does_not_touch_previous_status(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications", _app_row("shortlisted", previous_status="reviewed"))
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application", AsyncMock(return_value=_dummy_out("shortlisted")),
        ):
            client.patch(
                f"/employer/me/applications/{APPLICATION_ID}",
                json={"status": "shortlisted"},
                headers={"Authorization": "Bearer fake"},
            )
        update_sql = next(sql for sql, _ in conn.executed if "UPDATE public.applications" in sql)
        assert "previous_status" not in update_sql

    def test_patch_to_hired_records_outcome_and_event_once(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications", _app_row("offered"))
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application", AsyncMock(return_value=_dummy_out("hired")),
        ):
            r = client.patch(
                f"/employer/me/applications/{APPLICATION_ID}",
                json={"status": "hired"},
                headers={"Authorization": "Bearer fake"},
            )
        assert r.status_code == 200
        outcome_writes = [s for s, _ in conn.executed if "INSERT INTO public.hire_outcomes" in s]
        event_writes = [(s, a) for s, a in conn.executed
                        if "engagement_events" in s and "hire_reported" in s]
        assert len(outcome_writes) == 1
        assert len(event_writes) == 1
        _, ev_args = event_writes[0]
        assert ev_args[4]["application_id"] == APPLICATION_ID

    def test_patch_already_hired_is_a_noop_for_analytics(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications", _app_row("hired"))
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application", AsyncMock(return_value=_dummy_out("hired")),
        ):
            client.patch(
                f"/employer/me/applications/{APPLICATION_ID}",
                json={"status": "hired"},
                headers={"Authorization": "Bearer fake"},
            )
        assert not any("hire_outcomes" in s for s, _ in conn.executed)
        assert not any("hire_reported" in s for s, _ in conn.executed)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

class TestGuards:
    def test_double_revert_second_call_409(self, client: TestClient) -> None:
        # After a successful revert the row reads 'reviewed' — not revertible.
        conn = _conn_for_revert(_app_row("reviewed", previous_status=None))
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 409

    def test_concurrent_flip_guarded_update_409(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row("shortlisted", previous_status="reviewed"))

        real_execute = conn.execute

        async def losing_execute(sql: str, *args: Any) -> str:
            result = await real_execute(sql, *args)
            if "UPDATE public.applications" in sql:
                return "UPDATE 0"      # someone changed the row first
            return result

        conn.execute = losing_execute  # type: ignore[method-assign]
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 409
        # The loser must not audit or void anything.
        assert _audit_insert(conn) is None
        assert not any("hire_outcomes" in s for s, _ in conn.executed)

    def test_non_owner_404(self, client: TestClient) -> None:
        conn = _conn_for_revert(_app_row("shortlisted"), owns=False)
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 404

    def test_missing_application_404(self, client: TestClient) -> None:
        conn = _conn_for_revert(None)
        db, out = _ctx(conn)
        with db, out:
            r = _post_revert(client)
        assert r.status_code == 404
