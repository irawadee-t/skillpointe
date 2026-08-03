"""
Employer team — who's in the organization, email invites, and the public
join-by-token flow.

Employer surface (auth required):
  GET  /employer/me/team/overview            — members + pending invites + my org role
  POST /employer/me/team/invites             — invite by email (owner/admin only)
  POST /employer/me/team/invites/{id}/resend — rotate token + re-send the email
  POST /employer/me/team/invites/{id}/revoke — kill a pending invite

Public surface (token-authenticated, no session):
  GET  /auth/join/{token}                    — invite status + company + inviter
  POST /auth/join/{token}/accept             — create the account and join
  POST /auth/join/{token}/accept-session     — signed-in user with the invited
                                               email accepts without a new account

Security model: the URL token is 32 random url-safe bytes; only its SHA-256
digest is stored. Invites expire after 7 days, are single-use, and resending
ROTATES the token (the old link dies). All mutations are audited.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import _get_admin_client, get_current_user, require_employer_only
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro.email_templates import branded_email
from app.skilled_pro.notifications import notify
from app.skilled_pro.senders import send_email
from app.util.audit import write_audit
from app.util.rate_limit import rate_limit_sensitive_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employer/me/team", tags=["employer"])
join_router = APIRouter(prefix="/auth/join", tags=["auth"])

INVITE_TTL_DAYS = 7
ORG_ROLES = ("owner", "admin", "member")
# Org roles allowed to manage the team (invite / resend / revoke).
MANAGER_ROLES = ("owner", "admin")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TeamMemberOut(BaseModel):
    contact_id: UUID
    name: Optional[str] = None
    email: str
    title: Optional[str] = None
    role: str
    is_primary: bool = False
    is_me: bool = False
    joined_at: str


class TeamInviteOut(BaseModel):
    id: UUID
    email: str
    role: str
    title: Optional[str] = None
    invited_by_email: Optional[str] = None
    sent_at: str
    expires_at: str
    expired: bool
    # TRUE when the invite email was actually handed to a mail provider on the
    # most recent send — honest delivery state, never assumed.
    email_sent: bool = False


class TeamOverviewOut(BaseModel):
    company_name: str
    my_role: str
    can_manage: bool
    members: list[TeamMemberOut]
    invites: list[TeamInviteOut]


class InviteCreateIn(BaseModel):
    email: EmailStr
    role: str = Field(default="member")
    title: Optional[str] = Field(default=None, max_length=200)


class JoinInfoOut(BaseModel):
    status: str                      # valid | expired | revoked | used
    company_name: Optional[str] = None
    inviter_name: Optional[str] = None
    invited_email: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = None
    expires_at: Optional[str] = None
    # TRUE when an auth account already exists for the invited email — the
    # join page shows "sign in to accept" instead of the create-account form.
    account_exists: bool = False


class JoinAcceptIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=8, max_length=200)


class JoinAcceptOut(BaseModel):
    email: str
    company_name: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _my_contact(conn, user: CurrentUser):
    row = await conn.fetchrow(
        """
        SELECT ec.id, ec.employer_id, ec.role, e.name AS company_name
          FROM public.employer_contacts ec
          JOIN public.employers e ON e.id = ec.employer_id
         WHERE ec.user_id = $1
        """,
        user.user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employer profile not found.")
    return row


def _require_manager(contact_row) -> None:
    if contact_row["role"] not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only owners and admins can manage the team.",
        )


def _invite_email_content(
    *, company: str, inviter: str, role: str, token: str, expires_at,
) -> tuple[str, str, str]:
    """Returns (subject, html, text) for the invite email."""
    join_url = f"{get_settings().web_origin}/join/{token}"
    role_line = {"owner": "Owner", "admin": "Admin", "member": "Member"}.get(role, role)
    subject = f"Join {company} on SKILLED Nation"
    html, text = branded_email(
        preheader=f"{inviter} invited you to {company}'s employer workspace.",
        heading=f"{inviter} invited you to join {company}",
        paragraphs=[
            f"{company} uses SKILLED Nation to hire skilled-trades workers. "
            "As part of the team you can review applications, schedule "
            "interviews, and message candidates.",
            "Accept the invite to set up your account. It takes about a minute.",
        ],
        cta_label=f"Join {company} on SKILLED Nation",
        cta_url=join_url,
        meta_lines=[
            f"Your role: {role_line}",
            f"This invite expires {expires_at:%B %-d, %Y}.",
        ],
        footer_note=(
            "If you weren't expecting this, you can ignore this email — "
            "nothing happens without you."
        ),
    )
    return subject, html, text


async def _load_invite_by_token(conn, token: str):
    return await conn.fetchrow(
        """
        SELECT i.id, i.employer_id, i.email, i.role, i.title,
               i.expires_at, i.accepted_at, i.revoked_at, i.invited_by,
               e.name AS company_name,
               u.email AS inviter_email,
               u.raw_user_meta_data->>'full_name' AS inviter_name
          FROM public.employer_invites i
          JOIN public.employers e ON e.id = i.employer_id
     LEFT JOIN auth.users u ON u.id = i.invited_by
         WHERE i.token_hash = $1
        """,
        _hash_token(token),
    )


def _invite_status(inv, conn_now) -> str:
    if inv["accepted_at"] is not None:
        return "used"
    if inv["revoked_at"] is not None:
        return "revoked"
    if inv["expires_at"] is not None and inv["expires_at"] <= conn_now:
        return "expired"
    return "valid"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=TeamOverviewOut)
async def team_overview(user: CurrentUser = Depends(require_employer_only)):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        members = await conn.fetch(
            """
            SELECT ec.id AS contact_id, ec.title, ec.role, ec.is_primary,
                   ec.created_at, u.email,
                   u.raw_user_meta_data->>'full_name' AS name,
                   (ec.user_id = $2::uuid) AS is_me
              FROM public.employer_contacts ec
              JOIN auth.users u ON u.id = ec.user_id
             WHERE ec.employer_id = $1
          ORDER BY is_me DESC, ec.created_at
            """,
            me["employer_id"], user.user_id,
        )
        invites = await conn.fetch(
            """
            SELECT i.id, i.email, i.role, i.title, i.last_sent_at, i.expires_at,
                   (i.expires_at <= NOW()) AS expired,
                   u.email AS invited_by_email
              FROM public.employer_invites i
         LEFT JOIN auth.users u ON u.id = i.invited_by
             WHERE i.employer_id = $1
               AND i.accepted_at IS NULL AND i.revoked_at IS NULL
          ORDER BY i.created_at DESC
            """,
            me["employer_id"],
        )
    return TeamOverviewOut(
        company_name=me["company_name"],
        my_role=me["role"],
        can_manage=me["role"] in MANAGER_ROLES,
        members=[
            TeamMemberOut(
                contact_id=m["contact_id"],
                name=(m["name"] or "").strip() or None,
                email=m["email"] or "",
                title=m["title"],
                role=m["role"],
                is_primary=m["is_primary"],
                is_me=m["is_me"],
                joined_at=m["created_at"].isoformat(),
            )
            for m in members
        ],
        invites=[
            TeamInviteOut(
                id=i["id"], email=i["email"], role=i["role"], title=i["title"],
                invited_by_email=i["invited_by_email"],
                sent_at=i["last_sent_at"].isoformat(),
                expires_at=i["expires_at"].isoformat(),
                expired=bool(i["expired"]),
                email_sent=True,  # listing = it was sent at least once; the
                                  # create/resend responses carry live state
            )
            for i in invites
        ],
    )


# ---------------------------------------------------------------------------
# Invite lifecycle
# ---------------------------------------------------------------------------

@router.post("/invites", response_model=TeamInviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteCreateIn, user: CurrentUser = Depends(require_employer_only)):
    if body.role not in ORG_ROLES:
        raise HTTPException(status_code=422, detail="Role must be owner, admin, or member.")
    email = body.email.strip().lower()

    async with get_db() as conn:
        me = await _my_contact(conn, user)
        _require_manager(me)

        # Already on the team?
        existing_member = await conn.fetchrow(
            """
            SELECT 1 FROM public.employer_contacts ec
              JOIN auth.users u ON u.id = ec.user_id
             WHERE ec.employer_id = $1 AND lower(u.email) = $2
            """,
            me["employer_id"], email,
        )
        if existing_member:
            raise HTTPException(status_code=409, detail="That person is already on your team.")

        # Registered under a different role (worker/admin) — joining would
        # cross role boundaries; be honest instead of failing at accept time.
        other_role = await conn.fetchval(
            """
            SELECT up.role::text FROM public.user_profiles up
              JOIN auth.users u ON u.id = up.user_id
             WHERE lower(u.email) = $1
            """,
            email,
        )
        if other_role and other_role != "employer":
            raise HTTPException(
                status_code=409,
                detail="That email already has a SKILLED Nation account with a "
                       "different role, so it can't join an employer workspace.",
            )

        active = await conn.fetchrow(
            """
            SELECT id FROM public.employer_invites
             WHERE employer_id = $1 AND lower(email) = $2
               AND accepted_at IS NULL AND revoked_at IS NULL
            """,
            me["employer_id"], email,
        )
        if active:
            raise HTTPException(
                status_code=409,
                detail="There's already a pending invite for that email — resend or revoke it below.",
            )

        token = secrets.token_urlsafe(32)
        inviter_display = await conn.fetchval(
            "SELECT COALESCE(NULLIF(raw_user_meta_data->>'full_name', ''), email) FROM auth.users WHERE id = $1",
            user.user_id,
        ) or user.email

        row = await conn.fetchrow(
            """
            INSERT INTO public.employer_invites
              (employer_id, email, role, title, token_hash, invited_by, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW() + make_interval(days => $7))
            RETURNING id, email, role, title, last_sent_at, expires_at
            """,
            me["employer_id"], email, body.role,
            (body.title or "").strip() or None,
            _hash_token(token), user.user_id, INVITE_TTL_DAYS,
        )

        await write_audit(
            conn,
            action="team_invite_sent",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_invite", entity_id=str(row["id"]),
            after={"email": email, "org_role": body.role, "employer_id": str(me["employer_id"])},
        )

    subject, html, text = _invite_email_content(
        company=me["company_name"], inviter=inviter_display,
        role=body.role, token=token, expires_at=row["expires_at"],
    )
    result = await send_email(email, subject, text, html=html)
    if not result.delivered:
        logger.warning("Team invite email to %s not delivered: %s", email, result.detail)

    return TeamInviteOut(
        id=row["id"], email=row["email"], role=row["role"], title=row["title"],
        invited_by_email=user.email,
        sent_at=row["last_sent_at"].isoformat(),
        expires_at=row["expires_at"].isoformat(),
        expired=False,
        email_sent=result.delivered,
    )


@router.post("/invites/{invite_id}/resend", response_model=TeamInviteOut)
async def resend_invite(invite_id: UUID, user: CurrentUser = Depends(require_employer_only)):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        _require_manager(me)
        inv = await conn.fetchrow(
            "SELECT id, email, role, title, accepted_at, revoked_at FROM public.employer_invites WHERE id = $1 AND employer_id = $2",
            invite_id, me["employer_id"],
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invite not found.")
        if inv["accepted_at"] is not None:
            raise HTTPException(status_code=409, detail="That invite was already accepted.")
        if inv["revoked_at"] is not None:
            raise HTTPException(status_code=409, detail="That invite was revoked. Send a fresh one instead.")

        # Rotate the token — the previously emailed link stops working.
        token = secrets.token_urlsafe(32)
        row = await conn.fetchrow(
            """
            UPDATE public.employer_invites
               SET token_hash = $2,
                   last_sent_at = NOW(),
                   expires_at = NOW() + make_interval(days => $3)
             WHERE id = $1
            RETURNING id, email, role, title, last_sent_at, expires_at
            """,
            invite_id, _hash_token(token), INVITE_TTL_DAYS,
        )
        inviter_display = await conn.fetchval(
            "SELECT COALESCE(NULLIF(raw_user_meta_data->>'full_name', ''), email) FROM auth.users WHERE id = $1",
            user.user_id,
        ) or user.email
        await write_audit(
            conn,
            action="team_invite_resent",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_invite", entity_id=str(invite_id),
            metadata={"email": row["email"]},
        )

    subject, html, text = _invite_email_content(
        company=me["company_name"], inviter=inviter_display,
        role=row["role"], token=token, expires_at=row["expires_at"],
    )
    result = await send_email(row["email"], subject, text, html=html)
    if not result.delivered:
        logger.warning("Team invite resend to %s not delivered: %s", row["email"], result.detail)

    return TeamInviteOut(
        id=row["id"], email=row["email"], role=row["role"], title=row["title"],
        invited_by_email=user.email,
        sent_at=row["last_sent_at"].isoformat(),
        expires_at=row["expires_at"].isoformat(),
        expired=False,
        email_sent=result.delivered,
    )


@router.post("/invites/{invite_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: UUID, user: CurrentUser = Depends(require_employer_only)):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        _require_manager(me)
        upd = await conn.execute(
            """
            UPDATE public.employer_invites
               SET revoked_at = NOW(), revoked_by = $3::uuid
             WHERE id = $1 AND employer_id = $2
               AND accepted_at IS NULL AND revoked_at IS NULL
            """,
            invite_id, me["employer_id"], user.user_id,
        )
        if upd.endswith(" 0"):
            raise HTTPException(status_code=404, detail="No pending invite to revoke.")
        await write_audit(
            conn,
            action="team_invite_revoked",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_invite", entity_id=str(invite_id),
        )


# ---------------------------------------------------------------------------
# Public join flow
# ---------------------------------------------------------------------------

@join_router.get(
    "/{token}",
    response_model=JoinInfoOut,
    dependencies=[Depends(rate_limit_sensitive_ip("team_join_info"))],
)
async def join_info(token: str):
    async with get_db() as conn:
        inv = await _load_invite_by_token(conn, token)
        if not inv:
            raise HTTPException(status_code=404, detail="This invite link isn't valid.")
        now = await conn.fetchval("SELECT NOW()")
        account_exists = bool(
            await conn.fetchval(
                "SELECT 1 FROM auth.users WHERE lower(email) = lower($1)", inv["email"],
            )
        )
    return JoinInfoOut(
        status=_invite_status(inv, now),
        company_name=inv["company_name"],
        inviter_name=(inv["inviter_name"] or "").strip() or inv["inviter_email"],
        invited_email=inv["email"],
        role=inv["role"],
        title=inv["title"],
        expires_at=inv["expires_at"].isoformat() if inv["expires_at"] else None,
        account_exists=account_exists,
    )


async def _finalize_join(conn, inv, *, user_id: str, actor_email: str) -> None:
    """Create the contact link, mark the invite used, notify + audit.

    Caller has already validated the invite and created/verified the auth
    user. Runs inside the caller's transaction.
    """
    await conn.execute(
        """
        INSERT INTO public.employer_contacts (user_id, employer_id, title, role, is_primary)
        VALUES ($1, $2, $3, $4, FALSE)
        """,
        user_id, inv["employer_id"], inv["title"], inv["role"],
    )
    upd = await conn.execute(
        """
        UPDATE public.employer_invites
           SET accepted_at = NOW(), accepted_user_id = $2::uuid
         WHERE id = $1 AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > NOW()
        """,
        inv["id"], user_id,
    )
    if upd.endswith(" 0"):
        # Race: someone accepted/revoked between our check and now.
        raise HTTPException(status_code=409, detail="This invite was just used or revoked.")

    if inv["invited_by"]:
        await notify(
            conn,
            recipient_user_id=str(inv["invited_by"]),
            kind="team_invite_accepted",
            title=f"{actor_email} joined {inv['company_name']}",
            body="They accepted your invite and can now work applications with you.",
            link_href="/employer/team",
            payload={"invite_id": str(inv["id"]), "email": actor_email},
            dedupe_key=f"team_invite_accepted:{inv['id']}",
        )
    await write_audit(
        conn,
        action="team_invite_accepted",
        actor_id=user_id, actor_role="employer",
        entity_type="employer_invite", entity_id=str(inv["id"]),
        after={"email": actor_email, "org_role": inv["role"], "employer_id": str(inv["employer_id"])},
    )


@join_router.post(
    "/{token}/accept",
    response_model=JoinAcceptOut,
    dependencies=[Depends(rate_limit_sensitive_ip("team_join_accept"))],
)
async def join_accept(token: str, body: JoinAcceptIn):
    """Create a fresh account from a valid invite and link it to the employer."""
    async with get_db() as conn:
        inv = await _load_invite_by_token(conn, token)
        if not inv:
            raise HTTPException(status_code=404, detail="This invite link isn't valid.")
        now = await conn.fetchval("SELECT NOW()")
        st = _invite_status(inv, now)
        if st != "valid":
            detail = {
                "used": "This invite was already used.",
                "revoked": "This invite was revoked by the team.",
                "expired": "This invite expired. Ask your team to send a new one.",
            }[st]
            raise HTTPException(status_code=410, detail=detail)

        existing = await conn.fetchval(
            "SELECT id::text FROM auth.users WHERE lower(email) = lower($1)", inv["email"],
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Sign in to accept the invite.",
            )

    # Create the auth user OUTSIDE the DB transaction (external API call).
    client = _get_admin_client()
    try:
        created = client.auth.admin.create_user(
            {
                "email": inv["email"],
                "password": body.password,
                "email_confirm": True,  # the invite email itself proved inbox ownership
                "user_metadata": {"full_name": body.full_name.strip()},
                "app_metadata": {"role": "employer"},
            }
        )
        new_user_id = created.user.id
    except Exception as exc:
        logger.error("Join accept: auth user create failed for %s: %s", inv["email"], exc)
        raise HTTPException(status_code=502, detail="Could not create the account. Try again in a moment.")

    try:
        async with get_db() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, 'employer') ON CONFLICT (user_id) DO NOTHING",
                    new_user_id,
                )
                await _finalize_join(conn, inv, user_id=str(new_user_id), actor_email=inv["email"])
    except HTTPException:
        # Roll the orphaned auth user back so a retry isn't wedged on
        # "account already exists".
        try:
            client.auth.admin.delete_user(new_user_id)
        except Exception:
            logger.error("Could not clean up auth user %s after failed join", new_user_id)
        raise

    return JoinAcceptOut(email=inv["email"], company_name=inv["company_name"])


@join_router.post(
    "/{token}/accept-session",
    response_model=JoinAcceptOut,
    dependencies=[Depends(rate_limit_sensitive_ip("team_join_accept"))],
)
async def join_accept_session(
    token: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """A signed-in user whose email matches the invite accepts without
    creating a new account."""
    async with get_db() as conn:
        inv = await _load_invite_by_token(conn, token)
        if not inv:
            raise HTTPException(status_code=404, detail="This invite link isn't valid.")
        now = await conn.fetchval("SELECT NOW()")
        st = _invite_status(inv, now)
        if st != "valid":
            detail = {
                "used": "This invite was already used.",
                "revoked": "This invite was revoked by the team.",
                "expired": "This invite expired. Ask your team to send a new one.",
            }[st]
            raise HTTPException(status_code=410, detail=detail)
        if (user.email or "").lower() != inv["email"].lower():
            raise HTTPException(
                status_code=403,
                detail=f"This invite is for {inv['email']}. You're signed in as {user.email}.",
            )
        if user.role != "employer":
            raise HTTPException(
                status_code=409,
                detail="Your account isn't an employer account, so it can't join an employer workspace.",
            )
        already = await conn.fetchrow(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1", user.user_id,
        )
        if already:
            if str(already["employer_id"]) == str(inv["employer_id"]):
                raise HTTPException(status_code=409, detail="You're already on this team.")
            raise HTTPException(
                status_code=409,
                detail="Your account is already linked to another company workspace.",
            )
        async with conn.transaction():
            await _finalize_join(conn, inv, user_id=user.user_id, actor_email=user.email)

    return JoinAcceptOut(email=inv["email"], company_name=inv["company_name"])
