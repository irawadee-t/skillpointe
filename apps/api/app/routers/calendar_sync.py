"""
Calendar OAuth sync — the READ tier: connect Google/Outlook, overlay YOUR
busy times on the interview slot grid.

Authenticated (any role):
  GET    /me/calendar/connect/{provider}     — mint state + PKCE, return the
                                               provider authorize URL to redirect to
  POST   /me/calendar/connect/demo           — local-only deterministic demo
                                               connection (CALENDAR_FAKE_PROVIDER=true,
                                               refused in production)
  GET    /me/calendar/connections            — list my connections
  DELETE /me/calendar/connections/{id}       — disconnect (+ best-effort revocation)
  GET    /me/calendar/busy?start&end         — merged busy intervals across my
                                               connections (short cache, graceful
                                               token refresh)

Unauthenticated (the browser arrives here from the provider):
  GET    /calendar/callback/{provider}       — state check (single-use) → code
                                               exchange → encrypted token storage →
                                               redirect back to the web app

Token storage: access/refresh tokens are app-layer encrypted with the same
Fernet envelope used for screening answers (app/util/crypto.py) — plaintext
never reaches the database. Scopes are free/busy-minimal; event contents are
never requested.
"""
from __future__ import annotations

import logging
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro import calendar_sync as cal
from app.util.cache import cache_key, cached_json
from app.util.crypto import decrypt_str, encrypt_str

logger = logging.getLogger(__name__)

user_router = APIRouter(prefix="/me/calendar", tags=["me"])
public_router = APIRouter(tags=["calendar"])

STATE_TTL = timedelta(minutes=10)
BUSY_CACHE_TTL_SECONDS = 120
MAX_BUSY_WINDOW_DAYS = 35

PROVIDERS = ("google", "microsoft")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConnectStart(BaseModel):
    authorize_url: str


class ConnectionOut(BaseModel):
    id: str
    provider: str                      # google | microsoft | demo
    account_email: str
    connected_at: str
    last_used_at: str | None = None


class BusyInterval(BaseModel):
    start: str
    end: str


class BusySource(BaseModel):
    provider: str
    account_email: str
    ok: bool


class BusyOut(BaseModel):
    busy: list[BusyInterval]
    sources: list[BusySource]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_credentials(provider: str) -> tuple[str, str]:
    s = get_settings()
    if provider == "google":
        return s.google_calendar_client_id, s.google_calendar_client_secret
    return s.ms_graph_client_id, s.ms_graph_client_secret


def _redirect_uri(provider: str) -> str:
    return f"{get_settings().api_public_url.rstrip('/')}/calendar/callback/{provider}"


def _web_settings_url(status: str) -> str:
    return f"{get_settings().web_origin}/account/settings?calendar={status}#calendar"


def _demo_enabled() -> bool:
    s = get_settings()
    return bool(s.calendar_fake_provider) and s.app_env != "production"


def _row_out(row) -> ConnectionOut:
    return ConnectionOut(
        id=str(row["id"]),
        provider=row["provider"],
        account_email=row["account_email"],
        connected_at=row["connected_at"].isoformat(),
        last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
    )


# ---------------------------------------------------------------------------
# Connect (start) — mint state + PKCE, hand back the authorize URL
# ---------------------------------------------------------------------------

@user_router.get("/connect/{provider}", response_model=ConnectStart)
async def start_connect(provider: str, user: CurrentUser = Depends(get_current_user)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown calendar provider.")
    client_id, client_secret = _provider_credentials(provider)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=409,
            detail="That calendar provider isn't configured on this deployment.",
        )

    state = _secrets.token_urlsafe(24)
    verifier = cal.make_code_verifier()
    async with get_db() as conn:
        # Opportunistic sweep of expired states, then persist ours (single-use).
        await conn.execute(
            "DELETE FROM public.calendar_oauth_states WHERE created_at < NOW() - INTERVAL '10 minutes'"
        )
        await conn.execute(
            """
            INSERT INTO public.calendar_oauth_states (state, user_id, provider, code_verifier)
            VALUES ($1, $2::uuid, $3, $4)
            """,
            state, user.user_id, provider, verifier,
        )

    challenge = cal.code_challenge_s256(verifier)
    build = cal.google_authorize_url if provider == "google" else cal.microsoft_authorize_url
    return ConnectStart(authorize_url=build(client_id, _redirect_uri(provider), state, challenge))


# ---------------------------------------------------------------------------
# Callback — the browser lands here from the provider
# ---------------------------------------------------------------------------

@public_router.get("/calendar/callback/{provider}", include_in_schema=True)
async def oauth_callback(
    provider: str,
    state: str = Query(""),
    code: str = Query(""),
    error: str = Query(""),
):
    """Exchange the auth code and store the (encrypted) tokens, then send the
    browser back to the account settings page. Every failure path redirects
    with ?calendar=error rather than stranding the user on a JSON page."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown calendar provider.")
    if error or not code or not state:
        # User denied consent, or the provider bounced us with no code.
        return RedirectResponse(_web_settings_url("error"), status_code=303)

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            DELETE FROM public.calendar_oauth_states
             WHERE state = $1 AND provider = $2
               AND created_at > NOW() - INTERVAL '10 minutes'
            RETURNING user_id, code_verifier
            """,
            state, provider,
        )
    if not row:
        # Unknown, expired, replayed, or cross-provider state — fail closed.
        return RedirectResponse(_web_settings_url("error"), status_code=303)

    client_id, client_secret = _provider_credentials(provider)
    try:
        bundle = await cal.exchange_code(
            provider,
            code=code,
            code_verifier=row["code_verifier"],
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=_redirect_uri(provider),
        )
    except cal.CalendarProviderError:
        return RedirectResponse(_web_settings_url("error"), status_code=303)

    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO public.calendar_connections
              (user_id, provider, account_email,
               access_token_ciphertext, refresh_token_ciphertext,
               access_token_expires_at)
            VALUES ($1::uuid, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, provider, account_email) DO UPDATE SET
              access_token_ciphertext  = EXCLUDED.access_token_ciphertext,
              refresh_token_ciphertext = COALESCE(EXCLUDED.refresh_token_ciphertext,
                                                  calendar_connections.refresh_token_ciphertext),
              access_token_expires_at  = EXCLUDED.access_token_expires_at,
              connected_at             = NOW()
            """,
            str(row["user_id"]), provider, bundle.account_email,
            encrypt_str(bundle.access_token),
            encrypt_str(bundle.refresh_token) if bundle.refresh_token else None,
            bundle.expires_at,
        )
    return RedirectResponse(_web_settings_url("connected"), status_code=303)


# ---------------------------------------------------------------------------
# Demo provider (local only)
# ---------------------------------------------------------------------------

@user_router.post("/connect/demo", response_model=ConnectionOut)
async def connect_demo(user: CurrentUser = Depends(get_current_user)):
    """Create the deterministic demo connection. Exists ONLY when
    CALENDAR_FAKE_PROVIDER=true and never in production — the row flows
    through the same storage/fetch/overlay pipeline as a real provider."""
    if not _demo_enabled():
        raise HTTPException(status_code=404, detail="We couldn't find that.")
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO public.calendar_connections (user_id, provider, account_email)
            VALUES ($1::uuid, 'demo', $2)
            ON CONFLICT (user_id, provider, account_email) DO UPDATE SET connected_at = NOW()
            """,
            user.user_id, cal.DEMO_EMAIL,
        )
        row = await conn.fetchrow(
            """
            SELECT id, provider, account_email, connected_at, last_used_at
              FROM public.calendar_connections
             WHERE user_id = $1::uuid AND provider = 'demo'
            """,
            user.user_id,
        )
    if not row:
        raise HTTPException(status_code=500, detail="Could not create the demo connection.")
    return _row_out(row)


# ---------------------------------------------------------------------------
# Connections list / disconnect
# ---------------------------------------------------------------------------

@user_router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, provider, account_email, connected_at, last_used_at
              FROM public.calendar_connections
             WHERE user_id = $1::uuid
             ORDER BY connected_at
            """,
            user.user_id,
        )
    return [_row_out(r) for r in rows]


@user_router.delete("/connections/{connection_id}", status_code=204)
async def disconnect(connection_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """Delete the connection and best-effort revoke the grant at the provider
    (Google has a revocation endpoint; Microsoft v2 does not — removing our
    stored tokens is the whole story there)."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            DELETE FROM public.calendar_connections
             WHERE id = $1 AND user_id = $2::uuid
            RETURNING provider, refresh_token_ciphertext
            """,
            connection_id, user.user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="We couldn't find that connection.")
    if row["provider"] == "google" and row["refresh_token_ciphertext"]:
        token = decrypt_str(row["refresh_token_ciphertext"])
        if token:
            await cal.revoke_google(token)
    return None


# ---------------------------------------------------------------------------
# Busy — the overlay's data source
# ---------------------------------------------------------------------------

def _parse_instant(raw: str, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"'{name}' must be an ISO-8601 instant.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _connection_busy(
    conn, row, start: datetime, end: datetime, tz_offset_min: int
) -> list[tuple[datetime, datetime]]:
    """Busy intervals for ONE connection, refreshing the access token when it
    is expired up front or rejected mid-flight (single retry)."""
    provider = row["provider"]
    if provider == "demo":
        return cal.demo_busy_intervals(start, end, tz_offset_min)

    client_id, client_secret = _provider_credentials(provider)
    access = decrypt_str(row["access_token_ciphertext"]) or ""
    refresh = decrypt_str(row["refresh_token_ciphertext"]) or ""
    expires_at = row["access_token_expires_at"]

    async def persist(bundle: cal.TokenBundle) -> str:
        await conn.execute(
            """
            UPDATE public.calendar_connections
               SET access_token_ciphertext = $2,
                   refresh_token_ciphertext = COALESCE($3, refresh_token_ciphertext),
                   access_token_expires_at = $4
             WHERE id = $1
            """,
            row["id"], encrypt_str(bundle.access_token),
            encrypt_str(bundle.refresh_token) if bundle.refresh_token else None,
            bundle.expires_at,
        )
        return bundle.access_token

    async def do_refresh() -> str:
        if not refresh:
            raise cal.CalendarProviderError("no refresh token stored")
        bundle = await cal.refresh_tokens(
            provider, refresh_token=refresh,
            client_id=client_id, client_secret=client_secret,
        )
        return await persist(bundle)

    # Proactive refresh when the stored token is (about to be) dead.
    now = datetime.now(timezone.utc)
    if not access or (expires_at is not None and expires_at <= now + timedelta(seconds=60)):
        access = await do_refresh()

    async def fetch(token: str) -> list[tuple[datetime, datetime]]:
        if provider == "google":
            return await cal.fetch_google_busy(token, start, end)
        return await cal.fetch_microsoft_busy(token, row["account_email"], start, end)

    try:
        return await fetch(access)
    except cal.TokenExpiredError:
        # Stored expiry lied (revocation-and-reissue, clock skew) — refresh once.
        access = await do_refresh()
        return await fetch(access)


@user_router.get("/busy", response_model=BusyOut)
async def my_busy(
    start: str = Query(...),
    end: str = Query(...),
    tz_offset: int = Query(0, ge=-840, le=840,
                           description="JS Date.getTimezoneOffset() minutes; demo provider only"),
    user: CurrentUser = Depends(get_current_user),
):
    """Merged busy intervals for the visible grid window, across every
    connection the user has. Failures on one provider degrade to `ok: false`
    for that source instead of failing the whole overlay."""
    start_dt = _parse_instant(start, "start")
    end_dt = _parse_instant(end, "end")
    if end_dt <= start_dt:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if end_dt - start_dt > timedelta(days=MAX_BUSY_WINDOW_DAYS):
        raise HTTPException(status_code=422, detail="Window too large (max 35 days).")

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, provider, account_email,
                   access_token_ciphertext, refresh_token_ciphertext,
                   access_token_expires_at
              FROM public.calendar_connections
             WHERE user_id = $1::uuid
             ORDER BY connected_at
            """,
            user.user_id,
        )
        if not rows:
            return BusyOut(busy=[], sources=[])

        # Cache keyed on the exact connection set so disconnects take effect
        # immediately (the key changes) while repeat week-views hit the cache.
        key = cache_key(
            "calbusy", user.user_id,
            ",".join(sorted(str(r["id"]) for r in rows)),
            start_dt.isoformat(), end_dt.isoformat(), tz_offset,
        )

        async def produce():
            intervals: list[tuple[datetime, datetime]] = []
            sources: list[dict] = []
            for r in rows:
                try:
                    intervals.extend(await _connection_busy(conn, r, start_dt, end_dt, tz_offset))
                    sources.append({"provider": r["provider"],
                                    "account_email": r["account_email"], "ok": True})
                except Exception as exc:
                    logger.warning("busy fetch failed for %s connection %s: %s",
                                   r["provider"], r["id"], exc)
                    sources.append({"provider": r["provider"],
                                    "account_email": r["account_email"], "ok": False})
            merged = cal.merge_intervals(intervals)
            return {
                "busy": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in merged],
                "sources": sources,
            }

        data = await cached_json(key, BUSY_CACHE_TTL_SECONDS, produce)
        await conn.execute(
            "UPDATE public.calendar_connections SET last_used_at = NOW() WHERE user_id = $1::uuid",
            user.user_id,
        )
    return BusyOut(**data)
