"""
test_interviews.py — interview slot scheduling (the Calendly-style picker).

Covers:
  Propose (employer)
    - past start_at rejected at the schema edge (422)
    - more than 5 slots rejected (422)
    - happy path: prior proposed slots superseded (cancelled), fresh inserts,
      application moved to interviewing, applicant notified once
  Slot history (employer/admin)
    - admin may read without an employer_contacts link
    - a non-owner employer gets 404
  Accept (applicant)
    - accepting one slot auto-declines proposed siblings + notifies employer
  Decline (applicant)
    - declining the LAST proposed slot notifies the employer, carrying the
      optional reason
    - declining one of several stays quiet (no notification)

Mock-DB style (same approach as test_internal_apply.py): patch get_db in the
interviews router module, override the auth dependency, then assert on the SQL
the endpoint executed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    require_applicant,
    require_employer_only,
    require_employer_or_admin,
)
from app.auth.schemas import CurrentUser
from app.main import app

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
ADMIN_USER_ID = "cccccccc-0000-0000-0000-cccccccccccc"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
APPLICATION_ID = "44444444-0000-0000-0000-444444444444"
SLOT_ID = "66666666-0000-0000-0000-666666666666"


def _employer_user() -> CurrentUser:
    return CurrentUser(user_id=EMPLOYER_USER_ID, email="employer@test.local", role="employer", onboarding_complete=True)


def _admin_user() -> CurrentUser:
    return CurrentUser(user_id=ADMIN_USER_ID, email="admin@test.local", role="admin", onboarding_complete=True)


def _applicant_user() -> CurrentUser:
    return CurrentUser(user_id=APPLICANT_USER_ID, email="applicant@test.local", role="applicant", onboarding_complete=True)


class RoutedConn:
    """Async-ish conn whose fetch* calls dispatch on SQL substrings."""

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

    def notification_inserts(self) -> list[tuple[str, tuple]]:
        return [(s, a) for s, a in self.executed if "INSERT INTO public.notifications" in s]


def _patch_db(conn: RoutedConn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.interviews.get_db", return_value=ctx)


def _future(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _slot(start: datetime, minutes: int = 30) -> dict:
    return {"start_at": start.isoformat(), "end_at": (start + timedelta(minutes=minutes)).isoformat()}


def _slot_db_row(status: str = "proposed") -> dict:
    start = _future()
    return {
        "id": UUID(SLOT_ID), "application_id": UUID(APPLICATION_ID),
        "start_at": start, "end_at": start + timedelta(minutes=30),
        "status": status, "location": None, "meeting_url": None, "notes": None,
        "job_title": None, "employer_name": None, "applicant_name": None,
    }


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------

class TestPropose:
    def _app_row(self) -> dict:
        return {
            "id": UUID(APPLICATION_ID), "employer_id": UUID(EMPLOYER_ID),
            "applicant_id": UUID("11111111-0000-0000-0000-111111111111"),
            "job_id": UUID("33333333-0000-0000-0000-333333333333"),
            "title_raw": "Welder", "applicant_user_id": UUID(APPLICANT_USER_ID),
        }

    def test_past_slot_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        r = client.post(
            f"/employer/me/applications/{APPLICATION_ID}/propose",
            json={"slots": [_slot(past)]},
        )
        assert r.status_code == 422
        assert "past" in r.text

    def test_more_than_five_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        slots = [_slot(_future(24 + i)) for i in range(6)]
        r = client.post(
            f"/employer/me/applications/{APPLICATION_ID}/propose",
            json={"slots": slots},
        )
        assert r.status_code == 422

    def test_happy_path_supersedes_and_notifies(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications a", self._app_row())
        # One substring route serves BOTH contact queries in the propose flow:
        # the ownership check (SELECT 1 → truthy) and the default-"Me"
        # interviewer lookup (SELECT id, title) — carry keys for both.
        conn.route_fetchrow(
            "FROM public.employer_contacts WHERE user_id",
            {"?column?": 1, "id": "cccccccc-0000-0000-0000-000000000001", "title": "Recruiter"},
        )
        conn.route_fetch("FROM public.interview_slots", [])
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={"slots": [_slot(_future(24)), _slot(_future(30)), _slot(_future(48))]},
            )
        assert r.status_code == 200, r.text
        sql = conn.executed_sql()
        # Prior proposed slots superseded, fresh inserts, status forward.
        assert "SET status = 'cancelled'" in sql
        inserts = [s for s, _ in conn.executed if "INSERT INTO public.interview_slots" in s]
        assert len(inserts) == 3
        assert "'interviewing'::application_status_enum" in sql
        # Applicant notified exactly once.
        notes = conn.notification_inserts()
        assert len(notes) == 1
        assert "interview_proposed" in str(notes[0][1])

    def test_admin_cannot_propose(self, client: TestClient) -> None:
        # require_employer_only guards the route; simulate its rejection by NOT
        # overriding it — the real dependency 401s without a valid employer JWT.
        r = client.post(
            f"/employer/me/applications/{APPLICATION_ID}/propose",
            json={"slots": [_slot(_future())]},
        )
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Interviewer assignment ("Who's running this interview?")
# ---------------------------------------------------------------------------

CONTACT_ID = "77777777-0000-0000-0000-777777777777"


class TestInterviewer:
    def _conn(self) -> RoutedConn:
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.applications a",
            {
                "id": UUID(APPLICATION_ID), "employer_id": UUID(EMPLOYER_ID),
                "applicant_id": UUID("11111111-0000-0000-0000-111111111111"),
                "job_id": UUID("33333333-0000-0000-0000-333333333333"),
                "title_raw": "Welder", "applicant_user_id": UUID(APPLICANT_USER_ID),
            },
        )
        conn.route_fetchrow("SELECT 1 FROM public.employer_contacts", {"?column?": 1})
        conn.route_fetch("FROM public.interview_slots", [])
        return conn

    def test_default_me_resolves_proposer_contact(self, client: TestClient) -> None:
        """No interviewer sent → the proposing contact is stored as the assignee."""
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        conn.route_fetchrow(
            "SELECT id, title FROM public.employer_contacts",
            {"id": UUID(CONTACT_ID), "title": "Hiring Manager"},
        )
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={"slots": [_slot(_future(24))]},
            )
        assert r.status_code == 200, r.text
        inserts = [(s, a) for s, a in conn.executed if "INSERT INTO public.interview_slots" in s]
        assert len(inserts) == 1
        sql, args = inserts[0]
        assert "interviewer_contact_id" in sql
        assert UUID(CONTACT_ID) in args              # my own contact id
        assert "employer@test.local" in args         # my email
        assert "Hiring Manager" in args              # my contact title

    def test_teammate_assignment_round_trips(self, client: TestClient) -> None:
        """contact_id → validated against my employer; email/title backfilled;
        the applicant's proposal notification names the interviewer."""
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        conn.route_fetchrow(
            "JOIN auth.users u",
            {"id": UUID(CONTACT_ID), "title": "Production Supervisor", "email": "marcus@southwire.example"},
        )
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={
                    "slots": [_slot(_future(24))],
                    "interviewer": {"contact_id": CONTACT_ID, "name": "Marcus Lee"},
                },
            )
        assert r.status_code == 200, r.text
        _, args = next((s, a) for s, a in conn.executed if "INSERT INTO public.interview_slots" in s)
        assert UUID(CONTACT_ID) in args
        assert "Marcus Lee" in args
        assert "marcus@southwire.example" in args
        assert "Production Supervisor" in args
        notes = conn.notification_inserts()
        assert len(notes) == 1
        assert "You'll meet Marcus Lee, Production Supervisor." in str(notes[0][1])

    def test_foreign_contact_rejected(self, client: TestClient) -> None:
        """A contact_id outside my employer is a 400, never silently stored."""
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()  # no auth.users route → teammate lookup returns None
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={
                    "slots": [_slot(_future(24))],
                    "interviewer": {"contact_id": CONTACT_ID},
                },
            )
        assert r.status_code == 400
        assert "team" in r.text

    def test_freeform_interviewer_round_trips(self, client: TestClient) -> None:
        """Name + email for someone not in the system: stored as-is, no contact id."""
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/applications/{APPLICATION_ID}/propose",
                json={
                    "slots": [_slot(_future(24))],
                    "interviewer": {"name": "Dana Ortiz", "email": "dana@example.com", "title": "Shift Lead"},
                },
            )
        assert r.status_code == 200, r.text
        _, args = next((s, a) for s, a in conn.executed if "INSERT INTO public.interview_slots" in s)
        assert "Dana Ortiz" in args and "dana@example.com" in args and "Shift Lead" in args
        assert UUID(CONTACT_ID) not in args

    def test_interviewer_served_to_applicant(self, client: TestClient) -> None:
        """GET /applicant/me/interviews carries the interviewer fields."""
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = RoutedConn()
        row = _slot_db_row("proposed")
        row.update({
            "interviewer_contact_id": UUID(CONTACT_ID),
            "interviewer_name": "Marcus Lee",
            "interviewer_email": "marcus@southwire.example",
            "interviewer_title": "Production Supervisor",
            "job_title": "Welder", "employer_name": "Southwire",
        })
        conn.route_fetch("FROM public.interview_slots", [row])
        with _patch_db(conn):
            r = client.get("/applicant/me/interviews")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body[0]["interviewer_name"] == "Marcus Lee"
        assert body[0]["interviewer_title"] == "Production Supervisor"
        assert body[0]["interviewer_email"] == "marcus@southwire.example"


# ---------------------------------------------------------------------------
# Team listing
# ---------------------------------------------------------------------------

class TestTeam:
    def test_lists_my_employer_contacts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        conn = RoutedConn()
        conn.route_fetchrow("SELECT employer_id FROM public.employer_contacts", {"employer_id": UUID(EMPLOYER_ID)})
        conn.route_fetch(
            "JOIN auth.users u",
            [
                {"contact_id": UUID(CONTACT_ID), "title": "Hiring Manager", "is_primary": True,
                 "email": "employer@test.local", "is_me": True},
                {"contact_id": UUID("88888888-0000-0000-0000-888888888888"), "title": "Production Supervisor",
                 "is_primary": False, "email": "marcus@southwire.example", "is_me": False},
            ],
        )
        with _patch_db(conn):
            r = client.get("/employer/me/team")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 2
        assert body[0]["is_me"] is True
        assert body[1]["email"] == "marcus@southwire.example"

    def test_admin_gets_empty_team(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_or_admin] = _admin_user
        conn = RoutedConn()  # no employer_contacts row for admin
        with _patch_db(conn):
            r = client.get("/employer/me/team")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# Slot history (employer/admin)
# ---------------------------------------------------------------------------

class TestSlotHistory:
    def test_admin_can_read_without_ownership(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_or_admin] = _admin_user
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications WHERE id", {"employer_id": UUID(EMPLOYER_ID)})
        conn.route_fetch("FROM public.interview_slots", [_slot_db_row("accepted")])
        with _patch_db(conn):
            r = client.get(f"/employer/me/applications/{APPLICATION_ID}/slots")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1 and body[0]["status"] == "accepted"

    def test_non_owner_employer_404(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.applications WHERE id", {"employer_id": UUID(EMPLOYER_ID)})
        # employer_contacts ownership lookup returns nothing → 404
        with _patch_db(conn):
            r = client.get(f"/employer/me/applications/{APPLICATION_ID}/slots")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------

class TestAccept:
    def test_accept_declines_siblings_and_notifies(self, client: TestClient) -> None:
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = RoutedConn()
        start = _future()
        conn.route_fetchrow(
            "LEFT JOIN public.employer_contacts ec",
            {
                "id": UUID(SLOT_ID), "application_id": UUID(APPLICATION_ID),
                "status": "proposed", "start_at": start, "end_at": start + timedelta(minutes=30),
                "location": "Plant 4", "meeting_url": None, "notes": None,
                "interviewer_name": "Marcus Lee", "interviewer_title": "Production Supervisor",
                "employer_id": UUID(EMPLOYER_ID),
                "job_id": UUID("33333333-0000-0000-0000-333333333333"),
                "applicant_user_id": UUID(APPLICANT_USER_ID),
                "applicant_name": "Jordan Reyes", "job_title": "Welder",
                "employer_name": "Southwire",
                "employer_contact_user": UUID(EMPLOYER_USER_ID),
            },
        )
        conn.route_fetchrow("FROM public.applicants a JOIN", {"user_id": UUID(APPLICANT_USER_ID)})
        conn.route_fetchrow("FROM public.interview_slots s WHERE s.id", _slot_db_row("accepted"))
        with _patch_db(conn):
            r = client.post(f"/applicant/me/interviews/{SLOT_ID}/accept")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"
        sql = conn.executed_sql()
        assert "SET status = 'accepted'" in sql
        assert "SET status = 'declined'" in sql  # siblings auto-declined
        # Confirmation lands on BOTH sides: employer + applicant.
        notes = conn.notification_inserts()
        assert len(notes) == 2
        emp_args = str(notes[0][1])
        assert "interview_accepted" in emp_args
        # Content template: who confirmed + which job in the title.
        assert "Jordan Reyes confirmed" in emp_args
        assert "Welder" in emp_args
        # The assigned interviewer is surfaced to the employer too.
        assert "Marcus Lee" in emp_args
        app_args = str(notes[1][1])
        assert "Interview booked" in app_args
        assert str(APPLICANT_USER_ID) in app_args
        # The applicant is told who they'll meet.
        assert "Marcus Lee, Production Supervisor" in app_args
        # Calendar deep links ride in the payloads (google + both outlook hosts).
        assert "calendar.google.com" in app_args
        assert "outlook.live.com" in app_args
        assert "outlook.office.com" in app_args

    def test_accept_non_proposed_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = RoutedConn()
        conn.route_fetchrow(
            "LEFT JOIN public.employer_contacts ec",
            {
                "id": UUID(SLOT_ID), "application_id": UUID(APPLICATION_ID),
                "status": "declined", "start_at": _future(),
                "employer_id": UUID(EMPLOYER_ID),
                "job_id": UUID("33333333-0000-0000-0000-333333333333"),
                "applicant_user_id": UUID(APPLICANT_USER_ID),
                "applicant_name": "Jordan Reyes", "job_title": "Welder",
                "employer_contact_user": UUID(EMPLOYER_USER_ID),
            },
        )
        conn.route_fetchrow("FROM public.applicants a JOIN", {"user_id": UUID(APPLICANT_USER_ID)})
        with _patch_db(conn):
            r = client.post(f"/applicant/me/interviews/{SLOT_ID}/accept")
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# Decline
# ---------------------------------------------------------------------------

def _decline_conn(remaining_after: int) -> RoutedConn:
    conn = RoutedConn()
    conn.route_fetchrow(
        "FROM public.applicants ap JOIN",
        {"user_id": UUID(APPLICANT_USER_ID), "status": "proposed", "application_id": UUID(APPLICATION_ID)},
    )
    conn.route_fetchval("COUNT(*)", remaining_after)
    conn.route_fetchrow(
        "LEFT JOIN public.employer_contacts ec",
        {"user_id": UUID(EMPLOYER_USER_ID), "job_title": "Welder", "applicant_name": "Jordan Reyes"},
    )
    conn.route_fetchrow("FROM public.interview_slots s WHERE s.id", _slot_db_row("declined"))
    return conn


class TestDecline:
    def test_last_decline_notifies_with_reason(self, client: TestClient) -> None:
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = _decline_conn(remaining_after=0)
        with _patch_db(conn):
            r = client.post(
                f"/applicant/me/interviews/{SLOT_ID}/decline",
                json={"reason": "Mornings are out — I'm in class."},
            )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "declined"
        notes = conn.notification_inserts()
        assert len(notes) == 1
        args_str = str(notes[0][1])
        assert "interview_declined" in args_str
        assert "Mornings are out" in args_str

    def test_partial_decline_stays_quiet(self, client: TestClient) -> None:
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = _decline_conn(remaining_after=2)
        with _patch_db(conn):
            r = client.post(f"/applicant/me/interviews/{SLOT_ID}/decline")
        assert r.status_code == 200, r.text
        assert conn.notification_inserts() == []

    def test_decline_without_body_still_works(self, client: TestClient) -> None:
        # Backward compatibility: the pre-existing client sent no JSON body.
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = _decline_conn(remaining_after=1)
        with _patch_db(conn):
            r = client.post(f"/applicant/me/interviews/{SLOT_ID}/decline")
        assert r.status_code == 200, r.text

    def test_foreign_slot_404(self, client: TestClient) -> None:
        app.dependency_overrides[require_applicant] = _applicant_user
        conn = RoutedConn()
        conn.route_fetchrow(
            "FROM public.applicants ap JOIN",
            {"user_id": UUID("dddddddd-0000-0000-0000-dddddddddddd"), "status": "proposed", "application_id": UUID(APPLICATION_ID)},
        )
        with _patch_db(conn):
            r = client.post(f"/applicant/me/interviews/{SLOT_ID}/decline")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Cancel (employer) — a booked interview must never wedge the application
# ---------------------------------------------------------------------------

def _cancel_conn(
    slot_status: str = "accepted",
    *,
    owns: bool = True,
    remaining_open: int = 0,
    app_status: str = "interviewing",
    previous_status: str | None = "shortlisted",
) -> RoutedConn:
    conn = RoutedConn()
    start = _future()
    conn.route_fetchrow(
        "JOIN public.applications a",
        {
            "id": UUID(SLOT_ID), "status": slot_status,
            "start_at": start, "end_at": start + timedelta(minutes=30),
            "application_id": UUID(APPLICATION_ID),
            "employer_id": UUID(EMPLOYER_ID),
            "applicant_user_id": UUID(APPLICANT_USER_ID),
            "job_title": "Welder",
        },
    )
    if owns:
        conn.route_fetchrow("SELECT 1 FROM public.employer_contacts", {"?column?": 1})
    conn.route_fetchval("COUNT(*)", remaining_open)
    conn.route_fetchrow(
        "previous_status::text AS previous_status",
        {"status": app_status, "previous_status": previous_status},
    )
    conn.route_fetchrow("NULL::text AS job_title", _slot_db_row("cancelled"))
    return conn


def _restore_update(conn: RoutedConn) -> tuple[str, tuple] | None:
    for sql, args in conn.executed:
        if "UPDATE public.applications" in sql and "previous_status = NULL" in sql:
            return sql, args
    return None


class TestCancel:
    def test_cancel_accepted_restores_stage_and_notifies(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn("accepted", previous_status="shortlisted")
        with _patch_db(conn):
            r = client.post(
                f"/employer/me/interviews/{SLOT_ID}/cancel",
                json={"reason": "The interviewer is out that week."},
            )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
        sql = conn.executed_sql()
        assert "SET status = 'cancelled', cancelled_at = NOW()" in sql
        # The application returns to its stored pre-interview stage.
        _, args = _restore_update(conn)
        assert args[1] == "shortlisted"
        # The applicant is told honestly, with the reason carried along.
        notes = conn.notification_inserts()
        assert len(notes) == 1
        args_str = str(notes[0][1])
        assert "interview_cancelled" in args_str
        assert "interview for Welder was cancelled" in args_str
        assert "The interviewer is out that week." in args_str
        assert str(APPLICANT_USER_ID) in args_str
        # Audited.
        assert any("INSERT INTO public.audit_logs" in s and "interview_slot_cancelled" in str(a)
                   for s, a in conn.executed)

    def test_cancel_without_history_falls_back_to_reviewed(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn("accepted", previous_status=None)
        with _patch_db(conn):
            r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code == 200, r.text
        _, args = _restore_update(conn)
        assert args[1] == "reviewed"

    def test_cancel_proposed_with_siblings_leaves_application_alone(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn("proposed", remaining_open=2)
        with _patch_db(conn):
            r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code == 200, r.text
        assert _restore_update(conn) is None
        notes = conn.notification_inserts()
        assert len(notes) == 1
        assert "proposed interview time for Welder was withdrawn" in str(notes[0][1])

    def test_cancel_does_not_touch_application_already_moved_on(self, client: TestClient) -> None:
        # Application already rejected/hired etc. — the slot flips, the stage stays.
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn("accepted", app_status="rejected")
        with _patch_db(conn):
            r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code == 200, r.text
        assert _restore_update(conn) is None

    @pytest.mark.parametrize("status", ["declined", "cancelled", "completed"])
    def test_cancel_terminal_slot_409(self, client: TestClient, status: str) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn(status)
        with _patch_db(conn):
            r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code == 409
        assert conn.notification_inserts() == []

    def test_cancel_non_owner_404(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = _cancel_conn("accepted", owns=False)
        with _patch_db(conn):
            r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code == 404

    def test_admin_cannot_cancel(self, client: TestClient) -> None:
        # require_employer_only guards the route — no override, no access.
        r = client.post(f"/employer/me/interviews/{SLOT_ID}/cancel")
        assert r.status_code in (401, 403)
