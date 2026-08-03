"""
Institution partner portal (self-serve).

A college / training program logs in and uploads its own completion batches,
sees the roster of credentials it has issued on SKILLED, and reviews its import
history. Uploads run through the SAME match → normalize → Institution-Verified
pipeline as the admin console — but scoped to the signed-in institution.
"""
from __future__ import annotations

from typing import Annotated, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_institution
from app.db import get_db
from app.routers.ingest import IngestRequest, IngestRow, IngestSummary, ingest_credentials
from app.skilled_pro import file_lane

router = APIRouter(prefix="/institution/me", tags=["institution"])


class Institution(BaseModel):
    id: str
    name: str
    slug: Optional[str]
    credentials_issued: int
    learners: int


class RosterRow(BaseModel):
    applicant_name: str
    credential_name: str
    verification_badge: str
    issued_date: Optional[str]


class ImportRun(BaseModel):
    id: str
    row_count: int
    success_count: int
    error_count: int
    status: str
    created_at: str


class FileIngest(BaseModel):
    csv_text: str = Field(min_length=1)
    dry_run: bool = False


async def _resolve_institution(conn: asyncpg.Connection, user_id: str) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT i.id::text AS id, i.name, i.slug FROM public.institutions i "
        "JOIN public.institution_contacts c ON c.institution_id = i.id "
        "WHERE c.user_id = $1",
        user_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No institution linked to this account")
    return row


@router.get("", response_model=Institution)
async def my_institution(user: Annotated[CurrentUser, Depends(require_institution)]):
    async with get_db() as conn:
        inst = await _resolve_institution(conn, user.user_id)
        stats = await conn.fetchrow(
            "SELECT count(*) AS creds, count(DISTINCT applicant_id) AS learners "
            "FROM public.credentials WHERE metadata->>'institution' = $1",
            inst["name"],
        )
    return Institution(
        id=inst["id"], name=inst["name"], slug=inst["slug"],
        credentials_issued=int(stats["creds"]), learners=int(stats["learners"]),
    )


@router.post("/ingest", response_model=IngestSummary)
async def upload_completions(
    body: FileIngest,
    user: Annotated[CurrentUser, Depends(require_institution)],
):
    async with get_db() as conn:
        inst = await _resolve_institution(conn, user.user_id)
    parsed = file_lane.parse_csv(body.csv_text)
    if not parsed.rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"No valid rows (need {file_lane.REQUIRED}; {parsed.skipped} skipped)",
        )
    rows = [IngestRow(**r) for r in parsed.rows]
    req = IngestRequest(institution=inst["name"], rows=rows, dry_run=body.dry_run)
    # Reuse the audited admin pipeline; the route's own guard scopes it to this user.
    return await ingest_credentials(req, user)


@router.get("/roster", response_model=list[RosterRow])
async def roster(
    user: Annotated[CurrentUser, Depends(require_institution)],
    limit: int = Query(100, ge=1, le=500),
):
    async with get_db() as conn:
        inst = await _resolve_institution(conn, user.user_id)
        rows = await conn.fetch(
            """
            SELECT COALESCE(NULLIF(btrim(a.first_name || ' ' || a.last_name), ''), a.email) AS applicant_name,
                   COALESCE(c.canonical_name, c.raw_name) AS credential_name,
                   c.verification_level, c.issued_date
            FROM public.credentials c
            JOIN public.applicants a ON a.id = c.applicant_id
            WHERE c.metadata->>'institution' = $1
            ORDER BY c.updated_at DESC
            LIMIT $2
            """,
            inst["name"], limit,
        )
    from app.skilled_pro.verification import VerificationLevel
    return [
        RosterRow(
            applicant_name=r["applicant_name"],
            credential_name=r["credential_name"],
            verification_badge=VerificationLevel(int(r["verification_level"])).badge,
            issued_date=r["issued_date"].isoformat() if r["issued_date"] else None,
        )
        for r in rows
    ]


@router.get("/imports", response_model=list[ImportRun])
async def imports(user: Annotated[CurrentUser, Depends(require_institution)]):
    async with get_db() as conn:
        inst = await _resolve_institution(conn, user.user_id)
        rows = await conn.fetch(
            "SELECT id::text AS id, row_count, success_count, error_count, "
            "status::text AS status, created_at FROM public.import_runs "
            "WHERE source_file = $1 ORDER BY created_at DESC LIMIT 20",
            f"partner:{inst['name']}",
        )
    return [
        ImportRun(
            id=r["id"], row_count=r["row_count"] or 0, success_count=r["success_count"] or 0,
            error_count=r["error_count"] or 0, status=r["status"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
