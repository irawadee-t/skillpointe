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

from fastapi import Depends, HTTPException, status

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

_limiter: Optional[RateLimiter] = None


def _build_limiter() -> RateLimiter:
    try:
        import redis  # type: ignore

        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        client.ping()
        return RateLimiter(RedisBackend(client))
    except Exception as exc:  # pragma: no cover — infra-dependent
        logger.warning(
            "LLM rate limiter falling back to in-memory backend (Redis unreachable): %s",
            exc,
        )
        return RateLimiter(InMemoryBackend())


def _limiter_instance() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _build_limiter()
    return _limiter


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
