"""
Checkr-backed credential verification endpoints.

Applicant-initiated (consumer-permissioned): a worker asks to verify one of their
own credentials via Checkr. We create a hosted invitation, the worker completes
ID + consent on Checkr's screens, and Checkr later calls our webhook with the
report result — which raises the credential to Institution-Verified when clear.

Because the worker initiates and controls it and Checkr is the CRA, SkillPointe
stays out of Consumer-Reporting-Agency territory.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, require_applicant
from app.db import get_db
from app.integrations import IntegrationNotConfigured, checkr
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    derive_level,
)

router = APIRouter(prefix="/applicant/me/credentials", tags=["credentials"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class CheckrInviteOut(BaseModel):
    status: str
    # None when simulated — the frontend must not open any external URL then.
    invitation_url: Optional[str] = None
    package: str
    simulated: bool = False


class VerifyConfigOut(BaseModel):
    """Which optional verification methods are actually usable here — the UI
    hides methods that would dead-end (e.g. Checkr without a real API key)."""
    checkr_enabled: bool


class CheckrStatusOut(BaseModel):
    status: str
    package: Optional[str] = None
    invitation_url: Optional[str] = None
    updated_at: Optional[str] = None


async def _resolve_applicant(conn, user: CurrentUser):
    # View-as resolves by applicant id directly (supports unlinked applicants).
    row = await conn.fetchrow(
        "SELECT id::text AS id, email, first_name, last_name FROM public.applicants "
        "WHERE id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))",
        user.user_id,
        user.view_as_applicant_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant profile not found")
    return row


@router.get("/verify-config", response_model=VerifyConfigOut)
async def get_verify_config(
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Environment capabilities for the credentials verify panel.

    `checkr_enabled` is derived from checkr.is_configured() — the same check
    create_invitation uses to decide simulated/refused — so the UI only offers
    the background-check method when it can actually complete. The invite
    endpoint itself still answers honestly (simulated/503) for direct callers.
    """
    return VerifyConfigOut(checkr_enabled=checkr.is_configured())


@router.post("/{credential_id}/checkr/invite", response_model=CheckrInviteOut)
async def create_checkr_invite(
    credential_id: str,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Start a Checkr verification for one of the applicant's own credentials."""
    async with get_db() as conn:
        who = await _resolve_applicant(conn, user)
        cred = await conn.fetchrow(
            "SELECT id FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            credential_id, who["id"],
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
        if not who["email"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add an email to your profile first.")

        # Idempotency: if a verification is already open for this credential,
        # return it rather than creating a second Checkr candidate (a duplicate
        # CRA invitation costs money and re-triggers the FCRA flow).
        existing = await conn.fetchrow(
            "SELECT invitation_url, package, status FROM public.checkr_verifications "
            "WHERE credential_id = $1 AND applicant_id = $2 "
            "AND status NOT IN ('clear', 'consider', 'error') "
            "ORDER BY created_at DESC LIMIT 1",
            credential_id, who["id"],
        )
        if existing and existing["invitation_url"]:
            return CheckrInviteOut(
                status="invited", invitation_url=existing["invitation_url"],
                package=existing["package"] or "", simulated=False,
            )

        try:
            inv = await checkr.create_invitation(
                email=who["email"],
                first_name=who["first_name"] or "",
                last_name=who["last_name"] or "",
            )
        except IntegrationNotConfigured as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except Exception as exc:
            # A real Checkr outage/5xx must not surface as an unhandled 500.
            import logging
            logging.getLogger(__name__).error("Checkr invitation failed: %s", exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Background-check provider is temporarily unavailable. Please try again shortly.",
            )

        if inv.simulated:
            # Local/simulated mode: Checkr isn't actually configured. Do not
            # persist a fake candidate row and never hand back an external URL —
            # the frontend shows an inline "not enabled" state instead.
            return CheckrInviteOut(
                status="simulated", invitation_url=None,
                package=inv.package, simulated=True,
            )

        await conn.execute(
            """
            INSERT INTO public.checkr_verifications
              (credential_id, applicant_id, candidate_id, invitation_id, status, package, invitation_url)
            VALUES ($1, $2, $3, $4, 'invited', $5, $6)
            """,
            credential_id, who["id"], inv.candidate_id, inv.invitation_id, inv.package, inv.invitation_url,
        )
        await append_credential_record(
            conn, who["id"], credential_id, "checkr_invited",
            {"credential_id": credential_id, "package": inv.package, "simulated": inv.simulated},
        )

    return CheckrInviteOut(
        status="invited", invitation_url=inv.invitation_url,
        package=inv.package, simulated=inv.simulated,
    )


@router.get("/{credential_id}/checkr", response_model=CheckrStatusOut)
async def get_checkr_status(
    credential_id: str,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    async with get_db() as conn:
        who = await _resolve_applicant(conn, user)
        row = await conn.fetchrow(
            "SELECT status, package, invitation_url, updated_at FROM public.checkr_verifications "
            "WHERE credential_id = $1 AND applicant_id = $2 ORDER BY created_at DESC LIMIT 1",
            credential_id, who["id"],
        )
        if not row:
            return CheckrStatusOut(status="none")
        return CheckrStatusOut(
            status=row["status"], package=row["package"], invitation_url=row["invitation_url"],
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        )


@webhook_router.post("/checkr")
async def checkr_webhook(request: Request):
    """Receive Checkr webhooks. Signature-verified; on a completed report we set
    the credential to Institution-Verified when the result is clear."""
    raw = await request.body()
    sig = request.headers.get("x-checkr-signature")
    if not checkr.verify_webhook_signature(raw, sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")

    import json
    try:
        event = json.loads(raw.decode() or "{}")
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) if isinstance(event.get("data"), dict) else {}
    candidate_id = obj.get("candidate_id")
    report_id = obj.get("id") if etype.startswith("report.") else obj.get("report_id")
    result = obj.get("result")

    # Only act on report lifecycle events tied to a candidate we invited.
    if not candidate_id and not report_id:
        return {"ok": True, "ignored": etype}

    new_status = checkr.status_from_report(result) if result else "pending"

    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id::text, credential_id, applicant_id FROM public.checkr_verifications "
            "WHERE candidate_id = $1 OR report_id = $2 ORDER BY created_at DESC LIMIT 1",
            candidate_id, report_id,
        )
        if not row:
            return {"ok": True, "unmatched": True}

        await conn.execute(
            "UPDATE public.checkr_verifications SET status = $2, report_id = COALESCE($3, report_id), "
            "updated_at = now() WHERE id = $1::uuid",
            row["id"], new_status, report_id,
        )

        if new_status == "clear" and row["credential_id"]:
            derived = derive_level(VerificationEvidence(
                source=CredentialSource.BACKGROUND_CHECK,
                issuer_matched=True, document_authentic=True,
            ))
            cur = await conn.fetchval(
                "SELECT verification_level FROM public.credentials WHERE id = $1", row["credential_id"],
            )
            new_level = max(int(cur or 0), derived.value)
            await conn.execute(
                "UPDATE public.credentials SET verification_level = $2, source = 'background_check', "
                "needs_review = false WHERE id = $1",
                row["credential_id"], new_level,
            )
            await append_credential_record(
                conn, row["applicant_id"], row["credential_id"], "checkr_cleared",
                {"credential_id": row["credential_id"], "verification_level": new_level, "report_id": report_id},
            )

    return {"ok": True, "status": new_status}
