"""
Calendar OAuth sync — provider logic for the READ (free/busy overlay) tier.

Pure provider mechanics live here so the router stays thin and everything is
unit-testable with a mocked HTTP client:

  * PKCE (RFC 7636): verifier generation + S256 challenge.
  * Authorization-URL builders for Google and Microsoft (auth-code + PKCE).
      Google scope:   https://www.googleapis.com/auth/calendar.freebusy
                      (+ openid email so we can label the connection) —
                      freeBusy needs NO event-content access, so we ask for
                      the minimal scope on purpose.
      Microsoft:      Calendars.Read (delegated) + openid email offline_access.
  * Token exchange + refresh (httpx).
  * id_token email extraction (claims parsed WITHOUT signature verification —
    the token arrived directly from the provider's token endpoint over TLS,
    so its integrity is the transport's; we only use it for a display label).
  * Free/busy fetchers: Google freeBusy, Microsoft Graph getSchedule.
  * The deterministic demo provider (local-only; see router gating).
  * Interval normalization/merge shared by every provider.

No DB access in this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/calendar.freebusy"

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GETSCHEDULE_URL = "https://graph.microsoft.com/v1.0/me/calendar/getSchedule"
MS_SCOPES = "openid email offline_access https://graph.microsoft.com/Calendars.Read"

HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class CalendarProviderError(RuntimeError):
    """A provider call failed in a way the caller should surface or skip."""


class TokenExpiredError(CalendarProviderError):
    """Access token rejected (401) — refresh and retry once."""


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------

def make_code_verifier() -> str:
    """RFC 7636 code_verifier: 43–128 chars of unreserved characters."""
    return secrets.token_urlsafe(64)  # 86 chars


def code_challenge_s256(verifier: str) -> str:
    """S256 code_challenge = BASE64URL(SHA256(verifier)), no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# Authorization URLs
# ---------------------------------------------------------------------------

def google_authorize_url(
    client_id: str, redirect_uri: str, state: str, code_challenge: str
) -> str:
    return GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        # offline + consent so Google returns a refresh_token on every connect
        # (without prompt=consent a re-connect silently omits it).
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


def microsoft_authorize_url(
    client_id: str, redirect_uri: str, state: str, code_challenge: str
) -> str:
    return MS_AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "response_mode": "query",
        "scope": MS_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime          # UTC instant the access token dies
    account_email: str            # best-effort label from id_token ("" if absent)


def email_from_id_token(id_token: str | None) -> str:
    """Extract the email claim from a JWT WITHOUT verifying the signature.

    Safe here because the id_token came straight from the provider's token
    endpoint over TLS and is used only as a display label, never for authz.
    """
    if not id_token:
        return ""
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
        email = claims.get("email") or claims.get("preferred_username") or ""
        return email if isinstance(email, str) else ""
    except Exception:
        return ""


def _bundle_from_token_response(data: dict) -> TokenBundle:
    access = data.get("access_token") or ""
    if not access:
        raise CalendarProviderError("Token response carried no access_token.")
    expires_in = int(data.get("expires_in") or 3600)
    return TokenBundle(
        access_token=access,
        refresh_token=data.get("refresh_token") or None,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        account_email=email_from_id_token(data.get("id_token")),
    )


async def exchange_code(
    provider: str,
    *,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    http: httpx.AsyncClient | None = None,
) -> TokenBundle:
    """Authorization-code → tokens (with PKCE verifier)."""
    url = GOOGLE_TOKEN_URL if provider == "google" else MS_TOKEN_URL
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if provider == "microsoft":
        form["scope"] = MS_SCOPES
    data = await _post_form(url, form, http)
    return _bundle_from_token_response(data)


async def refresh_tokens(
    provider: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http: httpx.AsyncClient | None = None,
) -> TokenBundle:
    """Refresh-token → fresh access token. Providers may rotate the refresh
    token (Microsoft does); the caller must persist bundle.refresh_token when
    present, else keep the old one."""
    url = GOOGLE_TOKEN_URL if provider == "google" else MS_TOKEN_URL
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if provider == "microsoft":
        form["scope"] = MS_SCOPES
    data = await _post_form(url, form, http)
    return _bundle_from_token_response(data)


async def revoke_google(refresh_token: str, http: httpx.AsyncClient | None = None) -> None:
    """Best-effort Google token revocation on disconnect. Microsoft v2 has no
    per-token revocation endpoint — deleting our stored tokens is the whole
    story there (the grant dies when the refresh token ages out or the user
    removes the app at https://account.live.com/consent/Manage)."""
    try:
        async with _client(http) as (c, _own):
            await c.post(GOOGLE_REVOKE_URL, data={"token": refresh_token})
    except Exception as exc:  # never let revocation failure block disconnect
        logger.warning("google token revocation failed (continuing): %s", exc)


async def _post_form(url: str, form: dict, http: httpx.AsyncClient | None) -> dict:
    async with _client(http) as (c, _own):
        resp = await c.post(
            url, data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        # Log the provider's error code but never its full body (may echo ids).
        try:
            err = resp.json().get("error", "")
        except Exception:
            err = ""
        logger.warning("token endpoint %s returned %s (%s)", url, resp.status_code, err)
        raise CalendarProviderError(
            f"Token exchange failed ({resp.status_code} {err or 'error'})."
        )
    return resp.json()


class _client:
    """`async with _client(maybe_client) as (c, owned)` — use the injected
    client (tests) or own a short-lived one (production)."""

    def __init__(self, http: httpx.AsyncClient | None):
        self._injected = http
        self._owned: httpx.AsyncClient | None = None

    async def __aenter__(self):
        if self._injected is not None:
            return self._injected, False
        self._owned = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
        return self._owned, True

    async def __aexit__(self, *exc):
        if self._owned is not None:
            await self._owned.aclose()


# ---------------------------------------------------------------------------
# Free/busy fetchers  (return raw [(start, end)] UTC datetimes, unmerged)
# ---------------------------------------------------------------------------

def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def fetch_google_busy(
    access_token: str,
    start: datetime,
    end: datetime,
    http: httpx.AsyncClient | None = None,
) -> list[tuple[datetime, datetime]]:
    """POST freeBusy for the primary calendar. Free/busy only — no event
    titles, attendees, or locations ever cross the wire."""
    body = {
        "timeMin": start.astimezone(timezone.utc).isoformat(),
        "timeMax": end.astimezone(timezone.utc).isoformat(),
        "items": [{"id": "primary"}],
    }
    async with _client(http) as (c, _own):
        resp = await c.post(
            GOOGLE_FREEBUSY_URL, json=body,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 401:
        raise TokenExpiredError("google access token rejected")
    if resp.status_code != 200:
        raise CalendarProviderError(f"Google freeBusy returned {resp.status_code}.")
    payload = resp.json()
    out: list[tuple[datetime, datetime]] = []
    for cal in (payload.get("calendars") or {}).values():
        for item in cal.get("busy") or []:
            try:
                out.append((_parse_iso(item["start"]), _parse_iso(item["end"])))
            except Exception:
                continue
    return out


async def fetch_microsoft_busy(
    access_token: str,
    account_email: str,
    start: datetime,
    end: datetime,
    http: httpx.AsyncClient | None = None,
) -> list[tuple[datetime, datetime]]:
    """Graph getSchedule — the free/busy call (Calendars.Read, delegated).
    Busy / oof / tentative all count as busy for overlay purposes."""
    body = {
        "schedules": [account_email],
        "startTime": {
            "dateTime": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC",
        },
        "endTime": {
            "dateTime": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC",
        },
        "availabilityViewInterval": 30,
    }
    async with _client(http) as (c, _own):
        resp = await c.post(
            MS_GETSCHEDULE_URL, json=body,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 401:
        raise TokenExpiredError("microsoft access token rejected")
    if resp.status_code != 200:
        raise CalendarProviderError(f"Graph getSchedule returned {resp.status_code}.")
    payload = resp.json()
    out: list[tuple[datetime, datetime]] = []
    for sched in payload.get("value") or []:
        for item in sched.get("scheduleItems") or []:
            if (item.get("status") or "busy") not in ("busy", "oof", "tentative"):
                continue
            try:
                # getSchedule dateTimes come back naive in the requested tz (UTC).
                s = _parse_iso(item["start"]["dateTime"])
                e = _parse_iso(item["end"]["dateTime"])
                out.append((s, e))
            except Exception:
                continue
    return out


# ---------------------------------------------------------------------------
# Demo provider — deterministic busy blocks (local dev only; router gates it)
# ---------------------------------------------------------------------------

DEMO_EMAIL = "demo-calendar@skilled.local"


def demo_busy_intervals(
    start: datetime, end: datetime, tz_offset_min: int = 0
) -> list[tuple[datetime, datetime]]:
    """Deterministic pseudo-calendar so the whole storage → fetch → overlay
    pipeline is verifiable without provider keys.

    In the viewer's LOCAL time (derived from tz_offset_min, the JS
    `Date.getTimezoneOffset()` convention: local = UTC − offset):
      * every weekday: busy 9:00–10:00 (standup),
      * plus one meeting whose start hour/length are hash-of-date stable
        (between 11:00 and 17:30, 30/60/90 minutes).
    Same date → same blocks, forever. Clamped to [start, end].
    """
    offset = timedelta(minutes=tz_offset_min)
    out: list[tuple[datetime, datetime]] = []
    # Iterate local dates covering the window (pad a day each side for safety).
    local_start = (start.astimezone(timezone.utc) - offset).date() - timedelta(days=1)
    local_end = (end.astimezone(timezone.utc) - offset).date() + timedelta(days=1)
    day = local_start
    while day <= local_end:
        if day.weekday() < 5:  # Mon–Fri
            base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + offset
            # 9–10am local standup.
            out.append((base + timedelta(hours=9), base + timedelta(hours=10)))
            # One hash-stable meeting.
            h = int.from_bytes(
                hashlib.sha256(day.isoformat().encode()).digest()[:4], "big"
            )
            start_hour = 11 + (h % 7)            # 11..17
            half = 30 if (h >> 3) % 2 else 0     # :00 or :30
            length = (30, 60, 90)[(h >> 5) % 3]
            mtg = base + timedelta(hours=start_hour, minutes=half)
            out.append((mtg, mtg + timedelta(minutes=length)))
        day += timedelta(days=1)
    return [
        (max(s, start), min(e, end))
        for s, e in out
        if s < end and e > start
    ]


# ---------------------------------------------------------------------------
# Interval merge — shared by all providers
# ---------------------------------------------------------------------------

def merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Sort, drop empties/inverted, and merge overlapping or touching
    intervals. Input may span days and come from multiple connections."""
    cleaned = [(s, e) for s, e in intervals if e > s]
    cleaned.sort(key=lambda p: p[0])
    merged: list[tuple[datetime, datetime]] = []
    for s, e in cleaned:
        if merged and s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged
