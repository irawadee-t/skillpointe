"""
SKILLED ID partner API keys.

Keys are shown to the partner exactly once at creation; we persist only a
SHA-256 hash (optionally peppered with a server secret), never the raw key.
A short non-secret prefix is stored alongside so partners can identify a key in
the dashboard ("skid_live_a1b2…") and so lookups are O(1) by prefix.

Pure + stdlib → unit-testable. Constant-time comparison on verify.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

_KEY_BYTES = 32           # 256 bits of entropy
_PREFIX_VISIBLE = 8       # chars of the random part kept for display


@dataclass(frozen=True)
class GeneratedKey:
    raw: str          # full secret — return to caller ONCE, never store
    prefix: str       # non-secret display prefix, safe to store/show
    key_hash: str     # what we persist


def _hash(raw: str, pepper: str = "") -> str:
    if pepper:
        return hmac.new(pepper.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key(live: bool = True, pepper: str = "") -> GeneratedKey:
    env = "live" if live else "test"
    body = secrets.token_urlsafe(_KEY_BYTES).rstrip("=")
    raw = f"skid_{env}_{body}"
    prefix = f"skid_{env}_{body[:_PREFIX_VISIBLE]}"
    return GeneratedKey(raw=raw, prefix=prefix, key_hash=_hash(raw, pepper))


def hash_key(raw: str, pepper: str = "") -> str:
    """Hash a presented key for lookup/compare (same scheme as generation)."""
    return _hash(raw, pepper)


def verify_key(raw: str, stored_hash: str, pepper: str = "") -> bool:
    """Constant-time verify a presented raw key against a stored hash."""
    return hmac.compare_digest(_hash(raw, pepper), stored_hash)


def prefix_of(raw: str) -> str:
    """Recover the display prefix from a raw key (for O(1) DB lookup)."""
    parts = raw.split("_", 2)
    if len(parts) != 3:
        return ""
    env, body = parts[1], parts[2]
    return f"skid_{env}_{body[:_PREFIX_VISIBLE]}"
