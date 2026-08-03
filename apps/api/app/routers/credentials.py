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
from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth.dependencies import CurrentUser, require_applicant
from app.db import get_db
from app.integrations.badges import verify_badge_url
from app.integrations.ocr import get_ocr_provider, is_authoritative_provider
from app.skilled_pro import doc_verify, taxonomy
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    VerificationLevel,
    derive_level,
)

router = APIRouter(prefix="/applicant/me/credentials", tags=["credentials"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CredentialIn(BaseModel):
    raw_name: str = Field(min_length=2, max_length=200)
    # Structured category — validated against the taxonomy's CredentialType
    # (certification | license | degree | apprenticeship | safety | union | other).
    # When provided it drives the stored credential_type; otherwise we fall back
    # to the canonical taxonomy match.
    category: Optional[taxonomy.CredentialType] = None
    issuer: Optional[str] = Field(default=None, max_length=200)
    issued_date: Optional[date] = None
    expires_date: Optional[date] = None
    document_url: Optional[str] = Field(default=None, max_length=1000)
    # Optional issuer-assigned identifier + public verification URL (LinkedIn's
    # "Credential ID" / "Credential URL" fields). Stored in the existing
    # ``metadata`` jsonb column — no schema change.
    credential_ref: Optional[str] = Field(default=None, max_length=120)
    credential_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator("raw_name")
    @classmethod
    def _raw_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("raw_name must not be blank")
        return v

    @field_validator("credential_url")
    @classmethod
    def _credential_url_http(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("credential_url must be an http(s) URL")
        return v

    @model_validator(mode="after")
    def _dates_ordered(self) -> "CredentialIn":
        if (
            self.issued_date is not None
            and self.expires_date is not None
            and self.expires_date < self.issued_date
        ):
            raise ValueError("expires_date cannot be before issued_date")
        return self


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
    credential_ref: Optional[str] = None
    credential_url: Optional[str] = None
    # Partner-verification metadata (Phase 11 — NCCER / NSC / Credential Engine)
    provider_source: Optional[str] = None            # 'nccer' | 'nsc' | 'credential_engine' | ...
    provider_verified_at: Optional[str] = None       # ISO timestamp
    provider_external_ref: Optional[str] = None      # NCCER card #, NSC hash, etc.
    provider_stubbed: bool = False                   # True when result came from stub (no partner key)
    verification_provider: Optional[str] = None      # From credential_definitions — what CAN verify this
    ctdl_uri: Optional[str] = None
    authority: Optional[str] = None
    validity_note: Optional[str] = None              # Typical validity/renewal cadence
    verify_url: Optional[str] = None                 # Public issuer registry lookup, if one exists
    # TRUE while a document/badge verification sits in the admin review lane
    # (a pending 'credential_ambiguity' item). Drives the applicant-facing
    # "In review" state; flips back off when admin confirms OR dismisses.
    verification_review_pending: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_applicant_id(conn: asyncpg.Connection, user: CurrentUser) -> str:
    # View-as resolves by applicant id directly (supports unlinked applicants).
    row = await conn.fetchrow(
        "SELECT id::text AS id FROM public.applicants "
        "WHERE id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))",
        user.user_id,
        user.view_as_applicant_id,
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
    meta = _safe_get(row, "metadata")
    meta = meta if isinstance(meta, dict) else {}
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
        credential_ref=meta.get("credential_ref"),
        credential_url=meta.get("credential_url"),
        provider_source=_safe_get(row, "provider_source"),
        provider_verified_at=verified_at.isoformat() if verified_at else None,
        provider_external_ref=_safe_get(row, "provider_external_ref"),
        provider_stubbed=stubbed,
        verification_provider=_safe_get(row, "def_verification_provider"),
        ctdl_uri=_safe_get(row, "def_ctdl_uri"),
        authority=_safe_get(row, "def_authority"),
        validity_note=_safe_get(row, "def_validity_note"),
        verify_url=_safe_get(row, "def_verification_url"),
        verification_review_pending=bool(_safe_get(row, "verification_review_pending")),
    )


async def _definition_id_for_slug(conn: asyncpg.Connection, slug: Optional[str]):
    """Resolve a taxonomy slug to its credential_definitions row id (or None)."""
    if not slug:
        return None
    row = await conn.fetchrow(
        "SELECT id FROM public.credential_definitions WHERE canonical_code = $1 AND active",
        slug,
    )
    return row["id"] if row else None


async def _enqueue_verification_review(
    conn: asyncpg.Connection,
    credential_id: str,
    description: str,
) -> None:
    """Route a document/badge verification outcome to the admin review feed
    (once per pending credential).

    This is the verification lane ('credential_ambiguity' → /admin/review).
    It must NOT set credentials.needs_review — that column is the
    taxonomy-normalization flag and feeds the admin credentials queue; a
    perfectly-normalized credential whose document merely needs a human look
    does not belong there.
    """
    existing = await conn.fetchrow(
        "SELECT id FROM public.review_queue_items "
        "WHERE entity_type = 'credential' AND entity_id = $1::uuid "
        "AND item_type = 'credential_ambiguity' AND status = 'pending' LIMIT 1",
        credential_id,
    )
    if existing:
        return
    await conn.execute(
        """
        INSERT INTO public.review_queue_items
          (item_type, entity_type, entity_id, description, flags, confidence_level, priority)
        VALUES ('credential_ambiguity', 'credential', $1::uuid, $2, $3::jsonb, 'low', 4)
        """,
        credential_id, description,
        [{"flag_type": "verification_review", "detail": description}],
    )


async def _enqueue_taxonomy_review(
    conn: asyncpg.Connection,
    credential_id: str,
    raw_name: str,
    norm: taxonomy.NormalizationResult,
) -> None:
    """Route an unmatched / low-confidence normalization to the admin review
    queue (once per pending credential) — never silent-guess."""
    existing = await conn.fetchrow(
        "SELECT id FROM public.review_queue_items "
        "WHERE entity_type = 'credential' AND entity_id = $1::uuid "
        "AND item_type = 'taxonomy_mismatch' AND status = 'pending' LIMIT 1",
        credential_id,
    )
    if existing:
        return
    if norm.canonical is not None:
        description = (
            f"Credential '{raw_name}' matched '{norm.canonical.name}' at low "
            f"confidence ({norm.confidence:.2f}, {norm.method}). Confirm or fix."
        )
    else:
        description = f"Credential '{raw_name}' has no canonical taxonomy match."
    await conn.execute(
        """
        INSERT INTO public.review_queue_items
          (item_type, entity_type, entity_id, description, flags, confidence_level, priority)
        VALUES ('taxonomy_mismatch', 'credential', $1::uuid, $2, $3::jsonb, 'low', 5)
        """,
        credential_id, description,
        [{"flag_type": "taxonomy_normalization",
          "detail": {"raw_name": raw_name, "method": norm.method,
                     "confidence": norm.confidence,
                     "candidate": norm.canonical.slug if norm.canonical else None}}],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[CredentialOut])
async def list_credentials(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
        rows = await conn.fetch(
            """
            SELECT c.id, c.raw_name, c.canonical_code, c.canonical_name, c.credential_type,
                   c.issuer, c.normalization_confidence, c.needs_review, c.source,
                   c.verification_level, c.issued_date, c.expires_date, c.document_url,
                   c.metadata,
                   c.provider_source, c.provider_verified_at, c.provider_external_ref,
                   c.provider_receipt,
                   d.verification_provider AS def_verification_provider,
                   d.ctdl_uri              AS def_ctdl_uri,
                   d.authority             AS def_authority,
                   d.validity_note         AS def_validity_note,
                   d.verification_url      AS def_verification_url,
                   EXISTS (
                       SELECT 1 FROM public.review_queue_items q
                        WHERE q.entity_type = 'credential' AND q.entity_id = c.id
                          AND q.item_type = 'credential_ambiguity'
                          AND q.status = 'pending'
                   ) AS verification_review_pending
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
    # The worker's chosen category drives credential_type; the taxonomy match is
    # only a fallback when no category was supplied (legacy clients).
    credential_type = (
        body.category.value if body.category
        else (canonical.type.value if canonical else None)
    )
    extra_meta = {
        k: v for k, v in (
            ("credential_ref", (body.credential_ref or "").strip() or None),
            ("credential_url", body.credential_url),
        ) if v
    }
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
        definition_id = await _definition_id_for_slug(
            conn, canonical.slug if canonical else None
        )
        row = await conn.fetchrow(
            """
            INSERT INTO public.credentials
                (applicant_id, raw_name, canonical_code, canonical_name,
                 credential_type, issuer, normalization_confidence, needs_review,
                 source, verification_level, issued_date, expires_date, document_url,
                 metadata, definition_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'self',0,$9,$10,$11,$12,$13)
            RETURNING *
            """,
            applicant_id, body.raw_name,
            canonical.slug if canonical else None,
            canonical.name if canonical else None,
            credential_type,
            body.issuer or (canonical.issuer if canonical else None),
            norm.confidence, not norm.is_confident,
            body.issued_date, body.expires_date, body.document_url,
            extra_meta, definition_id,
        )
        if not norm.is_confident:
            await _enqueue_taxonomy_review(conn, str(row["id"]), body.raw_name, norm)
        await append_credential_record(
            conn, applicant_id, str(row["id"]), "created",
            {
                "credential_id": str(row["id"]),
                "raw_name": body.raw_name,
                "category": credential_type,
                "canonical_code": canonical.slug if canonical else None,
                "source": "self",
                "verification_level": 0,
            },
        )
        # Instrument the funnel's "added a credential" step — same connection
        # as the business insert. (Admin engagement analytics read this.)
        await conn.execute(
            """
            INSERT INTO public.engagement_events (applicant_id, event_type, event_data)
            VALUES ($1, 'credential_added', $2::jsonb)
            """,
            applicant_id,
            {
                "credential_id": str(row["id"]),
                "canonical_code": canonical.slug if canonical else None,
                "source": "self",
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
        applicant_id = await _resolve_applicant_id(conn, user)
        cred = await conn.fetchrow(
            "SELECT * FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            credential_id, applicant_id,
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")

        claimed_name = cred["canonical_name"] or cred["raw_name"]
        a = doc_verify.assess(extraction, claimed_name, cred["issuer"])

        # A "verified" decision may only AUTO-raise the badge when it comes from
        # an authoritative OCR provider (real cloud OCR with forgery checks). The
        # heuristic/demo provider merely confirms the text looks like a document,
        # so its best outcome is admin review — never an automatic verified badge.
        effective_decision = a.decision
        if a.decision == "verified" and not is_authoritative_provider(extraction.provider):
            effective_decision = "review"

        current = int(cred["verification_level"])
        new_level = current
        meta = {
            "ocr": {
                "provider": extraction.provider,
                "decision": a.decision,
                "effective_decision": effective_decision,
                "authoritative": is_authoritative_provider(extraction.provider),
                "score": a.score,
                "issuer_detected": extraction.issuer_detected,
                "reasons": a.reasons,
            }
        }

        if effective_decision == "verified":
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
            # Record the outcome; the review work (if any) goes to the
            # verification lane — never the taxonomy needs_review flag.
            await conn.execute(
                "UPDATE public.credentials SET "
                "metadata = COALESCE(metadata, '{}'::jsonb) || $2 WHERE id = $1",
                credential_id, meta,
            )
            if effective_decision == "review":
                await _enqueue_verification_review(
                    conn, credential_id,
                    f"Document for '{cred['raw_name']}' needs a human look "
                    f"(decision: {a.decision}, provider: {extraction.provider}).",
                )
            await append_credential_record(
                conn, applicant_id, credential_id, f"document_{effective_decision}",
                {"credential_id": credential_id, "score": a.score,
                 "decision": effective_decision, "raw_decision": a.decision},
            )

    reasons = list(a.reasons)
    if effective_decision == "review" and a.decision == "verified":
        reasons.append("sent to SkillPointe review because automatic verification needs an authoritative document scan")

    return VerifyDocOut(
        decision=effective_decision, score=a.score, name_matched=a.name_matched,
        issuer_matched=a.issuer_matched, document_authentic=a.document_authentic,
        reasons=reasons, new_verification_level=new_level,
        new_badge=VerificationLevel(new_level).badge, provider=extraction.provider,
    )


class VerifyBadgeIn(BaseModel):
    badge_url: str = Field(min_length=8, max_length=500)


class VerifyBadgeOut(BaseModel):
    verified: bool
    provider: str
    issuer: Optional[str] = None
    badge_name: Optional[str] = None
    earner_name: Optional[str] = None
    name_matched: bool = False
    new_verification_level: int
    new_badge: str
    detail: str = ""


def _name_overlap(claimed: str | None, found: str | None) -> float:
    """Fraction of the claimed-name tokens present in the found name."""
    import re as _re
    def toks(s: str | None) -> set[str]:
        return {t for t in _re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1}
    a, b = toks(claimed), toks(found)
    if not a:
        return 0.0
    return len(a & b) / len(a)


@router.post("/{credential_id}/verify-badge", response_model=VerifyBadgeOut)
async def verify_badge(
    credential_id: str,
    body: VerifyBadgeIn,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Verify a credential from a public digital-badge URL (Credly / Open Badges).

    A confirmed badge is registry-grade: the issuer hosts the assertion, so we
    raise the credential to Institution-Verified when the badge is valid AND its
    earner name matches the profile. This is the highest-trust, zero-cost tier —
    NCCER, for instance, issues through Credly.
    """
    result = await verify_badge_url(body.badge_url)

    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
        cred = await conn.fetchrow(
            "SELECT * FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            credential_id, applicant_id,
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")

        who = await conn.fetchrow(
            "SELECT first_name, last_name FROM public.applicants WHERE id = $1", applicant_id,
        )
        profile_name = " ".join(filter(None, [who["first_name"], who["last_name"]])) if who else ""
        # If the badge exposes no earner name we can't cross-check identity, so we
        # do not auto-verify — route to review instead.
        name_matched = bool(result.earner_name) and _name_overlap(profile_name, result.earner_name) >= 0.5

        meta = {
            "badge": {
                "provider": result.provider, "issuer": result.issuer,
                "badge_name": result.badge_name, "earner_name": result.earner_name,
                "url": result.url, "name_matched": name_matched, "detail": result.detail,
            }
        }

        if result.ok and name_matched:
            derived = derive_level(VerificationEvidence(
                source=CredentialSource.DIGITAL_BADGE,
                issuer_matched=True, document_authentic=True,
            ))
            new_level = max(int(cred["verification_level"]), derived.value)
            await conn.execute(
                "UPDATE public.credentials SET verification_level = $2, source = 'digital_badge', "
                "needs_review = false, issuer = COALESCE(issuer, $3), "
                "metadata = COALESCE(metadata, '{}'::jsonb) || $4 WHERE id = $1",
                credential_id, new_level, result.issuer, meta,
            )
            await append_credential_record(
                conn, applicant_id, credential_id, "badge_verified",
                {"credential_id": credential_id, "verification_level": new_level,
                 "provider": result.provider, "source": "digital_badge"},
            )
            return VerifyBadgeOut(
                verified=True, provider=result.provider, issuer=result.issuer,
                badge_name=result.badge_name, earner_name=result.earner_name,
                name_matched=True, new_verification_level=new_level,
                new_badge=VerificationLevel(new_level).badge,
                detail="Badge verified against the issuer.",
            )

        # Not verified: valid badge but name mismatch → review; invalid → rejected.
        # Review goes to the verification lane (review_queue_items), never the
        # taxonomy needs_review flag.
        needs_review = bool(result.ok and result.earner_name and not name_matched)
        await conn.execute(
            "UPDATE public.credentials SET "
            "metadata = COALESCE(metadata, '{}'::jsonb) || $2 WHERE id = $1",
            credential_id, meta,
        )
        if needs_review:
            await _enqueue_verification_review(
                conn, credential_id,
                f"Badge for '{cred['raw_name']}' is valid but the earner name "
                f"doesn't match the profile. Confirm identity.",
            )
        await append_credential_record(
            conn, applicant_id, credential_id,
            "badge_review" if needs_review else "badge_rejected",
            {"credential_id": credential_id, "provider": result.provider, "detail": result.detail},
        )
        level = int(cred["verification_level"])
        detail = (
            "Badge is valid but the name doesn't match your profile. Sent to review."
            if needs_review else (result.detail or "Could not verify this badge.")
        )
        return VerifyBadgeOut(
            verified=False, provider=result.provider, issuer=result.issuer,
            badge_name=result.badge_name, earner_name=result.earner_name,
            name_matched=name_matched, new_verification_level=level,
            new_badge=VerificationLevel(level).badge, detail=detail,
        )


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: str,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
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
