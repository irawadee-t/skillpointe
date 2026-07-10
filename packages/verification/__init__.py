"""Partner credential-verification adapters.

Each adapter implements the same VerificationResult contract. When the partner
API is not configured (no key), the adapter returns a `stubbed=True` result
that still shapes the downstream flow correctly. Swapping in real keys does not
require any code changes on the caller side.
"""
from .shared import VerificationResult, VerificationStatus
from . import ctdl, nccer, nsc

__all__ = ["VerificationResult", "VerificationStatus", "ctdl", "nccer", "nsc"]
