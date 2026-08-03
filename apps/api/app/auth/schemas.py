"""
Auth-related Pydantic schemas.

TokenPayload  — decoded Supabase JWT claims
CurrentUser   — the authenticated user injected into route handlers
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenPayload(BaseModel):
    """Decoded claims from a Supabase-issued JWT."""

    sub: str  # Supabase user UUID
    email: str | None = None
    role: str | None = None          # Supabase built-in role ("authenticated"), NOT our app role
    app_metadata: dict[str, Any] = {}
    user_metadata: dict[str, Any] = {}
    exp: int | None = None
    aud: str | None = None

    @property
    def supabase_user_id(self) -> str:
        return self.sub

    @property
    def app_role_from_jwt(self) -> str | None:
        """Role stored in app_metadata — convenience, use DB as authoritative source."""
        return self.app_metadata.get("role")


class CurrentUser(BaseModel):
    """Resolved authenticated user, injected into route handlers via Depends."""

    user_id: str
    email: str
    role: str                    # authoritative app role from user_profiles table
    onboarding_complete: bool = False

    # Admin "view as applicant" debug mode (read-only impersonation).
    # When set, this CurrentUser represents the TARGET applicant and
    # `impersonated_by` holds the real admin's auth user id. Only ever set by
    # require_applicant for GET requests carrying X-View-As-Applicant.
    impersonated_by: str | None = None
    view_as_applicant_id: str | None = None

    @property
    def is_view_as(self) -> bool:
        return self.impersonated_by is not None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_applicant(self) -> bool:
        return self.role == "applicant"

    @property
    def is_employer(self) -> bool:
        return self.role == "employer"
