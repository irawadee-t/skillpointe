"""
Account recovery + change flows.

Email change:
  POST /me/account/email/change     { new_email }
    → sends 6-digit token to new_email (stubbed via notifications; production uses Resend)
  POST /me/account/email/confirm    { token }
    → applies change (updates auth.users.email via Supabase admin API)

Phone change:
  POST /me/account/phone/change     { new_phone }
    → sends 6-digit token via SMS stub
  POST /me/account/phone/confirm    { token }

SKILLED ID recovery (partner-verified users who lost access):
  POST /me/account/skilled-id/recover   { reason }
    → opens admin review ticket
  GET  /admin/account-recovery                — admin queue
  POST /admin/account-recovery/{id}/resolve   { note, granted }
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.schemas.account import (
    CancelDeletionResponse,
    DeleteAccountRequest,
    DeleteAccountResponse,
    HardDeleteResponse,
)
from app.skilled_pro.notifications import notify
from app.skilled_pro.senders import send_email, send_sms
from app.util.audit import write_audit
from app.util.rate_limit import rate_limit_sensitive

logger = logging.getLogger(__name__)

user_router  = APIRouter(prefix="/me/account", tags=["me"])
admin_router = APIRouter(prefix="/admin/account-recovery", tags=["admin"])

_TOKEN_TTL_MIN = 20
# After this many wrong codes the pending request is burned and a new one must
# be requested — caps brute-force at a handful of tries per issued code.
_MAX_CONFIRM_ATTEMPTS = 5


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _deliver_code(channel: str, target: str, token: str) -> None:
    """Deliver a confirmation code out-of-band to the target email/phone.

    - Sends via Resend (email) or Twilio (SMS) when those providers are
      configured — the real, secure path.
    - Logs the code to the console ONLY in local dev, and only when no real
      provider delivered it, so a developer can still complete the flow. The
      code is never logged in staging/production.
    """
    msg = (
        f"Your SkillPointe confirmation code is {token}. "
        f"It expires in {_TOKEN_TTL_MIN} minutes. If you didn't request this, ignore this message."
    )
    if channel == "email":
        result = await send_email(target, "Your SkillPointe confirmation code", msg)
    else:
        result = await send_sms(target, msg)

    if not result.delivered and get_settings().is_local:
        logger.info("[%s dev] Code for %s: %s", channel, target, token)
    elif not result.delivered and not result.skipped:
        # Real provider was configured but failed — surface for ops, no code.
        logger.error("Confirmation code delivery failed for %s via %s: %s", target, channel, result.detail)


async def _consume_confirmation(conn, user_id, kind: str, token: str):
    """Look up the latest pending change request for (user, kind) and validate
    the supplied code with a per-request attempt lockout. Returns the row on
    success; raises HTTPException otherwise. Fetching by (user, kind) rather than
    by token hash is what lets us count wrong guesses and lock the request."""
    row = await conn.fetchrow(
        "SELECT id, new_value, expires_at, status, token_hash, attempts "
        "FROM public.account_change_requests "
        "WHERE user_id = $1 AND kind = $2 AND status = 'pending_confirmation' "
        "ORDER BY created_at DESC LIMIT 1",
        user_id, kind,
    )
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired code.")
    if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
        await conn.execute("UPDATE public.account_change_requests SET status = 'expired' WHERE id = $1", row["id"])
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")
    if row["attempts"] >= _MAX_CONFIRM_ATTEMPTS:
        await conn.execute("UPDATE public.account_change_requests SET status = 'cancelled' WHERE id = $1", row["id"])
        raise HTTPException(status_code=429, detail="Too many incorrect codes. Request a new one.")
    if row["token_hash"] != _hash(token.strip()):
        await conn.execute("UPDATE public.account_change_requests SET attempts = attempts + 1 WHERE id = $1", row["id"])
        remaining = max(0, _MAX_CONFIRM_ATTEMPTS - int(row["attempts"]) - 1)
        raise HTTPException(status_code=400, detail=f"Incorrect code. {remaining} attempt(s) left.")
    return row


def _mint_token() -> str:
    """Six-digit numeric code — friendlier on trades workers' phones than a UUID."""
    return f"{secrets.randbelow(1_000_000):06d}"


# ---------------------------------------------------------------------------
class EmailChangeIn(BaseModel):
    new_email: EmailStr


class PhoneChangeIn(BaseModel):
    new_phone: str = Field(..., min_length=7, max_length=32)


class TokenIn(BaseModel):
    token: str = Field(..., min_length=4, max_length=32)


class RecoveryIn(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class ChangeRequestOut(BaseModel):
    id: UUID
    kind: str
    status: str
    created_at: str
    expires_at: Optional[str] = None
    masked_target: Optional[str] = None


class RecoveryTicketOut(BaseModel):
    id: UUID
    user_id: UUID
    kind: str
    status: str
    reason: Optional[str] = None
    created_at: str
    reviewer_user_id: Optional[UUID] = None
    reviewer_note: Optional[str] = None
    user_email: Optional[str] = None


# ---------------------------------------------------------------------------
# User: email
# ---------------------------------------------------------------------------

@user_router.post(
    "/email/change",
    response_model=ChangeRequestOut,
    dependencies=[Depends(rate_limit_sensitive("email_change"))],
)
async def request_email_change(
    body: EmailChangeIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    token = _mint_token()
    async with get_db() as conn:
        await conn.execute(
            "UPDATE public.account_change_requests SET status = 'cancelled' WHERE user_id = $1 AND kind = 'email_change' AND status = 'pending_confirmation'",
            user.user_id,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO public.account_change_requests
              (user_id, kind, new_value, token_hash, ip_address, user_agent, expires_at)
            VALUES ($1, 'email_change', $2, $3, $4, $5, NOW() + ($6 || ' minutes')::interval)
            RETURNING id, created_at, expires_at
            """,
            user.user_id, str(body.new_email), _hash(token),
            (request.client.host if request.client else None),
            request.headers.get("user-agent"),
            str(_TOKEN_TTL_MIN),
        )
        # The code goes ONLY to the new address, out-of-band (email). It is
        # deliberately NOT written to an in-app notification — surfacing a
        # confirmation code inside the already-authenticated session would
        # defeat the point of confirming a second factor.
        await _deliver_code("email", str(body.new_email), token)

    return _out(row["id"], "email_change", "pending_confirmation", row["created_at"], row["expires_at"], _mask_email(str(body.new_email)))


@user_router.post(
    "/email/confirm",
    response_model=ChangeRequestOut,
    dependencies=[Depends(rate_limit_sensitive("email_confirm"))],
)
async def confirm_email_change(body: TokenIn, user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        row = await _consume_confirmation(conn, user.user_id, "email_change", body.token)

        # Supabase Admin update
        from app.auth.dependencies import _get_admin_client
        try:
            supabase = _get_admin_client()
            supabase.auth.admin.update_user_by_id(user.user_id, {"email": row["new_value"], "email_confirm": True})
        except Exception as e:
            logger.exception("Supabase email update failed")
            raise HTTPException(status_code=500, detail=f"Could not apply change: {e}")

        await conn.execute("UPDATE public.account_change_requests SET status = 'confirmed', confirmed_at = NOW() WHERE id = $1", row["id"])
        # Also sync applicants.email / employer_contacts.email if present
        await conn.execute("UPDATE public.applicants SET email = $2 WHERE user_id = $1", user.user_id, row["new_value"])
        await conn.execute("UPDATE public.employer_contacts SET email = $2 WHERE user_id = $1", user.user_id, row["new_value"])

    return _out(row["id"], "email_change", "confirmed", None, None, _mask_email(row["new_value"]))


# ---------------------------------------------------------------------------
# User: phone
# ---------------------------------------------------------------------------

@user_router.post(
    "/phone/change",
    response_model=ChangeRequestOut,
    dependencies=[Depends(rate_limit_sensitive("phone_change"))],
)
async def request_phone_change(
    body: PhoneChangeIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    token = _mint_token()
    async with get_db() as conn:
        await conn.execute(
            "UPDATE public.account_change_requests SET status = 'cancelled' WHERE user_id = $1 AND kind = 'phone_change' AND status = 'pending_confirmation'",
            user.user_id,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO public.account_change_requests
              (user_id, kind, new_value, token_hash, ip_address, user_agent, expires_at)
            VALUES ($1, 'phone_change', $2, $3, $4, $5, NOW() + ($6 || ' minutes')::interval)
            RETURNING id, created_at, expires_at
            """,
            user.user_id, body.new_phone.strip(), _hash(token),
            (request.client.host if request.client else None),
            request.headers.get("user-agent"),
            str(_TOKEN_TTL_MIN),
        )
        # Code goes out-of-band via SMS only — never as an in-app notification
        # to the logged-in session (see the email flow above for why).
        await _deliver_code("sms", body.new_phone, token)

    return _out(row["id"], "phone_change", "pending_confirmation", row["created_at"], row["expires_at"], _mask_phone(body.new_phone))


@user_router.post(
    "/phone/confirm",
    response_model=ChangeRequestOut,
    dependencies=[Depends(rate_limit_sensitive("phone_confirm"))],
)
async def confirm_phone_change(body: TokenIn, user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        row = await _consume_confirmation(conn, user.user_id, "phone_change", body.token)
        await conn.execute("UPDATE public.account_change_requests SET status = 'confirmed', confirmed_at = NOW() WHERE id = $1", row["id"])
        # Store on applicant/employer contact profile
        await conn.execute("UPDATE public.applicants SET phone = $2 WHERE user_id = $1", user.user_id, row["new_value"])
        await conn.execute("UPDATE public.employer_contacts SET phone = $2 WHERE user_id = $1", user.user_id, row["new_value"])
    return _out(row["id"], "phone_change", "confirmed", None, None, _mask_phone(row["new_value"]))


# ---------------------------------------------------------------------------
# SKILLED ID recovery — opens an admin ticket rather than self-serve
# ---------------------------------------------------------------------------

@user_router.post("/skilled-id/recover", response_model=ChangeRequestOut)
async def start_skilled_id_recovery(
    body: RecoveryIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.account_change_requests
              (user_id, kind, status, reason, ip_address, user_agent)
            VALUES ($1, 'skilled_id_recovery', 'admin_review', $2, $3, $4)
            RETURNING id, created_at
            """,
            user.user_id, body.reason.strip(),
            (request.client.host if request.client else None),
            request.headers.get("user-agent"),
        )
        await notify(
            conn,
            recipient_role="admin",
            kind="account_recovery_ticket",
            title="SKILLED ID recovery request",
            body=body.reason[:180],
            link_href=f"/admin/account-recovery/{row['id']}",
            payload={"ticket_id": str(row["id"]), "user_id": user.user_id},
        )
    return _out(row["id"], "skilled_id_recovery", "admin_review", row["created_at"], None, None)


# ---------------------------------------------------------------------------
# Admin: recovery queue
# ---------------------------------------------------------------------------

@admin_router.get("", response_model=list[RecoveryTicketOut])
async def list_recovery_tickets(_: CurrentUser = Depends(require_admin)):
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT r.id, r.user_id, r.kind::text AS kind, r.status::text AS status,
                   r.reason, r.created_at, r.reviewer_user_id, r.reviewer_note,
                   u.email AS user_email
              FROM public.account_change_requests r
         LEFT JOIN auth.users u ON u.id = r.user_id
             WHERE r.kind = 'skilled_id_recovery'
          ORDER BY (r.status = 'admin_review') DESC, r.created_at DESC
             LIMIT 100
            """,
        )
    return [
        RecoveryTicketOut(
            id=r["id"], user_id=r["user_id"], kind=r["kind"], status=r["status"],
            reason=r["reason"], created_at=r["created_at"].isoformat(),
            reviewer_user_id=r["reviewer_user_id"], reviewer_note=r["reviewer_note"],
            user_email=r["user_email"],
        )
        for r in rows
    ]


class ResolveIn(BaseModel):
    granted: bool
    note: str = Field(..., min_length=3, max_length=1000)


@admin_router.post("/{ticket_id}/resolve", response_model=RecoveryTicketOut)
async def resolve_ticket(ticket_id: UUID, body: ResolveIn, user: CurrentUser = Depends(require_admin)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.account_change_requests
               SET status = 'admin_resolved', reviewer_user_id = $2, reviewer_note = $3, confirmed_at = NOW()
             WHERE id = $1 AND kind = 'skilled_id_recovery' AND status = 'admin_review'
         RETURNING id, user_id, kind::text AS kind, status::text AS status, reason, created_at, reviewer_user_id, reviewer_note
            """,
            ticket_id, user.user_id, f"[{'GRANTED' if body.granted else 'DENIED'}] {body.note}",
        )
        if not row:
            raise HTTPException(status_code=409, detail="Ticket not open for review.")
        # Audit: an admin resolved an account-recovery ticket (grant/deny access).
        await write_audit(
            conn,
            action="account_recovery_granted" if body.granted else "account_recovery_denied",
            actor_id=user.user_id,
            actor_role=user.role,
            entity_type="account_change_requests",
            entity_id=str(ticket_id),
            metadata={"granted": body.granted, "note": (body.note or "")[:2000]},
        )
        # Notify the user
        # Templated body — the admin's note is never the raw body copy; it
        # appears (if at all) as a labeled detail line after the template.
        resolved_body = (
            "Your account recovery request was approved. Sign in to continue."
            if body.granted
            else "Your account recovery request was not approved."
        )
        if body.note and body.note.strip():
            resolved_body += f' Reviewer note: "{body.note.strip()[:300]}"'
        await notify(
            conn,
            recipient_user_id=str(row["user_id"]),
            kind="account_recovery_resolved",
            title=f"Account recovery {'approved' if body.granted else 'denied'}",
            body=resolved_body,
            link_href="/account/settings",
            payload={"ticket_id": str(ticket_id), "granted": body.granted},
            dedupe_key=f"account_recovery_resolved:{ticket_id}",
        )
    return RecoveryTicketOut(
        id=row["id"], user_id=row["user_id"], kind=row["kind"], status=row["status"],
        reason=row["reason"], created_at=row["created_at"].isoformat(),
        reviewer_user_id=row["reviewer_user_id"], reviewer_note=row["reviewer_note"],
    )


# ---------------------------------------------------------------------------
# DSAR — self-serve data export (GDPR Art. 15 / CCPA right to know)
# ---------------------------------------------------------------------------

# (table, key column) for the user's own data. Applicant/employer-keyed tables
# are resolved via the applicant/employer_contact id looked up from user_id.
_EXPORT_USER_KEYED = [
    "user_profiles", "notifications", "chat_sessions", "chat_messages",
    "conversations", "direct_messages", "account_change_requests",
]
_EXPORT_APPLICANT_KEYED = [
    "credentials", "applications", "saved_jobs", "matches",
    "match_dimension_scores", "extracted_applicant_signals",
    "applicant_resume_uploads", "hire_outcomes",
]


@user_router.get("/export")
async def export_my_data(request: Request, user: CurrentUser = Depends(get_current_user)):
    """Return a machine-readable export of all data held about the requester.

    Satisfies GDPR Article 15 (right of access) and CCPA "right to know" as a
    self-serve, user-initiated download. The export is itself audit-logged."""
    export: dict[str, object] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.user_id,
        "email": user.email,
        "data": {},
    }
    data: dict[str, object] = export["data"]  # type: ignore[assignment]

    async with get_db() as conn:
        applicant_id = await conn.fetchval(
            "SELECT id::text FROM public.applicants WHERE user_id = $1", user.user_id
        )

        async def _dump(table: str, where_col: str, value) -> None:
            if value is None:
                return
            try:
                rows = await conn.fetch(
                    f"SELECT * FROM public.{table} WHERE {where_col} = $1::uuid", value
                )
                # asyncpg Records → plain dicts; str() default handles dates/uuids.
                dicts = [dict(r) for r in rows]
                # Decrypt any at-rest-encrypted PII so the export is readable.
                if table == "applicant_resume_uploads":
                    from app.util.crypto import decrypt_str
                    for d in dicts:
                        if "raw_text" in d:
                            d["raw_text"] = decrypt_str(d["raw_text"])
                data[table] = dicts
            except Exception as exc:  # table may not have that column
                logger.debug("Export skipped %s.%s: %s", table, where_col, exc)

        for t in _EXPORT_USER_KEYED:
            await _dump(t, "user_id", user.user_id)
        # The applicants profile row itself is keyed by user_id.
        await _dump("applicants", "user_id", user.user_id)
        for t in _EXPORT_APPLICANT_KEYED:
            await _dump(t, "applicant_id", applicant_id)

        await write_audit(
            conn,
            action="data_export_requested",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="user_profiles", entity_id=user.user_id,
            ip_address=request.client.host if request.client else None,
            metadata={"tables": list(data.keys())},
        )

    # default=str so uuids/dates/decimals serialize cleanly.
    import json as _json

    from fastapi.responses import JSONResponse
    return JSONResponse(content=_json.loads(_json.dumps(export, default=str)))


# ---------------------------------------------------------------------------
def _out(id_, kind, status, created_at, expires_at, target):
    return ChangeRequestOut(
        id=id_,
        kind=kind,
        status=status,
        created_at=(created_at.isoformat() if created_at else datetime.now(timezone.utc).isoformat()),
        expires_at=expires_at.isoformat() if expires_at else None,
        masked_target=target,
    )


def _mask_email(e: str) -> str:
    if "@" not in e: return e
    local, domain = e.split("@", 1)
    if len(local) <= 2:
        return "•" * len(local) + "@" + domain
    return local[0] + "•" * (len(local) - 2) + local[-1] + "@" + domain


def _mask_phone(p: str) -> str:
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) < 4: return "•" * len(p)
    return "•" * (len(digits) - 4) + digits[-4:]


# ---------------------------------------------------------------------------
# GDPR / CCPA — Data deletion
# ---------------------------------------------------------------------------

# Tables cleared during hard-delete. Order matters: FK-dependent rows first.
# audit_logs is intentionally NOT listed — it stays as an immutable record.
_DELETE_CASCADE_TABLES: list[str] = [
    "direct_messages",
    "conversations",
    "chat_messages",
    "chat_sessions",
    "engagement_events",
    "saved_jobs",
    "match_dimension_scores",
    "matches",
    "extracted_applicant_signals",
    "applicant_resume_uploads",
    "credentials",
    "applications",
    "notifications",
    "account_change_requests",
    "employer_outreach",
    "hire_outcomes",
    "employer_contacts",
    "applicants",
    "user_profiles",
]

_HARD_DELETE_GRACE_DAYS = 7


@user_router.post("/delete-request", response_model=DeleteAccountResponse)
async def request_account_deletion(
    body: DeleteAccountRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> DeleteAccountResponse:
    """
    Schedule the current user's account for hard deletion after a 7-day grace
    period. Requires password re-authentication as a foot-gun guard.

    On success, `user_profiles.pending_deletion_at` is set. A scheduled worker
    (see app.worker.scheduler) hard-deletes accounts whose grace has elapsed.
    """
    from supabase import create_client

    settings = get_settings()

    # Re-auth via Supabase — verify the password matches the current session.
    try:
        anon = create_client(settings.supabase_url, settings.supabase_anon_key)
        anon.auth.sign_in_with_password({"email": user.email, "password": body.password})
    except Exception as exc:
        logger.info("delete-request password re-auth failed for %s: %s", user.user_id, exc)
        raise HTTPException(status_code=401, detail="Password re-authentication failed.")

    now = datetime.now(timezone.utc)
    hard_delete_after = now + timedelta(days=_HARD_DELETE_GRACE_DAYS)

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.user_profiles
               SET pending_deletion_at = NOW()
             WHERE user_id = $1
         RETURNING pending_deletion_at
            """,
            user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found.")

        await conn.execute(
            """
            INSERT INTO public.audit_logs
              (actor_id, actor_role, action, entity_type, entity_id, ip_address, metadata)
            VALUES ($1::uuid, 'user', 'account_deletion_requested', 'user_profiles', $1::uuid, $2, $3::jsonb)
            """,
            user.user_id,
            request.client.host if request.client else None,
            {
                "reason": (body.reason or "").strip()[:2000] or None,
                "hard_delete_after": hard_delete_after.isoformat(),
            },
        )
        await notify(
            conn,
            recipient_user_id=user.user_id,
            kind="account_deletion_scheduled",
            title="Your SkillPointe account is scheduled for deletion",
            body=(
                f"We received your deletion request. Your data will be permanently "
                f"removed on {hard_delete_after.strftime('%b %d, %Y')}. "
                f"Sign in and cancel any time before then to keep your account."
            ),
            payload={"hard_delete_after": hard_delete_after.isoformat()},
        )

    return DeleteAccountResponse(
        status="pending",
        pending_deletion_at=row["pending_deletion_at"],
        hard_delete_after=hard_delete_after,
        message=(
            "Account marked for deletion. You have "
            f"{_HARD_DELETE_GRACE_DAYS} days to cancel by signing in and calling "
            "the cancel endpoint."
        ),
    )


@user_router.post("/cancel-deletion", response_model=CancelDeletionResponse)
async def cancel_account_deletion(
    user: CurrentUser = Depends(get_current_user),
) -> CancelDeletionResponse:
    """Clear a pending deletion request during the grace window."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.user_profiles
               SET pending_deletion_at = NULL
             WHERE user_id = $1 AND pending_deletion_at IS NOT NULL
         RETURNING pending_deletion_at
            """,
            user.user_id,
        )
        if not row:
            raise HTTPException(status_code=409, detail="No pending deletion to cancel.")
        await conn.execute(
            """
            INSERT INTO public.audit_logs (actor_id, actor_role, action, entity_type, entity_id)
            VALUES ($1::uuid, 'user', 'account_deletion_cancelled', 'user_profiles', $1::uuid)
            """,
            user.user_id,
        )
    return CancelDeletionResponse(
        status="cancelled",
        message="Deletion request cancelled. Your account is active.",
    )


async def _hard_delete_user(conn, user_id: str) -> list[str]:
    """Cascade-delete all app data for a user across the configured tables.

    Deletion is executed in a single transaction so an interruption leaves the
    row set consistent. audit_logs is preserved as an immutable record.
    """
    cleared: list[str] = []
    async with conn.transaction():
        for table in _DELETE_CASCADE_TABLES:
            # Some tables key on `user_id`, others on `applicant_id`/`employer_id`
            # via joins — we defer to Postgres FK cascades where they exist and
            # explicitly clear user-keyed rows here.
            #
            # Each DELETE runs in its OWN savepoint (nested transaction): a table
            # without a `user_id` column raises, and in Postgres a raised
            # statement poisons the whole transaction until rollback. The
            # savepoint contains that failure so the remaining deletes — and the
            # audit tombstone below — still commit.
            try:
                async with conn.transaction():
                    await conn.execute(
                        f"DELETE FROM public.{table} WHERE user_id = $1",
                        user_id,
                    )
                cleared.append(table)
            except Exception as exc:
                # Table may not have user_id (e.g. matches, engagement_events);
                # rely on the cascading FKs from applicants/employer_contacts.
                logger.debug("Skipping %s (no direct user_id column?): %s", table, exc)

        # Finally, remove the Supabase auth user so the login is invalidated.
        from app.auth.dependencies import _get_admin_client
        try:
            supabase = _get_admin_client()
            supabase.auth.admin.delete_user(user_id)
            cleared.append("auth.users")
        except Exception as exc:
            logger.exception("Supabase auth delete failed for %s: %s", user_id, exc)

        # audit_logs is preserved — write a final tombstone.
        await conn.execute(
            """
            INSERT INTO public.audit_logs (actor_id, actor_role, action, entity_type, entity_id, metadata)
            VALUES (NULL, 'system', 'account_hard_deleted', 'user_profiles', $1::uuid, $2::jsonb)
            """,
            user_id,
            {"tables_cleared": cleared},
        )
    return cleared


@admin_router.delete(
    "/user/{user_id}",
    response_model=HardDeleteResponse,
)
async def admin_hard_delete_user(
    user_id: str,
    _: CurrentUser = Depends(require_admin),
) -> HardDeleteResponse:
    """Admin-only: hard-delete a user's account immediately (bypasses grace)."""
    async with get_db() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM public.user_profiles WHERE user_id = $1", user_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="User profile not found.")
        cleared = await _hard_delete_user(conn, user_id)
    return HardDeleteResponse(
        user_id=user_id,
        tables_cleared=cleared,
        completed_at=datetime.now(timezone.utc),
    )


async def sweep_expired_deletions() -> int:
    """
    Weekly worker task: hard-delete users whose pending_deletion_at is older
    than the grace window. Returns the number of accounts deleted.
    """
    cutoff_days = _HARD_DELETE_GRACE_DAYS
    deleted = 0
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id FROM public.user_profiles
             WHERE pending_deletion_at IS NOT NULL
               AND pending_deletion_at < NOW() - ($1 || ' days')::interval
            """,
            str(cutoff_days),
        )
        for r in rows:
            try:
                await _hard_delete_user(conn, r["user_id"])
                deleted += 1
            except Exception as exc:
                logger.exception("Hard-delete sweep failed for %s: %s", r["user_id"], exc)
    if deleted:
        logger.info("Deletion sweep: hard-deleted %d expired account(s)", deleted)
    return deleted
