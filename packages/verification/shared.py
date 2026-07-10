"""Shared contract for all partner-verification adapters.

All adapters return VerificationResult so callers can persist a uniform receipt
regardless of provider. `stubbed` is True when we could not call the partner
(missing config) and are returning a well-formed placeholder — the caller MUST
NOT surface a stubbed result as "verified" in user-facing UI, but should still
record it in the audit trail so operations can see what would have run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class VerificationStatus(str, Enum):
    VERIFIED     = "verified"       # Partner confirmed the credential is real and current
    NOT_FOUND    = "not_found"      # Partner searched and could not find a match
    EXPIRED      = "expired"        # Found but no longer valid
    REVOKED      = "revoked"        # Found and explicitly revoked
    ERROR        = "error"          # Partner call failed; try again later
    STUB         = "stub"           # No partner config; result is synthetic


@dataclass
class VerificationResult:
    provider:       str                          # 'nccer' | 'nsc' | 'credential_engine' | 'state_licensing'
    status:         VerificationStatus
    external_ref:   Optional[str]  = None        # e.g. NCCER card #, NSC verification hash
    verified_name:  Optional[str]  = None        # Name confirmed by partner
    credential:     Optional[str]  = None        # Credential name / degree title confirmed by partner
    issue_date:     Optional[str]  = None        # ISO date if provided
    expires_date:   Optional[str]  = None
    raw:            dict[str, Any] = field(default_factory=dict)   # Raw partner payload for audit
    stubbed:        bool = False

    def to_receipt(self) -> dict[str, Any]:
        """Serialized shape stored in credentials.provider_receipt."""
        return {
            "provider":      self.provider,
            "status":        self.status.value,
            "external_ref":  self.external_ref,
            "verified_name": self.verified_name,
            "credential":    self.credential,
            "issue_date":    self.issue_date,
            "expires_date":  self.expires_date,
            "stubbed":       self.stubbed,
            "raw":           self.raw,
        }
