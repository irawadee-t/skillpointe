"""
Application-layer symmetric encryption for at-rest sensitive fields
(applications.screening_answers.answer today; add more as we identify them).

v1 uses Fernet (AES-128-CBC + HMAC-SHA256) with a key from settings. Key
material lives in `SCREENING_ENCRYPTION_KEY` — production deployments MUST set
a stable, high-entropy key held in a KMS/secret store. This is a stopgap until
we route through a proper KMS with rotation semantics.

Version discipline:
- We store a version tag on rows (see applications.screening_answers_ciphertext_v)
  so future keys can co-exist during a rotation without a schema change.
- Ciphertext is prefixed with "v1:" so decrypt can dispatch even when the row
  hasn't been backfilled.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_PREFIX = "v1:"


@lru_cache(maxsize=1)
def _fernet():
    """Return a Fernet instance. Raises if production is misconfigured."""
    from cryptography.fernet import Fernet  # cryptography ships via python-jose[cryptography]

    settings = get_settings()
    raw = (settings.screening_encryption_key or "").strip()

    if not raw:
        if settings.app_env == "production":
            raise RuntimeError(
                "SCREENING_ENCRYPTION_KEY must be set in production. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
            )
        # Dev fallback: derive deterministically from the JWT secret so restarts
        # can decrypt previously-encrypted rows. NOT SAFE for production.
        seed = (settings.supabase_jwt_secret or "dev-fallback-seed").encode()
        derived = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
        return Fernet(derived)

    try:
        return Fernet(raw.encode())
    except Exception as exc:
        raise RuntimeError(
            f"SCREENING_ENCRYPTION_KEY is malformed: {exc}. "
            "Expected a urlsafe base64 32-byte key (Fernet.generate_key())."
        ) from exc


def encrypt_str(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a string; None passes through."""
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_str(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt if versioned; return input unchanged for legacy plaintext rows."""
    if ciphertext is None:
        return None
    if not isinstance(ciphertext, str) or not ciphertext.startswith(_PREFIX):
        # Legacy plaintext row (ciphertext_v = 0). Return as-is; caller can
        # backfill on next write.
        return ciphertext
    token = ciphertext[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as exc:
        logger.warning("decrypt_str failed; returning empty string: %s", exc)
        return ""
