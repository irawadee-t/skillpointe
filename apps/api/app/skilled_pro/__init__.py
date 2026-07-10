"""
SKILLED Pro core — verified-credentials platform building blocks.

This package holds the pure, deterministic, dependency-light logic that powers
SKILLED Pro's differentiating capabilities:

- taxonomy:     normalize free-text certs/licenses/degrees to a canonical taxonomy
- signing:      ed25519 signing + tamper-evident hash chaining of credential records
- verification: tiered verification-badge derivation (Self-Reported → SKILLED Verified)
- consent:      granular, independent consent-scope evaluation (display/internal/external)
- apikeys:      SKILLED ID partner API-key generation + verification (hash-at-rest)
- ratelimit:    backend-agnostic rate limiter (Redis in prod, in-memory in tests)

Everything here is unit-tested without a database or network so the logic that
governs trust and consent is provably correct.
"""
