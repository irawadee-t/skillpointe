"""
Auth router — identity + role management endpoints.

POST /auth/complete-signup   — finalize applicant self-signup (create user_profiles row)
GET  /auth/me                — return current user identity + role
POST /auth/invite-employer   — (admin only) invite an employer via email [Phase 2 scaffold]
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from app.auth.dependencies import (
    _get_admin_client,
    decode_supabase_jwt,
    get_current_user,
    require_admin,
)
from app.auth.schemas import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class MeResponse(BaseModel):
    user_id: str
    email: str
    role: str
    onboarding_complete: bool


class CompleteSignupResponse(BaseModel):
    role: str
    already_existed: bool


class InviteEmployerRequest(BaseModel):
    email: EmailStr
    company_name: str | None = None


class InviteEmployerResponse(BaseModel):
    email: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MeResponse:
    """Return the authenticated user's identity and app role."""
    return MeResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
        onboarding_complete=current_user.onboarding_complete,
    )


@router.post("/complete-signup", response_model=CompleteSignupResponse)
async def complete_signup(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> CompleteSignupResponse:
    """
    Called by the frontend immediately after Supabase self-signup.

    Creates a user_profiles row with role='applicant'.
    Sets app_metadata.role on the Supabase Auth user so the next JWT refresh
    includes the role in the token.

    Idempotent — safe to call multiple times; will not override existing roles.
    Only assigns 'applicant' role via this endpoint.
    Employer and admin roles are set through admin-controlled flows only.
    """
    token_data = decode_supabase_jwt(credentials.credentials)
    user_id = token_data.sub

    client = _get_admin_client()

    # Check if profile already exists
    existing = (
        client.table("user_profiles")
        .select("id, role")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        return CompleteSignupResponse(
            role=existing.data[0]["role"],
            already_existed=True,
        )

    # Create user_profiles row (role)
    try:
        client.table("user_profiles").insert(
            {"user_id": user_id, "role": "applicant"}
        ).execute()
    except Exception as exc:
        logger.error("Failed to create user_profiles for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user profile",
        )

    # Link or create applicants row.
    # If this email was already imported via CSV (user_id is NULL), claim that row.
    # Otherwise create a new stub.
    try:
        user_email = token_data.email
        existing_applicant = (
            client.table("applicants")
            .select("id, user_id")
            .eq("email", user_email)
            .is_("user_id", "null")
            .limit(1)
            .execute()
        )

        if existing_applicant.data:
            # Claim the imported row
            client.table("applicants").update(
                {"user_id": user_id, "source": "self_signup_linked"}
            ).eq("id", existing_applicant.data[0]["id"]).execute()
            logger.info("Linked imported applicant %s to user %s", existing_applicant.data[0]["id"], user_id)
        else:
            # No imported row — check if already has a row with this user_id
            owned = (
                client.table("applicants")
                .select("id")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not owned.data:
                client.table("applicants").insert(
                    {"user_id": user_id, "email": user_email, "source": "self_signup", "onboarding_complete": False}
                ).execute()
    except Exception as exc:
        logger.warning("Failed to create/link applicants row for %s: %s", user_id, exc)

    # Embed role in Supabase Auth app_metadata so JWT refresh includes it
    try:
        client.auth.admin.update_user_by_id(
            user_id,
            {"app_metadata": {"role": "applicant"}},
        )
    except Exception as exc:
        logger.warning("Could not set app_metadata for %s: %s", user_id, exc)

    # Fire-and-forget: compute initial matches for this new applicant
    try:
        import asyncio as _asyncio
        from app.db import get_db
        from app.worker.scheduler import trigger_recompute_for_applicant

        async def _trigger() -> None:
            try:
                async with get_db() as conn:
                    app_id = await conn.fetchval(
                        "SELECT id::text FROM public.applicants WHERE user_id = $1",
                        user_id,
                    )
                if app_id:
                    await trigger_recompute_for_applicant(app_id)
            except Exception as exc:
                logger.warning("Could not trigger recompute for new applicant %s: %s", user_id, exc)

        _asyncio.create_task(_trigger())
    except Exception as exc:
        logger.warning("Could not schedule recompute for new applicant %s: %s", user_id, exc)

    return CompleteSignupResponse(role="applicant", already_existed=False)


@router.post(
    "/invite-employer",
    response_model=InviteEmployerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_employer(
    body: InviteEmployerRequest,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> InviteEmployerResponse:
    """
    Admin-only: invite an employer by email.

    Creates a Supabase Auth invite, then creates a user_profiles row
    with role='employer'. The employer receives an email with a signup link.

    Full company profile creation is handled in Phase 3 (employer data model).
    """
    client = _get_admin_client()

    try:
        # Send Supabase invite email
        invite_resp = client.auth.admin.invite_user_by_email(
            body.email,
            options={"redirect_to": "http://localhost:3000/auth/callback?next=/employer"},
        )
        invited_user_id = invite_resp.user.id
    except Exception as exc:
        logger.error("Failed to invite employer %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send invite: {exc}",
        )

    # Create user_profiles row with employer role
    try:
        client.table("user_profiles").insert(
            {"user_id": invited_user_id, "role": "employer"}
        ).execute()
    except Exception as exc:
        logger.error("Failed to create employer profile for %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invite sent but profile creation failed",
        )

    # Set app_metadata.role for JWT claims
    try:
        client.auth.admin.update_user_by_id(
            invited_user_id,
            {"app_metadata": {"role": "employer"}},
        )
    except Exception as exc:
        logger.warning("Could not set app_metadata for employer %s: %s", body.email, exc)

    return InviteEmployerResponse(
        email=body.email,
        message="Invite sent. Employer will receive an email to complete signup.",
    )
