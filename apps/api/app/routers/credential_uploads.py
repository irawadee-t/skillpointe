"""
Credential document upload — the first-party document lane.

Nobody retypes a license. This router replaces the old paste-the-text flow with
industry-standard capture UX (Persona/Veriff-style):

  POST /applicant/me/credentials/{id}/verify/upload       — direct file upload
  POST /applicant/me/credentials/{id}/verify/phone-link   — mint a QR handoff link
  GET  /applicant/me/credentials/{id}/verify/phone-status — desktop polls for landing
  POST /credential-uploads/{token}                        — UNAUTHENTICATED phone upload

The uploaded file is stored in Supabase Storage (service-role), then run through
the existing OCR → doc_verify assessment pipeline. When the OCR provider cannot
read the file (images under the heuristic provider, or no provider at all) the
credential is routed to the SkillPointe manual review queue — never a dead end.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_applicant
from app.config import get_settings
from app.db import get_db
from app.integrations.ocr import get_ocr_provider, is_authoritative_provider
from app.skilled_pro import doc_verify, taxonomy
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    VerificationLevel,
    derive_level,
)
from app.util.audit import write_audit
from app.util.rate_limit import rate_limit_sensitive, rate_limit_sensitive_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applicant/me/credentials", tags=["credentials"])
public_router = APIRouter(tags=["credential-uploads"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# MIME type → storage extension. Anything else is a 415.
ALLOWED_MIME: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heic",
    "application/pdf": "pdf",
}
_EXT_TO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".pdf": "application/pdf",
}

TOKEN_TTL_MINUTES = 15


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DocUploadOut(BaseModel):
    status: str                        # "accepted" | "needs_review"
    decision: str                      # raw assessment decision (or "unreadable")
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    new_verification_level: int
    new_badge: str
    provider: str = "null"
    detail: str = ""


class DocumentUrlOut(BaseModel):
    url: str
    content_type: str
    expires_in: int


class PhoneLinkOut(BaseModel):
    url: str
    expires_at: str


class PhoneStatusOut(BaseModel):
    landed: bool
    verification_level: int
    badge: str
    needs_review: bool


class PhoneUploadOut(BaseModel):
    ok: bool
    status: str        # "accepted" | "needs_review"
    detail: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_upload(filename: str | None, content_type: str | None, size: int) -> tuple[str, str]:
    """Return (mime, extension) or raise 413/415. MIME wins; falls back to the
    file extension for browsers that send application/octet-stream."""
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB).",
        )
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file.")

    mime = (content_type or "").lower().split(";")[0].strip()
    if mime not in ALLOWED_MIME:
        fn = (filename or "").lower()
        mime = next((m for ext, m in _EXT_TO_MIME.items() if fn.endswith(ext)), "")
    if mime not in ALLOWED_MIME:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file type. Upload a JPG, PNG, WebP, HEIC photo or a PDF.",
        )
    return mime, ALLOWED_MIME[mime]


async def _resolve_owned_credential(
    conn: asyncpg.Connection, credential_id: UUID, user: "CurrentUser"
) -> asyncpg.Record:
    # View-as resolves by applicant id directly (supports unlinked applicants).
    row = await conn.fetchrow(
        """
        SELECT c.*, a.id AS a_id, a.user_id AS a_user_id
          FROM public.credentials c
          JOIN public.applicants  a ON a.id = c.applicant_id
         WHERE c.id = $1
           AND a.id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))
        """,
        credential_id, user.user_id, user.view_as_applicant_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
    return row


async def store_document(
    content: bytes, mime: str, ext: str, applicant_id: str, credential_id: str
) -> Optional[str]:
    """Upload the raw file to the Supabase Storage documents bucket with the
    service-role key. Returns the storage path, or None on any failure — a
    storage outage must not block the verification flow."""
    settings = get_settings()
    path = f"credentials/{applicant_id}/{credential_id}/{uuid4().hex}.{ext}"
    url = f"{settings.supabase_url}/storage/v1/object/{settings.storage_bucket_documents}/{path}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                content=content,
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": mime,
                    "x-upsert": "true",
                },
            )
        if resp.status_code in (200, 201):
            return f"{settings.storage_bucket_documents}/{path}"
        logger.warning("Credential document storage upload failed (%s): %s", resp.status_code, resp.text[:200])
    except Exception as exc:  # network / config — degrade gracefully
        logger.warning("Credential document storage upload errored: %s", exc)
    return None


SIGNED_URL_TTL_SECONDS = 600  # 10 minutes — long enough to view, short enough to leak nothing


def _storage_path_for(document_url: str) -> str:
    """`document_url` is stored as "<bucket>/<path>" (see store_document).
    Return just the object path inside the bucket."""
    bucket = get_settings().storage_bucket_documents
    path = document_url.strip().lstrip("/")
    prefix = f"{bucket}/"
    if path.startswith(prefix):
        path = path[len(prefix):]
    return path


async def create_signed_url(path: str) -> Optional[str]:
    """Ask Supabase Storage for a short-lived signed URL for a private object."""
    settings = get_settings()
    endpoint = (
        f"{settings.supabase_url}/storage/v1/object/sign/"
        f"{settings.storage_bucket_documents}/{path}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                endpoint,
                json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 200:
            signed = (resp.json() or {}).get("signedURL") or ""
            if signed:
                return f"{settings.supabase_url}/storage/v1{signed if signed.startswith('/') else '/' + signed}"
        logger.warning("Signed URL request failed (%s): %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Signed URL request errored: %s", exc)
    return None


async def _route_to_review(
    conn: asyncpg.Connection,
    *,
    credential_id: str,
    applicant_id: str,
    meta: dict,
    description: str,
    record_event: str,
    record_payload: dict,
) -> None:
    """Enqueue an admin review item (once per pending credential) and append to
    the signed audit chain.

    Deliberately does NOT touch credentials.needs_review: that column is the
    taxonomy-normalization flag (feeds the admin credentials "Needs review"
    queue + sidebar badge). Document-review work lives in review_queue_items
    ('credential_ambiguity') and surfaces on /admin/review — flipping the
    normalization flag here used to put perfectly-matched credentials
    ("OSHA 30", exact alias, 100% confidence) into the normalization queue.
    """
    await conn.execute(
        "UPDATE public.credentials SET "
        "metadata = COALESCE(metadata, '{}'::jsonb) || $2 WHERE id = $1",
        credential_id, meta,
    )
    existing = await conn.fetchrow(
        "SELECT id FROM public.review_queue_items "
        "WHERE entity_type = 'credential' AND entity_id = $1 AND status = 'pending' "
        "AND item_type = 'credential_ambiguity' LIMIT 1",
        credential_id,
    )
    if not existing:
        await conn.execute(
            """
            INSERT INTO public.review_queue_items
              (item_type, entity_type, entity_id, description, flags, confidence_level, priority)
            VALUES ('credential_ambiguity', 'credential', $1, $2, $3, 'low', 4)
            """,
            credential_id, description,
            [{"flag_type": "document_upload", "detail": description}],
        )
    await append_credential_record(conn, applicant_id, credential_id, record_event, record_payload)


async def process_document_upload(
    conn: asyncpg.Connection,
    *,
    cred: asyncpg.Record,
    applicant_id: str,
    actor_user_id: Optional[str],
    content: bytes,
    mime: str,
    ext: str,
    filename: str,
    channel: str,  # "desktop" | "phone"
) -> DocUploadOut:
    """Shared pipeline: store → extract text → assess → verify / route to review.

    Guaranteed to resolve to either an accepted (verified) state or a
    submitted-for-review state — an unreadable file is never a dead end.
    """
    credential_id = str(cred["id"])
    storage_path = await store_document(content, mime, ext, str(applicant_id), credential_id)

    provider = get_ocr_provider()
    text = ""
    try:
        if hasattr(provider, "extract_text_from_bytes"):
            text = provider.extract_text_from_bytes(content, mime) or ""
    except Exception as exc:  # OCR unavailable/misconfigured → review, not failure
        logger.warning("OCR text extraction unavailable (%s) — routing to review.", exc)
        text = ""

    current_level = int(cred["verification_level"])
    canonical_name = cred["canonical_name"]

    # Late canonicalization: rows created before the taxonomy expanded (or via
    # older clients) may have no canonical link. Re-run the deterministic
    # normalizer on the applicant's raw text — never overwrite raw_name, and
    # only persist when the normalizer is confident.
    if not cred["canonical_code"]:
        norm = taxonomy.normalize(cred["raw_name"])
        if norm.is_confident and norm.canonical is not None:
            canonical_name = norm.canonical.name
            await conn.execute(
                """
                UPDATE public.credentials
                   SET canonical_code = $2, canonical_name = $3,
                       credential_type = COALESCE(credential_type, $4),
                       issuer = COALESCE(issuer, $5),
                       normalization_confidence = $6,
                       definition_id = COALESCE(definition_id,
                           (SELECT d.id FROM public.credential_definitions d
                             WHERE d.canonical_code = $2 AND d.active))
                 WHERE id = $1
                """,
                credential_id, norm.canonical.slug, norm.canonical.name,
                norm.canonical.type.value, norm.canonical.issuer, norm.confidence,
            )

    claimed_name = canonical_name or cred["raw_name"]

    if text.strip():
        try:
            extraction = (
                provider.analyze_text(text) if hasattr(provider, "analyze_text")
                else provider.analyze(text)
            )
            a = doc_verify.assess(extraction, claimed_name, cred["issuer"])
        except Exception as exc:
            logger.warning("Document assessment failed (%s) — routing to review.", exc)
            extraction = None
            a = None
    else:
        extraction = None
        a = None

    # Auto-verification is reserved for authoritative OCR providers (real cloud
    # OCR with forgery checks) — same guardrail as the legacy text endpoint.
    verified = bool(
        a is not None
        and a.decision == "verified"
        and extraction is not None
        and is_authoritative_provider(extraction.provider)
    )

    meta = {
        "document_upload": {
            "channel": channel,
            "filename": filename,
            "mime": mime,
            "size_bytes": len(content),
            "storage_path": storage_path,
            "ocr_provider": extraction.provider if extraction else "none",
            "decision": a.decision if a else "unreadable",
            "score": a.score if a else 0.0,
        }
    }

    if verified and a is not None:
        derived = derive_level(VerificationEvidence(
            source=CredentialSource.DOCUMENT_UPLOAD,
            issuer_matched=True, document_authentic=True,
        ))
        new_level = max(current_level, derived.value)
        await conn.execute(
            "UPDATE public.credentials SET verification_level = $2, source = 'document_upload', "
            "needs_review = false, document_url = COALESCE($3, document_url), "
            "metadata = COALESCE(metadata, '{}'::jsonb) || $4 WHERE id = $1",
            credential_id, new_level, storage_path, meta,
        )
        await append_credential_record(
            conn, str(applicant_id), credential_id, "document_verified",
            {"credential_id": credential_id, "verification_level": new_level,
             "score": a.score, "source": "document_upload", "channel": channel},
        )
        out = DocUploadOut(
            status="accepted", decision=a.decision, score=a.score,
            reasons=list(a.reasons), new_verification_level=new_level,
            new_badge=VerificationLevel(new_level).badge,
            provider=extraction.provider if extraction else "none",
            detail="Document verified. Your badge has been updated.",
        )
    else:
        if storage_path:
            await conn.execute(
                "UPDATE public.credentials SET document_url = COALESCE($2, document_url) WHERE id = $1",
                credential_id, storage_path,
            )
        reasons = list(a.reasons) if a else []
        if a is None:
            reasons.append("document could not be machine-read, so it was sent to SkillPointe review")
            description = f"Uploaded document ({filename}) could not be machine-read; needs human review."
        else:
            reasons.append("sent to SkillPointe review because automatic verification needs an authoritative document scan")
            description = f"Uploaded document ({filename}) scored {a.score:.2f} ({a.decision}); needs human review."
        await _route_to_review(
            conn,
            credential_id=credential_id,
            applicant_id=str(applicant_id),
            meta=meta,
            description=description,
            record_event="document_review",
            record_payload={
                "credential_id": credential_id, "channel": channel,
                "decision": a.decision if a else "unreadable",
                "score": a.score if a else 0.0, "storage_path": storage_path,
            },
        )
        out = DocUploadOut(
            status="needs_review", decision=a.decision if a else "unreadable",
            score=a.score if a else 0.0, reasons=reasons,
            new_verification_level=current_level,
            new_badge=VerificationLevel(current_level).badge,
            provider=extraction.provider if extraction else "none",
            detail="Sent to SkillPointe review. We'll badge it once confirmed.",
        )

    await write_audit(
        conn,
        action="credential.document_uploaded",
        actor_id=actor_user_id,
        actor_role="applicant",
        entity_type="credential",
        entity_id=credential_id,
        metadata={
            "channel": channel, "filename": filename, "mime": mime,
            "size_bytes": len(content), "storage_path": storage_path,
            "outcome": out.status,
        },
    )
    return out


# ---------------------------------------------------------------------------
# Authenticated endpoints (desktop)
# ---------------------------------------------------------------------------

@router.post(
    "/{credential_id}/verify/upload",
    response_model=DocUploadOut,
    dependencies=[Depends(rate_limit_sensitive("credential_doc_upload"))],
)
async def upload_credential_document(
    credential_id: UUID,
    user: Annotated[CurrentUser, Depends(require_applicant)],
    file: UploadFile = File(...),
):
    """Upload a photo/scan of a certificate or license for this credential."""
    content = await file.read()
    mime, ext = validate_upload(file.filename, file.content_type, len(content))

    async with get_db() as conn:
        cred = await _resolve_owned_credential(conn, credential_id, user)
        return await process_document_upload(
            conn,
            cred=cred,
            applicant_id=cred["applicant_id"],
            actor_user_id=user.user_id,
            content=content,
            mime=mime,
            ext=ext,
            filename=file.filename or "document",
            channel="desktop",
        )


@router.get("/{credential_id}/document-url", response_model=DocumentUrlOut)
async def get_credential_document_url(
    credential_id: UUID,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Short-lived signed URL for the credential's uploaded document.

    The documents bucket is private, so the browser cannot render
    `document_url` directly. Ownership is enforced by the same join used
    everywhere else in this router — someone else's credential, or one with no
    document, is an indistinguishable 404.
    """
    async with get_db() as conn:
        cred = await _resolve_owned_credential(conn, credential_id, user)

    document_url = cred["document_url"]
    if not document_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document for this credential")

    path = _storage_path_for(str(document_url))
    signed = await create_signed_url(path)
    if not signed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document is not available")

    ext = f".{path.rsplit('.', 1)[-1].lower()}" if "." in path else ""
    return DocumentUrlOut(
        url=signed,
        content_type=_EXT_TO_MIME.get(ext, "application/octet-stream"),
        expires_in=SIGNED_URL_TTL_SECONDS,
    )


@router.post("/{credential_id}/verify/phone-link", response_model=PhoneLinkOut)
async def create_phone_link(
    credential_id: UUID,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Mint a single-use, 15-minute link the applicant opens on their phone
    (rendered as a QR code by the web app) to photograph the document."""
    token = secrets.token_urlsafe(32)
    async with get_db() as conn:
        cred = await _resolve_owned_credential(conn, credential_id, user)
        row = await conn.fetchrow(
            """
            INSERT INTO public.credential_upload_tokens
              (credential_id, applicant_id, token_hash, expires_at)
            VALUES ($1, $2, $3, now() + make_interval(mins => $4))
            RETURNING expires_at
            """,
            credential_id, cred["applicant_id"], hash_token(token), TOKEN_TTL_MINUTES,
        )

    origins = get_settings().cors_origins_list
    origin = origins[0] if origins else "http://localhost:3000"
    return PhoneLinkOut(
        url=f"{origin}/verify-doc/{token}",
        expires_at=row["expires_at"].isoformat(),
    )


@router.get("/{credential_id}/verify/phone-status", response_model=PhoneStatusOut)
async def phone_upload_status(
    credential_id: UUID,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    """Desktop polls this while the QR code is showing — reports whether the
    phone upload landed and the credential's current verification state."""
    async with get_db() as conn:
        cred = await _resolve_owned_credential(conn, credential_id, user)
        latest = await conn.fetchrow(
            """
            SELECT used_at FROM public.credential_upload_tokens
             WHERE credential_id = $1
          ORDER BY created_at DESC LIMIT 1
            """,
            credential_id,
        )
        # "In review" for the poller = a pending admin review item exists
        # (document-review lane) — NOT credentials.needs_review, which is the
        # taxonomy-normalization flag.
        pending = await conn.fetchrow(
            "SELECT id FROM public.review_queue_items "
            "WHERE entity_type = 'credential' AND entity_id = $1 "
            "AND status = 'pending' AND item_type = 'credential_ambiguity' LIMIT 1",
            credential_id,
        )
    level = int(cred["verification_level"])
    return PhoneStatusOut(
        landed=bool(latest and latest["used_at"]),
        verification_level=level,
        badge=VerificationLevel(level).badge,
        needs_review=bool(pending),
    )


# ---------------------------------------------------------------------------
# Unauthenticated phone endpoint (token IS the credential)
# ---------------------------------------------------------------------------

@public_router.post(
    "/credential-uploads/{token}",
    response_model=PhoneUploadOut,
    dependencies=[Depends(rate_limit_sensitive_ip("credential_phone_upload"))],
)
async def phone_upload(token: str, file: UploadFile = File(...)):
    """Accept the photo from the phone page. The single-use token (minted by
    phone-link) is the only credential; any invalid/expired/used token is a
    plain 404 so the endpoint offers no oracle."""
    content = await file.read()
    mime, ext = validate_upload(file.filename, file.content_type, len(content))

    token_hash = hash_token(token)
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, token_hash, credential_id, applicant_id, used_at, expires_at
              FROM public.credential_upload_tokens
             WHERE token_hash = $1
            """,
            token_hash,
        )
        now = datetime.now(timezone.utc)
        if (
            not row
            or not hmac.compare_digest(str(row["token_hash"]), token_hash)
            or row["used_at"] is not None
            or row["expires_at"] <= now
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

        # Single-use: claim atomically so a raced duplicate gets a 404.
        claimed = await conn.fetchrow(
            "UPDATE public.credential_upload_tokens SET used_at = now() "
            "WHERE id = $1 AND used_at IS NULL RETURNING id",
            row["id"],
        )
        if not claimed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

        cred = await conn.fetchrow(
            "SELECT * FROM public.credentials WHERE id = $1 AND applicant_id = $2",
            row["credential_id"], row["applicant_id"],
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

        actor = await conn.fetchrow(
            "SELECT user_id FROM public.applicants WHERE id = $1", row["applicant_id"],
        )
        result = await process_document_upload(
            conn,
            cred=cred,
            applicant_id=row["applicant_id"],
            actor_user_id=str(actor["user_id"]) if actor else None,
            content=content,
            mime=mime,
            ext=ext,
            filename=file.filename or "photo",
            channel="phone",
        )

    return PhoneUploadOut(
        ok=True,
        status=result.status,
        detail=(
            "Verified. Your badge has been updated."
            if result.status == "accepted"
            else "Got it. Sent to SkillPointe review. You can close this page."
        ),
    )
