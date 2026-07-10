"""
Public employer profile — accessible by any signed-in user.
Applicants see this before applying; employers can preview their own page.

GET /employers/{employer_id}/public
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db import get_db

router = APIRouter(prefix="/employers", tags=["employers"])


class EmployerPublicJob(BaseModel):
    id: UUID
    title: str
    city: Optional[str] = None
    state: Optional[str] = None
    work_setting: Optional[str] = None


class EmployerPublic(BaseModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    description: Optional[str] = None
    verified_worker_count: int = 0
    open_job_count: int = 0
    jobs: list[EmployerPublicJob] = []


@router.get("/{employer_id}/public", response_model=EmployerPublic)
async def get_employer_public(employer_id: UUID, _: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        emp = await conn.fetchrow(
            """
            SELECT id, name, industry, website, city, state, description
              FROM public.employers WHERE id = $1
            """,
            employer_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employer not found.")

        # Verified worker count — applicants who have a hired application at this employer
        # and at least one verified credential.
        verified_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT a.id)
              FROM public.applications ap
              JOIN public.applicants a ON a.id = ap.applicant_id
             WHERE ap.employer_id = $1
               AND ap.status = 'hired'
               AND EXISTS (
                 SELECT 1 FROM public.credentials c
                  WHERE c.applicant_id = a.id AND c.verification_level >= 1
               )
            """,
            employer_id,
        ) or 0

        jobs = await conn.fetch(
            """
            SELECT id, title_raw, city, state, work_setting::text AS work_setting
              FROM public.jobs
             WHERE employer_id = $1
          ORDER BY created_at DESC
             LIMIT 12
            """,
            employer_id,
        )

    return EmployerPublic(
        id=emp["id"],
        name=emp["name"],
        industry=emp["industry"],
        website=emp["website"],
        city=emp["city"],
        state=emp["state"],
        description=emp["description"],
        verified_worker_count=int(verified_count),
        open_job_count=len(jobs),
        jobs=[EmployerPublicJob(
            id=r["id"], title=r["title_raw"], city=r["city"], state=r["state"], work_setting=r["work_setting"],
        ) for r in jobs],
    )
