"""
Student Information System (SIS) ingestion adapter.

Same Protocol pattern as ocr.py: a provider that yields credential-completion
records, behind a swappable interface. `MockSISProvider` returns a small
deterministic feed so the SIS ingestion lane runs end-to-end without a vendor
account; `EllucianEthosSISProvider` is the production target (Ellucian Ethos API
for Banner/Colleague; Workday/PeopleSoft are sibling adapters) and raises a clear
error until credentials are configured.

The records flow through the SAME ingest pipeline as the partner-portal CSV lane
(`/admin/credentials/ingest`), so SIS-sourced credentials land at
Institution-Verified with signed, hash-chained audit records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from app.integrations import IntegrationNotConfigured


@dataclass(frozen=True)
class SISRecord:
    email: str
    credential_name: str
    issuer: str | None = None
    issued_date: date | None = None
    expires_date: date | None = None


@runtime_checkable
class SISProvider(Protocol):
    name: str
    def fetch_records(self, since: date | None = None) -> list[SISRecord]: ...


class NullSISProvider:
    """Safe default — no feed configured, returns nothing."""
    name = "null"
    def fetch_records(self, since: date | None = None) -> list[SISRecord]:
        return []


class MockSISProvider:
    """
    Deterministic demo feed. Targets known seeded applicants so the lane visibly
    matches + upserts, plus an unmatched row to exercise that path.
    """
    name = "mock-sis"

    def fetch_records(self, since: date | None = None) -> list[SISRecord]:
        issued = date(2025, 5, 15)
        return [
            SISRecord("applicant@test.local", "OSHA 10-Hour Construction Safety",
                      issuer="OSHA", issued_date=issued),
            SISRecord("riyakaru@stanford.edu", "Certified Welding Inspector (CWI)",
                      issuer="AWS", issued_date=issued),
            SISRecord("no-such-student@example.edu", "HVAC EPA 608",
                      issuer="EPA", issued_date=issued),
        ]


class EllucianEthosSISProvider:
    """Production SIS connector (Ellucian Ethos → Banner/Colleague). Not wired until
    creds exist; the ingest pipeline it feeds is already built + tested."""
    name = "ellucian-ethos"

    def __init__(self) -> None:
        raise IntegrationNotConfigured(
            "Ellucian Ethos SIS is not configured. Set ETHOS_API_KEY + base URL and "
            "implement fetch_records() per docs/skilled-pro/02 §1 and 08."
        )

    def fetch_records(self, since: date | None = None) -> list[SISRecord]:  # pragma: no cover
        raise IntegrationNotConfigured("Ellucian Ethos SIS not implemented")


def get_sis_provider() -> SISProvider:
    """Default to the mock feed so the lane is demoable; select a real provider via
    SIS_PROVIDER once credentials exist."""
    from app.config import get_settings
    provider = (getattr(get_settings(), "sis_provider", "") or "").lower()
    if provider in ("ethos", "ellucian", "ellucian-ethos"):
        return EllucianEthosSISProvider()
    if provider == "null":
        return NullSISProvider()
    return MockSISProvider()
