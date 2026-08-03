"""
ONE definition of "awaiting admin review" for the import pipeline, shared by:

  • GET /admin/analytics/dashboard  (priority-inbox counts)
  • GET /admin/job-imports          (the approval queue itself)
  • GET /admin/career-sources       (per-source staged counts)
  • the sidebar pending-work badges

Two kinds of batches carry reviewable work:
  1. status = 'pending'  — employer submitted the batch for review.
  2. status = 'draft' AND linked to a career source AND has staged rows —
     careers-page pulls sync into a rolling draft batch that is never
     "submitted"; its staged rows are review work the moment the pull lands.

Any surface that counts or lists "awaiting review" MUST go through this
module so the dashboard, the queue, and career sources can never disagree
(the "Ford submitted 5 jobs" vs "Draft" contradiction).
"""
from __future__ import annotations

from typing import Any

# WHERE fragment over alias `b` (public.job_import_batches).
AWAITING_IMPORT_REVIEW_WHERE = (
    "(b.status = 'pending' OR (b.status = 'draft' "
    "AND EXISTS (SELECT 1 FROM public.employer_career_sources s WHERE s.batch_id = b.id) "
    "AND EXISTS (SELECT 1 FROM public.job_import_rows r "
    "            WHERE r.batch_id = b.id AND r.status = 'staged')))"
)

# Career-source rolling drafts with staged rows only (the "Staged from
# careers pages" tab).
STAGED_FROM_CAREERS_WHERE = (
    "(b.status = 'draft' "
    "AND EXISTS (SELECT 1 FROM public.employer_career_sources s WHERE s.batch_id = b.id) "
    "AND EXISTS (SELECT 1 FROM public.job_import_rows r "
    "            WHERE r.batch_id = b.id AND r.status = 'staged'))"
)


async def count_awaiting_import_review(conn) -> dict[str, int]:
    """{"batches": N, "rows": M} — the one number every surface shows."""
    row = await conn.fetchrow(
        f"""
        SELECT count(*) AS batches,
               coalesce(sum((SELECT count(*) FROM public.job_import_rows r
                              WHERE r.batch_id = b.id AND r.status = 'staged')), 0) AS rows
          FROM public.job_import_batches b
         WHERE {AWAITING_IMPORT_REVIEW_WHERE}
        """
    )
    if not row:
        return {"batches": 0, "rows": 0}
    return {"batches": int(row["batches"] or 0), "rows": int(row["rows"] or 0)}


async def count_pending_review_items(conn) -> dict[str, Any]:
    """Pending review_queue_items, total + by item_type (guardrail flags,
    taxonomy mismatches, broken apply links, ...)."""
    rows = await conn.fetch(
        "SELECT item_type::text AS t, count(*) AS c "
        "FROM public.review_queue_items WHERE status = 'pending' GROUP BY 1"
    )
    by_type = {r["t"]: int(r["c"]) for r in rows}
    return {"total": sum(by_type.values()), "by_type": by_type}


def batch_review_state(status: str, from_career_source: bool, rows_staged: int) -> str:
    """Human-meaningful review state for a batch — no silent 'draft' fallback.

    awaiting_review      — submitted, in the admin queue
    staged_from_careers  — careers-page pull with staged rows to review
    draft                — employer still editing (genuinely not our work yet)
    approved/rejected/published — terminal review outcomes
    """
    if status == "pending":
        return "awaiting_review"
    if status == "draft" and from_career_source and rows_staged > 0:
        return "staged_from_careers"
    return status
