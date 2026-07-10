"""
External integration adapters.

Every external dependency (OCR, SIS, ATS, payments, notifications, data licensing)
sits behind a small **Protocol** with:
  - a Null/stub implementation that lets the whole platform run with the integration
    *unconfigured* (returns safe no-ops), and
  - a real implementation selected by a feature flag / configured credentials.

This keeps the core product fully functional and testable without any vendor
accounts, and makes each integration independently shippable once its credentials
and contracts are in place. See docs/skilled-pro/ for the production design of each.

`ocr.py` is the worked reference example (it feeds credential verification). The
remaining adapters (SIS via Ellucian Ethos, ATS via Merge.dev, payments via Stripe,
notifications via Expo/Knock) follow the identical pattern and are specified in the
dossiers; they are intentionally not stubbed until their credentials exist, to avoid
shipping dead code.
"""


class IntegrationNotConfigured(RuntimeError):
    """Raised when a real integration is invoked without configured credentials."""
