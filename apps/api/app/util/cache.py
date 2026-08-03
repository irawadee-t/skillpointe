"""
Tiny Redis cache-aside helper for hot, staleness-tolerant reads (job browse,
analytics dashboards). Degrades transparently to just running the producer when
Redis is unavailable — caching is an optimization, never a dependency.

    data = await cached_json("jobs:browse:<hash>", 30, produce)

Keep TTLs short for lists that change (browse) and lean on event-based
invalidation only where correctness needs it.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable

from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def _redis():
    global _client
    if _client is None:
        import redis.asyncio as aioredis  # type: ignore

        _client = aioredis.from_url(
            get_settings().redis_url, socket_connect_timeout=1, decode_responses=True
        )
    return _client


def cache_key(prefix: str, *parts: Any) -> str:
    """Build a stable cache key from a prefix and arbitrary parts."""
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


async def cached_json(key: str, ttl: int, producer: Callable[[], Awaitable[Any]]) -> Any:
    """Return cached JSON for `key`; on miss run `producer()`, cache, and return.
    Any Redis error falls through to the producer so the request still succeeds."""
    r = None
    try:
        r = _redis()
        hit = await r.get(key)
        if hit is not None:
            return json.loads(hit)
    except Exception as exc:  # pragma: no cover — infra-dependent
        logger.debug("cache read failed for %s: %s", key, exc)

    value = await producer()

    if r is not None:
        try:
            await r.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:  # pragma: no cover
            logger.debug("cache write failed for %s: %s", key, exc)
    return value
