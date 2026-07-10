"""
Tiered verification badges.

Trust ladder for a credential record:

    SELF_REPORTED        worker typed it in; no proof
    INSTITUTION_VERIFIED a recognized source attested it — a partner SIS feed,
                         partner-portal upload, or an issuer-matched verified document
    SKILLED_VERIFIED     the strongest tier — institution-verified AND the holder's
                         identity is verified AND SKILLED holds a valid cryptographic
                         signature over the (immutable) record

The level is *derived* from evidence, never set directly by a client, so a worker
can never self-assert a higher tier than their evidence supports.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerificationLevel(int, Enum):
    SELF_REPORTED = 0
    INSTITUTION_VERIFIED = 1
    SKILLED_VERIFIED = 2

    @property
    def badge(self) -> str:
        return {
            0: "Self-Reported",
            1: "Institution-Verified",
            2: "SKILLED Verified",
        }[self.value]


class CredentialSource(str, Enum):
    SELF = "self"                 # user-entered
    SIS = "sis"                   # direct SIS integration feed (Banner/Workday/PeopleSoft)
    PARTNER_PORTAL = "partner_portal"   # uploaded by a partner institution
    DOCUMENT_UPLOAD = "document_upload" # user-uploaded doc run through OCR/verification


# Sources that constitute an institutional attestation.
_INSTITUTIONAL_SOURCES = {CredentialSource.SIS, CredentialSource.PARTNER_PORTAL}


@dataclass(frozen=True)
class VerificationEvidence:
    source: CredentialSource
    issuer_matched: bool = False        # document/issuer matched a recognized issuer
    document_authentic: bool = False    # OCR/forgery pipeline passed
    identity_verified: bool = False     # holder identity verified (KYC/match)
    signature_valid: bool = False       # SKILLED cryptographic signature verifies


def derive_level(ev: VerificationEvidence) -> VerificationLevel:
    """
    Compute the verification level from evidence. Monotonic: more/better evidence
    can only raise the tier, never silently lower a legitimately higher one.
    """
    institutional = (
        ev.source in _INSTITUTIONAL_SOURCES
        or (ev.source == CredentialSource.DOCUMENT_UPLOAD and ev.issuer_matched and ev.document_authentic)
    )

    if institutional and ev.identity_verified and ev.signature_valid:
        return VerificationLevel.SKILLED_VERIFIED
    if institutional:
        return VerificationLevel.INSTITUTION_VERIFIED
    return VerificationLevel.SELF_REPORTED


def badge_for(level: VerificationLevel) -> str:
    return level.badge
