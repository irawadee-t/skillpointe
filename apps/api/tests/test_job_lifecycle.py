"""
test_job_lifecycle.py — employer job lifecycle management.

Pins the Mission-B contract:

  Transition matrix (PATCH /employer/me/jobs/{id}/status)
    - active → paused / filled / closed; paused → active / filled / closed;
      filled → active; closed → active — everything else is a 409
    - same-status PATCH is an idempotent no-op (no audit, no recompute)
    - every real transition stores previous_status, writes audit_logs
      (job_status_changed), and triggers a match recompute when applicant
      visibility flipped (is_active changed)

  Real undo (POST /employer/me/jobs/{id}/status/revert)
    - restores previous_status exactly once (previous_status clears)
    - nothing to revert → 409

  Delete guard (DELETE /employer/me/jobs/{id})
    - zero-activity job deletes (audited)
    - any applications / saved-job interest / outreach / hire history → 409
      ("close it instead")

  Isolation
    - a job the employer doesn't own → 404 on all three endpoints

  Applicant honesty
    - ApplicationOut carries job_active from jobs.is_active so an application
      to a posting that went inactive can show "no longer active".

Mock-DB style shared with test_internal_apply.py (RoutedConn).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app
from tests.test_internal_apply import RoutedConn, _patch_db  # noqa: F401

EMPLOYER_USER_ID = "eeeeeeee-0000-0000-0000-000000000001"
EMPLOYER_ID = "eeeeeeee-0000-0000-0000-000000000002"
JOB_ID = "aaaaaaaa-0000-0000-0000-00000000000a"


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=EMPLOYER_USER_ID, email="employer@test.local",
        role="employer", onboarding_complete=True,
    )


def _conn(
    *, current: str = "active", previous: str | None = None,
    is_active: bool | None = None, owns: bool = True,
    updated_status: str | None = None, has_activity: bool = False,
) -> RoutedConn:
    conn = RoutedConn()
    # The user is always a linked employer contact; owns=False means the JOB
    # belongs to someone else (queries scoped by employer_id find nothing).
    conn.route_fetchval("employer_contacts", EMPLOYER_ID)
    active = is_active if is_active is not None else (current == "active")
    job_row = {
        "id": JOB_ID, "status": current, "previous_status": previous,
        "is_active": active, "title_raw": "Welder I", "has_activity": has_activity,
    }
    conn.route_fetchrow("FROM public.jobs j", job_row if owns else None)
    conn.route_fetchrow("SELECT id, status, is_active FROM public.jobs",
                        job_row if owns else None)
    conn.route_fetchrow("SELECT id, status, previous_status, is_active FROM public.jobs",
                        job_row if owns else None)
    if updated_status is not None:
        conn.route_fetchrow(
            "UPDATE public.jobs",
            {"id": JOB_ID, "status": updated_status, "previous_status":
             None if previous else current if updated_status != current else None,
             "is_active": updated_status == "active"},
        )
    return conn


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _overrides():
    app.dependency_overrides[require_employer_only] = _employer_user
    yield
    app.dependency_overrides.clear()


def _audit_actions(conn: RoutedConn) -> list[str]:
    return [args[2] for sql, args in conn.executed
            if "audit_logs" in sql and len(args) > 2]


def _recompute_patch():
    return patch(
        "app.worker.scheduler.trigger_recompute_for_job", new_callable=AsyncMock,
    )


# ---------------------------------------------------------------------------
# Transition matrix
# ---------------------------------------------------------------------------

class TestTransitionMatrix:
    @pytest.mark.parametrize("frm,to", [
        ("active", "paused"), ("active", "filled"), ("active", "closed"),
        ("paused", "active"), ("paused", "filled"), ("paused", "closed"),
        ("filled", "active"), ("closed", "active"),
    ])
    def test_allowed_transitions(self, client, frm, to):
        conn = _conn(current=frm, updated_status=to)
        with _patch_db("employers", conn), _recompute_patch():
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status", json={"status": to})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == to
        assert "job_status_changed" in _audit_actions(conn)

    @pytest.mark.parametrize("frm,to", [
        ("filled", "paused"), ("filled", "closed"),
        ("closed", "paused"), ("closed", "filled"),
    ])
    def test_blocked_transitions(self, client, frm, to):
        conn = _conn(current=frm)
        with _patch_db("employers", conn):
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status", json={"status": to})
        assert r.status_code == 409
        assert "job_status_changed" not in _audit_actions(conn)

    def test_same_status_is_idempotent_noop(self, client):
        conn = _conn(current="paused", is_active=False)
        with _patch_db("employers", conn), _recompute_patch() as rec:
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status",
                             json={"status": "paused"})
        assert r.status_code == 200
        assert r.json()["status"] == "paused"
        assert "job_status_changed" not in _audit_actions(conn)
        rec.assert_not_called()

    def test_bogus_status_is_422(self, client):
        conn = _conn()
        with _patch_db("employers", conn):
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status",
                             json={"status": "archived"})
        assert r.status_code == 422

    def test_pause_triggers_visibility_recompute(self, client):
        conn = _conn(current="active", updated_status="paused")
        with _patch_db("employers", conn), _recompute_patch() as rec:
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status",
                             json={"status": "paused"})
        assert r.status_code == 200
        rec.assert_called_once_with(JOB_ID)

    def test_not_owned_job_is_404(self, client):
        conn = _conn(owns=False)
        with _patch_db("employers", conn):
            r = client.patch(f"/employer/me/jobs/{JOB_ID}/status",
                             json={"status": "paused"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Revert — real undo
# ---------------------------------------------------------------------------

class TestRevert:
    def test_revert_restores_previous_status(self, client):
        conn = _conn(current="paused", previous="active", is_active=False,
                     updated_status="active")
        with _patch_db("employers", conn), _recompute_patch() as rec:
            r = client.post(f"/employer/me/jobs/{JOB_ID}/status/revert")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"
        assert "job_status_reverted" in _audit_actions(conn)
        rec.assert_called_once_with(JOB_ID)

    def test_revert_without_history_is_409(self, client):
        conn = _conn(current="active", previous=None)
        with _patch_db("employers", conn):
            r = client.post(f"/employer/me/jobs/{JOB_ID}/status/revert")
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# Delete guard
# ---------------------------------------------------------------------------

class TestDeleteGuard:
    def test_zero_activity_job_deletes(self, client):
        conn = _conn(has_activity=False)
        with _patch_db("employers", conn):
            r = client.delete(f"/employer/me/jobs/{JOB_ID}")
        assert r.status_code == 200
        assert "DELETE FROM public.jobs" in conn.executed_sql()
        assert "job_deleted" in _audit_actions(conn)

    def test_job_with_activity_refuses_delete(self, client):
        conn = _conn(has_activity=True)
        with _patch_db("employers", conn):
            r = client.delete(f"/employer/me/jobs/{JOB_ID}")
        assert r.status_code == 409
        assert "close" in r.json()["detail"].lower()
        assert "DELETE FROM public.jobs" not in conn.executed_sql()

    def test_not_owned_job_is_404(self, client):
        conn = _conn(owns=False)
        with _patch_db("employers", conn):
            r = client.delete(f"/employer/me/jobs/{JOB_ID}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Applicant honesty — job_active rides along on ApplicationOut
# ---------------------------------------------------------------------------

class TestApplicationJobActive:
    def _row(self, active: bool) -> dict:
        from datetime import datetime, timezone
        return {
            "id": "bbbbbbbb-0000-0000-0000-00000000000b", "job_id": JOB_ID,
            "employer_id": EMPLOYER_ID,
            "applicant_id": "cccccccc-0000-0000-0000-00000000000c",
            "match_id": None, "status": "submitted", "knockout_failed": False,
            "cover_note": None,
            "submitted_at": datetime.now(timezone.utc),
            "employer_viewed_at": None, "reviewed_at": None, "decision_at": None,
            "resume_snapshot": {}, "screening_answers": [],
            "job_title": "Welder I", "job_active": active,
            "employer_name": "Acme", "applicant_first": "Jane", "applicant_last": "Doe",
        }

    def test_row_to_out_carries_job_active(self):
        from app.routers.applications import _row_to_out
        assert _row_to_out(self._row(True)).job_active is True
        assert _row_to_out(self._row(False)).job_active is False

    def test_app_select_includes_job_active(self):
        from app.routers.applications import _APP_SELECT
        assert "j.is_active AS job_active" in _APP_SELECT
