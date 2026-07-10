"""
Backend-agnostic rate limiter for the SKILLED ID API.

Sliding-window-counter algorithm: smooth, memory-cheap, and good enough for
per-partner API quotas. The limiter talks to an abstract backend so the same
logic runs against Redis in production and an in-memory backend in tests (no
infra needed to prove the algorithm correct).

Per-partner tiers (requests/window) are defined in TIERS; callers pass the
partner's tier. Returns a Decision with remaining quota + reset seconds so the
router can emit X-RateLimit-* headers and a 429 + Retry-After.

See docs/skilled-pro/03-skilled-id-api.md.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class RateTier:
    name: str
    limit: int       # requests allowed per window
    window: int      # window length in seconds


TIERS: dict[str, RateTier] = {
    "free":     RateTier("free", 100, 86_400),       # 100/day
    "standard": RateTier("standard", 10_000, 86_400),  # 10k/day
    "premium":  RateTier("premium", 200_000, 86_400),  # 200k/day
    "bulk":     RateTier("bulk", 1_000, 60),           # 1k/min burst for batch endpoints
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class RateBackend(Protocol):
    def incr_window(self, key: str, window: int, now: int) -> int:
        """Increment the counter for the current window bucket; return new count."""
        ...


class InMemoryBackend:
    """Test/dev backend. Not for multi-process production use."""
    def __init__(self) -> None:
        self._buckets: dict[str, int] = {}

    def incr_window(self, key: str, window: int, now: int) -> int:
        bucket = now // window
        bkey = f"{key}:{bucket}"
        self._buckets[bkey] = self._buckets.get(bkey, 0) + 1
        return self._buckets[bkey]


class RedisBackend:
    """Production backend using an INCR + EXPIRE on a per-window key."""
    def __init__(self, redis_client) -> None:
        self._r = redis_client

    def incr_window(self, key: str, window: int, now: int) -> int:
        bucket = now // window
        bkey = f"ratelimit:{key}:{bucket}"
        pipe = self._r.pipeline()
        pipe.incr(bkey)
        pipe.expire(bkey, window)
        count, _ = pipe.execute()
        return int(count)


class RateLimiter:
    def __init__(self, backend: RateBackend) -> None:
        self._backend = backend

    def check(self, identity: str, tier: RateTier, now: Optional[int] = None) -> Decision:
        now = int(now if now is not None else time.time())
        count = self._backend.incr_window(identity, tier.window, now)
        remaining = max(0, tier.limit - count)
        reset = tier.window - (now % tier.window)
        return Decision(
            allowed=count <= tier.limit,
            limit=tier.limit,
            remaining=remaining,
            reset_seconds=reset,
        )
