"""
Centralized, resilient OpenAI client.

Every user-facing LLM call should go through here so timeout + retry behavior is
consistent: a slow or failing OpenAI never hangs a request past the timeout, and
transient errors are retried a bounded number of times by the SDK. Callers still
wrap the call in try/except and provide a graceful fallback — resilience config
bounds the failure; the caller decides what to return on it.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def interactive_http_timeout() -> httpx.Timeout:
    """Shared timeout policy for user-facing outbound HTTP (LLM + partner APIs).

    Splits a short CONNECT budget from a generous READ budget so an unreachable
    or dead host fails fast (~5s) instead of making a waiting user burn the whole
    read budget just to open a socket. Real LLM generation legitimately takes
    tens of seconds, so we keep the read budget generous but bound everything.
    Use this instead of a bare ``httpx.AsyncClient(timeout=30.0)``, which sets
    the SAME long budget on connect/read/write/pool.
    """
    s = get_settings()
    return httpx.Timeout(
        s.openai_timeout_seconds,          # read/write/pool default
        connect=s.openai_connect_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_openai_client():
    """Return a shared OpenAI client with timeout + bounded retries, or None if
    no API key is configured (callers fall back to their non-LLM path)."""
    settings = get_settings()
    key = (settings.openai_api_key or "").strip()
    # Treat .env.example placeholder values as "not configured" — otherwise
    # every LLM-optional feature burns a doomed network call before falling
    # back to its deterministic path.
    if not key or key.lower().startswith(("your-", "your_", "changeme", "placeholder", "xxx")):
        return None
    from openai import OpenAI

    return OpenAI(
        api_key=settings.openai_api_key,
        # Split connect vs read so a dead endpoint fails fast; one bounded retry.
        timeout=httpx.Timeout(
            settings.openai_timeout_seconds,
            connect=settings.openai_connect_timeout_seconds,
        ),
        max_retries=settings.openai_max_retries,
    )
