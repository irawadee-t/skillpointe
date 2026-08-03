"""
Credential taxonomy surfaces.

Two lanes:
  GET   /credentials/taxonomy/suggest        — type-ahead over the canonical
        registry (any authenticated user; powers the applicant add-credential
        form and the admin fix picker). Deterministic, in-memory, DB-free.
  GET   /admin/credentials/normalization     — canonical-vs-raw console feed
  PATCH /admin/credentials/{id}/canonical    — admin fixes a mismatch (audited)

An admin fix writes audit_logs + a signed credential_records row, resolves any
pending taxonomy review-queue items, and NEVER touches the applicant's raw
text — raw_name is the applicant's, canonical_* is ours.
"""
from __future__ import annotations

from typing import Annotated, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.skilled_pro import taxonomy
from app.skilled_pro.records import append_credential_record

router = APIRouter(tags=["credential-taxonomy"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SuggestionOut(BaseModel):
    slug: str
    name: str
    category: str
    issuer: Optional[str] = None
    validity_note: Optional[str] = None
    verify_url: Optional[str] = None


class NormalizationRowOut(BaseModel):
    id: str
    applicant_id: str
    applicant_name: Optional[str] = None
    raw_name: str
    canonical_code: Optional[str] = None
    canonical_name: Optional[str] = None
    credential_type: Optional[str] = None
    issuer: Optional[str] = None
    normalization_confidence: float
    needs_review: bool
    source: str
    verification_level: int
    # HOW the mapper decided (exact/alias/token/fuzzy/none) + a human reason —
    # the console never shows a flag without saying why it was raised.
    match_method: str = "none"
    match_reason: str = ""
    # Identical raw strings collapse into one fix-once row.
    group_key: str = ""
    group_count: int = 1
    group_ids: list[str] = Field(default_factory=list)


class NormalizationListOut(BaseModel):
    items: list[NormalizationRowOut]
    total: int          # total GROUPS matching the filter ("Showing N of M")
    total_credentials: int
    limit: int
    offset: int


class CanonicalFixIn(BaseModel):
    # Canonical slug from the registry, or null to explicitly mark "no
    # canonical match" (clears the mapping and the review flag).
    slug: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=500)
    # Fix every credential whose raw text is identical (case/whitespace
    # insensitive) in one shot — the "applies to 3 credentials" row.
    apply_to_same_raw: bool = False


# ---------------------------------------------------------------------------
# Type-ahead suggestions (deterministic, in-memory)
# ---------------------------------------------------------------------------

@router.get("/credentials/taxonomy/suggest", response_model=list[SuggestionOut])
async def suggest_credentials(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
):
    return [
        SuggestionOut(
            slug=c.slug,
            name=c.name,
            category=c.type.value,
            issuer=c.issuer,
            validity_note=c.validity,
            verify_url=c.verify_url,
        )
        for c in taxonomy.suggest(q, limit=limit)
    ]


# ---------------------------------------------------------------------------
# Admin: canonical-vs-raw console
# ---------------------------------------------------------------------------

_ROW_SELECT = """
    SELECT c.id::text AS id, c.applicant_id::text AS applicant_id,
           TRIM(COALESCE(a.first_name, '') || ' ' || COALESCE(a.last_name, '')) AS applicant_name,
           c.raw_name, c.canonical_code, c.canonical_name, c.credential_type,
           c.issuer, c.normalization_confidence, c.needs_review, c.source,
           c.verification_level
      FROM public.credentials c
 LEFT JOIN public.applicants a ON a.id = c.applicant_id
"""


def _row_out(r: asyncpg.Record) -> NormalizationRowOut:
    return NormalizationRowOut(
        id=r["id"],
        applicant_id=r["applicant_id"],
        applicant_name=(r["applicant_name"] or None),
        raw_name=r["raw_name"],
        canonical_code=r["canonical_code"],
        canonical_name=r["canonical_name"],
        credential_type=r["credential_type"],
        issuer=r["issuer"],
        normalization_confidence=float(r["normalization_confidence"] or 0),
        needs_review=r["needs_review"],
        source=r["source"],
        verification_level=int(r["verification_level"]),
    )


_MATCH_REASONS = {
    "exact": "Exact match on a canonical credential name.",
    "alias": "Exactly matches a known name or alias of this credential.",
    "token": "The text contains a known credential alias, but with extra "
             "words around it. Worth a human glance.",
    "fuzzy": "Close-spelling match to a known alias (typo or OCR noise).",
    "none": "No canonical credential matched this text.",
}


def _match_info(raw_name: str) -> tuple[str, str]:
    """(method, human reason) for why this raw string mapped the way it did."""
    result = taxonomy.normalize(raw_name or "")
    method = result.method
    reason = _MATCH_REASONS.get(method, "")
    if method in ("token", "fuzzy") and result.canonical:
        reason += f" Best candidate: {result.canonical.name} ({result.confidence:.0%} confidence)."
    return method, reason


@router.get("/admin/credentials/normalization", response_model=NormalizationListOut)
async def list_normalization(
    user: Annotated[CurrentUser, Depends(require_admin)],
    only: str = Query(default="review", pattern="^(review|unmatched|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Canonical-vs-raw console feed. Identical raw strings are collapsed into
    one fix-once row (group_count = how many credentials the fix covers), and
    every flagged row carries the match method + a human reason."""
    where = {
        "review": "WHERE c.needs_review",
        "unmatched": "WHERE c.canonical_code IS NULL",
        "all": "",
    }[only]
    async with get_db() as conn:
        # One row per distinct raw string; the representative credential is the
        # most recent one in the group.
        rows = await conn.fetch(
            f"""
            WITH filtered AS ({_ROW_SELECT.replace('SELECT', 'SELECT c.created_at,', 1)} {where}),
            grouped AS (
                SELECT lower(trim(raw_name)) AS gkey,
                       count(*) AS gcount,
                       array_agg(id ORDER BY created_at DESC) AS gids,
                       (array_agg(id ORDER BY created_at DESC))[1] AS rep_id
                  FROM filtered GROUP BY 1
            )
            SELECT f.*, g.gkey, g.gcount, g.gids,
                   count(*) OVER () AS _gtotal,
                   sum(g.gcount) OVER () AS _ctotal
              FROM grouped g JOIN filtered f ON f.id = g.rep_id
             ORDER BY f.needs_review DESC, f.normalization_confidence ASC,
                      g.gcount DESC, f.created_at DESC
             LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
    total_groups = int(rows[0]["_gtotal"]) if rows else 0
    total_credentials = int(rows[0]["_ctotal"]) if rows else 0
    items: list[NormalizationRowOut] = []
    for r in rows:
        base = _row_out(r)
        method, reason = _match_info(r["raw_name"])
        base.match_method = method
        base.match_reason = reason
        base.group_key = r["gkey"]
        base.group_count = int(r["gcount"])
        base.group_ids = [str(i) for i in r["gids"]]
        items.append(base)
    return NormalizationListOut(items=items, total=total_groups,
                                total_credentials=total_credentials,
                                limit=limit, offset=offset)


@router.patch("/admin/credentials/{credential_id}/canonical", response_model=NormalizationRowOut)
async def fix_canonical(
    credential_id: str,
    body: CanonicalFixIn,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Admin override of a credential's canonical mapping. Auditable: writes
    audit_logs, appends a signed credential_records row, and resolves any
    pending taxonomy review-queue items for this credential."""
    definition = None
    if body.slug is not None:
        definition = taxonomy.get_by_slug(body.slug)
        if definition is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Unknown canonical slug: {body.slug}")

    async with get_db() as conn:
        cred = await conn.fetchrow(
            "SELECT id, applicant_id::text AS applicant_id, raw_name, canonical_code "
            "FROM public.credentials WHERE id = $1::uuid", credential_id,
        )
        if not cred:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")

        definition_id = None
        if definition is not None:
            def_row = await conn.fetchrow(
                "SELECT id FROM public.credential_definitions WHERE canonical_code = $1",
                definition.slug,
            )
            definition_id = def_row["id"] if def_row else None

        # Fix-once: optionally apply the same mapping to every credential whose
        # raw text is identical (case/whitespace-insensitive) and still flagged
        # or unmatched — the grouped console row's "applies to N credentials".
        target_ids = [credential_id]
        if body.apply_to_same_raw:
            siblings = await conn.fetch(
                """
                SELECT id::text AS id, applicant_id::text AS applicant_id,
                       raw_name, canonical_code
                  FROM public.credentials
                 WHERE lower(trim(raw_name)) = lower(trim($1))
                   AND id <> $2::uuid
                """,
                cred["raw_name"] or "", credential_id,
            )
        else:
            siblings = []

        # All writes (credential(s), review queue, audit log, signed records)
        # land atomically — a failure in any of them rolls the fix back.
        transaction = conn.transaction()
        await transaction.start()
        try:
            await _apply_fix(conn, credential_id, cred, definition, definition_id, body, user)
            for sib in siblings:
                await _apply_fix(conn, sib["id"], sib, definition, definition_id, body, user)
                target_ids.append(sib["id"])
        except Exception:
            await transaction.rollback()
            raise
        await transaction.commit()
        row = await conn.fetchrow(f"{_ROW_SELECT} WHERE c.id = $1::uuid", credential_id)
    out = _row_out(row)
    out.group_count = len(target_ids)
    out.group_ids = target_ids
    return out


async def _apply_fix(conn, credential_id, cred, definition, definition_id, body, user):
        await conn.execute(
            """
            UPDATE public.credentials
               SET canonical_code = $2, canonical_name = $3,
                   credential_type = COALESCE($4, credential_type),
                   issuer = COALESCE(issuer, $5),
                   definition_id = $6,
                   normalization_confidence = 1.0,
                   needs_review = false,
                   updated_at = now()
             WHERE id = $1::uuid
            """,
            credential_id,
            definition.slug if definition else None,
            definition.name if definition else None,
            definition.type.value if definition else None,
            definition.issuer if definition else None,
            definition_id,
        )
        # Resolve any pending taxonomy review items for this credential.
        await conn.execute(
            """
            UPDATE public.review_queue_items
               SET status = 'overridden', resolved_by = $2::uuid, resolved_at = now(),
                   resolution_action = 'overridden', resolution_notes = $3
             WHERE entity_type = 'credential' AND entity_id = $1::uuid
               AND item_type = 'taxonomy_mismatch' AND status = 'pending'
            """,
            credential_id, user.user_id,
            body.note or f"Admin set canonical to {definition.slug if definition else 'none'}",
        )
        await conn.execute(
            """
            INSERT INTO public.audit_logs
              (actor_id, actor_role, action, entity_type, entity_id, before_state, after_state)
            VALUES ($1::uuid, 'admin', 'credential.canonical_fix', 'credential', $2::uuid, $3, $4)
            """,
            user.user_id, credential_id,
            {"canonical_code": cred["canonical_code"], "raw_name": cred["raw_name"]},
            {"canonical_code": definition.slug if definition else None,
             "note": body.note},
        )
        await append_credential_record(
            conn, cred["applicant_id"], credential_id, "canonical_fixed",
            {
                "credential_id": credential_id,
                "canonical_code": definition.slug if definition else None,
                "fixed_by": "admin",
                "note": body.note,
            },
        )
