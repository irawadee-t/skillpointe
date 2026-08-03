"""
Shared per-user rate limiter for expensive LLM endpoints (chat, resume parse,
translation). Wraps the same sliding-window primitive used by
`app.skilled_pro.ratelimit`, but exposes a FastAPI dependency keyed on the
authenticated user's id.

Backing store:
- Redis when reachable (per-process singleton client, pinged on startup).
- In-memory fallback if Redis is unavailable — fails open with a warning so a
  Redis outage doesn't take down user-facing features.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.skilled_pro.ratelimit import (
    InMemoryBackend,
    RateLimiter,
    RateTier,
    RedisBackend,
)

logger = logging.getLogger(__name__)

# Default LLM tier: 5 calls / minute / user. Aggressive by design — these
# endpoints hit OpenAI and burn budget.
LLM_TIER = RateTier(name="llm_per_user", limit=5, window=60)

# Sensitive-action tier: 8 attempts / 15 min / (user, scope). Covers the
# account-change request + confirm surface so a 6-digit code can't be
# brute-forced. Deliberately strict; a legitimate user needs only a handful.
SENSITIVE_TIER = RateTier(name="sensitive_per_user", limit=8, window=900)

_limiter: Optional[RateLimiter] = None
# Shared per-process fallback used only while Redis is unreachable. It is NEVER
# cached as the definitive limiter, so once Redis recovers the next call latches
# onto it — a startup Redis blip no longer degrades a replica for its lifetime.
_inmem_fallback = RateLimiter(InMemoryBackend())


def _try_build_redis_limiter() -> Optional[RateLimiter]:
    try:
        import redis  # type: ignore

        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        client.ping()
        return RateLimiter(RedisBackend(client))
    except Exception as exc:  # pragma: no cover — infra-dependent
        logger.warning(
            "Rate limiter: Redis unreachable — using per-process fallback for this call (will retry Redis): %s",
            exc,
        )
        return None


def _limiter_instance() -> RateLimiter:
    global _limiter
    if _limiter is not None:
        return _limiter
    built = _try_build_redis_limiter()
    if built is not None:
        _limiter = built  # latch onto Redis the first time it's reachable
        return _limiter
    return _inmem_fallback  # transient — retried on the next call


def rate_limit_llm(scope: str = "llm") -> object:
    """
    Return a FastAPI dependency that enforces the LLM rate limit per (user, scope).

    Usage:
        @router.post(..., dependencies=[Depends(rate_limit_llm("chat"))])

    On breach: 429 Too Many Requests with a Retry-After header (seconds).
    On Redis outage: fails open — logs a warning, does not block the user.
    """

    async def _check(
        user: CurrentUser = Depends(get_current_user),
    ) -> None:
        try:
            key = f"llm:{scope}:{user.user_id}"
            decision = _limiter_instance().check(key, LLM_TIER)
        except Exception as exc:  # pragma: no cover — safety net
            logger.warning("Rate limit check failed open for %s: %s", scope, exc)
            return

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded ({LLM_TIER.limit}/min). "
                    f"Retry in {decision.reset_seconds}s."
                ),
                headers={
                    "Retry-After": str(decision.reset_seconds),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                },
            )

    return _check


def rate_limit_sensitive(scope: str) -> object:
    """
    Return a FastAPI dependency for security-sensitive endpoints (auth codes,
    account changes). Uses SENSITIVE_TIER and — unlike the LLM limiter — **fails
    closed**: if the backing store errors, the request is rejected rather than
    let through, because these are exactly the flows an attacker would target.

    Usage:
        @router.post(..., dependencies=[Depends(rate_limit_sensitive("email_confirm"))])
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> None:
        try:
            key = f"sensitive:{scope}:{user.user_id}"
            decision = _limiter_instance().check(key, SENSITIVE_TIER)
        except Exception as exc:  # fail CLOSED on the sensitive surface
            logger.error("Sensitive rate-limit backend error for %s — failing closed: %s", scope, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification is temporarily unavailable. Please try again shortly.",
            )

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many attempts. For your security, try again in "
                    f"{max(1, decision.reset_seconds // 60)} minute(s)."
                ),
                headers={"Retry-After": str(decision.reset_seconds)},
            )

    return _check


def rate_limit_sensitive_ip(scope: str) -> object:
    """
    Sensitive-tier rate limit for UNAUTHENTICATED endpoints (e.g. the phone
    credential-upload token surface), keyed by client IP instead of user id.
    Same tier and fail-closed behavior as `rate_limit_sensitive`.
    """

    async def _check(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        try:
            key = f"sensitive-ip:{scope}:{ip}"
            decision = _limiter_instance().check(key, SENSITIVE_TIER)
        except Exception as exc:  # fail CLOSED on the sensitive surface
            logger.error("Sensitive IP rate-limit backend error for %s — failing closed: %s", scope, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Uploads are temporarily unavailable. Please try again shortly.",
            )

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many attempts. Try again in "
                    f"{max(1, decision.reset_seconds // 60)} minute(s)."
                ),
                headers={"Retry-After": str(decision.reset_seconds)},
            )

    return _check
