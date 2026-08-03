"""
test_scheduling_requests.py — delegated interview scheduling
("let them pick the times").

Covers:
  Create
    - assignee must be on the team (400) and must not be yourself (400)
    - one pending request per application (409)
    - happy path: row inserted, assignee notified in-app + emailed a deep
      link, audit written
  Cancel
    - only the originator or an org owner/admin (403 for other members)
    - non-pending → 409; assignee notified it's off their plate
  Fulfilment via the propose endpoint (app/routers/interviews.py)
    - assignee proposes → request fulfilled + originator notified
    - someone else proposes → request cancelled as superseded + assignee told
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app
from app.skilled_pro.senders import SendResult

OWNER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
MATE_USER_ID = "dddddddd-0000-0000-0000-dddddddddddd"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
OWNER_CONTACT_ID = "55555555-0000-0000-0000-555555555555"
MATE_CONTACT_ID = "99999999-0000-0000-0000-999999999999"
APPLICATION_ID = "44444444-0000-0000-0000-444444444444"
REQUEST_ID = "66666666-0000-0000-0000-666666666666"


def _owner() -> CurrentUser:
    return CurrentUser(user_id=OWNER_USER_ID, email="owner@acme.test", role="employer", onboarding_complete=True)


def _mate() -> CurrentUser:
    return CurrentUser(user_id=MATE_USER_ID, email="mate@acme.test", role="employer", onboarding_complete=True)


class RoutedConn:
    def __init__(self) -> None:
        self.fetchrow_routes: list[tuple[str, Any]] = []
        self.fetch_routes: list[tuple[str, Any]] = []
        self.fetchval_routes: list[tuple[str, Any]] = []
        self.executed: list[tuple[str, tuple]] = []

    def route_fetchrow(self, needle: str, result: Any) -> None:
        self.fetchrow_routes.append((needle, result))

    def route_fetch(self, needle: str, result: Any) -> None:
        self.fetch_routes.append((needle, result))

    def route_fetchval(self, needle: str, result: Any) -> None:
        self.fetchval_routes.append((needle, result))

    async def fetchrow(self, sql: str, *args: Any):
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

    def notifications(self) -> list[tuple]:
        return [a for s, a in self.executed if "INSERT INTO public.notifications" in s]


def _patch_db(conn: RoutedConn, module: str = "scheduling"):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"app.routers.{module}.get_db", return_value=ctx)


def _patch_email(captured: list):
    async def _fake_send(to, subject, text, html=None):
        captured.append({"to": to, "subject": subject, "text": text, "html": html})
        return SendResult(ok=True)
    return patch("app.routers.scheduling.send_email", side_effect=_fake_send)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _me_row(contact_id: str = OWNER_CONTACT_ID, role: str = "owner") -> dict:
    return {"id": UUID(contact_id), "employer_id": UUID(EMPLOYER_ID), "role": role}


def _request_row(**over) -> dict:
    row = {
        "id": UUID(REQUEST_ID),
        "application_id": UUID(APPLICATION_ID),
        "status": "pending",
        "note": None,
        "created_at": _now(),
        "assignee_contact_id": UUID(MATE_CONTACT_ID),
        "requested_by": UUID(OWNER_USER_ID),
        "assignee_email": "mate@acme.test",
        "assignee_name": "Marcus Lee",
        "requester_name": "Casey Owner",
        "applicant_name": "Jordan Reyes",
        "job_title": "Welder",
    }
    row.update(over)
    return row


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreate:
    def _base_conn(self) -> RoutedConn:
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.employer_contacts WHERE user_id", _me_row())
        conn.route_fetchrow(
            "FROM public.applications a",
            {"id": UUID(APPLICATION_ID), "employer_id": UUID(EMPLOYER_ID),
             "applicant_name": "Jordan Reyes", "job_title": "Welder"},
        )
        conn.route_fetchrow(
            "WHERE ec.id = $1 AND ec.employer_id",
            {"id": UUID(MATE_CONTACT_ID), "user_id": UUID(MATE_USER_ID),
             "email": "mate@acme.test", "name": "Marcus Lee"},
        )
        conn.route_fetchrow(
            "INSERT INTO public.scheduling_requests",
            {"id": UUID(REQUEST_ID), "created_at": _now()},
        )
        conn.route_fetchval("FROM auth.users WHERE id", "Casey Owner")
        conn.route_fetchrow("FROM public.scheduling_requests sr", _request_row())
        return conn

    def test_assignee_not_on_team_400(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._base_conn()
        conn.fetchrow_routes = [r for r in conn.fetchrow_routes if r[0] != "WHERE ec.id = $1 AND ec.employer_id"]
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/scheduling-request",
                json={"assignee_contact_id": MATE_CONTACT_ID},
            )
        assert r.status_code == 400
        assert "isn't on your team" in r.json()["detail"]

    def test_self_assignment_400(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._base_conn()
        conn.route_fetchrow(
            "WHERE ec.id = $1 AND ec.employer_id",
            {"id": UUID(OWNER_CONTACT_ID), "user_id": UUID(OWNER_USER_ID),
             "email": "owner@acme.test", "name": "Casey Owner"},
        )
        # (insert at front so it wins over the base route)
        conn.fetchrow_routes.insert(0, conn.fetchrow_routes.pop())
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/scheduling-request",
                json={"assignee_contact_id": OWNER_CONTACT_ID},
            )
        assert r.status_code == 400
        assert "propose the times directly" in r.json()["detail"]

    def test_second_pending_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._base_conn()
        conn.route_fetchval("status = 'pending'", 1)
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/scheduling-request",
                json={"assignee_contact_id": MATE_CONTACT_ID},
            )
        assert r.status_code == 409

    def test_happy_path_notifies_and_emails(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._base_conn()
        sent: list[dict] = []
        with _patch_db(conn), _patch_email(sent):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/scheduling-request",
                json={"assignee_contact_id": MATE_CONTACT_ID, "note": "You know this crew best."},
            )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "pending"
        assert body["assignee_name"] == "Marcus Lee"
        assert body["requested_by_me"] is True

        # In-app notification to the assignee with the deep link.
        notes = conn.notifications()
        assert len(notes) == 1
        assert "scheduling_requested" in notes[0]
        assert f"/employer/applications/{APPLICATION_ID}" in notes[0]

        # Real email with the deep link.
        assert len(sent) == 1
        assert sent[0]["to"] == "mate@acme.test"
        assert "Jordan Reyes" in sent[0]["subject"]
        assert f"/employer/applications/{APPLICATION_ID}" in sent[0]["text"]

        assert "scheduling_request_created" in " ".join(str(a) for _, a in conn.executed)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

class TestCancel:
    def _conn(self, *, me_role: str = "owner", me_contact: str = OWNER_CONTACT_ID, **req_over) -> RoutedConn:
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.employer_contacts WHERE user_id", _me_row(me_contact, me_role))
        conn.route_fetchrow("FROM public.scheduling_requests sr", _request_row(**req_over))
        conn.route_fetchval("SELECT user_id FROM public.employer_contacts WHERE id", UUID(MATE_USER_ID))
        return conn

    def test_originator_cancels_and_assignee_notified(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._conn()
        with _patch_db(conn):
            r = client.post(f"/employer/me/scheduling-requests/{REQUEST_ID}/cancel")
        assert r.status_code == 204
        assert "SET status = 'cancelled'" in conn.executed_sql()
        notes = conn.notifications()
        assert len(notes) == 1 and "scheduling_cancelled" in notes[0]

    def test_other_member_cannot_cancel(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _mate
        # The mate is a plain member and NOT the originator.
        conn = self._conn(me_role="member", me_contact=MATE_CONTACT_ID)
        with _patch_db(conn):
            r = client.post(f"/employer/me/scheduling-requests/{REQUEST_ID}/cancel")
        assert r.status_code == 403

    def test_non_pending_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _owner
        conn = self._conn(status="fulfilled")
        with _patch_db(conn):
            r = client.post(f"/employer/me/scheduling-requests/{REQUEST_ID}/cancel")
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# Fulfilment through the propose endpoint
# ---------------------------------------------------------------------------

class TestFulfilment:
    def _propose_conn(self) -> RoutedConn:
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.applications a",
            {"id": UUID(APPLICATION_ID), "employer_id": UUID(EMPLOYER_ID),
             "applicant_id": UUID("11111111-0000-0000-0000-111111111111"),
             "job_id": UUID("33333333-0000-0000-0000-333333333333"),
             "title_raw": "Welder", "applicant_user_id": UUID("aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"),
             "applicant_name": "Jordan Reyes"},
        )
        conn.route_fetchrow(
            "SELECT id, requested_by, assignee_contact_id FROM public.scheduling_requests",
            {"id": UUID(REQUEST_ID), "requested_by": UUID(OWNER_USER_ID),
             "assignee_contact_id": UUID(MATE_CONTACT_ID)},
        )
        conn.route_fetch(
            "FROM public.interview_slots s WHERE s.application_id",
            [],
        )
        return conn

    def _slots(self) -> list[dict]:
        start = _now() + timedelta(days=2)
        return [{"start_at": start.isoformat(), "end_at": (start + timedelta(minutes=30)).isoformat()}]

    def test_assignee_proposal_fulfills_and_notifies_originator(self, client: TestClient) -> None:
        from app.auth.dependencies import require_employer_only as dep
        app.dependency_overrides[dep] = _mate
        conn = self._propose_conn()
        # Ownership check + "Me" interviewer default + fulfilment contact
        # lookup all hit employer_contacts for the mate.
        conn.route_fetchrow(
            "FROM public.employer_contacts WHERE user_id",
            {"1": 1, "id": UUID(MATE_CONTACT_ID), "title": "Supervisor"},
        )
        conn.route_fetchval(
            "SELECT id FROM public.employer_contacts WHERE user_id",
            UUID(MATE_CONTACT_ID),
        )
        conn.route_fetchval("FROM auth.users WHERE id", "Marcus Lee")
        with _patch_db(conn, module="interviews"):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={"slots": self._slots()},
            )
        assert r.status_code == 200
        sql = conn.executed_sql()
        assert "SET status = 'fulfilled'" in sql
        joined = " ".join(str(a) for _, a in conn.executed)
        assert "scheduling_fulfilled" in joined            # originator notified
        assert "scheduling_request_fulfilled" in joined    # audited

    def test_other_proposer_supersedes_and_notifies_assignee(self, client: TestClient) -> None:
        from app.auth.dependencies import require_employer_only as dep
        app.dependency_overrides[dep] = _owner
        conn = self._propose_conn()
        conn.route_fetchrow(
            "FROM public.employer_contacts WHERE user_id",
            {"1": 1, "id": UUID(OWNER_CONTACT_ID), "title": None},
        )
        conn.route_fetchval(
            "SELECT id FROM public.employer_contacts WHERE user_id",
            UUID(OWNER_CONTACT_ID),
        )
        conn.route_fetchval("SELECT user_id FROM public.employer_contacts WHERE id", UUID(MATE_USER_ID))
        conn.route_fetchval("FROM auth.users WHERE id", "Casey Owner")
        with _patch_db(conn, module="interviews"):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={"slots": self._slots()},
            )
        assert r.status_code == 200
        sql = conn.executed_sql()
        assert "cancelled_reason = 'superseded_by_direct_proposal'" in sql
        joined = " ".join(str(a) for _, a in conn.executed)
        assert "scheduling_cancelled" in joined             # assignee released
        assert "scheduling_request_superseded" in joined    # audited
