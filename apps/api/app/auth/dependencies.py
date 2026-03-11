"""
FastAPI authentication and authorization dependencies.

Usage in route handlers:
    @router.get("/me")
    async def me(user: Annotated[CurrentUser, Depends(get_current_user)]):
        ...

    @router.get("/admin-only")
    async def admin_only(user: Annotated[CurrentUser, Depends(require_admin)]):
        ...

Architecture notes (CLAUDE.md):
- Supabase Auth owns identity (JWT issuance, session management).
- user_profiles table owns app-level role (authoritative).
- JWT app_metadata.role is a convenience cache; DB is the source of truth.
- Service role key is used for privileged DB queries here.
- All enforcement is in backend — never trust frontend-only checks.
"""
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from supabase import Client, create_client

from app.auth.schemas import CurrentUser, TokenPayload
from app.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


# ---------------------------------------------------------------------------
# Supabase admin client (service role — bypasses RLS)
# ---------------------------------------------------------------------------

@lru_cache
def _get_admin_client() -> Client:
    """Singleton Supabase client using service role key. Bypasses RLS."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ---------------------------------------------------------------------------
# JWT validation
# ---------------------------------------------------------------------------

def decode_supabase_jwt(token: str) -> TokenPayload:
    """
    Validate and decode a Supabase-issued JWT.

    Raises HTTP 401 on any validation failure.
    Algorithm: HS256 (both local and cloud Supabase use HS256 with the JWT secret).
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return TokenPayload(**payload)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Core dependency: get authenticated user
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> CurrentUser:
    """
    Validate JWT → look up user_profiles for authoritative role → return CurrentUser.

    This is the base dependency. Use require_* wrappers to enforce specific roles.
    """
    token_data = decode_supabase_jwt(credentials.credentials)
    user_id = token_data.sub

    client = _get_admin_client()

    try:
        result = (
            client.table("user_profiles")
            .select("role, onboarding_complete")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.error("DB error looking up user_profiles for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify user profile",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found. Complete signup first.",
        )

    return CurrentUser(
        user_id=user_id,
        email=token_data.email or "",
        role=result.data["role"],
        onboarding_complete=result.data["onboarding_complete"],
    )


# ---------------------------------------------------------------------------
# Role enforcement dependencies
# ---------------------------------------------------------------------------

def _require_roles(*roles: str):
    """
    Factory that returns a FastAPI dependency enforcing one of the given roles.
    Usage: Depends(_require_roles("admin", "employer"))
    """
    async def checker(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this resource",
            )
        return current_user

    return checker


# Public aliases — use these in route handlers
require_admin = _require_roles("admin")
require_applicant = _require_roles("applicant")
require_employer = _require_roles("employer")
require_employer_or_admin = _require_roles("employer", "admin")
require_authenticated = get_current_user   # any valid role
