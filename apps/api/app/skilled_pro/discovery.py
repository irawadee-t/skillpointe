"""
Verified-worker discovery invariants (employer side).

Two rules govern whether a worker is discoverable / verifiable by an employer —
both are enforced everywhere worker data is exposed to employers:

  1. CONSENT  — the worker explicitly granted external sharing of their
                ``certifications`` to the ``employer`` requester category.
  2. VERIFIED — the worker holds at least one credential at
                INSTITUTION_VERIFIED or higher (self-reported claims are never
                surfaced as "verified" to employers).

Data minimization: employer-facing surfaces expose identity + trade + verified
credentials only. Contact details (email/phone) are a *separate* consent category
and are never returned here — employers reach out through the messaging/outreach
flow, which has its own gate.

The consent predicate is pure + unit-tested so the rule that protects workers is
provably correct, and the SQL search applies the identical condition via the
JSONB containment operator.
"""
from __future__ import annotations

from typing import Iterable

from app.skilled_pro.consent import RequesterCategory, parse_external_sharing
from app.skilled_pro.verification import VerificationLevel

# Employers only ever see verified status, never self-reported claims.
MIN_VERIFIED_LEVEL: int = VerificationLevel.INSTITUTION_VERIFIED.value  # 1

# The requester category that the directory/verify surfaces act as.
DISCOVERY_REQUESTER = RequesterCategory.EMPLOYER

# Consent data-category that gates employer access to credentials.
GATED_CATEGORY = "certifications"


def employer_may_access(external_sharing: Iterable[str] | None) -> bool:
    """
    True iff the worker consented to share their certifications with employers.
    Accepts the raw external_sharing list (e.g. from consent_settings JSONB).
    """
    return DISCOVERY_REQUESTER in parse_external_sharing(external_sharing or [])
