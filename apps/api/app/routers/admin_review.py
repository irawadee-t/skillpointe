"""
admin_review.py — the ops review feed + the audit-log reader.

  GET  /admin/review                — one prioritized feed over
        review_queue_items (chat guardrail trips, credential/taxonomy
        ambiguity, broken apply links, borderline matches, ...), grouped by
        type, each row deep-linking to the surface where it gets fixed.
  POST /admin/review/{id}/resolve   — resolve or dismiss an item (audited).
  GET  /admin/audit-logs            — read-only audit trail with filters +
        pagination (actor, action, entity, date range).

review_queue_items has been written to by extraction, chat guardrails, and
the careers-page link checker since Phase 7 — this gives that queue a face.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_admin
from app.db import get_db
from app.skilled_pro.notifications import notify
from app.skilled_pro.records import append_credential_record
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    VerificationLevel,
    derive_level,
)
from app.util.audit import write_audit
from app.util.review_queue import count_pending_review_items

router = APIRouter(prefix="/admin", tags=["admin-review"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ReviewItemOut(BaseModel):
    id: str
    item_type: str
    entity_type: str
    entity_id: str
    description: Optional[str] = None
    flags: Any = None
    confidence_level: Optional[str] = None
    priority: int = 5
    status: str
    created_at: str
    resolved_at: Optional[str] = None
    resolution_action: Optional[str] = None
    resolution_notes: Optional[str] = None
    # Where this item gets FIXED — computed per item type/entity.
    link_href: Optional[str] = None


class ReviewFeedOut(BaseModel):
    items: list[ReviewItemOut]
    total: int
    limit: int
    offset: int
    pending_by_type: dict[str, int]
    pending_total: int


class ResolveIn(BaseModel):
    action: str = Field(pattern="^(reviewed|overridden|dismissed)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class AuditLogOut(BaseModel):
    id: str
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    note: Optional[str] = None
    metadata: Any = None
    created_at: str


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int
    actions: list[str]        # distinct actions for the filter dropdown
    entity_types: list[str]   # distinct entity types for the filter dropdown


# ---------------------------------------------------------------------------
# Deep links: where each review item type gets resolved
# ---------------------------------------------------------------------------

_STATIC_LINKS: dict[str, str] = {
    "taxonomy_mismatch": "/admin/credentials#queue",
    "credential_ambiguity": "/admin/credentials#queue",
    "extraction_confidence": "/admin/credentials#queue",
    "low_confidence_verifier": "/admin/credentials#queue",
    "borderline_match": "/admin/test-matches",
    "geography_ambiguity": "/admin/test-matches",
    "suspicious_import": "/admin/job-imports",
    "admin_override_review": "/admin/audit",
}


def _resolution_link(item_type: str, entity_type: str, entity_id: str,
                     batch_by_row: dict[str, str]) -> Optional[str]:
    if item_type == "broken_apply_link" or entity_type == "import_row":
        batch = batch_by_row.get(entity_id)
        return f"/admin/job-imports/{batch}" if batch else "/admin/job-imports"
    if entity_type == "credential":
        return "/admin/credentials#queue"
    if entity_type == "career_source":
        return "/admin/career-sources"
    return _STATIC_LINKS.get(item_type)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/review", response_model=ReviewFeedOut)
async def review_feed(
    user: Annotated[CurrentUser, Depends(require_admin)],
    status_filter: str = Query(default="pending",
                               pattern="^(pending|reviewed|overridden|dismissed|all)$"),
    item_type: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    where = ["TRUE"]
    params: list[Any] = []
    if status_filter != "all":
        params.append(status_filter)
        where.append(f"q.status = ${len(params)}::review_status_enum")
    if item_type:
        params.append(item_type)
        where.append(f"q.item_type::text = ${len(params)}")
    params.append(limit)
    lim = len(params)
    params.append(offset)
    off = len(params)
    async with get_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT q.id::text AS id, q.item_type::text AS item_type,
                   q.entity_type, q.entity_id::text AS entity_id,
                   q.description, q.flags, q.confidence_level::text AS confidence_level,
                   q.priority, q.status::text AS status,
                   q.created_at, q.resolved_at, q.resolution_action, q.resolution_notes,
                   count(*) OVER () AS _total
              FROM public.review_queue_items q
             WHERE {" AND ".join(where)}
             ORDER BY q.priority ASC, q.created_at DESC
             LIMIT ${lim} OFFSET ${off}
            """,
            *params,
        )
        total = int(rows[0]["_total"]) if rows else 0
        # Resolve import-row entities to their batch for real deep links.
        row_ids = [r["entity_id"] for r in rows if r["entity_type"] == "import_row"]
        batch_by_row: dict[str, str] = {}
        if row_ids:
            for br in await conn.fetch(
                "SELECT id::text AS id, batch_id::text AS batch_id "
                "FROM public.job_import_rows WHERE id = ANY($1::uuid[])", row_ids,
            ):
                batch_by_row[br["id"]] = br["batch_id"]
        pending = await count_pending_review_items(conn)
    items = [
        ReviewItemOut(
            id=r["id"], item_type=r["item_type"], entity_type=r["entity_type"],
            entity_id=r["entity_id"], description=r["description"], flags=r["flags"],
            confidence_level=r["confidence_level"], priority=int(r["priority"] or 5),
            status=r["status"], created_at=r["created_at"].isoformat(),
            resolved_at=r["resolved_at"].isoformat() if r["resolved_at"] else None,
            resolution_action=r["resolution_action"],
            resolution_notes=r["resolution_notes"],
            link_href=_resolution_link(r["item_type"], r["entity_type"],
                                       r["entity_id"], batch_by_row),
        )
        for r in rows
    ]
    return ReviewFeedOut(items=items, total=total, limit=limit, offset=offset,
                         pending_by_type=pending["by_type"],
                         pending_total=pending["total"])


@router.post("/review/{item_id}/resolve", response_model=ReviewItemOut)
async def resolve_review_item(
    item_id: str, body: ResolveIn,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Resolve (reviewed/overridden) or dismiss a review item. Audited."""
    new_status = "dismissed" if body.action == "dismissed" else body.action
    async with get_db() as conn:
        before = await conn.fetchrow(
            "SELECT id, item_type::text AS item_type, status::text AS status "
            "FROM public.review_queue_items WHERE id = $1::uuid", item_id,
        )
        if not before:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review item not found")
        if before["status"] != "pending":
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Item already {before['status']}")
        row = await conn.fetchrow(
            """
            UPDATE public.review_queue_items
               SET status = $2::review_status_enum,
                   resolved_by = $3::uuid, resolved_at = now(),
                   resolution_action = $4, resolution_notes = $5,
                   updated_at = now()
             WHERE id = $1::uuid
            RETURNING id::text AS id, item_type::text AS item_type, entity_type,
                      entity_id::text AS entity_id, description, flags,
                      confidence_level::text AS confidence_level, priority,
                      status::text AS status, created_at, resolved_at,
                      resolution_action, resolution_notes
            """,
            item_id, new_status, user.user_id, body.action, body.note,
        )
        await write_audit(
            conn,
            action="review_item_resolved",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="review_queue_item", entity_id=item_id,
            before={"status": "pending", "item_type": before["item_type"]},
            after={"status": new_status, "action": body.action},
            metadata={"note": body.note} if body.note else None,
        )

        # Document-review lane: "reviewed"/"overridden" on a credential
        # ambiguity item IS the human confirmation the upload flow promised
        # ("we'll badge it once confirmed"). Without this, resolving only
        # closed the queue item and the credential stayed Self-Reported
        # forever — a dead-end promise to the applicant.
        if (
            row["item_type"] == "credential_ambiguity"
            and row["entity_type"] == "credential"
            and body.action in ("reviewed", "overridden")
        ):
            await _grant_document_verification(conn, row["entity_id"], user)

        # Dismissal is also an outcome the applicant must hear: the credential
        # returns to its self-reported state (the pending review item was its
        # only "in review" signal) and the applicant gets an honest,
        # actionable notification instead of waiting forever.
        if (
            row["item_type"] == "credential_ambiguity"
            and row["entity_type"] == "credential"
            and body.action == "dismissed"
        ):
            await _dismiss_document_verification(conn, row["entity_id"], user)
    return ReviewItemOut(
        id=row["id"], item_type=row["item_type"], entity_type=row["entity_type"],
        entity_id=row["entity_id"], description=row["description"], flags=row["flags"],
        confidence_level=row["confidence_level"], priority=int(row["priority"] or 5),
        status=row["status"], created_at=row["created_at"].isoformat(),
        resolved_at=row["resolved_at"].isoformat() if row["resolved_at"] else None,
        resolution_action=row["resolution_action"],
        resolution_notes=row["resolution_notes"],
        link_href=None,
    )


async def _grant_document_verification(conn, credential_id: str, user: CurrentUser) -> None:
    """Admin confirmed an uploaded credential document: raise the credential to
    the document-upload verification level (never lower an existing one),
    append to the signed record chain, and tell the applicant."""
    cred = await conn.fetchrow(
        "SELECT c.id, c.verification_level, c.applicant_id::text AS applicant_id, "
        "       COALESCE(c.canonical_name, c.raw_name) AS name, a.user_id "
        "  FROM public.credentials c JOIN public.applicants a ON a.id = c.applicant_id "
        " WHERE c.id = $1::uuid",
        credential_id,
    )
    if not cred:
        return
    derived = derive_level(VerificationEvidence(
        source=CredentialSource.DOCUMENT_UPLOAD,
        issuer_matched=True, document_authentic=True,
    ))
    new_level = max(int(cred["verification_level"]), derived.value)
    await conn.execute(
        "UPDATE public.credentials SET verification_level = $2, source = 'document_upload', "
        "updated_at = now() WHERE id = $1::uuid",
        credential_id, new_level,
    )
    await append_credential_record(
        conn, cred["applicant_id"], str(credential_id), "document_verified",
        {"credential_id": str(credential_id), "verification_level": new_level,
         "source": "admin_review", "resolved_by": str(user.user_id)},
    )
    if cred["user_id"]:
        try:
            await notify(
                conn,
                recipient_user_id=str(cred["user_id"]),
                kind="credential_verified",
                title=f"{cred['name']} is verified",
                body=f"SkillPointe reviewed your document. Your badge is now {VerificationLevel(new_level).badge}.",
                link_href="/applicant/credentials",
                payload={"credential_id": str(credential_id), "verification_level": new_level},
                dedupe_key=f"credential_verified:{credential_id}",
            )
        except Exception as exc:  # the grant itself must not roll back on a tray hiccup
            import logging
            logging.getLogger(__name__).warning(
                "credential_verified notification failed for %s: %s", credential_id, exc
            )


async def _dismiss_document_verification(conn, credential_id: str, user: CurrentUser) -> None:
    """Admin dismissed the document-review item without confirming: the
    credential stays at its current (self-reported) level, the outcome is
    appended to the signed record chain, and the applicant is told what to
    try next — never a silent forever-pending state."""
    cred = await conn.fetchrow(
        "SELECT c.id, c.verification_level, c.applicant_id::text AS applicant_id, "
        "       COALESCE(c.canonical_name, c.raw_name) AS name, a.user_id "
        "  FROM public.credentials c JOIN public.applicants a ON a.id = c.applicant_id "
        " WHERE c.id = $1::uuid",
        credential_id,
    )
    if not cred:
        return
    await append_credential_record(
        conn, cred["applicant_id"], str(credential_id), "document_review_dismissed",
        {"credential_id": str(credential_id),
         "verification_level": int(cred["verification_level"]),
         "source": "admin_review", "resolved_by": str(user.user_id)},
    )
    if cred["user_id"]:
        try:
            await notify(
                conn,
                recipient_user_id=str(cred["user_id"]),
                kind="credential_review_dismissed",
                title=f"We couldn't verify your {cred['name']} from the document",
                body="It stays self-reported for now. Try a clearer photo, a badge link, or another verification method.",
                link_href="/applicant/credentials",
                payload={"credential_id": str(credential_id)},
                dedupe_key=f"credential_review_dismissed:{credential_id}",
            )
        except Exception as exc:  # the dismissal itself must not roll back on a tray hiccup
            import logging
            logging.getLogger(__name__).warning(
                "credential_review_dismissed notification failed for %s: %s", credential_id, exc
            )


@router.get("/audit-logs", response_model=AuditLogListOut)
async def audit_logs(
    user: Annotated[CurrentUser, Depends(require_admin)],
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_role: Optional[str] = None,
    date_from: Optional[str] = Query(default=None, description="ISO date, inclusive"),
    date_to: Optional[str] = Query(default=None, description="ISO date, inclusive"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Read-only audit trail. Every admin mutation lands here (guardrail:
    'all admin overrides are auditable') — this is the reader."""
    where = ["TRUE"]
    params: list[Any] = []
    if action:
        params.append(action)
        where.append(f"a.action = ${len(params)}")
    if entity_type:
        params.append(entity_type)
        where.append(f"a.entity_type = ${len(params)}")
    if actor_role:
        params.append(actor_role)
        where.append(f"a.actor_role = ${len(params)}")
    if date_from:
        params.append(date_from)
        where.append(f"a.created_at >= ${len(params)}::date")
    if date_to:
        params.append(date_to)
        where.append(f"a.created_at < (${len(params)}::date + interval '1 day')")
    params.append(limit)
    lim = len(params)
    params.append(offset)
    off = len(params)
    async with get_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT a.id::text AS id, a.actor_id::text AS actor_id, a.actor_role,
                   a.action, a.entity_type, a.entity_id::text AS entity_id,
                   a.metadata, a.created_at,
                   count(*) OVER () AS _total
              FROM public.audit_logs a
             WHERE {" AND ".join(where)}
             ORDER BY a.created_at DESC
             LIMIT ${lim} OFFSET ${off}
            """,
            *params,
        )
        total = int(rows[0]["_total"]) if rows else 0
        actions = [r["action"] for r in await conn.fetch(
            "SELECT DISTINCT action FROM public.audit_logs ORDER BY action LIMIT 200")]
        entity_types = [r["entity_type"] for r in await conn.fetch(
            "SELECT DISTINCT entity_type FROM public.audit_logs "
            "WHERE entity_type IS NOT NULL ORDER BY entity_type LIMIT 200")]

    def _note(meta: Any) -> Optional[str]:
        if isinstance(meta, dict):
            n = meta.get("note")
            return str(n) if n else None
        return None

    items = [
        AuditLogOut(
            id=r["id"], actor_id=r["actor_id"], actor_role=r["actor_role"],
            action=r["action"], entity_type=r["entity_type"], entity_id=r["entity_id"],
            note=_note(r["metadata"]), metadata=r["metadata"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
    return AuditLogListOut(items=items, total=total, limit=limit, offset=offset,
                           actions=actions, entity_types=entity_types)
