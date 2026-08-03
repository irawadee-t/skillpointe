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
import uuid as _uuid
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from supabase import Client, create_client

from app.auth.schemas import CurrentUser, TokenPayload
from app.config import get_settings
from app.db import get_db

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

@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """
    Fetch and cache the JWKS from Supabase Auth.
    Used when Supabase signs JWTs with ES256 (Supabase CLI v2+).
    Cached for the process lifetime — restart API to rotate keys.
    """
    settings = get_settings()
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch JWKS from %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch JWT signing keys",
        )


def decode_supabase_jwt(token: str) -> TokenPayload:
    """
    Validate and decode a Supabase-issued JWT.

    Supports both HS256 (Supabase CLI v1 / cloud) and ES256 (Supabase CLI v2+).
    Algorithm is detected from the JWT header — ES256 tokens are validated
    against the JWKS endpoint; HS256 tokens against the configured JWT secret.

    Raises HTTP 401 on any validation failure.
    """
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")

        if alg == "HS256":
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # ES256 / RS256 — validate via JWKS
            jwks = _fetch_jwks()
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["ES256", "RS256"],
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
            .limit(1)
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
        role=result.data[0]["role"],
        onboarding_complete=result.data[0]["onboarding_complete"],
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
require_employer = _require_roles("employer")


# ---------------------------------------------------------------------------
# Applicant dependency + admin "view as applicant" debug mode
# ---------------------------------------------------------------------------

# Header an admin sends to resolve /applicant/me/* endpoints against a chosen
# applicant instead of themselves. Strictly read-only (GET/HEAD) and admin-only.
VIEW_AS_HEADER = "X-View-As-Applicant"

_VIEW_AS_READONLY_METHODS = {"GET", "HEAD"}


async def _resolve_view_as_target(applicant_id: str, admin: CurrentUser) -> CurrentUser:
    """
    Resolve the target applicant for an admin view-as request.

    Returns a CurrentUser that impersonates the applicant (role='applicant').
    `view_as_applicant_id` is ALWAYS set and is what applicant endpoints use to
    resolve the applicant row — this works even for bulk-imported applicants
    with no linked auth user. For those, `user_id` stays the ADMIN's own auth
    id (never a fabricated UUID); it is only a fallback key and matches no
    applicant row, which is fine because view-as is GET-only.
    `impersonated_by` records the real admin for downstream awareness.
    """
    try:
        _uuid.UUID(applicant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant not found for view-as",
        )

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text AS id, user_id::text AS user_id, email
            FROM public.applicants
            WHERE id = $1::uuid
            """,
            applicant_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant not found for view-as",
        )

    return CurrentUser(
        user_id=row["user_id"] or admin.user_id,
        email=row["email"] or "",
        role="applicant",
        onboarding_complete=True,
        impersonated_by=admin.user_id,
        view_as_applicant_id=row["id"],
    )


async def require_applicant(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """
    Applicant-scoped dependency for every /applicant/me/* endpoint.

    Normal sessions: behaves exactly like the old _require_roles("applicant") —
    applicants pass through unchanged, every other role gets 403.

    Admin view-as debug mode: when the caller is an admin AND the request
    carries the X-View-As-Applicant header, the target applicant is resolved
    instead. Guardrails (CLAUDE.md — admin must never act on behalf of others):
      - admin-only: any non-admin sending the header gets 403
      - read-only:  any non-GET/HEAD method under view-as gets 403
      - auditable:  session starts are logged via POST /admin/view-as/{id}/start
    """
    view_as_id = request.headers.get(VIEW_AS_HEADER)

    if view_as_id is None:
        # Zero behavior change for normal sessions.
        if current_user.role != "applicant":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this resource",
            )
        return current_user

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="View-as is restricted to admins",
        )
    if request.method.upper() not in _VIEW_AS_READONLY_METHODS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="View-as is read-only",
        )

    return await _resolve_view_as_target(view_as_id.strip(), current_user)
# Alias of require_employer with an explicit name at call sites for endpoints
# that MUST NOT be reachable by admins (mutations that would create/modify data
# on behalf of an employer). Use this whenever an endpoint's business logic
# assumes `user.user_id` maps to a real employer_contacts row.
require_employer_only = _require_roles("employer")

# WARNING — Any endpoint using require_employer_or_admin must explicitly branch
# on `user.role == "admin"` (or `user.is_admin`) to keep admins in a read-only
# posture. Mutations, outreach sends, hires, and account onboarding on behalf of
# a specific employer must instead use `require_employer_only`.
require_employer_or_admin = _require_roles("employer", "admin")
require_institution = _require_roles("institution")
require_institution_or_admin = _require_roles("institution", "admin")
require_authenticated = get_current_user   # any valid role
