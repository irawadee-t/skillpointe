"""
Applicant AI profile summary + PDF résumé export.

- POST /applicant/me/summary   generate (grounded LLM, graceful fallback) + store
- PUT  /applicant/me/summary   save an edited summary
- GET  /applicant/me/resume.pdf  download a one-page résumé built from verified data
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_applicant
from app.db import get_db
from app.skilled_pro.ai import generate_summary
from app.skilled_pro.resume import build_resume_pdf
from app.skilled_pro.verification import VerificationLevel

router = APIRouter(prefix="/applicant/me", tags=["resume"])


class SummaryOut(BaseModel):
    summary: Optional[str]
    source: Optional[str] = None       # "ai" | "template" | "manual"
    generated_at: Optional[str] = None


class SummaryIn(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)


async def _load_profile(conn: asyncpg.Connection, user_id: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT a.id::text AS id, a.first_name, a.last_name, a.email, a.city, a.state,
               a.program_name_raw, a.available_from_date, a.willing_to_relocate,
               a.profile_summary, a.profile_summary_generated_at,
               jf.name AS trade
        FROM public.applicants a
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
        WHERE a.user_id = $1
        """,
        user_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant profile not found")

    creds = await conn.fetch(
        "SELECT canonical_name, raw_name, credential_type, issuer, verification_level "
        "FROM public.credentials WHERE applicant_id = $1 "
        "ORDER BY verification_level DESC, created_at DESC",
        row["id"],
    )
    name = " ".join(p for p in [row["first_name"], row["last_name"]] if p) or "SKILLED Worker"
    return {
        "id": row["id"],
        "name": name,
        "email": row["email"],
        "trade": row["trade"],
        "program": row["program_name_raw"],
        "city": row["city"],
        "state": row["state"],
        "available_from": row["available_from_date"].isoformat() if row["available_from_date"] else None,
        "willing_to_relocate": bool(row["willing_to_relocate"]),
        "profile_summary": row["profile_summary"],
        "summary_generated_at": row["profile_summary_generated_at"].isoformat() if row["profile_summary_generated_at"] else None,
        "credentials": [
            {
                "name": c["canonical_name"] or c["raw_name"],
                "raw_name": c["raw_name"],
                "credential_type": c["credential_type"],
                "issuer": c["issuer"],
                "badge": VerificationLevel(int(c["verification_level"])).badge,
            }
            for c in creds
        ],
    }


@router.get("/summary", response_model=SummaryOut)
async def get_summary(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        profile = await _load_profile(conn, user.user_id)
    return SummaryOut(summary=profile["profile_summary"], generated_at=profile["summary_generated_at"])


@router.post("/summary", response_model=SummaryOut)
async def generate_profile_summary(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        profile = await _load_profile(conn, user.user_id)
        text, source = await generate_summary(profile)
        row = await conn.fetchrow(
            "UPDATE public.applicants SET profile_summary = $2, "
            "profile_summary_generated_at = now() WHERE id = $1 "
            "RETURNING profile_summary_generated_at",
            profile["id"], text,
        )
    return SummaryOut(
        summary=text, source=source,
        generated_at=row["profile_summary_generated_at"].isoformat(),
    )


@router.put("/summary", response_model=SummaryOut)
async def save_profile_summary(
    body: SummaryIn,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    async with get_db() as conn:
        profile = await _load_profile(conn, user.user_id)
        row = await conn.fetchrow(
            "UPDATE public.applicants SET profile_summary = $2, "
            "profile_summary_generated_at = now() WHERE id = $1 "
            "RETURNING profile_summary_generated_at",
            profile["id"], body.summary.strip(),
        )
    return SummaryOut(
        summary=body.summary.strip(), source="manual",
        generated_at=row["profile_summary_generated_at"].isoformat(),
    )


@router.get("/resume.pdf")
async def download_resume(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        profile = await _load_profile(conn, user.user_id)
    pdf = build_resume_pdf(profile, summary=profile.get("profile_summary"))
    filename = (profile["name"].replace(" ", "_") or "resume") + "_SKILLED.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
