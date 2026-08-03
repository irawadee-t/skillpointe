"""
test_calendar_feed.py — the per-user ICS subscription feed + feed tokens.

Covers:
  Token crypto (pure, app/skilled_pro/signing.py)
    - make → parse → verify round-trip
    - tampered token / wrong secret / malformed token all fail closed
  GET /calendar/feed.ics (unauthenticated; token IS the credential)
    - malformed token → 401
    - unknown user → 401
    - rotated-away (wrong-secret) token → 401
    - cross-user isolation: a token HMAC'd with another user's secret never
      validates against mine
    - content: one VEVENT per confirmed slot, stable UID, interviewer in
      DESCRIPTION, cancelled-after-accept slots ship STATUS:CANCELLED +
      SEQUENCE:1, and the whole document parses as ICS
  GET /me/calendar/feed + POST /me/calendar/feed/rotate
    - mint returns a verifiable token; rotate changes it
  GET /me/calendar/providers
    - OAuth keys unset locally → both connect buttons stay hidden

Mock-DB style (same approach as test_interviews.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.main import app
from app.skilled_pro.ics import FeedEvent, build_feed_ics
from app.skilled_pro.signing import make_feed_token, parse_feed_token, verify_feed_token

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
SLOT_ID = "66666666-0000-0000-0000-666666666666"
SLOT_ID_2 = "66666666-0000-0000-0000-666666666667"
SECRET = "test-feed-secret"
OTHER_SECRET = "someone-elses-secret"


# ---------------------------------------------------------------------------
# Token crypto
# ---------------------------------------------------------------------------

class TestFeedToken:
    def test_round_trip(self) -> None:
        token = make_feed_token(APPLICANT_USER_ID, SECRET)
        assert parse_feed_token(token) == APPLICANT_USER_ID
        assert verify_feed_token(token, SECRET) is True

    def test_wrong_secret_fails(self) -> None:
        token = make_feed_token(APPLICANT_USER_ID, SECRET)
        assert verify_feed_token(token, OTHER_SECRET) is False

    def test_tampered_uid_fails(self) -> None:
        # Swap in another user id while keeping the original MAC.
        token = make_feed_token(APPLICANT_USER_ID, SECRET)
        mac = token.split(".", 1)[1]
        forged = make_feed_token(OTHER_USER_ID, SECRET).split(".", 1)[0] + "." + mac
        assert parse_feed_token(forged) == OTHER_USER_ID
        assert verify_feed_token(forged, SECRET) is False

    def test_malformed_tokens(self) -> None:
        for bad in ("", "no-dot", ".", "x.", ".y", "!!!.zzz"):
            assert verify_feed_token(bad, SECRET) is False


# ---------------------------------------------------------------------------
# Mock DB plumbing
# ---------------------------------------------------------------------------

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
        return "INSERT 0 1"


def _patch_db(conn: RoutedConn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.calendar_feed.get_db", return_value=ctx)


def _future(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _feed_row(slot_id: str = SLOT_ID, status: str = "accepted", *, hours: int = 48) -> dict:
    start = _future(hours)
    return {
        "id": UUID(slot_id), "start_at": start, "end_at": start + timedelta(minutes=30),
        "status": status, "location": "Plant 4", "meeting_url": "https://meet.example/x",
        "notes": None,
        "interviewer_name": "Marcus Lee", "interviewer_title": "Production Supervisor",
        "accepted_at": datetime.now(timezone.utc),
        "job_title": "Welder", "employer_name": "Southwire",
        "applicant_name": "Jordan Reyes", "viewer_role": "applicant",
    }


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _applicant_user() -> CurrentUser:
    return CurrentUser(user_id=APPLICANT_USER_ID, email="applicant@test.local", role="applicant", onboarding_complete=True)


# ---------------------------------------------------------------------------
# ICS parsing helper — unfold + structural sanity, no external deps
# ---------------------------------------------------------------------------

def parse_ics(text: str) -> list[dict[str, str]]:
    """Unfold per RFC 5545 §3.1 and return one property-dict per VEVENT.
    Asserts the overall document structure is well-formed."""
    assert text.endswith("\r\n")
    raw_lines = text.split("\r\n")
    unfolded: list[str] = []
    for line in raw_lines:
        if line.startswith(" "):
            assert unfolded, "continuation line before any content"
            unfolded[-1] += line[1:]
        elif line:
            unfolded.append(line)
    assert unfolded[0] == "BEGIN:VCALENDAR"
    assert unfolded[-1] == "END:VCALENDAR"
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in unfolded[1:-1]:
        assert ":" in line, f"property without value: {line!r}"
        key, val = line.split(":", 1)
        if line == "BEGIN:VEVENT":
            assert current is None, "nested VEVENT"
            current = {}
        elif line == "END:VEVENT":
            assert current is not None, "END:VEVENT without BEGIN"
            events.append(current)
            current = None
        elif current is not None:
            current[key] = val
    assert current is None, "unterminated VEVENT"
    return events


class TestIcsBuilder:
    def test_empty_feed_is_valid(self) -> None:
        events = parse_ics(build_feed_ics([]))
        assert events == []

    def test_escaping_and_folding(self) -> None:
        ev = FeedEvent(
            uid="u1@x", start_at=_future(), end_at=_future(2),
            summary="Interview; with, commas\nand newlines " + "x" * 200,
        )
        text = build_feed_ics([ev])
        # Every raw line respects the 75-octet fold limit.
        for line in text.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75
        parsed = parse_ics(text)
        assert parsed[0]["SUMMARY"].startswith("Interview\\; with\\, commas\\n")


# ---------------------------------------------------------------------------
# GET /calendar/feed.ics
# ---------------------------------------------------------------------------

class TestFeedEndpoint:
    def _secret_conn(self, *, role: str = "applicant") -> RoutedConn:
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.calendar_feed_secrets", {"secret": SECRET})
        conn.route_fetchval("SELECT role FROM public.user_profiles", role)
        return conn

    def test_malformed_token_401(self, client: TestClient) -> None:
        conn = RoutedConn()
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": "garbage"})
        assert r.status_code == 401

    def test_unknown_user_401(self, client: TestClient) -> None:
        conn = RoutedConn()  # no secret row
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": make_feed_token(APPLICANT_USER_ID, SECRET)})
        assert r.status_code == 401

    def test_rotated_secret_revokes_old_token_401(self, client: TestClient) -> None:
        conn = self._secret_conn()  # DB now holds SECRET…
        old_token = make_feed_token(APPLICANT_USER_ID, "previous-secret")  # …token minted before rotation
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": old_token})
        assert r.status_code == 401

    def test_cross_user_isolation_401(self, client: TestClient) -> None:
        """A token minted with ANOTHER user's secret must not open my feed:
        the uid in the token routes the secret lookup, so the MAC can never
        match unless it was minted with that same user's own secret."""
        conn = self._secret_conn()  # my secret is SECRET
        forged = make_feed_token(APPLICANT_USER_ID, OTHER_SECRET)
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": forged})
        assert r.status_code == 401

    def test_feed_content_confirmed_and_cancelled(self, client: TestClient) -> None:
        conn = self._secret_conn()
        conn.route_fetch(
            "FROM public.interview_slots",
            [_feed_row(SLOT_ID, "accepted"), _feed_row(SLOT_ID_2, "cancelled", hours=72)],
        )
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": make_feed_token(APPLICANT_USER_ID, SECRET)})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/calendar")
        events = parse_ics(r.text)
        assert len(events) == 2

        confirmed = next(e for e in events if e["STATUS"] == "CONFIRMED")
        cancelled = next(e for e in events if e["STATUS"] == "CANCELLED")
        # Stable UID per slot — matches the client-side .ics download UID
        # scheme so subscribed + downloaded copies dedupe.
        assert confirmed["UID"] == f"interview-{SLOT_ID}@skillednation"
        assert cancelled["UID"] == f"interview-{SLOT_ID_2}@skillednation"
        assert confirmed["SEQUENCE"] == "0"
        assert cancelled["SEQUENCE"] == "1"
        assert "Welder" in confirmed["SUMMARY"] and "Southwire" in confirmed["SUMMARY"]
        assert "Marcus Lee (Production Supervisor)" in confirmed["DESCRIPTION"]
        assert confirmed["LOCATION"] == "Plant 4"
        assert "DTSTART" in confirmed and confirmed["DTSTART"].endswith("Z")

    def test_feed_stable_across_calls(self, client: TestClient) -> None:
        conn = self._secret_conn()
        conn.route_fetch("FROM public.interview_slots", [_feed_row()])
        token = make_feed_token(APPLICANT_USER_ID, SECRET)
        with _patch_db(conn):
            a = client.get("/calendar/feed.ics", params={"token": token})
            b = client.get("/calendar/feed.ics", params={"token": token})
        # Same UID both times (only DTSTAMP may differ).
        uid = lambda resp: parse_ics(resp.text)[0]["UID"]  # noqa: E731
        assert uid(a) == uid(b)

    def test_admin_role_gets_empty_calendar(self, client: TestClient) -> None:
        conn = self._secret_conn(role="admin")
        with _patch_db(conn):
            r = client.get("/calendar/feed.ics", params={"token": make_feed_token(APPLICANT_USER_ID, SECRET)})
        assert r.status_code == 200
        assert parse_ics(r.text) == []


# ---------------------------------------------------------------------------
# Mint + rotate + providers
# ---------------------------------------------------------------------------

class TestMintAndRotate:
    def test_mint_returns_verifiable_token(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = _applicant_user
        conn = RoutedConn()
        conn.route_fetchrow("FROM public.calendar_feed_secrets", {"secret": SECRET, "rotated_at": None})
        with _patch_db(conn):
            r = client.get("/me/calendar/feed")
        assert r.status_code == 200, r.text
        body = r.json()
        assert verify_feed_token(body["token"], SECRET)
        assert body["feed_path"] == f"/calendar/feed.ics?token={body['token']}"

    def test_rotate_issues_new_secret(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = _applicant_user
        conn = RoutedConn()
        with _patch_db(conn):
            r = client.post("/me/calendar/feed/rotate")
        assert r.status_code == 200, r.text
        # The upsert carried a fresh secret, and the returned token verifies
        # against THAT secret (not the old one).
        upserts = [a for s, a in conn.executed if "calendar_feed_secrets" in s]
        assert len(upserts) == 1
        new_secret = upserts[0][1]
        assert new_secret != SECRET
        assert verify_feed_token(r.json()["token"], new_secret)

    def test_feed_requires_auth(self, client: TestClient) -> None:
        r = client.get("/me/calendar/feed")
        assert r.status_code in (401, 403)


class TestProviders:
    def test_oauth_buttons_hidden_when_unconfigured(self, client: TestClient, monkeypatch) -> None:
        # Pin the demo flag off (a developer's local .env may enable it) so the
        # unconfigured baseline is deterministic on any machine.
        from app.config import get_settings
        monkeypatch.setenv("CALENDAR_FAKE_PROVIDER", "false")
        get_settings.cache_clear()
        app.dependency_overrides[get_current_user] = _applicant_user
        r = client.get("/me/calendar/providers")
        get_settings.cache_clear()
        assert r.status_code == 200
        body = r.json()
        # Local env has no OAuth keys — both "Connect …" buttons stay hidden,
        # and the demo provider is absent unless explicitly enabled.
        assert body == {
            "google_configured": False,
            "outlook_configured": False,
            "demo_available": False,
        }
