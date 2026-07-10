"""
Commute / drive-time for a specific applicant-job match.

GET /applicant/me/matches/{match_id}/commute
  → { minutes, provider, from_label, to_label, cached }

Provider order: cached matches row → Google/Mapbox (if key) → haversine estimate.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro.commute import drive_minutes
from app.skilled_pro.geocode import geocode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/applicant/me", tags=["applicant"])


class CommuteOut(BaseModel):
    minutes: Optional[int] = None
    provider: str = "unknown"     # google | mapbox | haversine | unknown
    from_label: Optional[str] = None
    to_label: Optional[str] = None
    unavailable_reason: Optional[str] = None


@router.get("/matches/{match_id}/commute", response_model=CommuteOut)
async def match_commute(match_id: UUID, user: CurrentUser = Depends(require_applicant)):
    settings = get_settings()

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT m.id,
                   m.drive_minutes, m.drive_provider,
                   a.city AS a_city, a.state AS a_state, a.zip_code AS a_zip,
                   j.city AS j_city, j.state AS j_state, j.zip_code AS j_zip
              FROM public.matches m
              JOIN public.applicants a ON a.id = m.applicant_id
              JOIN public.jobs j       ON j.id = m.job_id
             WHERE m.id = $1 AND a.user_id = $2
            """,
            match_id, user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Match not found.")

        from_label = _label(row["a_city"], row["a_state"])
        to_label   = _label(row["j_city"], row["j_state"])

        # Fast path — already computed and stored on the match row.
        if row["drive_minutes"] is not None:
            return CommuteOut(
                minutes=int(row["drive_minutes"]),
                provider=row["drive_provider"] or "cached",
                from_label=from_label,
                to_label=to_label,
            )

        # Geocode both endpoints. If either fails, tell the UI why so we can
        # render a soft "unavailable" state instead of pretending.
        origin = await geocode(conn, city=row["a_city"] or "", state=row["a_state"] or "", zip_code=row["a_zip"] or "")
        if origin is None:
            return CommuteOut(from_label=from_label, to_label=to_label,
                              unavailable_reason="Add your city + state to see drive time.")
        dest = await geocode(conn, city=row["j_city"] or "", state=row["j_state"] or "", zip_code=row["j_zip"] or "")
        if dest is None:
            return CommuteOut(from_label=from_label, to_label=to_label,
                              unavailable_reason="Job location unavailable.")

        minutes, provider = await drive_minutes(
            conn,
            origin=origin,
            destination=dest,
            google_key=settings.google_maps_api_key,
            mapbox_token=settings.mapbox_access_token,
        )

        # Persist onto the match so future renders are one query, no geocode/API cost.
        await conn.execute(
            "UPDATE public.matches SET drive_minutes = $1, drive_provider = $2 WHERE id = $3",
            minutes, provider, match_id,
        )

    return CommuteOut(
        minutes=minutes,
        provider=provider,
        from_label=from_label,
        to_label=to_label,
    )


def _label(city: Optional[str], state: Optional[str]) -> Optional[str]:
    parts = [p for p in (city, state) if p]
    return ", ".join(parts) if parts else None
