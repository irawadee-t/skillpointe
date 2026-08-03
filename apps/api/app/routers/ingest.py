"""
Bulk credential ingestion — the partner-portal / SIS lane.

An admin (acting for a partner institution) submits a batch of credential
completions. Each row is matched to an applicant by email, the credential name is
normalized against the taxonomy, and the credential is upserted at
INSTITUTION_VERIFIED with a signed, hash-chained audit record. A dry run returns
the same per-row plan without writing, so admins can preview before committing.

This is what makes the verification tiers real — self-service credentials stay
Self-Reported; only a trusted source (here, a partner feed) raises the tier.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_admin
from app.db import get_db
from app.integrations.sis import get_sis_provider
from app.skilled_pro import file_lane
from app.skilled_pro.ingest import IngestRowInput, plan_row
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    VerificationLevel,
    derive_level,
)

router = APIRouter(prefix="/admin/credentials/ingest", tags=["ingest"])

MAX_ROWS = 1000
# Trusted institutional source → Institution-Verified.
INGEST_LEVEL: VerificationLevel = derive_level(
    VerificationEvidence(source=CredentialSource.PARTNER_PORTAL)
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IngestRow(BaseModel):
    email: str
    credential_name: str
    issuer: Optional[str] = None
    issued_date: Optional[date] = None
    expires_date: Optional[date] = None


class IngestRequest(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    rows: list[IngestRow]
    dry_run: bool = False


class RowResult(BaseModel):
    email: str
    credential_name: str
    status: str                       # ok | unmatched | error
    action: Optional[str] = None      # created | upgraded | unchanged
    applicant_name: Optional[str] = None
    canonical_name: Optional[str] = None
    verification_badge: Optional[str] = None
    needs_review: bool = False
    detail: Optional[str] = None


class IngestSummary(BaseModel):
    dry_run: bool
    institution: str
    total: int
    matched: int
    created: int
    upgraded: int
    unchanged: int
    unmatched: int
    errors: int
    import_run_id: Optional[str] = None
    results: list[RowResult]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=IngestSummary)
async def ingest_credentials(
    body: IngestRequest,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    if not body.rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No rows provided")
    if len(body.rows) > MAX_ROWS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Max {MAX_ROWS} rows per batch")

    results: list[RowResult] = []
    counts = {"created": 0, "upgraded": 0, "unchanged": 0, "unmatched": 0, "errors": 0}

    async with get_db() as conn:
        for row in body.rows:
            plan = plan_row(
                IngestRowInput(
                    email=row.email,
                    credential_name=row.credential_name,
                    issuer=row.issuer,
                )
            )
            if not plan.ok:
                counts["errors"] += 1
                results.append(RowResult(
                    email=plan.email, credential_name=plan.credential_name,
                    status="error", detail=plan.error,
                ))
                continue

            appl = await conn.fetchrow(
                "SELECT id::text AS id, first_name, last_name "
                "FROM public.applicants WHERE lower(email) = $1",
                plan.email,
            )
            if not appl:
                counts["unmatched"] += 1
                results.append(RowResult(
                    email=plan.email, credential_name=plan.credential_name,
                    status="unmatched", canonical_name=plan.normalized.canonical.name if plan.normalized and plan.normalized.canonical else None,
                    detail="No applicant with this email",
                ))
                continue

            applicant_name = " ".join(
                p for p in [appl["first_name"], appl["last_name"]] if p
            ) or plan.email
            canonical = plan.normalized.canonical if plan.normalized else None
            canonical_name = canonical.name if canonical else None

            # Find an existing credential to upgrade (by canonical code, else raw name).
            if plan.canonical_code:
                existing = await conn.fetchrow(
                    "SELECT id::text AS id, verification_level, source FROM public.credentials "
                    "WHERE applicant_id = $1 AND canonical_code = $2 LIMIT 1",
                    appl["id"], plan.canonical_code,
                )
            else:
                existing = await conn.fetchrow(
                    "SELECT id::text AS id, verification_level, source FROM public.credentials "
                    "WHERE applicant_id = $1 AND canonical_code IS NULL "
                    "AND lower(raw_name) = lower($2) LIMIT 1",
                    appl["id"], plan.credential_name,
                )

            # Determine action.
            if existing:
                new_level = max(int(existing["verification_level"]), INGEST_LEVEL.value)
                action = (
                    "upgraded"
                    if new_level > int(existing["verification_level"])
                    or existing["source"] != CredentialSource.PARTNER_PORTAL.value
                    else "unchanged"
                )
            else:
                new_level = INGEST_LEVEL.value
                action = "created"

            if not body.dry_run:
                meta = {"institution": body.institution, "ingested_by": user.user_id}
                if existing:
                    await conn.execute(
                        """
                        UPDATE public.credentials SET
                            verification_level = $2,
                            source = 'partner_portal',
                            issuer = COALESCE($3, issuer),
                            issued_date = COALESCE($4, issued_date),
                            expires_date = COALESCE($5, expires_date),
                            needs_review = $6,
                            metadata = metadata || $7::jsonb,
                            updated_at = now()
                        WHERE id = $1
                        """,
                        existing["id"], new_level, row.issuer,
                        row.issued_date, row.expires_date, plan.needs_review, meta,
                    )
                    cred_id = existing["id"]
                else:
                    created = await conn.fetchrow(
                        """
                        INSERT INTO public.credentials
                            (applicant_id, raw_name, canonical_code, canonical_name,
                             credential_type, issuer, normalization_confidence, needs_review,
                             source, verification_level, issued_date, expires_date, metadata,
                             definition_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'partner_portal',$9,$10,$11,$12::jsonb,
                                (SELECT d.id FROM public.credential_definitions d
                                  WHERE d.canonical_code = $3 AND d.active))
                        RETURNING id::text AS id
                        """,
                        appl["id"], plan.credential_name,
                        plan.canonical_code, canonical_name,
                        canonical.type.value if canonical else None,
                        row.issuer or (canonical.issuer if canonical else None),
                        plan.normalized.confidence if plan.normalized else 0,
                        plan.needs_review, new_level, row.issued_date, row.expires_date, meta,
                    )
                    cred_id = created["id"]

                await append_credential_record(
                    conn, appl["id"], cred_id, "verified",
                    {
                        "credential_id": cred_id,
                        "canonical_code": plan.canonical_code,
                        "raw_name": plan.credential_name,
                        "source": "partner_portal",
                        "institution": body.institution,
                        "verification_level": new_level,
                        "action": action,
                    },
                )

            counts[action] += 1
            results.append(RowResult(
                email=plan.email, credential_name=plan.credential_name,
                status="ok", action=action, applicant_name=applicant_name,
                canonical_name=canonical_name,
                verification_badge=VerificationLevel(new_level).badge,
                needs_review=plan.needs_review,
            ))

        matched = counts["created"] + counts["upgraded"] + counts["unchanged"]
        import_run_id: Optional[str] = None

        if not body.dry_run:
            run_status = (
                "failed" if matched == 0
                else "partial" if (counts["errors"] + counts["unmatched"]) > 0
                else "complete"
            )
            run = await conn.fetchrow(
                """
                INSERT INTO public.import_runs
                    (import_type, source_file, row_count, success_count, error_count,
                     warning_count, status, error_summary, completed_at, initiated_by)
                VALUES ('credential_ingest', $1, $2, $3, $4, $5, $6::import_status_enum,
                        $7::jsonb, now(), $8::uuid)
                RETURNING id::text AS id
                """,
                f"partner:{body.institution}", len(body.rows), matched,
                counts["errors"], counts["unmatched"], run_status,
                {"institution": body.institution, "counts": counts},
                user.user_id,
            )
            import_run_id = run["id"]

    return IngestSummary(
        dry_run=body.dry_run,
        institution=body.institution,
        total=len(body.rows),
        matched=matched,
        created=counts["created"],
        upgraded=counts["upgraded"],
        unchanged=counts["unchanged"],
        unmatched=counts["unmatched"],
        errors=counts["errors"],
        import_run_id=import_run_id,
        results=results,
    )


# ---------------------------------------------------------------------------
# Alternate lanes — SIS pull + SFTP/file-drop — feed the SAME pipeline above.
# ---------------------------------------------------------------------------

class SISIngestRequest(BaseModel):
    dry_run: bool = False


@router.post("/sis", response_model=IngestSummary)
async def ingest_from_sis(
    body: SISIngestRequest,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Pull credential completions from the configured SIS provider and ingest them.
    Defaults to a deterministic mock feed; a real connector (Ellucian Ethos →
    Banner/Colleague) is an adapter swap once credentials are configured."""
    provider = get_sis_provider()
    records = provider.fetch_records()
    if not records:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"SIS provider '{provider.name}' returned no records")
    rows = [
        IngestRow(
            email=r.email, credential_name=r.credential_name, issuer=r.issuer,
            issued_date=r.issued_date, expires_date=r.expires_date,
        )
        for r in records
    ]
    req = IngestRequest(institution=f"SIS:{provider.name}", rows=rows, dry_run=body.dry_run)
    return await ingest_credentials(req, user)


class FileIngestRequest(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    csv_text: str = Field(min_length=1)
    dry_run: bool = False


@router.post("/file", response_model=IngestSummary)
async def ingest_from_file(
    body: FileIngestRequest,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Process a CSV batch delivered via the SFTP / secure file-drop lane. The
    transport drops files into the lane; this parses + ingests them."""
    parsed = file_lane.parse_csv(body.csv_text)
    if not parsed.rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"No valid rows (need columns {file_lane.REQUIRED}; {parsed.skipped} skipped)",
        )
    rows = [IngestRow(**r) for r in parsed.rows]
    req = IngestRequest(institution=body.institution, rows=rows, dry_run=body.dry_run)
    return await ingest_credentials(req, user)
