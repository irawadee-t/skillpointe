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

import logging
from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_admin, require_employer_or_admin
from app.db import get_db
from app.skilled_pro.job_imports import parse_csv_rows, universal_scrape
from app.util.audit import write_audit
from app.util.review_queue import (
    AWAITING_IMPORT_REVIEW_WHERE,
    STAGED_FROM_CAREERS_WHERE,
    batch_review_state,
    count_awaiting_import_review,
)

logger = logging.getLogger(__name__)

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
    link_status: Optional[str] = None  # ok | broken | blocked | null (unchecked)
    link_checked_at: Optional[str] = None
    posted_date: Optional[str] = None
    first_seen_at: Optional[str] = None   # when this posting first entered the batch
    last_synced_at: Optional[str] = None  # last time a sync touched this row


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
    # Admin-console enrichment (defaults keep employer responses unchanged).
    # review_state: awaiting_review | staged_from_careers | draft | approved |
    # rejected | published — the honest chip, no silent "draft" fallback for
    # careers-page pulls that are actually review work.
    review_state: Optional[str] = None
    from_career_source: bool = False
    rows_staged: int = 0
    rows_held: int = 0


class BatchDetail(BatchOut):
    rows: list[RowOut]
    # Admin rows pagination — total row count (all statuses) and per-status
    # breakdown so the UI never silently truncates.
    rows_count: int = 0
    rows_by_status: dict[str, int] = Field(default_factory=dict)


class AdminBatchListOut(BaseModel):
    items: list[BatchOut]
    total: int
    limit: int
    offset: int
    # The ONE shared "awaiting review" definition (util.review_queue) —
    # identical numbers on the dashboard, this queue, and career sources.
    awaiting: dict[str, int]


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


class ApproveIn(BaseModel):
    note: Optional[str] = None
    # Optional per-row decisions: { row_id: "approve" | "reject" | "hold" }.
    # If a row has no explicit decision, staged rows publish EXCEPT rows whose
    # apply link is broken/blocked — those default to "hold" (parked as
    # status='held', reported to the employer, never silently skipped).
    row_decisions: Optional[dict[str, str]] = None


class RejectIn(BaseModel):
    # A rejection without a reason is useless to the employer — enforced
    # server-side (422), not just in the UI. No row_decisions here: rejecting
    # a batch is all-or-nothing; per-row splits go through /approve.
    note: str = Field(min_length=3, max_length=2000)


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
                "link_status": r["link_status"] if "link_status" in r.keys() else None,
                "link_checked_at": r["link_checked_at"].isoformat()
                if "link_checked_at" in r.keys() and r["link_checked_at"] else None,
                "posted_date": str(r["posted_date"])
                if "posted_date" in r.keys() and r["posted_date"] else None,
                "first_seen_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_synced_at": r["updated_at"].isoformat()
                if "updated_at" in r.keys() and r["updated_at"] else None,
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
                ON CONFLICT (batch_id, source_url) WHERE source_url IS NOT NULL DO NOTHING
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
            "We couldn't detect a supported career-page platform at that URL. "
            "Supported: Workday, Greenhouse, Lever. Try uploading a CSV instead."
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
        # Label = the filename when we have one, else a plain "CSV import".
        # Row/skip counts live in rows_total and the UI meta line, not the title.
        batch_id = await _create_batch(
            conn, employer_id=emp_id, user_id=user.user_id, source="csv",
            source_label=body.label or "CSV import",
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
            source_label="Manual entry",
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


@emp_router.post("/{batch_id}/rows/{row_id}/restore")
async def restore_row(batch_id: str, row_id: str,
                      user: Annotated[CurrentUser, Depends(require_employer_or_admin)]):
    """Undo an exclude — the row goes back to 'staged' so it can be submitted."""
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        owned = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid "
            "AND status IN ('draft','rejected')", batch_id, emp_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Batch not editable")
        restored = await conn.fetchval(
            "UPDATE public.job_import_rows SET status = 'staged', updated_at = now() "
            "WHERE id = $1::uuid AND batch_id = $2::uuid AND status = 'excluded' RETURNING id",
            row_id, batch_id,
        )
        if not restored:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Row is not excluded")
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
                                "No staged rows to submit. Add jobs or restore excluded ones first.")
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
    """Configure auto-sync for a URL batch.

    Persisted on the owning career source (employer_career_sources) — the
    scheduler's per-source auto-sync uses the learned-profile incremental
    path, so this was consolidated there (closes the old TODO #143 stub).
    """
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user)
        owned = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid AND employer_id = $2::uuid",
            batch_id, emp_id,
        )
        if not owned:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        enabled = body.interval_days is not None and body.interval_days > 0
        hours = max(1, min(168, (body.interval_days or 7) * 24))
        updated = await conn.fetchval(
            """
            UPDATE public.employer_career_sources SET
                auto_sync_enabled = $3,
                auto_sync_interval_hours = CASE WHEN $3 THEN $4
                                                ELSE auto_sync_interval_hours END,
                next_auto_sync_at = CASE WHEN $3 THEN now() + make_interval(hours => $4)
                                         ELSE NULL END,
                updated_at = now()
            WHERE batch_id = $1::uuid AND employer_id = $2::uuid
            RETURNING id
            """,
            batch_id, emp_id, enabled, hours,
        )
        if not updated:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This batch isn't linked to a connected careers page. Connect the "
                "URL under Add jobs to enable auto-sync.",
            )
    return {"ok": True, "interval_days": body.interval_days}


# ============================================================================
# Admin endpoints
# ============================================================================

def _import_row_dict(r: asyncpg.Record) -> dict[str, Any]:
    """RowOut mapping for admin detail (mirrors _batch_out's include_rows
    mapping — kept separate so admin pagination doesn't touch the employer
    path; update both if the row shape changes)."""
    keys = r.keys()
    return {
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
        "link_status": r["link_status"] if "link_status" in keys else None,
        "link_checked_at": r["link_checked_at"].isoformat()
        if "link_checked_at" in keys and r["link_checked_at"] else None,
        "posted_date": str(r["posted_date"])
        if "posted_date" in keys and r["posted_date"] else None,
        "first_seen_at": r["created_at"].isoformat() if r["created_at"] else None,
        "last_synced_at": r["updated_at"].isoformat()
        if "updated_at" in keys and r["updated_at"] else None,
    }


# Filter → WHERE fragment over alias `b`. "awaiting" (the default) is the
# shared definition: submitted batches + careers-page pulls with staged rows.
_ADMIN_LIST_FILTERS: dict[str, str] = {
    "awaiting": AWAITING_IMPORT_REVIEW_WHERE,
    "staged": STAGED_FROM_CAREERS_WHERE,
    "pending": "b.status = 'pending'",
    "approved": "b.status = 'approved'",
    "rejected": "b.status = 'rejected'",
    "published": "b.status = 'published'",
    "draft": "b.status = 'draft'",
    "all": "TRUE",   # every batch, every status — nothing hidden
}

_ADMIN_ENRICH_SQL = """
    EXISTS (SELECT 1 FROM public.employer_career_sources s
             WHERE s.batch_id = b.id) AS from_career_source,
    (SELECT count(*) FROM public.job_import_rows r
      WHERE r.batch_id = b.id AND r.status = 'staged') AS rows_staged,
    (SELECT count(*) FROM public.job_import_rows r
      WHERE r.batch_id = b.id AND r.status = 'held') AS rows_held
"""


async def _admin_batch_out(conn, rec) -> dict[str, Any]:
    """_batch_out + admin enrichment (review_state, careers-pull provenance,
    staged/held row counts)."""
    out = await _batch_out(conn, rec)
    keys = tuple(rec.keys())
    from_cs = bool(rec["from_career_source"]) if "from_career_source" in keys else False
    staged = int(rec["rows_staged"] or 0) if "rows_staged" in keys else 0
    held = int(rec["rows_held"] or 0) if "rows_held" in keys else 0
    out["from_career_source"] = from_cs
    out["rows_staged"] = staged
    out["rows_held"] = held
    out["review_state"] = batch_review_state(rec["status"], from_cs, staged)
    return out


@adm_router.get("", response_model=AdminBatchListOut)
async def list_admin_batches(
    user: Annotated[CurrentUser, Depends(require_admin)],
    status_filter: str = Query(default="awaiting"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """The admin approval queue. Default view = everything awaiting review
    (submitted batches AND careers-page pulls with staged rows — one shared
    definition with the dashboard). `all` includes every batch status."""
    where = _ADMIN_LIST_FILTERS.get(status_filter)
    if where is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown status_filter '{status_filter}'. "
            f"One of: {', '.join(sorted(_ADMIN_LIST_FILTERS))}",
        )
    async with get_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT b.*, {_ADMIN_ENRICH_SQL},
                   count(*) OVER () AS _total
              FROM public.job_import_batches b
             WHERE {where}
             ORDER BY (b.status = 'pending') DESC,
                      b.submitted_at DESC NULLS LAST,
                      b.updated_at DESC NULLS LAST,
                      b.created_at DESC
             LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
        total = int(rows[0]["_total"]) if rows else 0
        items = [await _admin_batch_out(conn, r) for r in rows]
        awaiting = await count_awaiting_import_review(conn)
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "awaiting": awaiting}


@adm_router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch_admin(
    batch_id: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
    rows_limit: int = Query(default=500, ge=1, le=2000),
    rows_offset: int = Query(default=0, ge=0),
):
    async with get_db() as conn:
        rec = await conn.fetchrow(
            f"SELECT b.*, {_ADMIN_ENRICH_SQL} "
            "FROM public.job_import_batches b WHERE b.id = $1::uuid", batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        out = await _admin_batch_out(conn, rec)
        status_rows = await conn.fetch(
            "SELECT status::text AS s, count(*) AS c FROM public.job_import_rows "
            "WHERE batch_id = $1::uuid GROUP BY 1", batch_id,
        )
        by_status = {r["s"]: int(r["c"]) for r in status_rows}
        rrows = await conn.fetch(
            "SELECT * FROM public.job_import_rows WHERE batch_id = $1::uuid "
            "ORDER BY created_at ASC LIMIT $2 OFFSET $3",
            batch_id, rows_limit, rows_offset,
        )
        out["rows"] = [_import_row_dict(r) for r in rrows]
        out["rows_count"] = sum(by_status.values())
        out["rows_by_status"] = by_status
        return out


@adm_router.post("/{batch_id}/approve", response_model=BatchOut)
async def approve_batch(batch_id: str, body: ApproveIn,
                        user: Annotated[CurrentUser, Depends(require_admin)]):
    """Approve a batch — staged rows publish to public.jobs.

    Row decisions: approve | reject | hold. Rows whose apply link is
    broken/blocked DEFAULT to hold (status='held') unless the admin explicitly
    approves them — holding is a real, visible decision, never an absence."""
    decisions = body.row_decisions or {}
    bad = {v for v in decisions.values() if v not in ("approve", "reject", "hold")}
    if bad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid row decision(s): {', '.join(sorted(bad))}. "
            "Each decision must be approve, reject, or hold.",
        )
    async with get_db() as conn:
        rec = await conn.fetchrow(
            f"SELECT b.*, e.name AS emp_name, {_ADMIN_ENRICH_SQL} "
            "FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id WHERE b.id = $1::uuid",
            batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        # Careers-page pulls live in a rolling draft batch that is never
        # "submitted" — their staged rows are reviewable directly.
        is_careers_draft = rec["status"] == "draft" and bool(rec["from_career_source"])
        if rec["status"] != "pending" and not is_careers_draft:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Batch is {rec['status']}")

        published = 0
        published_job_ids: list[str] = []
        rejected = 0
        held = 0

        # Pull all staged rows.
        rows = await conn.fetch(
            "SELECT * FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'",
            batch_id,
        )
        for r in rows:
            link_status = r["link_status"] if "link_status" in r.keys() else None
            default = "hold" if link_status in ("broken", "blocked") else "approve"
            decision = decisions.get(str(r["id"]), default)
            if decision == "reject":
                await conn.execute(
                    "UPDATE public.job_import_rows SET status = 'rejected', updated_at = now() "
                    "WHERE id = $1::uuid", str(r["id"]),
                )
                rejected += 1
                continue
            if decision == "hold":
                # Explicit, visible state — the row is parked (broken/blocked
                # apply link or reviewer judgment), reported to the employer,
                # and stays actionable in the queue. Never a silent skip.
                await conn.execute(
                    "UPDATE public.job_import_rows SET status = 'held', updated_at = now() "
                    "WHERE id = $1::uuid", str(r["id"]),
                )
                held += 1
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
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO UPDATE SET
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
            published_job_ids.append(str(job_id))
            published += 1

        # Ontology enrichment BEFORE recompute so the gates see the
        # enriched fields (entry_friendly, credentials, years, shift). This
        # is the stage that makes any new partner's postings arrive fully
        # classified with zero manual steps.
        if published_job_ids:
            from app.skilled_pro.job_enrichment import enrich_jobs
            try:
                await enrich_jobs(conn, published_job_ids)
            except Exception:
                logger.exception("Job enrichment failed for batch %s", batch_id)
            import asyncio as _asyncio

            from app.worker.scheduler import trigger_recompute_for_job
            for _jid in published_job_ids:
                _asyncio.create_task(trigger_recompute_for_job(_jid))

        # Careers-page rolling batches stay 'draft' — they keep receiving rows
        # on every sync, and the queue drops them automatically once no staged
        # rows remain (the shared awaiting-review definition).
        if is_careers_draft:
            new_status = "draft"
        else:
            new_status = "published" if rejected == 0 and held == 0 else "approved"
        await conn.execute(
            "UPDATE public.job_import_batches SET status = $2, reviewer_id = $3::uuid, "
            "reviewer_note = $4, reviewed_at = now(), published_at = now(), "
            "rows_approved = rows_approved + $5, rows_rejected = rows_rejected + $6, "
            "updated_at = now() WHERE id = $1::uuid",
            batch_id, new_status, user.user_id, body.note, published, rejected,
        )
        await write_audit(
            conn,
            action="job_import_approved",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="job_import_batches", entity_id=batch_id,
            after={"status": new_status, "published": published, "rejected": rejected,
                   "held": held},
            metadata={"employer_id": str(rec["employer_id"]),
                      "from_career_source": bool(rec["from_career_source"])},
        )
        # Honest outcome messaging: "partial" whenever anything was held OR
        # rejected — a held row is not published, and the employer must know.
        kind = "job_import_partial" if (rejected + held) > 0 else "job_import_approved"
        parts = [f"{published} job{'s' if published != 1 else ''} live"]
        if held:
            parts.append(f"{held} held (apply link needs fixing)")
        if rejected:
            parts.append(f"{rejected} excluded")
        title = (
            " · ".join(parts) if (rejected + held) > 0
            else f"{published} job{'s' if published != 1 else ''} approved and published"
        )
        await _notify(
            conn, kind=kind, recipient_user_id=str(rec["created_by"]),
            title=title, body=body.note,
            link_href=f"/employer/jobs/imports/{batch_id}",
            payload={"batch_id": batch_id, "published": published,
                     "rejected": rejected, "held": held},
        )
        rowrec = await conn.fetchrow(
            f"SELECT b.*, {_ADMIN_ENRICH_SQL} "
            "FROM public.job_import_batches b WHERE b.id = $1::uuid", batch_id,
        )
        return await _admin_batch_out(conn, rowrec)


@adm_router.post("/{batch_id}/reject", response_model=BatchOut)
async def reject_batch(batch_id: str, body: RejectIn,
                       user: Annotated[CurrentUser, Depends(require_admin)]):
    """Reject a batch. A note is REQUIRED (422 without one) — the employer
    needs a reason to act on. Careers-page rolling drafts reject their staged
    rows in place and stay draft (the source keeps syncing)."""
    async with get_db() as conn:
        rec = await conn.fetchrow(
            f"SELECT b.*, e.name AS emp_name, {_ADMIN_ENRICH_SQL} "
            "FROM public.job_import_batches b "
            "JOIN public.employers e ON e.id = b.employer_id WHERE b.id = $1::uuid",
            batch_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
        is_careers_draft = rec["status"] == "draft" and bool(rec["from_career_source"])
        if rec["status"] != "pending" and not is_careers_draft:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Batch is {rec['status']}")
        rejected_rows = 0
        if is_careers_draft:
            # Reject the staged rows, keep the rolling batch alive.
            res = await conn.execute(
                "UPDATE public.job_import_rows SET status = 'rejected', updated_at = now() "
                "WHERE batch_id = $1::uuid AND status = 'staged'", batch_id,
            )
            try:
                rejected_rows = int(str(res).split()[-1])
            except (ValueError, IndexError):
                rejected_rows = 0
            await conn.execute(
                "UPDATE public.job_import_batches SET reviewer_id = $2::uuid, "
                "reviewer_note = $3, reviewed_at = now(), "
                "rows_rejected = rows_rejected + $4, updated_at = now() WHERE id = $1::uuid",
                batch_id, user.user_id, body.note, rejected_rows,
            )
        else:
            await conn.execute(
                "UPDATE public.job_import_batches SET status = 'rejected', reviewer_id = $2::uuid, "
                "reviewer_note = $3, reviewed_at = now(), updated_at = now() WHERE id = $1::uuid",
                batch_id, user.user_id, body.note,
            )
        await write_audit(
            conn,
            action="job_import_rejected",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="job_import_batches", entity_id=batch_id,
            after={"status": "draft" if is_careers_draft else "rejected",
                   "rejected_rows": rejected_rows},
            metadata={"note": body.note[:2000],
                      "from_career_source": bool(rec["from_career_source"])},
        )
        await _notify(
            conn, kind="job_import_rejected", recipient_user_id=str(rec["created_by"]),
            title=(f"{rejected_rows} staged job{'s' if rejected_rows != 1 else ''} "
                   "rejected: review the note"
                   if is_careers_draft else
                   "Batch rejected: review the note and resubmit"),
            body=body.note, link_href=f"/employer/jobs/imports/{batch_id}",
            payload={"batch_id": batch_id, "rejected_rows": rejected_rows},
        )
        rowrec = await conn.fetchrow(
            f"SELECT b.*, {_ADMIN_ENRICH_SQL} "
            "FROM public.job_import_batches b WHERE b.id = $1::uuid", batch_id,
        )
        return await _admin_batch_out(conn, rowrec)


# ============================================================================
# Notifications
# ============================================================================

@adm_router.get("/notifications/admin")
async def admin_notifications(
    user: Annotated[CurrentUser, Depends(require_admin)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT id::text, kind::text, title, body, link_href, read_at, created_at, "
            "count(*) OVER () AS _total "
            "FROM public.notifications WHERE recipient_role = 'admin' "
            "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        total = int(rows[0]["_total"]) if rows else 0
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [
                {
                    "id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"],
                    "link_href": r["link_href"],
                    "read": r["read_at"] is not None,
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ],
        }


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
