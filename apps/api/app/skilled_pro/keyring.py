"""
Signing key provider for credential/consent records.

Loads the Ed25519 keypair from settings (KMS-injected PEM in production). If no
key is configured (local dev), generates an ephemeral keypair once per process
and logs a loud warning — records signed with an ephemeral key will not verify
after a restart, which is acceptable for dev and unacceptable for prod.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.skilled_pro import signing

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _ephemeral() -> tuple[str, str]:
    logger.warning(
        "SKILLED signing keys not configured — generating an EPHEMERAL keypair. "
        "Records will not verify across restarts. Set SKILLED_SIGNING_PRIVATE_KEY "
        "/ SKILLED_SIGNING_PUBLIC_KEY for any non-dev environment."
    )
    return signing.generate_keypair()


def get_private_key() -> str:
    s = get_settings()
    if s.skilled_signing_private_key:
        return s.skilled_signing_private_key
    return _ephemeral()[0]


def get_public_key() -> str:
    s = get_settings()
    if s.skilled_signing_public_key:
        return s.skilled_signing_public_key
    return _ephemeral()[1]


def get_key_id() -> str:
    return get_settings().skilled_signing_key_id


def get_api_key_pepper() -> str:
    return get_settings().skilled_api_key_pepper
