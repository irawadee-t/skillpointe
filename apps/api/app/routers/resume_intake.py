"""
Resume upload + parse for applicant onboarding.

POST /applicant/me/resume/parse   — upload a resume, return structured fields for confirmation
POST /applicant/me/resume/apply   — merge confirmed fields into the applicant profile
GET  /applicant/me/resume/uploads — list this applicant's prior uploads
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro import taxonomy
from app.skilled_pro.resume_parse import (
    MAX_UPLOAD_BYTES,
    extract_text_from_upload,
    parse_resume_signals,
)
from app.util.crypto import encrypt_str
from app.util.rate_limit import rate_limit_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/applicant/me/resume", tags=["applicant"])


class ParsedCertification(BaseModel):
    """A résumé-extracted certification, canonicalized against the credential
    taxonomy. The raw string is always preserved; canonical fields are only
    set when the deterministic normalizer is confident."""
    raw: str
    canonical_slug: str | None = None
    canonical_name: str | None = None
    category: str | None = None
    issuer: str | None = None
    confidence: float = 0.0
    needs_review: bool = True


class ParsedResume(BaseModel):
    upload_id: UUID
    filename: str
    fields: dict = Field(default_factory=dict)
    certifications: list[str] = Field(default_factory=list)
    certifications_canonical: list[ParsedCertification] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    raw_text_preview: str = ""


def _canonicalize_certs(names: list[str]) -> list[ParsedCertification]:
    out: list[ParsedCertification] = []
    for raw in names:
        norm = taxonomy.normalize(raw)
        c = norm.canonical if norm.is_confident else None
        out.append(ParsedCertification(
            raw=raw,
            canonical_slug=c.slug if c else None,
            canonical_name=c.name if c else None,
            category=c.type.value if c else None,
            issuer=c.issuer if c else None,
            confidence=norm.confidence,
            needs_review=not norm.is_confident,
        ))
    return out


class ApplyResumeIn(BaseModel):
    upload_id: UUID
    accept: dict = Field(default_factory=dict)


class UploadOut(BaseModel):
    id: UUID
    filename: str
    created_at: str
    applied_at: str | None = None


_MERGEABLE = {
    "first_name", "last_name", "phone", "email", "city", "state",
    "program_name_raw", "career_goals_raw", "experience_raw", "bio_raw",
    "years_experience",
}


@router.post(
    "/parse",
    response_model=ParsedResume,
    dependencies=[Depends(rate_limit_llm("resume_parse"))],
)
async def parse_resume(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_applicant),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB).")

    text = extract_text_from_upload(content, file.content_type or "", file.filename or "")
    if not text:
        raise HTTPException(status_code=400, detail="Could not read this file. Please upload a PDF, DOCX, or TXT resume.")

    settings = get_settings()
    signals = parse_resume_signals(
        text,
        openai_api_key=settings.openai_api_key,
        model=settings.llm_extraction_model,
    )
    # Canonicalize extracted certs against the credential taxonomy so they land
    # normalized in stored parsed_json (raw strings are always kept alongside).
    certs_canonical = _canonicalize_certs(signals.get("certifications", []) or [])
    signals["certifications_canonical"] = [c.model_dump() for c in certs_canonical]

    async with get_db() as conn:
        applicant_id = await _applicant_id_for_user(conn, user)
        row = await conn.fetchrow(
            """
            INSERT INTO public.applicant_resume_uploads
              (applicant_id, filename, content_type, size_bytes, raw_text, parsed_json)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb)
            RETURNING id, filename
            """,
            applicant_id,
            file.filename or "resume",
            file.content_type or "application/octet-stream",
            len(content),
            # Encrypt the full résumé text at rest — it's the largest PII blob and
            # is write-only storage (matching reads the structured parsed_json).
            encrypt_str(text),
            json.dumps(signals),
        )

    fields = {
        k: v for k, v in signals.items()
        if k not in ("certifications", "certifications_canonical", "skills")
    }
    return ParsedResume(
        upload_id=row["id"],
        filename=row["filename"],
        fields=fields,
        certifications=signals.get("certifications", []),
        certifications_canonical=certs_canonical,
        skills=signals.get("skills", []),
        raw_text_preview=text[:400],
    )


@router.post("/apply")
async def apply_resume(
    body: ApplyResumeIn,
    user: CurrentUser = Depends(require_applicant),
):
    accepted = {k: v for k, v in (body.accept or {}).items() if k in _MERGEABLE and v not in (None, "", [])}
    if not accepted:
        raise HTTPException(status_code=400, detail="No fields selected to apply.")

    async with get_db() as conn:
        applicant_id = await _applicant_id_for_user(conn, user)
        upload = await conn.fetchrow(
            "SELECT id FROM public.applicant_resume_uploads WHERE id = $1 AND applicant_id = $2",
            body.upload_id, applicant_id,
        )
        if not upload:
            raise HTTPException(status_code=404, detail="Upload not found.")

        set_clauses: list[str] = []
        values: list = []
        idx = 1
        for k, v in accepted.items():
            set_clauses.append(f"{k} = COALESCE(${idx}, {k})")
            values.append(v)
            idx += 1

        values.append(applicant_id)
        await conn.execute(
            f"UPDATE public.applicants SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${idx}",
            *values,
        )
        await conn.execute(
            "UPDATE public.applicant_resume_uploads SET applied_at = NOW() WHERE id = $1",
            body.upload_id,
        )

    return {"ok": True, "applied": list(accepted.keys())}


@router.get("/uploads", response_model=list[UploadOut])
async def list_uploads(user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        applicant_id = await _applicant_id_for_user(conn, user)
        rows = await conn.fetch(
            """
            SELECT id, filename, created_at, applied_at
              FROM public.applicant_resume_uploads
             WHERE applicant_id = $1
          ORDER BY created_at DESC LIMIT 20
            """,
            applicant_id,
        )
    return [
        UploadOut(
            id=r["id"],
            filename=r["filename"],
            created_at=r["created_at"].isoformat(),
            applied_at=r["applied_at"].isoformat() if r["applied_at"] else None,
        )
        for r in rows
    ]


async def _applicant_id_for_user(conn: asyncpg.Connection, user: CurrentUser) -> UUID:
    # View-as resolves by applicant id directly (supports unlinked applicants).
    row = await conn.fetchrow(
        "SELECT id FROM public.applicants "
        "WHERE id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))",
        user.user_id,
        user.view_as_applicant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Applicant profile not found.")
    return row["id"]
