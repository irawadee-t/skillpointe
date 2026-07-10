"""
Response-time SLAs.

GET /admin/analytics/sla         — summary + list of dormant applications
POST /admin/analytics/sla/nudge  — send a nudge notification to the employer contact
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.skilled_pro.notifications import notify

router = APIRouter(prefix="/admin/analytics/sla", tags=["admin"])

_DORMANT_DAYS = 5


class DormantApplication(BaseModel):
    application_id: UUID
    employer_id: UUID
    employer_name: Optional[str]
    job_id: UUID
    job_title: str
    applicant_name: Optional[str]
    submitted_at: str
    days_dormant: int
    knockout_failed: bool


class SLASummary(BaseModel):
    dormant_count: int
    dormant_employers: int
    threshold_days: int
    items: list[DormantApplication]


@router.get("", response_model=SLASummary)
async def sla_summary(_: CurrentUser = Depends(require_admin)):
    async with get_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT a.id AS application_id, a.employer_id, e.name AS employer_name,
                   a.job_id, j.title_raw AS job_title,
                   ap.first_name, ap.last_name,
                   a.submitted_at, a.knockout_failed,
                   EXTRACT(DAY FROM NOW() - a.submitted_at)::int AS days_dormant
              FROM public.applications a
              JOIN public.employers e   ON e.id  = a.employer_id
              JOIN public.jobs j        ON j.id  = a.job_id
              JOIN public.applicants ap ON ap.id = a.applicant_id
             WHERE a.employer_viewed_at IS NULL
               AND a.status IN ('submitted', 'reviewed')
               AND a.submitted_at < NOW() - INTERVAL '{_DORMANT_DAYS} days'
          ORDER BY a.submitted_at
             LIMIT 200
            """,
        )
        dormant_employers = await conn.fetchval(
            f"""
            SELECT COUNT(DISTINCT a.employer_id) FROM public.applications a
             WHERE a.employer_viewed_at IS NULL
               AND a.submitted_at < NOW() - INTERVAL '{_DORMANT_DAYS} days'
            """
        )
    items = [
        DormantApplication(
            application_id=r["application_id"],
            employer_id=r["employer_id"],
            employer_name=r["employer_name"],
            job_id=r["job_id"],
            job_title=r["job_title"],
            applicant_name=f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or None,
            submitted_at=r["submitted_at"].isoformat(),
            days_dormant=int(r["days_dormant"] or 0),
            knockout_failed=r["knockout_failed"],
        )
        for r in rows
    ]
    return SLASummary(
        dormant_count=len(items),
        dormant_employers=int(dormant_employers or 0),
        threshold_days=_DORMANT_DAYS,
        items=items,
    )


class NudgeIn(BaseModel):
    application_id: UUID
    note: Optional[str] = None


@router.post("/nudge")
async def nudge_employer(body: NudgeIn, admin_user: CurrentUser = Depends(require_admin)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT a.id, a.employer_id, a.job_id, j.title_raw, ec.user_id AS contact_user
              FROM public.applications a
              JOIN public.jobs j ON j.id = a.job_id
         LEFT JOIN public.employer_contacts ec ON ec.employer_id = a.employer_id
             WHERE a.id = $1
          ORDER BY ec.created_at LIMIT 1
            """,
            body.application_id,
        )
        if not row or not row["contact_user"]:
            raise HTTPException(status_code=404, detail="Application or employer contact not found.")
        await notify(
            conn,
            recipient_user_id=str(row["contact_user"]),
            kind="sla_dormant_application",
            title=f"Nudge: an applicant is waiting on {row['title_raw']}",
            body=body.note or "SkillPointe admin has flagged this application as needing a review.",
            link_href=f"/employer/applications/{body.application_id}",
            payload={"application_id": str(body.application_id), "nudged_by": admin_user.user_id},
        )
    return {"ok": True}
