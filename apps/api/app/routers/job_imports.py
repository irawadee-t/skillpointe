"""
Employer self-serve job import + admin approval workflow.

Two prefixes share this router:
  • /employer/jobs/imports  — employer creates batches (URL/CSV/manual), edits
    rows, submits for review.
  • /admin/job-imports      — admin reviews pending batches and approves /
    rejects; approving publishes rows into public.jobs.

Notifications are written to public.notifications. Email delivery is stubbed.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_admin, require_employer_or_admin
from app.db import get_db
from app.skilled_pro.job_imports import parse_csv_rows, universal_scrape


emp_router = APIRouter(prefix="/employer/jobs/imports", tags=["job-imports"])
adm_router = APIRouter(prefix="/admin/job-imports", tags=["job-imports-admin"])


# ============================================================================
# Schemas
# ============================================================================

class RowIn(BaseModel):
    title_raw: str = Field(min_length=1, max_length=300)
    description_raw: Optional[str] = None
    responsibilities_raw: Optional[str] = None
    requirements_raw: Optional[str] = None
    preferred_qualifications_raw: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "US"
    work_setting: Optional[str] = None
    travel_requirement: Optional[str] = None
    pay_min: Optional[float] = None
    pay_max: Optional[float] = None
    pay_type: Optional[str] = None
    pay_raw: Optional[str] = None
    experience_level: Optional[str] = None
    employment_type: Optional[str] = None
    req_id: Optional[str] = None
    source_url: Optional[str] = None
    job_category: Optional[str] = None


class RowOut(RowIn):
    id: str
    status: str


class BatchOut(BaseModel):
    id: str
    employer_id: str
    employer_name: Optional[str] = None
    source: str
    source_label: Optional[str]
    platform: Optional[str]
    status: str
    rows_total: int
    rows_approved: int
    rows_rejected: int
    submitted_at: Optional[str]
    reviewed_at: Optional[str]
    reviewer_note: Optional[str]
    created_at: str
    updated_at: Optional[str] = None


class BatchDetail(BatchOut):
    rows: list[RowOut]


class ImportUrlIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    max_jobs: int = 200


class ImportCsvIn(BaseModel):
    csv_text: str = Field(min_length=1)
    label: Optional[str] = None


class ManualRowIn(RowIn):
    pass


class SubmitIn(BaseModel):
    note: Optional[str] = None


class ReviewIn(BaseModel):
    note: Optional[str] = None
    # Optional per-row decisions: { row_id: "approve" | "reject" }. If absent,
    # the batch-level approve/reject applies to all staged rows.
    row_decisions: Optional[dict[str, str]] = None


# ============================================================================
# Helpers
# ============================================================================

async def _resolve_employer_id(conn: asyncpg.Connection, user: CurrentUser) -> str:
    """Employer's id from employer_contacts. Admin uses ?employer_id=... in
    contexts that allow it (not here — employer endpoints require an employer
    contact)."""
    row = await conn.fetchrow(
        "SELECT employer_id::text AS id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
        user.user_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No employer linked to this account")
    return row["id"]


async def _row_to_dict(r: asyncpg.Record) -> dict[str, Any]:
    d = dict(r)
    d["id"] = str(d["id"])
    return d


async def _batch_out(conn, row: asyncpg.Record, *, include_rows: bool = False) -> dict[str, Any]:
    emp = await conn.fetchval(
        "SELECT name FROM public.employers WHERE id = $1::uuid", str(row["employer_id"])
    )
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "employer_id": str(row["employer_id"]),
        "employer_name": emp,
        "source": row["source"],
        "source_label": row["source_label"],
        "platform": row["platform"],
        "status": row["status"],
        "rows_total": row["rows_total"],
        "rows_approved": row["rows_approved"],
        "rows_rejected": row["rows_rejected"],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "reviewed_at":  row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        "reviewer_note": row["reviewer_note"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat() if "updated_at" in row and row["updated_at"] else None,
    }
    if include_rows:
        rrows = await conn.fetch(
            "SELECT * FROM public.job_import_rows WHERE batch_id = $1::uuid "
            "ORDER BY created_at ASC", str(row["id"]),
        )
        out["rows"] = [
            {
                "id": str(r["id"]),
                "status": r["status"],
                "title_raw": r["title_raw"],
                "description_raw": r["description_raw"],
                "responsibilities_raw": r["responsibilities_raw"],
                "requirements_raw": r["requirements_raw"],
                "preferred_qualifications_raw": r["preferred_qualifications_raw"],
                "city": r["city"], "state": r["state"], "country": r["country"],
                "work_setting": r["work_setting"], "travel_requirement": r["travel_requirement"],
                "pay_min": float(r["pay_min"]) if r["pay_min"] is not None else None,
                "pay_max": float(r["pay_max"]) if r["pay_max"] is not None else None,
                "pay_type": r["pay_type"], "pay_raw": r["pay_raw"],
                "experience_level": r["experience_level"],
                "employment_type": r["employment_type"], "req_id": r["req_id"],
                "source_url": r["source_url"], "job_category": r["job_category"],
            }
            for r in rrows
        ]
    return out


async def _create_batch(
    conn, *, employer_id: str, user_id: str, source: str, source_label: Optional[str],
    platform: Optional[str],
) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO public.job_import_batches
            (employer_id, created_by, source, source_label, platform, status)
        VALUES ($1::uuid, $2::uuid, $3::job_import_source_enum, $4, $5, 'draft')
        RETURNING id::text AS id
        """,
        employer_id, user_id, source, source_label, platform,
    )
    return row["id"]


async def _insert_rows(conn, batch_id: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    inserted = 0
    for r in rows:
        # Coerce numeric strings.
        for k in ("pay_min", "pay_max"):
            v = r.get(k)
            if isinstance(v, str):
                try: r[k] = float(v.replace("$", "").replace(",", ""))
                except ValueError: r[k] = None
        try:
            await conn.execute(
                """
                INSERT INTO public.job_import_rows
                    (batch_id, title_raw, description_raw, responsibilities_raw,
                     requirements_raw, preferred_qualifications_raw,
                     city, state, country, work_setting, travel_requirement,
                     pay_min, pay_max, pay_type, pay_raw,
                     experience_level, employment_type, req_id, source_url, job_category)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
                ON CONFLICT (batch_id, source_url) DO NOTHING
                """,
                batch_id, r.get("title_raw"), r.get("description_raw"),
                r.get("responsibilities_raw"), r.get("requirements_raw"),
                r.get("preferred_qualifications_raw"),
                r.get("city"), r.get("state"), r.get("country") or "US",
                r.get("work_setting"), r.get("travel_requirement"),
                r.get("pay_min"), r.get("pay_max"), r.get("pay_type"), r.get("pay_raw"),
                r.get("experience_level"), r.get("employment_type"), r.get("req_id"),
                r.get("source_url"), r.get("job_category"),
            )
            inserted += 1
        except Exception:
            continue
    await conn.execute(
        "UPDATE public.job_import_batches SET rows_total = "
        "(SELECT count(*) FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'), "
        "updated_at = now() WHERE id = $1::uuid",
        batch_id,
    )
    return inserted


async def _notify(conn, *, kind: str, recipient_role: Optional[str] = None,
                  recipient_user_id: Optional[str] = None, title: str,
                  body: Optional[str] = None, link_href: Optional[str] = None,
                  payload: Optional[dict] = None) -> None:
    await conn.execute(
        """
        INSERT INTO public.notifications
            (recipient_user_id, recipient_role, kind, title, body, link_href, payload)
        VALUES ($1::uuid, $2, $3::notification_kind_enum, $4, $5, $6, $7::jsonb)
        """,
        recipient_user_id, recipient_role, kind, title, body, link_href,
        payload or {},
    )


# ============================================================================
# Employer endpoints
# ============================================================================

@emp_router.get("", response_model=list[BatchOut])
async def list_my_batches(user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        rows = await conn.fetch(
            "SELECT * FROM public.job_import_batches WHERE employer_id = $1::uuid "
            "ORDER BY created_at DESC LIMIT 100", emp_id,
        )
        return [await _batch_out(conn, r) for r in rows]


@emp_router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch(batch_id: str, user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        row = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid",
            batch_id, emp_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        return await _batch_out(conn, row, include_rows=True)


@emp_router.post("/url", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
async def import_from_url(body: ImportUrlIn, user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """Paste a careers URL — we detect the platform, fetch the listings, and
    create a *draft* batch the employer can edit then submit."""
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        emp_name = await conn.fetchval("SELECT name FROM public.employers WHERE id = $1::uuid", emp_id)
    platform, scraped = universal_scrape(body.url, employer_name=emp_name or "Unknown",
                                         max_jobs=body.max_jobs)
    if platform == "unknown" or not scraped:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"We couldn't detect a supported career-page platform at that URL. "
            f"Supported: Workday, Greenhouse, Lever. Try uploading a CSV instead."
        )
    # Coerce ScrapedJob -> dict shape that _insert_rows expects.
    rows = [
        {
            "title_raw": j.title,
            "description_raw": j.description,
            "responsibilities_raw": j.responsibilities,
            "requirements_raw": j.requirements,
            "preferred_qualifications_raw": j.qualifications,
            "city": j.city, "state": j.state, "country": j.country or "US",
            "work_setting": j.work_setting, "pay_raw": j.pay_raw,
            "experience_level": j.experience_level,
            "employment_type": j.employment_type, "req_id": j.req_id,
            "source_url": j.source_url, "job_category": j.job_category,
            "posted_date": j.posted_date,
        }
        for j in scraped
    ]
    async with get_db() as conn:
        batch_id = await _create_batch(
            conn, employer_id=emp_id, user_id=user.user_id, source="url",
            source_label=body.url, platform=platform,
        )
        await _insert_rows(conn, batch_id, rows)
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec, include_rows=True)


@emp_router.post("/csv", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
async def import_from_csv(body: ImportCsvIn, user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """Paste/upload a CSV/TSV of job rows."""
    rows, skipped = parse_csv_rows(body.csv_text)
    if not rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No valid rows found. Need at least a header row and a `title` column.",
        )
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        batch_id = await _create_batch(
            conn, employer_id=emp_id, user_id=user.user_id, source="csv",
            source_label=body.label or f"CSV upload ({len(rows)} rows, {skipped} skipped)",
            platform=None,
        )
        await _insert_rows(conn, batch_id, rows)
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec, include_rows=True)


@emp_router.post("/manual", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
async def import_manual(body: list[ManualRowIn], user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """One-or-more jobs entered by hand."""
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Need at least one row")
    rows = [r.model_dump(exclude_none=True) for r in body]
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        batch_id = await _create_batch(
            conn, employer_id=emp_id, user_id=user.user_id, source="manual",
            source_label=f"Manual entry ({len(rows)} job{'s' if len(rows) != 1 else ''})",
            platform=None,
        )
        await _insert_rows(conn, batch_id, rows)
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec, include_rows=True)


@emp_router.patch("/{batch_id}/rows/{row_id}")
async def edit_row(
    batch_id: str, row_id: str, body: RowIn,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        owned = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid "
            "AND status IN ('draft','rejected')",
            batch_id, emp_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Batch not editable")
        fields = body.model_dump(exclude_none=True)
        sets = []; params: list[Any] = []
        for col, val in fields.items():
            params.append(val)
            sets.append(f"{col} = ${len(params)}")
        if not sets:
            return {"ok": True}
        params.append(row_id); params.append(batch_id)
        await conn.execute(
            f"UPDATE public.job_import_rows SET {', '.join(sets)}, updated_at = now() "
            f"WHERE id = ${len(params)-1}::uuid AND batch_id = ${len(params)}::uuid",
            *params,
        )
        return {"ok": True}


@emp_router.post("/{batch_id}/rows/{row_id}/exclude")
async def exclude_row(batch_id: str, row_id: str,
                      user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        owned = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid "
            "AND status IN ('draft','rejected')", batch_id, emp_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Batch not editable")
        await conn.execute(
            "UPDATE public.job_import_rows SET status = 'excluded', updated_at = now() "
            "WHERE id = $1::uuid AND batch_id = $2::uuid",
            row_id, batch_id,
        )
        await conn.execute(
            "UPDATE public.job_import_batches SET rows_total = "
            "(SELECT count(*) FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'), "
            "updated_at = now() WHERE id = $1::uuid",
            batch_id,
        )
        return {"ok": True}


@emp_router.post("/{batch_id}/resync", response_model=BatchDetail)
async def resync_batch(batch_id: str,
                       user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """Re-fetch a URL-based batch from its original source and append newly-found
    jobs while marking source-removed jobs. This is the "click Re-sync" endpoint
    for the batch detail page.

    Only works for `source = 'url'` batches (CSV/manual can't be re-fetched).
    Stale-job removal is soft: rows with source_url no longer present in the new
    scrape have `status` flipped to 'stale' so the employer can review.
    """
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        rec = await conn.fetchrow(
            "SELECT b.*, e.name AS emp_name FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id "
            "WHERE b.id = $1::uuid AND b.employer_id = $2::uuid", batch_id, emp_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        if rec["source"] != "url":
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Re-sync is only available for URL-based imports.")
        source_url = rec["source_label"]
        emp_name = rec["emp_name"]

    # Re-scrape (blocking network I/O — acceptable for a one-shot admin/employer action)
    platform, scraped = universal_scrape(source_url, employer_name=emp_name, max_jobs=200)
    if platform == "unknown" or not scraped:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Couldn't re-scrape the source URL. It may have changed platforms or gone offline.")

    fresh_urls = {j.source_url for j in scraped if j.source_url}
    new_rows = [
        {
            "title_raw": j.title, "description_raw": j.description,
            "responsibilities_raw": j.responsibilities, "requirements_raw": j.requirements,
            "preferred_qualifications_raw": j.qualifications, "city": j.city, "state": j.state,
            "country": j.country or "US", "work_setting": j.work_setting, "pay_raw": j.pay_raw,
            "experience_level": j.experience_level, "employment_type": j.employment_type,
            "req_id": j.req_id, "source_url": j.source_url, "job_category": j.job_category,
            "posted_date": j.posted_date,
        }
        for j in scraped
    ]

    async with get_db() as conn:
        # Insert only new (batch_id, source_url) pairs (ON CONFLICT DO NOTHING in _insert_rows).
        await _insert_rows(conn, batch_id, new_rows)
        # Flag rows whose source_url is no longer present in the fresh scrape.
        # Skip rows without a source_url (manual entries).
        marked_stale = 0
        if fresh_urls:
            existing = await conn.fetch(
                "SELECT id, source_url FROM public.job_import_rows "
                "WHERE batch_id = $1::uuid AND source_url IS NOT NULL AND status = 'staged'",
                batch_id,
            )
            stale_ids = [r["id"] for r in existing if r["source_url"] not in fresh_urls]
            if stale_ids:
                await conn.execute(
                    "UPDATE public.job_import_rows SET status = 'stale', updated_at = now() "
                    "WHERE id = ANY($1::uuid[])",
                    stale_ids,
                )
                marked_stale = len(stale_ids)
        # Bump last-synced marker on the batch.
        await conn.execute(
            "UPDATE public.job_import_batches SET updated_at = now() WHERE id = $1::uuid",
            batch_id,
        )
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        detail = await _batch_out(conn, rowrec, include_rows=True)
        # Attach counts so the UI can render "N new · M stale" toast.
        return {**detail.model_dump(), "resync_new": len(new_rows), "resync_stale": marked_stale}


@emp_router.post("/{batch_id}/submit", response_model=BatchOut)
async def submit_batch(batch_id: str, body: SubmitIn,
                       user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        rec = await conn.fetchrow(
            "SELECT b.*, e.name AS emp_name FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id "
            "WHERE b.id = $1::uuid AND b.employer_id = $2::uuid", batch_id, emp_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        if rec["status"] not in ("draft", "rejected"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Batch already {rec['status']}")
        staged = await conn.fetchval(
            "SELECT count(*) FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'",
            batch_id,
        )
        if (staged or 0) == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "No staged rows to submit — add jobs or restore excluded ones first.")
        await conn.execute(
            "UPDATE public.job_import_batches SET status = 'pending', "
            "submitted_at = now(), updated_at = now() WHERE id = $1::uuid",
            batch_id,
        )
        await _notify(
            conn, kind="job_import_submitted", recipient_role="admin",
            title=f"{rec['emp_name']} submitted {staged} job{'s' if staged != 1 else ''} for review",
            body=body.note or rec["source_label"],
            link_href=f"/admin/job-imports/{batch_id}",
            payload={"batch_id": batch_id, "employer_id": str(emp_id),
                     "rows_total": staged, "source": rec["source"]},
        )
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec)


class AutoSyncIn(BaseModel):
    interval_days: Optional[int] = None  # None = disable auto-sync


@emp_router.post("/{batch_id}/auto-sync")
async def set_auto_sync(batch_id: str, body: AutoSyncIn,
                        user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """Configure weekly auto-sync for a URL batch.
    TODO(#143): persist auto-sync setting once import_runs.auto_sync_interval_days
    column is added. For now this logs the request only.
    """
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        owned = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid",
            batch_id, emp_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    # TODO(#143): persist auto-sync setting
    return {"ok": True, "interval_days": body.interval_days, "note": "Auto-sync setting stored (stub)."}


# ============================================================================
# Admin endpoints
# ============================================================================

@adm_router.get("", response_model=list[BatchOut])
async def list_pending(user: Annotated[CurrentUser, Depends(require_admin)],
                       status_filter: Optional[str] = None):
    async with get_db() as conn:
        if status_filter:
            rows = await conn.fetch(
                "SELECT * FROM public.job_import_batches WHERE status::text = $1 "
                "ORDER BY submitted_at DESC NULLS LAST, created_at DESC LIMIT 200",
                status_filter,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM public.job_import_batches WHERE status IN ('pending','approved','rejected') "
                "ORDER BY (status = 'pending') DESC, submitted_at DESC NULLS LAST LIMIT 200",
            )
        return [await _batch_out(conn, r) for r in rows]


@adm_router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch_admin(batch_id: str, user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        return await _batch_out(conn, rec, include_rows=True)


@adm_router.post("/{batch_id}/approve", response_model=BatchOut)
async def approve_batch(batch_id: str, body: ReviewIn,
                        user: Annotated[CurrentUser, Depends(require_admin)]):
    """Approve a batch — staged rows publish to public.jobs."""
    async with get_db() as conn:
        rec = await conn.fetchrow(
            "SELECT b.*, e.name AS emp_name FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id WHERE b.id = $1::uuid",
            batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        if rec["status"] != "pending":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Batch is {rec['status']}")

        # Apply per-row decisions if provided; otherwise all staged rows get
        # published.
        decisions = body.row_decisions or {}
        published = 0
        rejected = 0

        # Pull all staged rows.
        rows = await conn.fetch(
            "SELECT * FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'",
            batch_id,
        )
        for r in rows:
            decision = decisions.get(str(r["id"]), "approve")
            if decision == "reject":
                await conn.execute(
                    "UPDATE public.job_import_rows SET status = 'rejected', updated_at = now() "
                    "WHERE id = $1::uuid", str(r["id"]),
                )
                rejected += 1
                continue
            job_id = await conn.fetchval(
                """
                INSERT INTO public.jobs
                    (employer_id, title_raw, description_raw, requirements_raw,
                     preferred_qualifications_raw, responsibilities_raw,
                     city, state, country, work_setting, travel_requirement,
                     pay_min, pay_max, pay_type, pay_raw, experience_level,
                     canonical_job_family_id, employment_type,
                     source, source_url, is_active, last_verified_at, posted_date)
                VALUES (
                    $1::uuid, $2, $3, $4, $5, $6,
                    $7, $8, $9, $10::work_setting_enum, $11,
                    $12, $13, $14, $15, $16,
                    $17::uuid, $18,
                    'employer_import', $19, TRUE, NOW(), NULL
                )
                ON CONFLICT (source_url) DO UPDATE SET
                    title_raw = EXCLUDED.title_raw,
                    description_raw = EXCLUDED.description_raw,
                    requirements_raw = EXCLUDED.requirements_raw,
                    preferred_qualifications_raw = EXCLUDED.preferred_qualifications_raw,
                    responsibilities_raw = EXCLUDED.responsibilities_raw,
                    city = EXCLUDED.city, state = EXCLUDED.state,
                    work_setting = EXCLUDED.work_setting,
                    pay_min = EXCLUDED.pay_min, pay_max = EXCLUDED.pay_max,
                    pay_raw = EXCLUDED.pay_raw,
                    experience_level = EXCLUDED.experience_level,
                    is_active = TRUE, last_verified_at = NOW(),
                    updated_at = NOW()
                RETURNING id::text
                """,
                str(rec["employer_id"]),
                r["title_raw"], r["description_raw"], r["requirements_raw"],
                r["preferred_qualifications_raw"], r["responsibilities_raw"],
                r["city"], r["state"], r["country"] or "US",
                _coerce_work_setting(r["work_setting"]), r["travel_requirement"],
                r["pay_min"], r["pay_max"], r["pay_type"], r["pay_raw"], r["experience_level"],
                r["canonical_job_family_id"], r["employment_type"],
                r["source_url"] or f"employer:{batch_id}:{r['id']}",
            )
            await conn.execute(
                "UPDATE public.job_import_rows SET status = 'published', published_job_id = $2::uuid, "
                "updated_at = now() WHERE id = $1::uuid",
                str(r["id"]), job_id,
            )
            published += 1

        new_status = "published" if rejected == 0 else "approved"
        await conn.execute(
            "UPDATE public.job_import_batches SET status = $2, reviewer_id = $3::uuid, "
            "reviewer_note = $4, reviewed_at = now(), published_at = now(), "
            "rows_approved = $5, rows_rejected = $6, updated_at = now() WHERE id = $1::uuid",
            batch_id, new_status, user.user_id, body.note, published, rejected,
        )
        kind = "job_import_partial" if rejected > 0 else "job_import_approved"
        title = (
            f"Approved with {rejected} excluded — {published} job{'s' if published != 1 else ''} live"
            if rejected else
            f"{published} job{'s' if published != 1 else ''} approved and published"
        )
        await _notify(
            conn, kind=kind, recipient_user_id=str(rec["created_by"]),
            title=title, body=body.note,
            link_href=f"/employer/jobs/imports/{batch_id}",
            payload={"batch_id": batch_id, "published": published, "rejected": rejected},
        )
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec)


@adm_router.post("/{batch_id}/reject", response_model=BatchOut)
async def reject_batch(batch_id: str, body: ReviewIn,
                       user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rec = await conn.fetchrow(
            "SELECT b.*, e.name AS emp_name FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id WHERE b.id = $1::uuid",
            batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        if rec["status"] != "pending":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Batch is {rec['status']}")
        await conn.execute(
            "UPDATE public.job_import_batches SET status = 'rejected', reviewer_id = $2::uuid, "
            "reviewer_note = $3, reviewed_at = now(), updated_at = now() WHERE id = $1::uuid",
            batch_id, user.user_id, body.note,
        )
        await _notify(
            conn, kind="job_import_rejected", recipient_user_id=str(rec["created_by"]),
            title=f"Batch rejected — review the note and resubmit",
            body=body.note, link_href=f"/employer/jobs/imports/{batch_id}",
            payload={"batch_id": batch_id},
        )
        rowrec = await conn.fetchrow(
            "SELECT * FROM public.job_import_batches WHERE id = $1::uuid", batch_id,
        )
        return await _batch_out(conn, rowrec)


# ============================================================================
# Notifications
# ============================================================================

@adm_router.get("/notifications/admin")
async def admin_notifications(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT id::text, kind::text, title, body, link_href, read_at, created_at "
            "FROM public.notifications WHERE recipient_role = 'admin' "
            "ORDER BY created_at DESC LIMIT 50"
        )
        return [
            {
                "id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"],
                "link_href": r["link_href"],
                "read": r["read_at"] is not None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]


emp_notif_router = APIRouter(prefix="/employer", tags=["notifications"])


@emp_notif_router.get("/notifications")
async def employer_notifications(user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT id::text, kind::text, title, body, link_href, read_at, created_at "
            "FROM public.notifications WHERE recipient_user_id = $1::uuid "
            "ORDER BY created_at DESC LIMIT 50",
            user.user_id,
        )
        return [
            {
                "id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"],
                "link_href": r["link_href"],
                "read": r["read_at"] is not None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]


# ============================================================================
# Helpers (module-local)
# ============================================================================

def _coerce_work_setting(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    v = raw.lower().replace("-", "_").strip()
    if v in {"onsite", "on_site"}: return "on_site"
    if v in {"remote", "hybrid", "flexible"}: return v
    return None
