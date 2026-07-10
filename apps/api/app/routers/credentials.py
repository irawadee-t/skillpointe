"""
Applicant credentials — add / list / update / remove, with taxonomy
normalization and a cryptographically signed, append-only audit trail.

Self-service: an applicant manages their own credentials. Newly added ones are
SELF_REPORTED (tier 0); institution/SKILLED verification is raised by the
ingestion + verification pipelines (SIS feeds, partner portal, document OCR),
never by the worker. Every change appends a signed, hash-chained
``credential_records`` row so the history is tamper-evident.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_applicant
from app.db import get_db
from app.skilled_pro import taxonomy, doc_verify
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    VerificationLevel, VerificationEvidence, CredentialSource, derive_level,
)
from app.integrations.ocr import get_ocr_provider

router = APIRouter(prefix="/applicant/me/credentials", tags=["credentials"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CredentialIn(BaseModel):
    raw_name: str = Field(min_length=2, max_length=200)
    issuer: Optional[str] = Field(default=None, max_length=200)
    issued_date: Optional[date] = None
    expires_date: Optional[date] = None
    document_url: Optional[str] = Field(default=None, max_length=1000)


class CredentialOut(BaseModel):
    id: str
    raw_name: str
    canonical_code: Optional[str]
    canonical_name: Optional[str]
    credential_type: Optional[str]
    issuer: Optional[str]
    normalization_confidence: float
    needs_review: bool
    source: str
    verification_level: int
    verification_badge: str
    issued_date: Optional[date]
    expires_date: Optional[date]
    document_url: Optional[str]
    # Partner-verification metadata (Phase 11 — NCCER / NSC / Credential Engine)
    provider_source: Optional[str] = None            # 'nccer' | 'nsc' | 'credential_engine' | ...
    provider_verified_at: Optional[str] = None       # ISO timestamp
    provider_external_ref: Optional[str] = None      # NCCER card #, NSC hash, etc.
    provider_stubbed: bool = False                   # True when result came from stub (no partner key)
    verification_provider: Optional[str] = None      # From credential_definitions — what CAN verify this
    ctdl_uri: Optional[str] = None
    authority: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_applicant_id(conn: asyncpg.Connection, user_id: str) -> str:
    row = await conn.fetchrow(
        "SELECT id::text AS id FROM public.applicants WHERE user_id = $1", user_id
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant profile not found")
    return row["id"]


def _safe_get(row: asyncpg.Record, key: str):
    """asyncpg.Record.keys() has a quirky KeysView where `in` gives false
    negatives for aliased join columns — use try/except to check membership."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _to_out(row: asyncpg.Record) -> CredentialOut:
    level = VerificationLevel(row["verification_level"])
    receipt = _safe_get(row, "provider_receipt")
    stubbed = bool(receipt.get("stubbed")) if isinstance(receipt, dict) else False
    verified_at = _safe_get(row, "provider_verified_at")
    return CredentialOut(
        id=str(row["id"]),
        raw_name=row["raw_name"],
        canonical_code=row["canonical_code"],
        canonical_name=row["canonical_name"],
        credential_type=row["credential_type"],
        issuer=row["issuer"],
        normalization_confidence=float(row["normalization_confidence"]),
        needs_review=row["needs_review"],
        source=row["source"],
        verification_level=level.value,
        verification_badge=level.badge,
        issued_date=row["issued_date"],
        expires_date=row["expires_date"],
        document_url=row["document_url"],
        provider_source=_safe_get(row, "provider_source"),
        provider_verified_at=verified_at.isoformat() if verified_at else None,
        provider_external_ref=_safe_get(row, "provider_external_ref"),
        provider_stubbed=stubbed,
        verification_provider=_safe_get(row, "def_verification_provider"),
        ctdl_uri=_safe_get(row, "def_ctdl_uri"),
        authority=_safe_get(row, "def_authority"),
    )
    verified_at = row["provider_verified_at"] if "provider_verified_at" in keys else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[CredentialOut])
async def list_credentials(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user.user_id)
        rows = await conn.fetch(
            """
            SELECT c.id, c.raw_name, c.canonical_code, c.canonical_name, c.credential_type,
                   c.issuer, c.normalization_confidence, c.needs_review, c.source,
                   c.verification_level, c.issued_date, c.expires_date, c.document_url,
                   c.provider_source, c.provider_verified_at, c.provider_external_ref,
                   c.provider_receipt,
                   d.verification_provider AS def_verification_provider,
                   d.ctdl_uri              AS def_ctdl_uri,
                   d.authority             AS def_authority
              FROM public.credentials c
         LEFT JOIN public.credential_definitions d ON d.id = c.definition_id
             WHERE c.applicant_id = $1
          ORDER BY c.verification_level DESC, c.created_at DESC
            """,
            applicant_id,
        )
    return [_to_out(r) for r in rows]


@router.post("", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
async def add_credential(
    body: CredentialIn,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    norm = taxonomy.normalize(body.raw_name)
    canonical = norm.canonical
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user.user_id)
        row = await conn.fetchrow(
            """
            INSERT INTO public.credentials
                (applicant_id, raw_name, canonical_code, canonical_name,
                 credential_type, issuer, normalization_confidence, needs_review,
                 source, verification_level, issued_date, expires_date, document_url)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'self',0,$9,$10,$11)
            RETURNING *
            """,
            applicant_id, body.raw_name,
            canonical.code if canonical else None,
            canonical.name if canonical else None,
            canonical.type.value if canonical else None,
            body.issuer or (canonical.issuer if canonical else None),
            norm.confidence, not norm.is_confident,
            body.issued_date, body.expires_date, body.document_url,
        )
        await append_credential_record(
            conn, applicant_id, str(row["id"]), "created",
            {
                "credential_id": str(row["id"]),
                "raw_name": body.raw_name,
                "canonical_code": canonical.code if canonical else None,
                "source": "self",
                "verification_level": 0,
            },
        )
    return _to_out(row)


class VerifyDocIn(BaseModel):
    document_text: Optional[str] = Field(default=None, max_length=20000)
    document_url: Optional[str] = Field(default=None, max_length=1000)


class VerifyDocOut(BaseModel):
    decision: str
    score: float
    name_matched: bool
    issuer_matched: bool
    document_authentic: bool
    reasons: list[str]
    new_verification_level: int
    new_badge: str
    provider: str


@router.post("/{credential_id}/verify-document", response_model=VerifyDocOut)
async def verify_document(
    credential_id: str,
    body: VerifyDocIn,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Run an uploaded document through OCR + assessment. A confirmed issuer-matched,
    authentic document raises the credential to Institution-Verified; a borderline
    result is routed to admin review; a failure leaves it Self-Reported."""
    if not (body.document_text or body.document_url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide document_text or document_url")

    provider = get_ocr_provider()
    if body.document_text and hasattr(provider, "analyze_text"):
        extraction = provider.analyze_text(body.document_text)
    else:
        extraction = provider.analyze(body.document_url or body.document_text or "")

    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user.user_id)
        cred = await conn.fetchrow(
            "SELECT * FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            credential_id, applicant_id,
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")

        claimed_name = cred["canonical_name"] or cred["raw_name"]
        a = doc_verify.assess(extraction, claimed_name, cred["issuer"])

        current = int(cred["verification_level"])
        new_level = current
        meta = {
            "ocr": {
                "provider": extraction.provider,
                "decision": a.decision,
                "score": a.score,
                "issuer_detected": extraction.issuer_detected,
                "reasons": a.reasons,
            }
        }

        if a.decision == "verified":
            derived = derive_level(VerificationEvidence(
                source=CredentialSource.DOCUMENT_UPLOAD,
                issuer_matched=True, document_authentic=True,
            ))
            new_level = max(current, derived.value)
            await conn.execute(
                "UPDATE public.credentials SET verification_level = $2, source = 'document_upload', "
                "needs_review = false, document_url = COALESCE($3, document_url), "
                "metadata = COALESCE(metadata, '{}'::jsonb) || $4 WHERE id = $1",
                credential_id, new_level, body.document_url, meta,
            )
            await append_credential_record(
                conn, applicant_id, credential_id, "document_verified",
                {"credential_id": credential_id, "verification_level": new_level,
                 "score": a.score, "source": "document_upload"},
            )
        else:
            await conn.execute(
                "UPDATE public.credentials SET needs_review = $2, "
                "metadata = COALESCE(metadata, '{}'::jsonb) || $3 WHERE id = $1",
                credential_id, a.decision == "review", meta,
            )
            await append_credential_record(
                conn, applicant_id, credential_id, f"document_{a.decision}",
                {"credential_id": credential_id, "score": a.score, "decision": a.decision},
            )

    return VerifyDocOut(
        decision=a.decision, score=a.score, name_matched=a.name_matched,
        issuer_matched=a.issuer_matched, document_authentic=a.document_authentic,
        reasons=a.reasons, new_verification_level=new_level,
        new_badge=VerificationLevel(new_level).badge, provider=extraction.provider,
    )


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: str,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user.user_id)
        owned = await conn.fetchrow(
            "SELECT id FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            credential_id, applicant_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
        # Record the revocation BEFORE deleting (audit trail outlives the row).
        await append_credential_record(
            conn, applicant_id, credential_id, "revoked",
            {"credential_id": credential_id, "action": "deleted_by_owner"},
        )
        await conn.execute("DELETE FROM public.credentials WHERE id = $1", credential_id)
    return None
