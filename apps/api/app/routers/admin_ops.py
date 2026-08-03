"""
admin_ops.py — Admin operational actions.

POST /admin/ops/recompute-matches — kick off a full match recompute on demand.
The scheduler already runs one every 6 hours behind a Redis lock; this gives
admins a button for "I just changed something, rescore everyone NOW". Reuses
the exact locked path the scheduler uses, so concurrent clicks / overlap with
the cron run are safe (second caller finds the lock held and no-ops).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.util.audit import write_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ops", tags=["admin"])


class RecomputeResponse(BaseModel):
    started: bool
    detail: str


@router.post("/recompute-matches", response_model=RecomputeResponse, status_code=202)
async def recompute_all_matches(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> RecomputeResponse:
    from app.worker.scheduler import _locked_recompute

    async with get_db() as conn:
        await write_audit(
            conn,
            action="recompute_matches_triggered",
            actor_id=current_user.user_id,
            actor_role="admin",
            entity_type="matches",
            entity_id=None,
        )

    # Fire and forget — the run takes minutes; progress lands in recompute_runs.
    asyncio.create_task(_locked_recompute())
    return RecomputeResponse(
        started=True,
        detail="Recompute started. Progress is tracked in recompute runs; scores update as it completes.",
    )


class PendingCounts(BaseModel):
    """Sidebar badge feed — same shared definitions as the destination pages."""
    imports_awaiting_batches: int
    imports_awaiting_rows: int
    credentials_needs_review: int
    review_items_pending: int


@router.get("/pending-counts", response_model=PendingCounts)
async def pending_counts(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> PendingCounts:
    from app.util.review_queue import (
        count_awaiting_import_review,
        count_pending_review_items,
    )

    async with get_db() as conn:
        imports = await count_awaiting_import_review(conn)
        review = await count_pending_review_items(conn)
        creds = await conn.fetchval(
            "SELECT count(*) FROM public.credentials WHERE needs_review = TRUE"
        )
    return PendingCounts(
        imports_awaiting_batches=imports["batches"],
        imports_awaiting_rows=imports["rows"],
        credentials_needs_review=int(creds or 0),
        review_items_pending=review["total"],
    )
