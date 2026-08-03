"""
Consent Center — granular, per-category consent the worker controls, with a
cryptographically signed, append-only consent ledger.

Three independent scopes per data category: display, internal_use,
external_sharing (a list of requester categories). External sharing defaults to
empty (deny). Every change appends a signed ``consent_records`` row so external
data-sharing is auditable and provable — required for FERPA/CCPA-grade consent.
"""
from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_applicant
from app.db import get_db
from app.skilled_pro.consent import parse_external_sharing
from app.skilled_pro.records import append_consent_record

router = APIRouter(prefix="/applicant/me/consent", tags=["consent"])

# Data categories a worker can govern independently.
DATA_CATEGORIES = (
    "certifications",
    "employment_history",
    "education",
    "wage_expectations",
    "contact_info",
    "portfolio",
)


class ConsentSettingOut(BaseModel):
    data_category: str
    display: bool
    internal_use: bool
    external_sharing: list[str]


class ConsentUpdate(BaseModel):
    display: bool = False
    internal_use: bool = True
    external_sharing: list[str] = Field(default_factory=list)


async def _resolve_applicant_id(conn: asyncpg.Connection, user: CurrentUser) -> str:
    # View-as resolves by applicant id directly (supports unlinked applicants).
    row = await conn.fetchrow(
        "SELECT id::text AS id FROM public.applicants "
        "WHERE id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))",
        user.user_id,
        user.view_as_applicant_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant profile not found")
    return row["id"]


@router.get("", response_model=list[ConsentSettingOut])
async def get_consent(user: Annotated[CurrentUser, Depends(require_applicant)]):
    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
        rows = await conn.fetch(
            "SELECT data_category, display, internal_use, external_sharing "
            "FROM public.consent_settings WHERE applicant_id = $1",
            applicant_id,
        )
    existing = {r["data_category"]: r for r in rows}
    # Return a row for every known category (defaults for any not yet set).
    out: list[ConsentSettingOut] = []
    for cat in DATA_CATEGORIES:
        r = existing.get(cat)
        if r:
            out.append(ConsentSettingOut(
                data_category=cat,
                display=r["display"],
                internal_use=r["internal_use"],
                external_sharing=list(r["external_sharing"] or []),
            ))
        else:
            out.append(ConsentSettingOut(
                data_category=cat, display=False, internal_use=True, external_sharing=[]
            ))
    return out


@router.put("/{data_category}", response_model=ConsentSettingOut)
async def update_consent(
    data_category: str,
    body: ConsentUpdate,
    user: Annotated[CurrentUser, Depends(require_applicant)],
):
    if data_category not in DATA_CATEGORIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown data category '{data_category}'")

    # Validate + canonicalize requester categories (drops anything unrecognized).
    valid = sorted(c.value for c in parse_external_sharing(body.external_sharing))

    async with get_db() as conn:
        applicant_id = await _resolve_applicant_id(conn, user)
        row = await conn.fetchrow(
            """
            INSERT INTO public.consent_settings
                (applicant_id, data_category, display, internal_use, external_sharing, updated_at)
            VALUES ($1,$2,$3,$4,$5, now())
            ON CONFLICT (applicant_id, data_category) DO UPDATE
              SET display = EXCLUDED.display,
                  internal_use = EXCLUDED.internal_use,
                  external_sharing = EXCLUDED.external_sharing,
                  updated_at = now()
            RETURNING data_category, display, internal_use, external_sharing
            """,
            # Pass the Python list directly — the asyncpg JSONB codec (db.py)
            # serializes it. (Pre-dumping + ::jsonb double-encodes into a string.)
            applicant_id, data_category, body.display, body.internal_use, valid,
        )
        await append_consent_record(
            conn, applicant_id, data_category,
            {
                "data_category": data_category,
                "display": body.display,
                "internal_use": body.internal_use,
                "external_sharing": valid,
            },
        )
    return ConsentSettingOut(
        data_category=row["data_category"],
        display=row["display"],
        internal_use=row["internal_use"],
        external_sharing=list(row["external_sharing"] or []),
    )
