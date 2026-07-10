"""
Interview scheduling — the Calendly-style slot picker.

Employer flow:
  GET  /employer/me/availability                                       — my recurring weekly windows
  PUT  /employer/me/availability                                       — replace
  POST /employer/me/applications/{app_id}/propose                      — propose 3-5 time slots
  POST /employer/me/interviews/{slot_id}/cancel                        — cancel a proposed/accepted slot

Applicant flow:
  GET  /applicant/me/interviews                                        — all proposals + accepted
  POST /applicant/me/interviews/{slot_id}/accept                       — pick this one (auto-declines siblings)
  POST /applicant/me/interviews/{slot_id}/decline                      — decline this one
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_applicant, require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.skilled_pro.notifications import notify

logger = logging.getLogger(__name__)

emp_router = APIRouter(prefix="/employer/me", tags=["employer"])
app_router = APIRouter(prefix="/applicant/me", tags=["applicant"])


# ---------------------------------------------------------------------------
class AvailabilityWindow(BaseModel):
    weekday: int = Field(..., ge=0, le=6)     # 0=Sun
    start_time: str                            # "09:00"
    end_time: str                              # "17:00"
    timezone: str = "America/New_York"


class AvailabilityReplace(BaseModel):
    windows: list[AvailabilityWindow]


class SlotProposal(BaseModel):
    start_at: datetime
    end_at: datetime
    location: Optional[str] = None
    meeting_url: Optional[str] = None
    notes: Optional[str] = None


class ProposeIn(BaseModel):
    slots: list[SlotProposal] = Field(..., min_length=1, max_length=5)


class SlotOut(BaseModel):
    id: UUID
    application_id: UUID
    start_at: str
    end_at: str
    status: str
    location: Optional[str] = None
    meeting_url: Optional[str] = None
    notes: Optional[str] = None
    job_title: Optional[str] = None
    employer_name: Optional[str] = None
    applicant_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@emp_router.get("/availability", response_model=list[AvailabilityWindow])
async def get_availability(user: CurrentUser = Depends(require_employer_or_admin)):
    async with get_db() as conn:
        emp = await conn.fetchrow("SELECT employer_id FROM public.employer_contacts WHERE user_id = $1", user.user_id)
        if not emp:
            return []
        rows = await conn.fetch(
            "SELECT weekday, start_time::text AS start_time, end_time::text AS end_time, timezone FROM public.interview_availability WHERE employer_id = $1 AND active ORDER BY weekday, start_time",
            emp["employer_id"],
        )
    return [AvailabilityWindow(**dict(r)) for r in rows]


@emp_router.put("/availability", response_model=list[AvailabilityWindow])
async def replace_availability(body: AvailabilityReplace, user: CurrentUser = Depends(require_employer_or_admin)):
    async with get_db() as conn:
        emp = await conn.fetchrow("SELECT employer_id FROM public.employer_contacts WHERE user_id = $1", user.user_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employer profile not found.")
        async with conn.transaction():
            await conn.execute("DELETE FROM public.interview_availability WHERE employer_id = $1", emp["employer_id"])
            for w in body.windows:
                await conn.execute(
                    "INSERT INTO public.interview_availability (employer_id, weekday, start_time, end_time, timezone) VALUES ($1, $2, $3::time, $4::time, $5) ON CONFLICT DO NOTHING",
                    emp["employer_id"], w.weekday, w.start_time, w.end_time, w.timezone,
                )
    return await get_availability(user=user)


# ---------------------------------------------------------------------------
# Propose slots for an application
# ---------------------------------------------------------------------------

@emp_router.post("/applications/{application_id}/propose", response_model=list[SlotOut])
async def propose_slots(
    application_id: UUID,
    body: ProposeIn,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    async with get_db() as conn:
        app_row = await conn.fetchrow(
            """
            SELECT a.id, a.employer_id, a.applicant_id, a.job_id, j.title_raw,
                   ap.user_id AS applicant_user_id
              FROM public.applications a
              JOIN public.jobs j ON j.id = a.job_id
              JOIN public.applicants ap ON ap.id = a.applicant_id
             WHERE a.id = $1
            """,
            application_id,
        )
        if not app_row:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user.role != "admin":
            owns = await conn.fetchrow(
                "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, app_row["employer_id"],
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Application not found.")

        for s in body.slots:
            if s.end_at <= s.start_at:
                raise HTTPException(status_code=400, detail="Each slot's end must be after its start.")

        # Wipe any prior proposed-but-unaccepted slots for this application, then insert fresh.
        async with conn.transaction():
            await conn.execute(
                "UPDATE public.interview_slots SET status = 'cancelled', cancelled_at = NOW() WHERE application_id = $1 AND status = 'proposed'",
                application_id,
            )
            for s in body.slots:
                await conn.execute(
                    """
                    INSERT INTO public.interview_slots
                      (application_id, proposed_by, start_at, end_at, location, meeting_url, notes, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'proposed')
                    """,
                    application_id, user.user_id, s.start_at, s.end_at, s.location, s.meeting_url, s.notes,
                )

            # Move application status forward
            await conn.execute(
                "UPDATE public.applications SET status = 'interviewing'::application_status_enum, updated_at = NOW() WHERE id = $1",
                application_id,
            )

            if app_row["applicant_user_id"]:
                await notify(
                    conn,
                    recipient_user_id=str(app_row["applicant_user_id"]),
                    kind="interview_proposed",
                    title=f"Interview times proposed for {app_row['title_raw']}",
                    body=f"You have {len(body.slots)} time slot{'s' if len(body.slots) != 1 else ''} to pick from.",
                    link_href=f"/applicant/applications/{application_id}",
                    payload={"application_id": str(application_id), "slot_count": len(body.slots)},
                )

    return await _slots_for_application(application_id)


# ---------------------------------------------------------------------------
# Applicant: view + accept
# ---------------------------------------------------------------------------

@app_router.get("/interviews", response_model=list[SlotOut])
async def list_my_interviews(user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status,
                   s.location, s.meeting_url, s.notes,
                   j.title_raw AS job_title, e.name AS employer_name, NULL::text AS applicant_name
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants ap  ON ap.id = a.applicant_id
              JOIN public.jobs j         ON j.id = a.job_id
              JOIN public.employers e    ON e.id = a.employer_id
             WHERE ap.user_id = $1
               AND s.status IN ('proposed', 'accepted')
          ORDER BY s.start_at
            """,
            user.user_id,
        )
    return [_slot_row(r) for r in rows]


@app_router.post("/interviews/{slot_id}/accept", response_model=SlotOut)
async def accept_slot(slot_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.id, s.application_id, s.status::text AS status,
                   a.employer_id, a.job_id,
                   ap.user_id AS applicant_user_id,
                   ec.user_id AS employer_contact_user
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants  ap ON ap.id = a.applicant_id
         LEFT JOIN public.employer_contacts ec ON ec.employer_id = a.employer_id
             WHERE s.id = $1
             ORDER BY ec.created_at LIMIT 1
            """,
            slot_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Slot not found.")
        applicant_user = await conn.fetchrow(
            "SELECT user_id FROM public.applicants a JOIN public.applications ap ON ap.applicant_id = a.id JOIN public.interview_slots s ON s.application_id = ap.id WHERE s.id = $1",
            slot_id,
        )
        if not applicant_user or str(applicant_user["user_id"]) != user.user_id:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if row["status"] != "proposed":
            raise HTTPException(status_code=409, detail=f"Slot is {row['status']} — cannot accept.")

        async with conn.transaction():
            await conn.execute(
                "UPDATE public.interview_slots SET status = 'accepted', accepted_at = NOW() WHERE id = $1",
                slot_id,
            )
            # Auto-decline siblings for the same application
            await conn.execute(
                "UPDATE public.interview_slots SET status = 'declined', declined_at = NOW() WHERE application_id = $1 AND id != $2 AND status = 'proposed'",
                row["application_id"], slot_id,
            )
            if row["employer_contact_user"]:
                await notify(
                    conn,
                    recipient_user_id=str(row["employer_contact_user"]),
                    kind="interview_accepted",
                    title="Interview time confirmed",
                    body="The applicant accepted one of your proposed times.",
                    link_href=f"/employer/applications/{row['application_id']}",
                    payload={"application_id": str(row['application_id']), "slot_id": str(slot_id)},
                )

    fresh = await conn.fetchrow(
        "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.id = $1",
        slot_id,
    )
    return _slot_row(fresh)


@app_router.post("/interviews/{slot_id}/decline", response_model=SlotOut)
async def decline_slot(slot_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        applicant_user = await conn.fetchrow(
            "SELECT ap.user_id, s.status::text AS status FROM public.applicants ap JOIN public.applications a ON a.applicant_id = ap.id JOIN public.interview_slots s ON s.application_id = a.id WHERE s.id = $1",
            slot_id,
        )
        if not applicant_user or str(applicant_user["user_id"]) != user.user_id:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if applicant_user["status"] != "proposed":
            raise HTTPException(status_code=409, detail=f"Slot is {applicant_user['status']} — cannot decline.")
        await conn.execute("UPDATE public.interview_slots SET status = 'declined', declined_at = NOW() WHERE id = $1", slot_id)
        fresh = await conn.fetchrow(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.id = $1",
            slot_id,
        )
    return _slot_row(fresh)


# ---------------------------------------------------------------------------
async def _slots_for_application(application_id: UUID) -> list[SlotOut]:
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.application_id = $1 ORDER BY s.start_at",
            application_id,
        )
    return [_slot_row(r) for r in rows]


def _slot_row(r) -> SlotOut:
    return SlotOut(
        id=r["id"],
        application_id=r["application_id"],
        start_at=r["start_at"].isoformat(),
        end_at=r["end_at"].isoformat(),
        status=r["status"],
        location=r["location"],
        meeting_url=r["meeting_url"],
        notes=r["notes"],
        job_title=r.get("job_title") if hasattr(r, "get") else r["job_title"],
        employer_name=r.get("employer_name") if hasattr(r, "get") else r["employer_name"],
        applicant_name=r.get("applicant_name") if hasattr(r, "get") else r["applicant_name"],
    )
