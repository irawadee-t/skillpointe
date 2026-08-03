"""
Training-pathway recommendations.

When an applicant's match fails a credential gate (e.g. missing OSHA 30, CDL,
AWS D1.1), we surface concrete programs at partner colleges that grant the
credential — turning "you're not eligible" into "here's the path forward."

Routes:
  GET /training/programs?credential=osha_30&state=GA  — filter
  GET /applicant/me/matches/{match_id}/training       — recs for a specific match
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_applicant
from app.auth.schemas import CurrentUser
from app.db import get_db

logger = logging.getLogger(__name__)

pub_router = APIRouter(prefix="/training", tags=["training"])
app_router = APIRouter(prefix="/applicant/me", tags=["applicant"])


class ProgramOut(BaseModel):
    id: UUID
    name: str
    credential_key: str
    provider_name: str
    provider_url: Optional[str] = None
    duration_weeks: Optional[int] = None
    cost_range: Optional[str] = None
    format: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


class MatchTrainingOut(BaseModel):
    match_id: UUID
    missing_credentials: list[str]
    recommendations: list[ProgramOut]


@pub_router.get("/programs", response_model=list[ProgramOut])
async def list_programs(
    credential: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 20,
    _: CurrentUser = Depends(get_current_user),
):
    where = ["tp.active"]
    values: list = []
    idx = 1
    if credential:
        where.append(f"tp.credential_key = ${idx}")
        values.append(credential)
        idx += 1
    if state:
        where.append(f"tp.state = ${idx}")
        values.append(state.upper()[:2])
        idx += 1

    async with get_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT tp.id, tp.name, tp.credential_key, tp.duration_weeks, tp.cost_range,
                   tp.format, tp.city, tp.state, tp.url, tp.description,
                   pr.name AS provider_name, pr.website_url AS provider_url
              FROM public.training_programs tp
              JOIN public.training_providers pr ON pr.id = tp.provider_id
             WHERE {" AND ".join(where)}
          ORDER BY tp.duration_weeks NULLS LAST, tp.name
             LIMIT {int(limit)}
            """,
            *values,
        )
    return [ProgramOut(**dict(r)) for r in rows]


@app_router.get("/matches/{match_id}/training", response_model=MatchTrainingOut)
async def training_for_match(
    match_id: UUID,
    user: CurrentUser = Depends(require_applicant),
):
    async with get_db() as conn:
        m = await conn.fetchrow(
            """
            SELECT m.id, m.required_missing_items, m.top_gaps,
                   a.state AS applicant_state, a.id AS applicant_id
              FROM public.matches m
              JOIN public.applicants a ON a.id = m.applicant_id
             WHERE m.id = $1
               AND a.id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))
            """,
            match_id, user.user_id, user.view_as_applicant_id,
        )
        if not m:
            raise HTTPException(status_code=404, detail="Match not found.")

        raw = m["required_missing_items"]
        if raw is None:
            gaps: list[str] = []
        elif isinstance(raw, list):
            gaps = [str(x) for x in raw]
        else:
            gaps = [str(raw)]
        top_gaps = m["top_gaps"]
        if isinstance(top_gaps, list):
            gaps.extend([str(g) for g in top_gaps])

        credential_keys = _infer_credentials(gaps)

        recs: list[ProgramOut] = []
        seen: set[str] = set()
        if credential_keys:
            state = m["applicant_state"]
            rows = await conn.fetch(
                """
                SELECT tp.id, tp.name, tp.credential_key, tp.duration_weeks, tp.cost_range,
                       tp.format, tp.city, tp.state, tp.url, tp.description,
                       pr.name AS provider_name, pr.website_url AS provider_url
                  FROM public.training_programs tp
                  JOIN public.training_providers pr ON pr.id = tp.provider_id
                 WHERE tp.active
                   AND tp.credential_key = ANY($1::text[])
              ORDER BY (tp.state = $2) DESC, tp.duration_weeks NULLS LAST
                 LIMIT 12
                """,
                credential_keys, (state or "").upper()[:2],
            )
            for r in rows:
                key = f"{r['credential_key']}::{r['provider_name']}"
                if key in seen:
                    continue
                seen.add(key)
                recs.append(ProgramOut(**dict(r)))

    return MatchTrainingOut(
        match_id=match_id,
        missing_credentials=credential_keys,
        recommendations=recs,
    )


_CRED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"osha\s*30",              re.I),  "osha_30"),
    (re.compile(r"osha\s*10",              re.I),  "osha_30"),
    (re.compile(r"\bcdl\b|commercial driver", re.I), "cdl_a"),
    (re.compile(r"class\s*a",              re.I),  "cdl_a"),
    (re.compile(r"aws\s*d\s*1\.1|d1\.1|structural weld", re.I), "welding_aws_d1_1"),
    (re.compile(r"weld|mig|tig|stick",     re.I),  "welding_aws_d1_1"),
    (re.compile(r"nccer|electric",         re.I),  "nccer_electrical"),
    (re.compile(r"epa\s*608|refrigerant|hvac", re.I), "epa_608"),
    (re.compile(r"diesel",                 re.I),  "diesel_tech"),
    (re.compile(r"mechatron",              re.I),  "mechatronics"),
    (re.compile(r"industrial maintenance", re.I),  "industrial_maint"),
]


def _infer_credentials(gaps: list[str]) -> list[str]:
    if not gaps:
        return []
    hits: list[str] = []
    for gap in gaps:
        for pat, key in _CRED_PATTERNS:
            if pat.search(gap):
                if key not in hits:
                    hits.append(key)
                break
    return hits
