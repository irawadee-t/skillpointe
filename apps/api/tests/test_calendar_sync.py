"""
test_calendar_sync.py — the OAuth READ tier (busy overlay).

Covers:
  PKCE + state
    - RFC 7636 S256 test vector
    - /me/calendar/connect/{provider} persists a single-use state row whose
      verifier hashes to the code_challenge in the authorize URL
    - unknown provider → 404; unconfigured provider → 409
    - callback with unknown/expired state → error redirect, nothing stored
  Token exchange (mocked HTTP)
    - exchange_code posts the PKCE verifier and parses the id_token email
    - callback stores ENCRYPTED tokens (round-trips through decrypt_str,
      ciphertext is not the plaintext)
  Refresh-on-401
    - a freeBusy 401 triggers exactly one refresh + retry, and the new
      access token is persisted encrypted
  Busy merge / normalization
    - overlaps, touching, cross-day, unsorted, inverted-dropped
  Demo (fake) provider gate
    - Settings default is False; POST /me/calendar/connect/demo → 404 when off
    - enforce_production_safety refuses CALENDAR_FAKE_PROVIDER=true in production
    - when enabled (non-prod), the demo connection feeds deterministic busy
      blocks through the SAME /me/calendar/busy pipeline
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
from app.config import ProductionConfigError, Settings, enforce_production_safety, get_settings
from app.main import app
from app.skilled_pro import calendar_sync as cal
from app.util.crypto import decrypt_str

USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
CONN_ID = UUID("77777777-0000-0000-0000-777777777777")


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mock DB plumbing (same routed-connection style as test_calendar_feed.py)
# ---------------------------------------------------------------------------

class RoutedConn:
    def __init__(self) -> None:
        self.fetchrow_routes: list[tuple[str, Any]] = []
        self.fetch_routes: list[tuple[str, Any]] = []
        self.executed: list[tuple[str, tuple]] = []

    def route_fetchrow(self, needle: str, result: Any) -> None:
        self.fetchrow_routes.append((needle, result))

    def route_fetch(self, needle: str, result: Any) -> None:
        self.fetch_routes.append((needle, result))

    async def fetchrow(self, sql: str, *args: Any):
        self.executed.append((sql, args))
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
        return None

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        return "INSERT 0 1"


def _patch_db(conn: RoutedConn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.calendar_sync.get_db", return_value=ctx)


async def _no_cache(key, ttl, producer):
    return await producer()


def _user() -> CurrentUser:
    return CurrentUser(user_id=USER_ID, email="e@test.local", role="employer",
                       onboarding_complete=True)


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def demo_on(monkeypatch):
    monkeypatch.setenv("CALENDAR_FAKE_PROVIDER", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def demo_off(monkeypatch):
    # Real env vars beat the developer's local .env (which may set the flag),
    # so the "off" behavior is deterministic on any machine.
    monkeypatch.setenv("CALENDAR_FAKE_PROVIDER", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def google_keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_ID", "gid-123")
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_SECRET", "gsec-456")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------

class TestPkce:
    def test_rfc7636_s256_vector(self) -> None:
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        assert cal.code_challenge_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    def test_verifier_shape(self) -> None:
        v = cal.make_code_verifier()
        assert 43 <= len(v) <= 128
        assert cal.make_code_verifier() != v  # random


# ---------------------------------------------------------------------------
# Connect start
# ---------------------------------------------------------------------------

class TestConnectStart:
    def test_unknown_provider_404(self, client: TestClient) -> None:
        assert client.get("/me/calendar/connect/icloud").status_code == 404

    def test_unconfigured_provider_409(self, client: TestClient) -> None:
        assert client.get("/me/calendar/connect/google").status_code == 409

    def test_state_row_matches_challenge_in_url(self, client: TestClient, google_keys) -> None:
        conn = RoutedConn()
        with _patch_db(conn):
            r = client.get("/me/calendar/connect/google")
        assert r.status_code == 200
        url = r.json()["authorize_url"]
        assert url.startswith(cal.GOOGLE_AUTH_URL)
        # Minimal scope — free/busy, never calendar.events.
        assert "calendar.freebusy" in url
        assert "calendar.events" not in url
        assert "code_challenge_method=S256" in url

        inserts = [(sql, args) for sql, args in conn.executed
                   if "INSERT INTO public.calendar_oauth_states" in sql]
        assert len(inserts) == 1
        state, user_id, provider, verifier = inserts[0][1]
        assert user_id == USER_ID and provider == "google"
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        assert q["state"] == [state]
        assert q["code_challenge"] == [cal.code_challenge_s256(verifier)]
        assert q["redirect_uri"] == ["http://localhost:8000/calendar/callback/google"]


# ---------------------------------------------------------------------------
# Token exchange (mocked HTTP)
# ---------------------------------------------------------------------------

def _id_token(email: str) -> str:
    import base64
    import json
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"h.{payload}.sig"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeHttp:
    """Stands in for httpx.AsyncClient — records posts, returns queued responses."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.posts: list[tuple[str, dict]] = []

    async def post(self, url: str, data=None, json=None, headers=None):
        self.posts.append((url, data if data is not None else json))
        return self.responses.pop(0)


class TestExchange:
    @pytest.mark.asyncio
    async def test_exchange_posts_verifier_and_parses_email(self) -> None:
        http = FakeHttp([FakeResponse(200, {
            "access_token": "at-1", "refresh_token": "rt-1",
            "expires_in": 3600, "id_token": _id_token("me@gmail.com"),
        })])
        bundle = await cal.exchange_code(
            "google", code="the-code", code_verifier="the-verifier",
            client_id="cid", client_secret="cs",
            redirect_uri="http://localhost:8000/calendar/callback/google",
            http=http,  # type: ignore[arg-type]
        )
        url, form = http.posts[0]
        assert url == cal.GOOGLE_TOKEN_URL
        assert form["code_verifier"] == "the-verifier"
        assert form["grant_type"] == "authorization_code"
        assert bundle.access_token == "at-1"
        assert bundle.refresh_token == "rt-1"
        assert bundle.account_email == "me@gmail.com"
        assert bundle.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_exchange_error_raises(self) -> None:
        http = FakeHttp([FakeResponse(400, {"error": "invalid_grant"})])
        with pytest.raises(cal.CalendarProviderError):
            await cal.exchange_code(
                "google", code="x", code_verifier="v", client_id="c",
                client_secret="s", redirect_uri="r",
                http=http,  # type: ignore[arg-type]
            )

    def test_email_from_garbage_id_token_is_empty(self) -> None:
        assert cal.email_from_id_token(None) == ""
        assert cal.email_from_id_token("not-a-jwt") == ""
        assert cal.email_from_id_token("a.!!!.c") == ""


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class TestCallback:
    def test_unknown_state_error_redirect_nothing_stored(self, client: TestClient) -> None:
        conn = RoutedConn()  # DELETE ... RETURNING routes to None
        with _patch_db(conn):
            r = client.get("/calendar/callback/google?state=nope&code=abc",
                           follow_redirects=False)
        assert r.status_code == 303
        assert "calendar=error" in r.headers["location"]
        assert not [s for s, _ in conn.executed if "INSERT INTO public.calendar_connections" in s]

    def test_provider_error_param_redirects(self, client: TestClient) -> None:
        r = client.get("/calendar/callback/google?error=access_denied",
                       follow_redirects=False)
        assert r.status_code == 303
        assert "calendar=error" in r.headers["location"]

    def test_success_stores_encrypted_tokens(self, client: TestClient, google_keys) -> None:
        conn = RoutedConn()
        conn.route_fetchrow(
            "DELETE FROM public.calendar_oauth_states",
            {"user_id": UUID(USER_ID), "code_verifier": "the-verifier"},
        )
        bundle = cal.TokenBundle(
            access_token="plain-access", refresh_token="plain-refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            account_email="me@gmail.com",
        )
        with _patch_db(conn), patch(
            "app.routers.calendar_sync.cal.exchange_code",
            new=AsyncMock(return_value=bundle),
        ) as ex:
            r = client.get("/calendar/callback/google?state=st1&code=code1",
                           follow_redirects=False)
        assert r.status_code == 303
        assert "calendar=connected" in r.headers["location"]
        assert ex.await_args.kwargs["code"] == "code1"
        assert ex.await_args.kwargs["code_verifier"] == "the-verifier"

        ins = [(s, a) for s, a in conn.executed
               if "INSERT INTO public.calendar_connections" in s]
        assert len(ins) == 1
        _, args = ins[0]
        user_id, provider, email, access_ct, refresh_ct, _exp = args
        assert user_id == USER_ID and provider == "google" and email == "me@gmail.com"
        # Encrypted at rest: versioned ciphertext, never the plaintext,
        # and it round-trips through the shared crypto util.
        assert access_ct.startswith("v1:") and "plain-access" not in access_ct
        assert refresh_ct.startswith("v1:") and "plain-refresh" not in refresh_ct
        assert decrypt_str(access_ct) == "plain-access"
        assert decrypt_str(refresh_ct) == "plain-refresh"

    def test_replayed_state_single_use(self, client: TestClient, google_keys) -> None:
        # First hit consumes the row (DELETE RETURNING); second returns None.
        conn = RoutedConn()
        served = {"n": 0}

        def once():
            served["n"] += 1
            if served["n"] == 1:
                return {"user_id": UUID(USER_ID), "code_verifier": "v"}
            return None

        conn.route_fetchrow("DELETE FROM public.calendar_oauth_states", once)
        bundle = cal.TokenBundle("a", "r", datetime.now(timezone.utc) + timedelta(hours=1), "e@x")
        with _patch_db(conn), patch(
            "app.routers.calendar_sync.cal.exchange_code",
            new=AsyncMock(return_value=bundle),
        ):
            first = client.get("/calendar/callback/google?state=s&code=c", follow_redirects=False)
            second = client.get("/calendar/callback/google?state=s&code=c", follow_redirects=False)
        assert "calendar=connected" in first.headers["location"]
        assert "calendar=error" in second.headers["location"]


# ---------------------------------------------------------------------------
# Refresh-on-401
# ---------------------------------------------------------------------------

class TestRefreshOn401:
    @pytest.mark.asyncio
    async def test_401_refreshes_once_and_persists(self, google_keys) -> None:
        from app.routers.calendar_sync import _connection_busy
        from app.util.crypto import encrypt_str

        conn = RoutedConn()
        row = {
            "id": CONN_ID, "provider": "google", "account_email": "me@gmail.com",
            "access_token_ciphertext": encrypt_str("stale-access"),
            "refresh_token_ciphertext": encrypt_str("the-refresh"),
            # Looks valid, but the provider will 401 it.
            "access_token_expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        start, end = _utc(2026, 8, 10), _utc(2026, 8, 17)
        busy = [(_utc(2026, 8, 11, 14), _utc(2026, 8, 11, 15))]

        calls = {"fetch": 0}

        async def fake_fetch(token, s, e, http=None):
            calls["fetch"] += 1
            if token == "stale-access":
                raise cal.TokenExpiredError("nope")
            assert token == "fresh-access"
            return busy

        fresh = cal.TokenBundle("fresh-access", "rotated-refresh",
                                datetime.now(timezone.utc) + timedelta(hours=1), "")
        with patch("app.routers.calendar_sync.cal.fetch_google_busy", new=fake_fetch), \
             patch("app.routers.calendar_sync.cal.refresh_tokens",
                   new=AsyncMock(return_value=fresh)) as rf:
            out = await _connection_busy(conn, row, start, end, 0)

        assert out == busy
        assert calls["fetch"] == 2          # 401 then retry — exactly once
        rf.assert_awaited_once()
        assert rf.await_args.kwargs["refresh_token"] == "the-refresh"
        # The refreshed access token was persisted encrypted.
        updates = [(s, a) for s, a in conn.executed if "UPDATE public.calendar_connections" in s]
        assert len(updates) == 1
        _, args = updates[0]
        assert decrypt_str(args[1]) == "fresh-access"
        assert decrypt_str(args[2]) == "rotated-refresh"

    @pytest.mark.asyncio
    async def test_expired_token_refreshes_proactively(self, google_keys) -> None:
        from app.routers.calendar_sync import _connection_busy
        from app.util.crypto import encrypt_str

        conn = RoutedConn()
        row = {
            "id": CONN_ID, "provider": "google", "account_email": "me@gmail.com",
            "access_token_ciphertext": encrypt_str("dead"),
            "refresh_token_ciphertext": encrypt_str("the-refresh"),
            "access_token_expires_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        fresh = cal.TokenBundle("fresh", None,
                                datetime.now(timezone.utc) + timedelta(hours=1), "")
        fetched: list[str] = []

        async def fake_fetch(token, s, e, http=None):
            fetched.append(token)
            return []

        with patch("app.routers.calendar_sync.cal.fetch_google_busy", new=fake_fetch), \
             patch("app.routers.calendar_sync.cal.refresh_tokens",
                   new=AsyncMock(return_value=fresh)):
            await _connection_busy(conn, row, _utc(2026, 8, 10), _utc(2026, 8, 11), 0)
        assert fetched == ["fresh"]  # never even tried the dead token


# ---------------------------------------------------------------------------
# Merge / normalization
# ---------------------------------------------------------------------------

class TestMerge:
    def test_overlaps_merge(self) -> None:
        a = (_utc(2026, 8, 10, 9), _utc(2026, 8, 10, 10, 30))
        b = (_utc(2026, 8, 10, 10), _utc(2026, 8, 10, 11))
        assert cal.merge_intervals([a, b]) == [(a[0], b[1])]

    def test_touching_merge(self) -> None:
        a = (_utc(2026, 8, 10, 9), _utc(2026, 8, 10, 10))
        b = (_utc(2026, 8, 10, 10), _utc(2026, 8, 10, 11))
        assert cal.merge_intervals([a, b]) == [(a[0], b[1])]

    def test_disjoint_stay_apart_and_sort(self) -> None:
        a = (_utc(2026, 8, 10, 14), _utc(2026, 8, 10, 15))
        b = (_utc(2026, 8, 10, 9), _utc(2026, 8, 10, 10))
        assert cal.merge_intervals([a, b]) == [b, a]

    def test_cross_day_interval_swallows(self) -> None:
        long = (_utc(2026, 8, 10, 22), _utc(2026, 8, 11, 8))
        inner = (_utc(2026, 8, 11, 1), _utc(2026, 8, 11, 2))
        assert cal.merge_intervals([inner, long]) == [long]

    def test_inverted_and_empty_dropped(self) -> None:
        bad = (_utc(2026, 8, 10, 12), _utc(2026, 8, 10, 11))
        empty = (_utc(2026, 8, 10, 12), _utc(2026, 8, 10, 12))
        assert cal.merge_intervals([bad, empty]) == []


# ---------------------------------------------------------------------------
# Demo provider — gate + determinism
# ---------------------------------------------------------------------------

class TestDemoProvider:
    def test_settings_default_is_off(self) -> None:
        # The flag CANNOT default on — a fresh Settings has it false.
        assert Settings.model_fields["calendar_fake_provider"].default is False

    def test_endpoint_404_when_flag_off(self, client: TestClient, demo_off) -> None:
        assert client.post("/me/calendar/connect/demo").status_code == 404

    def test_providers_hide_demo_when_off(self, client: TestClient, demo_off) -> None:
        body = client.get("/me/calendar/providers").json()
        assert body["demo_available"] is False

    def test_production_boot_refuses_flag(self) -> None:
        settings = get_settings().model_copy(update={
            "app_env": "production",
            "calendar_fake_provider": True,
            # Satisfy the other production checks so THIS one is what trips.
            "skilled_signing_private_key": "pem", "skilled_signing_key_id": "k1",
            "screening_encryption_key": "x",
            "supabase_url": "https://x.supabase.co",
            "database_url": "postgresql://u@db.host/x",
            "redis_url": "redis://r.host:6379",
        })
        with pytest.raises(ProductionConfigError, match="CALENDAR_FAKE_PROVIDER"):
            enforce_production_safety(settings, MagicMock())

    def test_connect_demo_when_enabled(self, client: TestClient, demo_on) -> None:
        conn = RoutedConn()
        conn.route_fetchrow("SELECT id, provider, account_email", {
            "id": CONN_ID, "provider": "demo", "account_email": cal.DEMO_EMAIL,
            "connected_at": datetime.now(timezone.utc), "last_used_at": None,
        })
        with _patch_db(conn):
            r = client.post("/me/calendar/connect/demo")
        assert r.status_code == 200
        assert r.json()["provider"] == "demo"
        assert r.json()["account_email"] == cal.DEMO_EMAIL

    def test_demo_busy_deterministic_and_placed(self) -> None:
        start, end = _utc(2026, 8, 10), _utc(2026, 8, 17)  # Mon–Mon
        a = cal.demo_busy_intervals(start, end, tz_offset_min=240)  # UTC-4
        b = cal.demo_busy_intervals(start, end, tz_offset_min=240)
        assert a == b and len(a) > 0
        # Every weekday has the 9–10am LOCAL standup: 13:00–14:00 UTC at -4.
        standups = [(s, e) for s, e in a if s.hour == 13 and e.hour == 14]
        assert len(standups) == 5
        assert all(s >= start and e <= end for s, e in a)

    def test_busy_endpoint_via_demo_pipeline(self, client: TestClient, demo_on) -> None:
        conn = RoutedConn()
        conn.route_fetch("FROM public.calendar_connections", [{
            "id": CONN_ID, "provider": "demo", "account_email": cal.DEMO_EMAIL,
            "access_token_ciphertext": None, "refresh_token_ciphertext": None,
            "access_token_expires_at": None,
        }])
        with _patch_db(conn), patch("app.routers.calendar_sync.cached_json", new=_no_cache):
            r = client.get("/me/calendar/busy", params={
                "start": "2026-08-10T00:00:00Z", "end": "2026-08-17T00:00:00Z",
                "tz_offset": 240,
            })
        assert r.status_code == 200
        body = r.json()
        assert body["sources"] == [
            {"provider": "demo", "account_email": cal.DEMO_EMAIL, "ok": True}
        ]
        assert len(body["busy"]) > 0
        # Sorted, non-overlapping (merged), ISO instants.
        starts = [i["start"] for i in body["busy"]]
        assert starts == sorted(starts)
        # last_used stamped.
        assert [s for s, _ in conn.executed if "SET last_used_at" in s]

    def test_busy_no_connections_empty(self, client: TestClient) -> None:
        conn = RoutedConn()
        with _patch_db(conn):
            r = client.get("/me/calendar/busy", params={
                "start": "2026-08-10T00:00:00Z", "end": "2026-08-17T00:00:00Z",
            })
        assert r.status_code == 200
        assert r.json() == {"busy": [], "sources": []}

    def test_busy_validation(self, client: TestClient) -> None:
        conn = RoutedConn()
        with _patch_db(conn):
            bad_order = client.get("/me/calendar/busy", params={
                "start": "2026-08-17T00:00:00Z", "end": "2026-08-10T00:00:00Z"})
            too_big = client.get("/me/calendar/busy", params={
                "start": "2026-08-01T00:00:00Z", "end": "2026-12-01T00:00:00Z"})
            not_iso = client.get("/me/calendar/busy", params={
                "start": "tuesday", "end": "2026-08-10T00:00:00Z"})
        assert bad_order.status_code == 422
        assert too_big.status_code == 422
        assert not_iso.status_code == 422


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:
    def test_disconnect_deletes_and_revokes_google(self, client: TestClient) -> None:
        from app.util.crypto import encrypt_str
        conn = RoutedConn()
        conn.route_fetchrow("DELETE FROM public.calendar_connections", {
            "provider": "google",
            "refresh_token_ciphertext": encrypt_str("the-refresh"),
        })
        with _patch_db(conn), patch(
            "app.routers.calendar_sync.cal.revoke_google", new=AsyncMock()
        ) as rv:
            r = client.delete(f"/me/calendar/connections/{CONN_ID}")
        assert r.status_code == 204
        rv.assert_awaited_once_with("the-refresh")

    def test_disconnect_wrong_id_404(self, client: TestClient) -> None:
        conn = RoutedConn()
        with _patch_db(conn):
            assert client.delete(f"/me/calendar/connections/{CONN_ID}").status_code == 404
