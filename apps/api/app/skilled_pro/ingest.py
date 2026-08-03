"""
Pure planning logic for bulk credential ingestion (partner-portal / SIS lane).

Validates and normalizes each inbound row before any DB work, so the parsing and
normalization decisions are unit-testable without a database. The router layer
applies the resulting plan (resolve applicant → upsert → sign).

Ingested credentials come from a trusted institutional source, so they resolve
to INSTITUTION_VERIFIED (see verification.derive_level for PARTNER_PORTAL/SIS).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.skilled_pro import taxonomy
from app.skilled_pro.taxonomy import NormalizationResult

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class IngestRowInput:
    email: str
    credential_name: str
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    expires_date: Optional[str] = None


@dataclass(frozen=True)
class RowPlan:
    ok: bool
    email: str                          # normalized (lowercased) email
    credential_name: str
    normalized: Optional[NormalizationResult]
    error: Optional[str] = None

    @property
    def canonical_code(self) -> Optional[str]:
        # DB-facing slug (credentials.canonical_code / credential_definitions.canonical_code).
        return self.normalized.canonical.slug if self.normalized and self.normalized.canonical else None

    @property
    def needs_review(self) -> bool:
        # Unmatched or low-confidence taxonomy mappings go to admin review even
        # though the source is trusted — we still want a clean canonical link.
        return not (self.normalized and self.normalized.is_confident)


def plan_row(raw: IngestRowInput) -> RowPlan:
    email = (raw.email or "").strip().lower()
    name = (raw.credential_name or "").strip()

    if not email:
        return RowPlan(False, email, name, None, "Missing email")
    if not _EMAIL_RE.match(email):
        return RowPlan(False, email, name, None, "Invalid email")
    if not name:
        return RowPlan(False, email, name, None, "Missing credential name")

    return RowPlan(True, email, name, taxonomy.normalize(name), None)
