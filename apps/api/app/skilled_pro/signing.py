"""
Cryptographic signing + tamper-evident chaining for credential records.

We follow the spirit of W3C Verifiable Credentials / Open Badges 3.0: a
credential record is canonicalized to deterministic JSON, hashed (SHA-256), and
signed with Ed25519. Records are also chained — each record stores the hash of
the previous record for its subject — so the audit trail is append-only and
tamper-evident (changing any historical record breaks every subsequent hash).

Pure-stdlib + ``cryptography`` (already a dependency via python-jose[cryptography]).
No DB or network here so the crypto is fully unit-testable.

See docs/skilled-pro/02-credentials-verification.md for the standards rationale
and the migration path to full W3C VC issuance.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

GENESIS_HASH = "0" * 64  # prev_hash for a subject's first credential record


def canonicalize(record: dict[str, Any]) -> bytes:
    """
    Deterministic JSON encoding for signing/hashing.

    Sorted keys, no insignificant whitespace, UTF-8. Two records that are equal
    as data produce identical bytes regardless of key order — essential for
    reproducible signatures and hashes.
    """
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(record: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonicalized record."""
    return hashlib.sha256(canonicalize(record)).hexdigest()


def chain_hash(content_hex: str, prev_hash: str) -> str:
    """
    Hash that links a record to its predecessor: SHA-256(content_hash || prev_hash).
    Storing this per record makes the per-subject history tamper-evident.
    """
    return hashlib.sha256(f"{content_hex}{prev_hash}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def generate_keypair() -> tuple[str, str]:
    """
    Generate an Ed25519 keypair. Returns (private_pem, public_pem) as strings.
    In production the private key lives in a KMS / secret store, never in the DB.
    """
    priv = Ed25519PrivateKey.generate()
    private_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def load_private_key(private_pem: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Expected an Ed25519 private key")
    return key


def load_public_key(public_pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Expected an Ed25519 public key")
    return key


# ---------------------------------------------------------------------------
# Sign / verify
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignedRecord:
    content_hash: str
    prev_hash: str
    chain_hash: str
    signature: str   # base64(ed25519 signature over the chain_hash bytes)
    algorithm: str = "Ed25519"


def sign_record(
    record: dict[str, Any],
    private_pem: str,
    prev_hash: str = GENESIS_HASH,
) -> SignedRecord:
    """
    Canonicalize → hash → chain → sign. The signature covers the chain hash, so
    it simultaneously attests to the record content AND its position in history.
    """
    chash = content_hash(record)
    link = chain_hash(chash, prev_hash)
    priv = load_private_key(private_pem)
    sig = priv.sign(link.encode("utf-8"))
    return SignedRecord(
        content_hash=chash,
        prev_hash=prev_hash,
        chain_hash=link,
        signature=base64.b64encode(sig).decode("ascii"),
    )


def verify_record(
    record: dict[str, Any],
    signed: SignedRecord,
    public_pem: str,
) -> bool:
    """
    Verify that ``record`` matches ``signed`` and the signature is valid.

    Checks: (1) content hash still matches the record, (2) chain hash is
    internally consistent, (3) Ed25519 signature over the chain hash verifies.
    Any tampering with the record, the chain, or the signature fails this.
    """
    if content_hash(record) != signed.content_hash:
        return False
    if chain_hash(signed.content_hash, signed.prev_hash) != signed.chain_hash:
        return False
    try:
        pub = load_public_key(public_pem)
        pub.verify(base64.b64decode(signed.signature), signed.chain_hash.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_chain(items: list[tuple[dict[str, Any], SignedRecord]], public_pem: str) -> bool:
    """
    Verify an ordered per-subject history: every record verifies AND each record's
    prev_hash equals the previous record's chain_hash (genesis for the first).
    """
    expected_prev = GENESIS_HASH
    for record, signed in items:
        if signed.prev_hash != expected_prev:
            return False
        if not verify_record(record, signed, public_pem):
            return False
        expected_prev = signed.chain_hash
    return True
