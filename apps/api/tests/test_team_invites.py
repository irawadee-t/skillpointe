"""
test_team_invites.py — employer team page + email invite lifecycle.

Covers:
  Overview
    - members + pending invites + my org role; member cannot manage
  Invite create
    - org-role gating: member gets 403, owner succeeds
    - token security: the DB never sees the raw token — only its SHA-256
      digest — and the emailed join link carries the raw token that hashes
      to exactly that digest; expiry rides in the INSERT (7 days)
    - duplicate active invite → 409; already-on-team → 409
    - invalid role → 422
  Resend / revoke
    - resend ROTATES the token hash (old link dies) and re-emails
    - revoke flips revoked_at; revoking twice → 404
  Public join surface
    - status honesty: valid / expired / revoked / used
    - accept on an expired invite → 410
    - accept creates the auth user (mocked Supabase admin), the
      user_profiles + employer_contacts rows with the INVITED role, marks
      the invite used, and notifies the inviter
    - accept-session: email mismatch → 403; wrong app role → 409

Mock-DB style (same approach as test_interviews.py): patch get_db in the
team router module, override auth dependencies, assert on the SQL executed.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_employer_only
from app.auth.schemas import CurrentUser
from app.main import app
from app.skilled_pro.senders import SendResult

EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
CONTACT_ID = "55555555-0000-0000-0000-555555555555"
INVITE_ID = "77777777-0000-0000-0000-777777777777"
INVITED_USER_ID = "88888888-0000-0000-0000-888888888888"


def _employer_user() -> CurrentUser:
    return CurrentUser(user_id=EMPLOYER_USER_ID, email="owner@acme.test", role="employer", onboarding_complete=True)


class RecordingConn:
    """Async-ish conn: fetch* dispatch on SQL substrings AND record args."""

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


def _patch_db(conn: RecordingConn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.team.get_db", return_value=ctx)


def _patch_email(captured: list):
    async def _fake_send(to, subject, text, html=None):
        captured.append({"to": to, "subject": subject, "text": text, "html": html})
        return SendResult(ok=True)
    return patch("app.routers.team.send_email", side_effect=_fake_send)


def _me_row(role: str = "owner") -> dict:
    return {
        "id": UUID(CONTACT_ID),
        "employer_id": UUID(EMPLOYER_ID),
        "role": role,
        "company_name": "Acme Industrial",
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invite_row(**over) -> dict:
    row = {
        "id": UUID(INVITE_ID),
        "employer_id": UUID(EMPLOYER_ID),
        "email": "new.hire@example.com",
        "role": "member",
        "title": "Recruiter",
        "expires_at": _now() + timedelta(days=5),
        "accepted_at": None,
        "revoked_at": None,
        "invited_by": UUID(EMPLOYER_USER_ID),
        "company_name": "Acme Industrial",
        "inviter_email": "owner@acme.test",
        "inviter_name": "Casey Owner",
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
# Overview
# ---------------------------------------------------------------------------

class TestOverview:
    def test_members_invites_and_role(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row("member"))
        conn.route_fetch(
            "FROM public.employer_contacts ec",
            [
                {
                    "contact_id": UUID(CONTACT_ID), "title": "HR Lead", "role": "member",
                    "is_primary": False, "created_at": _now(), "email": "owner@acme.test",
                    "name": "Casey Owner", "is_me": True,
                }
            ],
        )
        conn.route_fetch(
            "FROM public.employer_invites i",
            [
                {
                    "id": UUID(INVITE_ID), "email": "new.hire@example.com", "role": "admin",
                    "title": None, "last_sent_at": _now(), "expires_at": _now() + timedelta(days=7),
                    "expired": False, "invited_by_email": "owner@acme.test",
                }
            ],
        )
        with _patch_db(conn):
            r = client.get("/employer/me/team/overview")
        assert r.status_code == 200
        body = r.json()
        assert body["company_name"] == "Acme Industrial"
        assert body["my_role"] == "member"
        assert body["can_manage"] is False          # members are read-only
        assert body["members"][0]["is_me"] is True
        assert body["invites"][0]["email"] == "new.hire@example.com"


# ---------------------------------------------------------------------------
# Invite create
# ---------------------------------------------------------------------------

class TestInviteCreate:
    def _conn(self, role: str = "owner") -> RecordingConn:
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row(role))
        conn.route_fetchval("FROM auth.users WHERE id", "Casey Owner")
        conn.route_fetchrow(
            "INSERT INTO public.employer_invites",
            {
                "id": UUID(INVITE_ID), "email": "new.hire@example.com", "role": "member",
                "title": None, "last_sent_at": _now(), "expires_at": _now() + timedelta(days=7),
            },
        )
        return conn

    def test_member_cannot_invite(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn(role="member")
        with _patch_db(conn):
            r = client.post("/employer/me/team/invites", json={"email": "new.hire@example.com", "role": "member"})
        assert r.status_code == 403
        assert "owners and admins" in r.json()["detail"].lower()

    def test_invalid_role_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        r = client.post("/employer/me/team/invites", json={"email": "x@acme.test", "role": "superuser"})
        assert r.status_code == 422

    def test_owner_invites_token_hashed_and_emailed(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        sent: list[dict] = []
        with _patch_db(conn), _patch_email(sent):
            r = client.post(
                "/employer/me/team/invites",
                json={"email": "New.Hire@example.com", "role": "member", "title": "Recruiter"},
            )
        assert r.status_code == 201
        body = r.json()
        assert body["email_sent"] is True

        # Exactly one email, to the invitee, subject carries the company.
        assert len(sent) == 1
        assert sent[0]["to"] == "new.hire@example.com"
        assert sent[0]["subject"] == "Join Acme Industrial on SKILLED Nation"
        assert "Casey Owner" in sent[0]["html"]

        # Token security: raw token appears ONLY in the email link; the DB
        # insert got its SHA-256 digest.
        m = re.search(r"/join/([A-Za-z0-9_-]{20,})", sent[0]["text"])
        assert m, "join link missing from plaintext part"
        raw_token = m.group(1)
        insert_calls = [c for c in conn.fetchrow_calls if "INSERT INTO public.employer_invites" in c[0]]
        assert len(insert_calls) == 1
        stored_hash = insert_calls[0][1][4]
        assert stored_hash == hashlib.sha256(raw_token.encode()).hexdigest()
        assert raw_token not in str(insert_calls[0][1])
        # 7-day expiry parameter
        assert 7 in insert_calls[0][1]

        # Audited
        assert "team_invite_sent" in " ".join(str(a) for _, a in conn.executed)

    def test_duplicate_active_invite_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        conn.route_fetchrow("accepted_at IS NULL AND revoked_at IS NULL", {"id": UUID(INVITE_ID)})
        with _patch_db(conn):
            r = client.post("/employer/me/team/invites", json={"email": "new.hire@example.com", "role": "member"})
        assert r.status_code == 409
        assert "pending invite" in r.json()["detail"]

    def test_already_member_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = self._conn()
        conn.route_fetchrow("lower(u.email)", {"?column?": 1})
        with _patch_db(conn):
            r = client.post("/employer/me/team/invites", json={"email": "new.hire@example.com", "role": "member"})
        assert r.status_code == 409
        assert "already on your team" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Resend / revoke
# ---------------------------------------------------------------------------

class TestResendRevoke:
    def test_resend_rotates_token(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row())
        conn.route_fetchrow(
            "SELECT id, email, role, title, accepted_at, revoked_at",
            {"id": UUID(INVITE_ID), "email": "new.hire@example.com", "role": "member",
             "title": None, "accepted_at": None, "revoked_at": None},
        )
        conn.route_fetchrow(
            "UPDATE public.employer_invites",
            {"id": UUID(INVITE_ID), "email": "new.hire@example.com", "role": "member",
             "title": None, "last_sent_at": _now(), "expires_at": _now() + timedelta(days=7)},
        )
        conn.route_fetchval("FROM auth.users WHERE id", "Casey Owner")
        sent: list[dict] = []
        with _patch_db(conn), _patch_email(sent):
            r = client.post(f"/employer/me/team/invites/{INVITE_ID}/resend")
        assert r.status_code == 200
        assert len(sent) == 1
        # The rotate wrote a fresh hash and the new emailed token matches it.
        update_calls = [c for c in conn.fetchrow_calls if "UPDATE public.employer_invites" in c[0]]
        assert update_calls and "token_hash = $2" in update_calls[0][0]
        new_hash = update_calls[0][1][1]
        m = re.search(r"/join/([A-Za-z0-9_-]{20,})", sent[0]["text"])
        assert m and hashlib.sha256(m.group(1).encode()).hexdigest() == new_hash

    def test_resend_accepted_conflicts(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row())
        conn.route_fetchrow(
            "SELECT id, email, role, title, accepted_at, revoked_at",
            {"id": UUID(INVITE_ID), "email": "x@acme.test", "role": "member",
             "title": None, "accepted_at": _now(), "revoked_at": None},
        )
        with _patch_db(conn):
            r = client.post(f"/employer/me/team/invites/{INVITE_ID}/resend")
        assert r.status_code == 409

    def test_revoke(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row())
        with _patch_db(conn):
            r = client.post(f"/employer/me/team/invites/{INVITE_ID}/revoke")
        assert r.status_code == 204
        assert "SET revoked_at = NOW()" in conn.executed_sql()
        assert "team_invite_revoked" in " ".join(str(a) for _, a in conn.executed)

    def test_revoke_member_forbidden(self, client: TestClient) -> None:
        app.dependency_overrides[require_employer_only] = _employer_user
        conn = RecordingConn()
        conn.route_fetchrow("JOIN public.employers e", _me_row("member"))
        with _patch_db(conn):
            r = client.post(f"/employer/me/team/invites/{INVITE_ID}/revoke")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Public join surface
# ---------------------------------------------------------------------------

class TestJoin:
    def _conn_with_invite(self, **over) -> RecordingConn:
        conn = RecordingConn()
        conn.route_fetchrow("FROM public.employer_invites i", _invite_row(**over))
        conn.route_fetchval("SELECT NOW()", _now())
        return conn

    def test_info_valid(self, client: TestClient) -> None:
        conn = self._conn_with_invite()
        with _patch_db(conn):
            r = client.get("/auth/join/some-token")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "valid"
        assert body["company_name"] == "Acme Industrial"
        assert body["inviter_name"] == "Casey Owner"
        assert body["invited_email"] == "new.hire@example.com"
        assert body["account_exists"] is False

    def test_info_unknown_token_404(self, client: TestClient) -> None:
        conn = RecordingConn()
        conn.route_fetchval("SELECT NOW()", _now())
        with _patch_db(conn):
            r = client.get("/auth/join/not-a-real-token")
        assert r.status_code == 404

    @pytest.mark.parametrize(
        "over,expected",
        [
            ({"expires_at": _now() - timedelta(hours=1)}, "expired"),
            ({"revoked_at": _now()}, "revoked"),
            ({"accepted_at": _now()}, "used"),
        ],
    )
    def test_info_dead_states(self, client: TestClient, over: dict, expected: str) -> None:
        conn = self._conn_with_invite(**over)
        with _patch_db(conn):
            r = client.get("/auth/join/some-token")
        assert r.status_code == 200
        assert r.json()["status"] == expected

    def test_accept_expired_410(self, client: TestClient) -> None:
        conn = self._conn_with_invite(expires_at=_now() - timedelta(hours=1))
        with _patch_db(conn):
            r = client.post("/auth/join/some-token/accept", json={"full_name": "Pat", "password": "Test1234!"})
        assert r.status_code == 410
        assert "expired" in r.json()["detail"]

    def test_accept_creates_account_with_invited_role(self, client: TestClient) -> None:
        conn = self._conn_with_invite(role="admin")
        admin_client = MagicMock()
        admin_client.auth.admin.create_user.return_value = MagicMock(user=MagicMock(id=INVITED_USER_ID))
        with _patch_db(conn), patch("app.routers.team._get_admin_client", return_value=admin_client):
            r = client.post(
                "/auth/join/some-token/accept",
                json={"full_name": "Pat Member", "password": "Test1234!"},
            )
        assert r.status_code == 200
        assert r.json() == {"email": "new.hire@example.com", "company_name": "Acme Industrial"}

        # Auth user created confirmed, with the employer app role.
        created = admin_client.auth.admin.create_user.call_args[0][0]
        assert created["email"] == "new.hire@example.com"
        assert created["email_confirm"] is True
        assert created["app_metadata"] == {"role": "employer"}
        assert created["user_metadata"] == {"full_name": "Pat Member"}

        sql = conn.executed_sql()
        assert "INSERT INTO public.user_profiles" in sql
        assert "INSERT INTO public.employer_contacts" in sql
        # The contact row carries the INVITED org role.
        contact_args = next(a for s, a in conn.executed if "INSERT INTO public.employer_contacts" in s)
        assert "admin" in contact_args
        assert "SET accepted_at = NOW()" in sql
        # Inviter notified in-app.
        assert any("INSERT INTO public.notifications" in s for s, _ in conn.executed)

    def test_accept_existing_email_conflicts(self, client: TestClient) -> None:
        conn = self._conn_with_invite()
        conn.route_fetchval("FROM auth.users WHERE lower(email)", INVITED_USER_ID)
        with _patch_db(conn):
            r = client.post("/auth/join/some-token/accept", json={"full_name": "Pat", "password": "Test1234!"})
        assert r.status_code == 409
        assert "Sign in" in r.json()["detail"]

    def test_accept_session_email_mismatch_403(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=INVITED_USER_ID, email="someone.else@other.test", role="employer",
            onboarding_complete=True,
        )
        conn = self._conn_with_invite()
        with _patch_db(conn):
            r = client.post("/auth/join/some-token/accept-session")
        assert r.status_code == 403
        assert "new.hire@example.com" in r.json()["detail"]

    def test_accept_session_wrong_role_409(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=INVITED_USER_ID, email="new.hire@example.com", role="applicant",
            onboarding_complete=True,
        )
        conn = self._conn_with_invite()
        with _patch_db(conn):
            r = client.post("/auth/join/some-token/accept-session")
        assert r.status_code == 409
