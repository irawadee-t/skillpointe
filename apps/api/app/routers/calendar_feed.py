"""
Calendar piping — the no-OAuth tier.

Authenticated (any role):
  GET  /me/calendar/feed            — mint/fetch my personal feed URL (signed token)
  POST /me/calendar/feed/rotate     — rotate my feed secret (revokes old URLs)
  GET  /me/calendar/providers       — which OAuth "Connect …" buttons may render

Unauthenticated (token IS the credential):
  GET  /calendar/feed.ics?token=…   — live ICS subscription feed of my upcoming
                                      confirmed interviews. Google Calendar,
                                      Outlook, and Apple Calendar poll this URL,
                                      so external calendars stay in sync without
                                      OAuth. UIDs are stable per slot; cancelled
                                      slots ship STATUS:CANCELLED + SEQUENCE:1.

Feed scope by role:
  applicant        — their own interviews.
  employer contact — every interview on their company's applications (which
                     includes any assigned to them as the interviewer).

Token model: per-user random secret in public.calendar_feed_secrets keys an
HMAC token (see app/skilled_pro/signing.py — make/verify_feed_token). Rotating
the secret revokes every previously issued URL for that user only.

---------------------------------------------------------------------------
OAUTH SYNC — the READ tier (free/busy overlay) is BUILT
---------------------------------------------------------------------------
See app/routers/calendar_sync.py: connect Google (auth-code + PKCE, scope
calendar.freebusy) or Microsoft Graph (Calendars.Read delegated), encrypted
refresh-token storage in public.calendar_connections, and
GET /me/calendar/busy powering the busy overlay on the interview slot grid.
GET /me/calendar/providers below gates the frontend "Connect …" buttons on
the config keys (google_calendar_client_id/_secret, ms_graph_client_id/
_secret) and exposes the local-only demo provider flag.

Still TODO(calendar-oauth-write): the two-way PUSH tier (creating events on
slot accept/cancel) would need the wider scopes calendar.events /
Calendars.ReadWrite — intentionally not requested today; the ICS feed above
covers the write direction without OAuth.
"""
from __future__ import annotations

import logging
import secrets as _secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro.ics import FeedEvent, build_feed_ics
from app.skilled_pro.signing import make_feed_token, parse_feed_token, verify_feed_token

logger = logging.getLogger(__name__)

user_router = APIRouter(prefix="/me/calendar", tags=["me"])
public_router = APIRouter(tags=["calendar"])

FEED_PATH = "/calendar/feed.ics"


# ---------------------------------------------------------------------------
class FeedInfo(BaseModel):
    token: str
    feed_path: str      # path + query on the API origin; client composes the absolute URL
    rotated_at: str | None = None


class ProvidersOut(BaseModel):
    google_configured: bool
    outlook_configured: bool
    # Local-only deterministic demo calendar (CALENDAR_FAKE_PROVIDER=true,
    # never in production) — lets the busy overlay be exercised without keys.
    demo_available: bool = False


async def _get_or_create_secret(conn, user_id: str) -> tuple[str, str | None]:
    row = await conn.fetchrow(
        "SELECT secret, rotated_at FROM public.calendar_feed_secrets WHERE user_id = $1",
        user_id,
    )
    if row:
        return row["secret"], row["rotated_at"].isoformat() if row["rotated_at"] else None
    secret = _secrets.token_urlsafe(32)
    await conn.execute(
        """
        INSERT INTO public.calendar_feed_secrets (user_id, secret)
        VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING
        """,
        user_id, secret,
    )
    # Re-read in case of a concurrent insert racing us.
    row = await conn.fetchrow(
        "SELECT secret FROM public.calendar_feed_secrets WHERE user_id = $1", user_id,
    )
    return (row["secret"] if row else secret), None


@user_router.get("/feed", response_model=FeedInfo)
async def get_my_feed(user: CurrentUser = Depends(get_current_user)):
    """Mint (or return the existing) personal calendar feed URL."""
    async with get_db() as conn:
        secret, rotated_at = await _get_or_create_secret(conn, user.user_id)
    token = make_feed_token(user.user_id, secret)
    return FeedInfo(token=token, feed_path=f"{FEED_PATH}?token={token}", rotated_at=rotated_at)


@user_router.post("/feed/rotate", response_model=FeedInfo)
async def rotate_my_feed(user: CurrentUser = Depends(get_current_user)):
    """Rotate my feed secret. Every previously issued feed URL stops working."""
    secret = _secrets.token_urlsafe(32)
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO public.calendar_feed_secrets (user_id, secret, rotated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET secret = EXCLUDED.secret, rotated_at = NOW()
            """,
            user.user_id, secret,
        )
    token = make_feed_token(user.user_id, secret)
    return FeedInfo(
        token=token,
        feed_path=f"{FEED_PATH}?token={token}",
        rotated_at=datetime.now(timezone.utc).isoformat(),
    )


@user_router.get("/providers", response_model=ProvidersOut)
async def calendar_providers(user: CurrentUser = Depends(get_current_user)):
    """Which OAuth calendar connections are provisioned. The frontend renders a
    "Connect Google Calendar / Connect Outlook" button ONLY for configured
    providers — nothing renders locally where the keys are unset."""
    s = get_settings()
    return ProvidersOut(
        google_configured=bool(s.google_calendar_client_id and s.google_calendar_client_secret),
        outlook_configured=bool(s.ms_graph_client_id and s.ms_graph_client_secret),
        demo_available=bool(s.calendar_fake_provider) and s.app_env != "production",
    )


# ---------------------------------------------------------------------------
# The public feed — token is the credential
# ---------------------------------------------------------------------------

def _describe(row) -> str:
    bits: list[str] = []
    if row["applicant_name"] and row["viewer_role"] == "employer":
        bits.append(f"Interview with {row['applicant_name']}.")
    elif row["employer_name"]:
        bits.append(f"Interview with {row['employer_name']}.")
    if row["interviewer_name"]:
        who = row["interviewer_name"]
        if row["interviewer_title"]:
            who += f" ({row['interviewer_title']})"
        bits.append(f"Run by {who}.")
    if row["meeting_url"]:
        bits.append(f"Join: {row['meeting_url']}")
    if row["notes"]:
        bits.append(row["notes"])
    return "\n".join(bits)


@public_router.get(FEED_PATH, include_in_schema=True)
async def calendar_feed(token: str = Query(...)):
    """Per-user authenticated ICS feed. Any invalid, forged, or rotated-away
    token is an identical 401 — the token is the only credential."""
    user_id = parse_feed_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid calendar token.")

    async with get_db() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT secret FROM public.calendar_feed_secrets WHERE user_id = $1::uuid",
                user_id,
            )
        except Exception:
            # Malformed user_id (not a uuid) — same as a bad token.
            raise HTTPException(status_code=401, detail="Invalid calendar token.")
        if not row or not verify_feed_token(token, row["secret"]):
            raise HTTPException(status_code=401, detail="Invalid calendar token.")

        role = await conn.fetchval(
            "SELECT role FROM public.user_profiles WHERE user_id = $1::uuid", user_id,
        )
        if role not in ("applicant", "employer"):
            # Admins and unknown roles have no personal interview calendar.
            return _ics_response(build_feed_ics([]))

        # Upcoming confirmed interviews, plus recently cancelled ones that had
        # been confirmed (STATUS:CANCELLED propagates the removal to
        # subscribers that already imported the event).
        base_select = """
            SELECT s.id, s.start_at, s.end_at, s.status::text AS status,
                   s.location, s.meeting_url, s.notes,
                   s.interviewer_name, s.interviewer_title,
                   s.accepted_at,
                   COALESCE(j.title_normalized, j.title_raw) AS job_title,
                   e.name AS employer_name,
                   CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name,
                   $2::text AS viewer_role
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants ap  ON ap.id = a.applicant_id
              JOIN public.jobs j         ON j.id = a.job_id
              JOIN public.employers e    ON e.id = a.employer_id
             WHERE s.end_at > NOW() - INTERVAL '1 day'
               AND ( s.status = 'accepted'
                     OR (s.status = 'cancelled' AND s.accepted_at IS NOT NULL) )
        """
        if role == "applicant":
            rows = await conn.fetch(
                base_select + " AND ap.user_id = $1::uuid ORDER BY s.start_at",
                user_id, role,
            )
        else:
            rows = await conn.fetch(
                base_select
                + """ AND a.employer_id = (
                          SELECT employer_id FROM public.employer_contacts
                          WHERE user_id = $1::uuid LIMIT 1
                      ) ORDER BY s.start_at""",
                user_id, role,
            )

    events: list[FeedEvent] = []
    for r in rows:
        if role == "employer":
            summary = f"Interview: {(r['applicant_name'] or 'Applicant').strip() or 'Applicant'} ({r['job_title'] or 'Job'})"
        else:
            summary = f"Interview: {r['job_title'] or 'Job'}"
            if r["employer_name"]:
                summary += f" at {r['employer_name']}"
        events.append(
            FeedEvent(
                uid=f"interview-{r['id']}@skillednation",
                start_at=r["start_at"],
                end_at=r["end_at"],
                summary=summary,
                description=_describe(r),
                location=r["location"] or "",
                url=r["meeting_url"] or "",
                cancelled=(r["status"] == "cancelled"),
            )
        )
    return _ics_response(build_feed_ics(events))


def _ics_response(body: str) -> Response:
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="skilled-interviews.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )
