"""
test_withdraw_and_quiet_window.py — production-readiness structural fixes.

Covers:
  Applicant withdraw gate
    - withdraw from 'interviewing' is allowed, cancels every open interview
      slot server-side, and the employer's notification carries the
      interview-cancellation context
    - withdraw from 'offered' → 409 with an honest "message the employer" line
    - terminal states → 409
    - plain withdraw (no interview) still notifies without the extra context

  Rejection quiet window
    - PATCH → rejected writes the applicant notification with deliver_after
      set (~15s ahead) so the employer's undo toast outlives the ping
    - shortlist/hire notifications stay instant (deliver_after NULL)
    - revert of a rejection deletes the still-pending notification row

  Hire path parity
    - POST /employer/me/jobs/{jid}/candidates/{aid}/hire notifies the
      applicant (application_hired) even without an application row
    - non-hired outcomes (declined/withdrew) stay quiet

  Credential review dismissal
    - dismissing a credential_ambiguity item appends to the record chain and
      notifies the applicant that the credential stays self-reported

Mock-DB style shared with test_internal_apply.py (RoutedConn).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin, require_applicant, require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app
from tests.test_internal_apply import (  # noqa: F401  (shared harness)
    APPLICANT_ID,
    APPLICANT_USER_ID,
    APPLICATION_ID,
    EMPLOYER_ID,
    EMPLOYER_USER_ID,
    JOB_ID,
    RoutedConn,
    _patch_db,
)

ADMIN_USER_ID = "cccccccc-0000-0000-0000-cccccccccccc"
SLOT_ID = "66666666-0000-0000-0000-666666666666"
CREDENTIAL_ID = "77777777-0000-0000-0000-777777777777"


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


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id=ADMIN_USER_ID, email="admin@test.local",
        role="admin", onboarding_complete=True,
    )


def _dummy_out(status: str = "withdrawn"):
    from app.routers.applications import ApplicationOut
    return ApplicationOut(
        id=APPLICATION_ID, job_id=JOB_ID, job_title="Welder",
        employer_id=EMPLOYER_ID, applicant_id=APPLICANT_ID,
        status=status, knockout_failed=False,
        submitted_at="2026-08-01T00:00:00", days_since_submitted=0,
    )


def _notes(conn: RoutedConn) -> list[tuple[str, tuple]]:
    return [(s, a) for s, a in conn.executed if "INSERT INTO public.notifications" in s]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Withdraw gate
# ---------------------------------------------------------------------------

def _withdraw_conn(status: str, cancelled_slots: list[dict] | None = None) -> RoutedConn:
    conn = RoutedConn()
    # The employer-notify info row (contains "AS employer_user") must be
    # registered BEFORE the generic applications route — routes match in order.
    conn.route_fetchrow(
        "AS employer_user",
        {"job_title": "Welder", "applicant_name": "Jane Doe",
         "employer_user": EMPLOYER_USER_ID},
    )
    conn.route_fetchrow("FROM public.applications", {"id": APPLICATION_ID, "status": status})
    conn.route_fetch("UPDATE public.interview_slots", cancelled_slots or [])
    return conn


def _post_withdraw(client: TestClient):
    return client.post(
        f"/applicant/me/applications/{APPLICATION_ID}/withdraw",
        headers={"Authorization": "Bearer fake"},
    )


def _withdraw_ctx(conn: RoutedConn):
    from app.routers import applications as apps_mod
    app.dependency_overrides[require_applicant] = _applicant_user
    return (
        _patch_db("applications", conn),
        patch.object(apps_mod, "get_my_application", AsyncMock(return_value=_dummy_out())),
    )


class TestWithdrawGate:
    def test_withdraw_from_interviewing_cancels_slots_and_tells_employer(self, client: TestClient) -> None:
        start = datetime.now(timezone.utc) + timedelta(days=2)
        conn = _withdraw_conn("interviewing", cancelled_slots=[
            {"id": SLOT_ID, "start_at": start,
             "end_at": start + timedelta(minutes=30), "was_accepted": True},
        ])
        db, out = _withdraw_ctx(conn)
        with db, out:
            r = _post_withdraw(client)
        assert r.status_code == 200, r.text
        sql = conn.executed_sql()
        # Withdraw is race-guarded on the status we just read.
        assert "status = 'withdrawn'" in sql
        # Employer hears about the withdrawal WITH the cancellation context.
        notes = _notes(conn)
        assert len(notes) == 1
        args_str = str(notes[0][1])
        assert "application_withdrawn" in args_str
        assert "interview was cancelled" in args_str
        assert "cancelled_interview_slots" in args_str

    def test_withdraw_from_interviewing_proposed_only_context(self, client: TestClient) -> None:
        start = datetime.now(timezone.utc) + timedelta(days=2)
        conn = _withdraw_conn("interviewing", cancelled_slots=[
            {"id": SLOT_ID, "start_at": start,
             "end_at": start + timedelta(minutes=30), "was_accepted": False},
        ])
        db, out = _withdraw_ctx(conn)
        with db, out:
            r = _post_withdraw(client)
        assert r.status_code == 200, r.text
        assert "proposed interview times were released" in str(_notes(conn)[0][1])

    def test_withdraw_from_offered_blocked_with_honest_message(self, client: TestClient) -> None:
        conn = _withdraw_conn("offered")
        db, out = _withdraw_ctx(conn)
        with db, out:
            r = _post_withdraw(client)
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "offer" in detail.lower()
        assert "message the employer" in detail.lower()
        assert _notes(conn) == []

    @pytest.mark.parametrize("status", ["hired", "rejected", "withdrawn"])
    def test_withdraw_terminal_states_409(self, client: TestClient, status: str) -> None:
        conn = _withdraw_conn(status)
        db, out = _withdraw_ctx(conn)
        with db, out:
            r = _post_withdraw(client)
        assert r.status_code == 409
        assert _notes(conn) == []

    def test_plain_withdraw_has_no_interview_context(self, client: TestClient) -> None:
        conn = _withdraw_conn("submitted")
        db, out = _withdraw_ctx(conn)
        with db, out:
            r = _post_withdraw(client)
        assert r.status_code == 200, r.text
        # No slot cancellation ran, and the notification stays plain.
        assert "interview_slots" not in conn.executed_sql()
        args_str = str(_notes(conn)[0][1])
        assert "application_withdrawn" in args_str
        assert "interview was cancelled" not in args_str


# ---------------------------------------------------------------------------
# Rejection quiet window
# ---------------------------------------------------------------------------

def _patch_conn(status: str = "reviewed") -> RoutedConn:
    conn = RoutedConn()
    conn.route_fetchrow(
        "match_id, status::text AS status",
        {"employer_id": EMPLOYER_ID, "applicant_id": APPLICANT_ID,
         "job_id": JOB_ID, "match_id": None, "status": status},
    )
    conn.route_fetchrow("employer_contacts", {"?column?": 1})
    conn.route_fetchrow(
        "JOIN public.employers e",
        {"user_id": APPLICANT_USER_ID, "job_title": "Welder", "employer_name": "Acme"},
    )
    return conn


def _do_patch(client: TestClient, conn: RoutedConn, status: str, out_status: str):
    from app.routers import applications as apps_mod
    app.dependency_overrides[require_employer_only] = _employer_user
    with _patch_db("applications", conn), patch.object(
        apps_mod, "get_employer_application",
        AsyncMock(return_value=_dummy_out(out_status)),
    ):
        return client.patch(
            f"/employer/me/applications/{APPLICATION_ID}",
            json={"status": status},
            headers={"Authorization": "Bearer fake"},
        )


class TestRejectionQuietWindow:
    def test_reject_notification_is_deferred(self, client: TestClient) -> None:
        conn = _patch_conn("reviewed")
        r = _do_patch(client, conn, "rejected", "rejected")
        assert r.status_code == 200, r.text
        notes = _notes(conn)
        assert len(notes) == 1
        sql, args = notes[0]
        assert "deliver_after" in sql
        assert "application_rejected" in str(args)
        deliver_after = args[-1]
        assert isinstance(deliver_after, datetime)
        delta = (deliver_after - datetime.now(timezone.utc)).total_seconds()
        assert 5 < delta <= 60          # ~15s ahead, comfortably past the toast

    @pytest.mark.parametrize("status", ["shortlisted", "hired"])
    def test_positive_news_stays_instant(self, client: TestClient, status: str) -> None:
        conn = _patch_conn("reviewed")
        r = _do_patch(client, conn, status, status)
        assert r.status_code == 200, r.text
        notes = _notes(conn)
        assert len(notes) == 1
        assert notes[0][1][-1] is None      # deliver_after NULL = instant

    def test_revert_deletes_pending_rejection_notification(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.applications",
            {"employer_id": EMPLOYER_ID, "applicant_id": APPLICANT_ID,
             "job_id": JOB_ID, "match_id": None,
             "status": "rejected", "previous_status": "shortlisted",
             "decision_note": None, "decision_at": None},
        )
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application",
            AsyncMock(return_value=_dummy_out("shortlisted")),
        ):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/revert",
                headers={"Authorization": "Bearer fake"},
            )
        assert r.status_code == 200, r.text
        deletes = [(s, a) for s, a in conn.executed
                   if "DELETE FROM public.notifications" in s]
        assert len(deletes) == 1
        sql, args = deletes[0]
        assert "application_rejected" in sql
        assert "deliver_after > NOW()" in sql      # only still-pending rows
        assert args[0] == APPLICATION_ID

    def test_revert_of_shortlist_does_not_touch_notifications(self, client: TestClient) -> None:
        from app.routers import applications as apps_mod
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.applications",
            {"employer_id": EMPLOYER_ID, "applicant_id": APPLICANT_ID,
             "job_id": JOB_ID, "match_id": None,
             "status": "shortlisted", "previous_status": "reviewed",
             "decision_note": None, "decision_at": None},
        )
        conn.route_fetchrow("employer_contacts", {"?column?": 1})
        app.dependency_overrides[require_employer_only] = _employer_user
        with _patch_db("applications", conn), patch.object(
            apps_mod, "get_employer_application",
            AsyncMock(return_value=_dummy_out("reviewed")),
        ):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/revert",
                headers={"Authorization": "Bearer fake"},
            )
        assert r.status_code == 200, r.text
        assert not any("DELETE FROM public.notifications" in s for s, _ in conn.executed)


# ---------------------------------------------------------------------------
# Hire path parity — the non-application hire notifies the applicant
# ---------------------------------------------------------------------------

def _hire_conn(*, application_id: str | None = APPLICATION_ID) -> RoutedConn:
    conn = RoutedConn()
    conn.route_fetchval("FROM public.employer_contacts", EMPLOYER_ID)
    conn.route_fetchval("FROM public.jobs WHERE id", JOB_ID)
    conn.route_fetchrow(
        "INSERT INTO public.hire_outcomes",
        {"id": "88888888-0000-0000-0000-888888888888",
         "outcome_type": "hired", "created_at": "2026-08-02T00:00:00"},
    )
    conn.route_fetchrow(
        "FROM public.applicants ap",
        {"user_id": APPLICANT_USER_ID, "job_title": "Welder",
         "employer_name": "Acme", "application_id": application_id},
    )
    return conn


def _post_hire(client: TestClient, conn: RoutedConn, outcome: str = "hired"):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    app.dependency_overrides[require_employer_only] = _employer_user
    with patch("app.routers.employers.get_db", return_value=ctx):
        return client.post(
            f"/employer/me/jobs/{JOB_ID}/candidates/{APPLICANT_ID}/hire",
            json={"outcome_type": outcome},
            headers={"Authorization": "Bearer fake"},
        )


class TestHireNotifies:
    def test_hire_notifies_applicant(self, client: TestClient) -> None:
        conn = _hire_conn()
        r = _post_hire(client, conn)
        assert r.status_code == 201, r.text
        notes = _notes(conn)
        assert len(notes) == 1
        args_str = str(notes[0][1])
        assert "application_hired" in args_str
        assert "You were hired for Welder" in args_str
        assert str(APPLICANT_USER_ID) in args_str
        # Deep link goes to the application when one exists.
        assert f"/applicant/applications/{APPLICATION_ID}" in args_str

    def test_hire_without_application_row_still_notifies(self, client: TestClient) -> None:
        conn = _hire_conn(application_id=None)
        r = _post_hire(client, conn)
        assert r.status_code == 201, r.text
        notes = _notes(conn)
        assert len(notes) == 1
        assert "/applicant/applications" in str(notes[0][1])

    @pytest.mark.parametrize("outcome", ["declined", "withdrew"])
    def test_non_hire_outcomes_stay_quiet(self, client: TestClient, outcome: str) -> None:
        conn = _hire_conn()
        r = _post_hire(client, conn, outcome)
        assert r.status_code == 201, r.text
        assert _notes(conn) == []


# ---------------------------------------------------------------------------
# Credential review dismissal — the applicant hears the outcome
# ---------------------------------------------------------------------------

class TestCredentialDismissal:
    def _resolve(self, client: TestClient, conn: RoutedConn, action: str):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        app.dependency_overrides[require_admin] = _admin_user
        with patch("app.routers.admin_review.get_db", return_value=ctx):
            return client.post(
                f"/admin/review/{CREDENTIAL_ID}/resolve",
                json={"action": action},
                headers={"Authorization": "Bearer fake"},
            )

    def _conn(self) -> RoutedConn:
        now = datetime.now(timezone.utc)
        conn = RoutedConn()
        conn.route_fetchrow(
            "UPDATE public.review_queue_items",
            {"id": CREDENTIAL_ID, "item_type": "credential_ambiguity",
             "entity_type": "credential", "entity_id": CREDENTIAL_ID,
             "description": None, "flags": None, "confidence_level": None,
             "priority": 4, "status": "dismissed", "created_at": now,
             "resolved_at": now, "resolution_action": "dismissed",
             "resolution_notes": None},
        )
        conn.route_fetchrow(
            "FROM public.review_queue_items",
            {"id": CREDENTIAL_ID, "item_type": "credential_ambiguity", "status": "pending"},
        )
        conn.route_fetchrow(
            "FROM public.credentials c JOIN public.applicants a",
            {"id": CREDENTIAL_ID, "verification_level": 0,
             "applicant_id": APPLICANT_ID, "name": "OSHA 30",
             "user_id": APPLICANT_USER_ID},
        )
        return conn

    def test_dismiss_notifies_applicant_and_appends_record(self, client: TestClient) -> None:
        conn = self._conn()
        r = self._resolve(client, conn, "dismissed")
        assert r.status_code == 200, r.text
        # Honest, actionable notification — never a forever-pending state.
        notes = _notes(conn)
        assert len(notes) == 1
        args_str = str(notes[0][1])
        assert "credential_review_dismissed" in args_str
        assert "OSHA 30" in args_str
        assert "self-reported" in args_str
        assert str(APPLICANT_USER_ID) in args_str
        # The outcome lands on the signed record chain.
        assert any("INSERT INTO public.credential_records" in s
                   and "document_review_dismissed" in str(a)
                   for s, a in conn.executed)
        # Dismissal never raises the badge.
        assert not any("SET verification_level" in s for s, _ in conn.executed)