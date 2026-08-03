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
  POST /applicant/me/interviews/{slot_id}/decline                      — decline this one (optional reason)

Shared:
  GET  /employer/me/applications/{app_id}/slots                        — full slot history for one application
                                                                          (employer-owner or admin read-only)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.auth.dependencies import (
    require_applicant,
    require_employer_only,
    require_employer_or_admin,
)
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.skilled_pro.ics import google_calendar_link, outlook_calendar_link
from app.skilled_pro.notifications import notify
from app.util.audit import write_audit

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
    location: Optional[str] = Field(default=None, max_length=300)
    meeting_url: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _window_sane(self) -> "SlotProposal":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        # Reject slots that start in the past. Both offset-aware and naive
        # datetimes are accepted by the API, so compare in matching terms.
        now = (
            datetime.now(self.start_at.tzinfo)
            if self.start_at.tzinfo is not None
            else datetime.now()
        )
        if self.start_at < now:
            raise ValueError("start_at cannot be in the past")
        return self


class InterviewerIn(BaseModel):
    """Who runs the interview — information routing, not access control.

    Three shapes the propose panel sends:
      * omitted / all-empty  → defaults to the proposing contact ("Me")
      * contact_id set       → a teammate from employer_contacts (validated to
                               belong to the same employer)
      * name/email free-form → someone not in the system
    """
    contact_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    title: Optional[str] = Field(default=None, max_length=200)


class ProposeIn(BaseModel):
    slots: list[SlotProposal] = Field(..., min_length=1, max_length=5)
    interviewer: Optional[InterviewerIn] = None


class DeclineIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class CancelIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class SlotOut(BaseModel):
    id: UUID
    application_id: UUID
    start_at: str
    end_at: str
    status: str
    # TRUE when this slot was ever the booked (accepted) time — lets the UIs
    # tell "the booked interview was cancelled" apart from a declined proposal.
    was_accepted: bool = False
    location: Optional[str] = None
    meeting_url: Optional[str] = None
    notes: Optional[str] = None
    job_title: Optional[str] = None
    employer_name: Optional[str] = None
    applicant_name: Optional[str] = None
    interviewer_contact_id: Optional[UUID] = None
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None
    interviewer_title: Optional[str] = None


class TeamContactOut(BaseModel):
    contact_id: UUID
    email: str
    name: Optional[str] = None      # auth user's full_name when set
    title: Optional[str] = None
    role: str = "member"            # org role: owner / admin / member
    is_primary: bool = False
    is_me: bool = False


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
async def replace_availability(body: AvailabilityReplace, user: CurrentUser = Depends(require_employer_only)):
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
# Team — the assignable interviewers for "Who's running this interview?"
# ---------------------------------------------------------------------------

@emp_router.get("/team", response_model=list[TeamContactOut])
async def my_team(user: CurrentUser = Depends(require_employer_or_admin)):
    """Everyone linked to my employer via employer_contacts (multiple contacts
    per employer are supported — user_id is unique, employer_id is not).
    Admin has no employer link and gets an empty list."""
    async with get_db() as conn:
        emp = await conn.fetchrow(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1",
            user.user_id,
        )
        if not emp:
            return []
        rows = await conn.fetch(
            """
            SELECT ec.id AS contact_id, ec.title, ec.is_primary, ec.role,
                   u.email, NULLIF(u.raw_user_meta_data->>'full_name', '') AS name,
                   (ec.user_id = $2::uuid) AS is_me
              FROM public.employer_contacts ec
              JOIN auth.users u ON u.id = ec.user_id
             WHERE ec.employer_id = $1
          ORDER BY is_me DESC, ec.is_primary DESC, ec.created_at
            """,
            emp["employer_id"], user.user_id,
        )
    return [
        TeamContactOut(
            contact_id=r["contact_id"], email=r["email"] or "",
            name=_val(r, "name"),
            title=r["title"], role=_val(r, "role") or "member",
            is_primary=r["is_primary"], is_me=r["is_me"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Propose slots for an application
# ---------------------------------------------------------------------------

@emp_router.post("/applications/{application_id}/propose", response_model=list[SlotOut])
async def propose_slots(  # employer-only: admin does not schedule interviews for an employer
    application_id: UUID,
    body: ProposeIn,
    user: CurrentUser = Depends(require_employer_only),
):
    async with get_db() as conn:
        app_row = await conn.fetchrow(
            """
            SELECT a.id, a.employer_id, a.applicant_id, a.job_id, j.title_raw,
                   ap.user_id AS applicant_user_id,
                   CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name
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

        # Resolve who's running the interview (same assignee for the whole
        # batch — the applicant picks a time, not a person).
        inter = body.interviewer or InterviewerIn()
        interviewer_contact_id: Optional[UUID] = None
        interviewer_name = (inter.name or "").strip() or None
        interviewer_email = (inter.email or "").strip() or None
        interviewer_title = (inter.title or "").strip() or None
        if inter.contact_id:
            teammate = await conn.fetchrow(
                """
                SELECT ec.id, ec.title, u.email
                  FROM public.employer_contacts ec
                  JOIN auth.users u ON u.id = ec.user_id
                 WHERE ec.id = $1 AND ec.employer_id = $2
                """,
                inter.contact_id, app_row["employer_id"],
            )
            if not teammate:
                raise HTTPException(status_code=400, detail="That interviewer isn't on your team.")
            interviewer_contact_id = teammate["id"]
            interviewer_email = interviewer_email or teammate["email"]
            interviewer_title = interviewer_title or teammate["title"]
        elif not interviewer_name and not interviewer_email:
            # Default: "Me" — the proposing contact runs it.
            me = await conn.fetchrow(
                "SELECT id, title FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, app_row["employer_id"],
            )
            if me:
                interviewer_contact_id = me["id"]
                interviewer_title = me["title"]
            interviewer_email = user.email or None

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
                      (application_id, proposed_by, start_at, end_at, location, meeting_url, notes, status,
                       interviewer_contact_id, interviewer_name, interviewer_email, interviewer_title)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'proposed', $8, $9, $10, $11)
                    """,
                    application_id, user.user_id, s.start_at, s.end_at, s.location, s.meeting_url, s.notes,
                    interviewer_contact_id, interviewer_name, interviewer_email, interviewer_title,
                )

            # Move application status forward
            await conn.execute(
                "UPDATE public.applications SET status = 'interviewing'::application_status_enum, updated_at = NOW() WHERE id = $1",
                application_id,
            )

            if app_row["applicant_user_id"]:
                note_body = f"You have {len(body.slots)} time slot{'s' if len(body.slots) != 1 else ''} to pick from."
                if interviewer_name:
                    who = interviewer_name + (f", {interviewer_title}" if interviewer_title else "")
                    note_body += f" You'll meet {who}."
                await notify(
                    conn,
                    recipient_user_id=str(app_row["applicant_user_id"]),
                    kind="interview_proposed",
                    title=f"Interview times proposed for {app_row['title_raw']}",
                    body=note_body,
                    link_href=f"/applicant/applications/{application_id}",
                    payload={
                        "application_id": str(application_id),
                        "slot_count": len(body.slots),
                        **({"interviewer_name": interviewer_name} if interviewer_name else {}),
                        **({"interviewer_title": interviewer_title} if interviewer_title else {}),
                    },
                )

            # Delegated scheduling — resolve any pending "let them pick the
            # times" request for this application:
            #   * proposer IS the assignee  → fulfilled; originator notified
            #   * anyone else proposed first → cancelled as superseded;
            #     assignee told it's off their plate (no dead pending state)
            pending_req = await conn.fetchrow(
                "SELECT id, requested_by, assignee_contact_id FROM public.scheduling_requests WHERE application_id = $1 AND status = 'pending'",
                application_id,
            )
            if pending_req:
                my_contact_id = await conn.fetchval(
                    "SELECT id FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                    user.user_id, app_row["employer_id"],
                )
                proposer_name = await conn.fetchval(
                    "SELECT COALESCE(NULLIF(raw_user_meta_data->>'full_name', ''), email) FROM auth.users WHERE id = $1",
                    user.user_id,
                ) or user.email
                who = (_val(app_row, "applicant_name") or "").strip() or "the applicant"
                job_name = app_row["title_raw"] or "your job"
                is_assignee = my_contact_id is not None and str(my_contact_id) == str(
                    pending_req["assignee_contact_id"]
                )
                if is_assignee:
                    await conn.execute(
                        "UPDATE public.scheduling_requests SET status = 'fulfilled', fulfilled_at = NOW(), fulfilled_by = $2::uuid WHERE id = $1 AND status = 'pending'",
                        pending_req["id"], user.user_id,
                    )
                    if str(pending_req["requested_by"]) != str(user.user_id):
                        await notify(
                            conn,
                            recipient_user_id=str(pending_req["requested_by"]),
                            kind="scheduling_fulfilled",
                            title=f"{proposer_name} proposed {len(body.slots)} time{'s' if len(body.slots) != 1 else ''} for {who} ({job_name})",
                            body="The applicant picks one, and it locks in for both sides.",
                            link_href=f"/employer/applications/{application_id}",
                            payload={
                                "application_id": str(application_id),
                                "scheduling_request_id": str(pending_req["id"]),
                            },
                            dedupe_key=f"scheduling_fulfilled:{pending_req['id']}",
                        )
                    await write_audit(
                        conn,
                        action="scheduling_request_fulfilled",
                        actor_id=user.user_id, actor_role=user.role,
                        entity_type="scheduling_request", entity_id=str(pending_req["id"]),
                        before={"status": "pending"}, after={"status": "fulfilled"},
                    )
                else:
                    await conn.execute(
                        "UPDATE public.scheduling_requests SET status = 'cancelled', cancelled_at = NOW(), cancelled_reason = 'superseded_by_direct_proposal' WHERE id = $1 AND status = 'pending'",
                        pending_req["id"],
                    )
                    assignee_user = await conn.fetchval(
                        "SELECT user_id FROM public.employer_contacts WHERE id = $1",
                        pending_req["assignee_contact_id"],
                    )
                    if assignee_user and str(assignee_user) != str(user.user_id):
                        await notify(
                            conn,
                            recipient_user_id=str(assignee_user),
                            kind="scheduling_cancelled",
                            title=f"No need to propose times for {who} ({job_name})",
                            body=f"{proposer_name} proposed times directly, so the request is closed.",
                            link_href=f"/employer/applications/{application_id}",
                            payload={
                                "application_id": str(application_id),
                                "scheduling_request_id": str(pending_req["id"]),
                            },
                            dedupe_key=f"scheduling_cancelled:{pending_req['id']}",
                        )
                    await write_audit(
                        conn,
                        action="scheduling_request_superseded",
                        actor_id=user.user_id, actor_role=user.role,
                        entity_type="scheduling_request", entity_id=str(pending_req["id"]),
                        before={"status": "pending"}, after={"status": "cancelled"},
                    )

    return await _slots_for_application(application_id)


# ---------------------------------------------------------------------------
# Cancel a slot (employer) + the shared cancel/restore internals
# ---------------------------------------------------------------------------

# Stages an application may safely return to when its interview goes away.
_PRE_INTERVIEW_STAGES = ("submitted", "reviewed", "shortlisted")


async def cancel_open_slots(conn, application_id: UUID) -> list:
    """Cancel every proposed/accepted slot on an application.

    Shared by the employer cancel endpoint's sibling cleanup and the
    applicant withdraw-from-interviewing flow. accepted_at is left intact so
    the ICS feed keeps emitting STATUS:CANCELLED for previously confirmed
    times. Returns the cancelled rows.
    """
    return await conn.fetch(
        """
        UPDATE public.interview_slots
           SET status = 'cancelled', cancelled_at = NOW()
         WHERE application_id = $1 AND status IN ('proposed', 'accepted')
        RETURNING id, start_at, end_at, (accepted_at IS NOT NULL) AS was_accepted
        """,
        application_id,
    )


async def restore_application_stage(conn, application_id: UUID) -> Optional[str]:
    """After the last open slot on an 'interviewing' application is cancelled,
    return the application to its pre-interview stage (previous_status when it
    is a safe pre-interview stage, else 'reviewed'). Returns the restored
    stage, or None when nothing changed (open slots remain, or the
    application already moved on)."""
    remaining = await conn.fetchval(
        "SELECT COUNT(*) FROM public.interview_slots WHERE application_id = $1 AND status IN ('proposed', 'accepted')",
        application_id,
    )
    if remaining:
        return None
    row = await conn.fetchrow(
        "SELECT status::text AS status, previous_status::text AS previous_status FROM public.applications WHERE id = $1",
        application_id,
    )
    if not row or row["status"] != "interviewing":
        return None
    prev = row["previous_status"]
    target = prev if prev in _PRE_INTERVIEW_STAGES else "reviewed"
    upd = await conn.execute(
        """
        UPDATE public.applications
           SET status = $2::application_status_enum,
               previous_status = NULL,
               updated_at = NOW()
         WHERE id = $1 AND status = 'interviewing'::application_status_enum
        """,
        application_id, target,
    )
    return None if upd.endswith(" 0") else target


@emp_router.post("/interviews/{slot_id}/cancel", response_model=SlotOut)
async def cancel_slot(
    slot_id: UUID,
    body: Optional[CancelIn] = None,
    # Employer-only: cancelling an interview is an employer act; admin views
    # scheduling read-only.
    user: CurrentUser = Depends(require_employer_only),
):
    """Cancel a proposed or accepted (booked) interview slot.

    A booked interview must never wedge the application: when the last open
    slot goes away, the application returns to its pre-interview stage
    (previous_status, fallback reviewed), the applicant is notified honestly,
    the ICS feed emits STATUS:CANCELLED for the confirmed time, and the
    cancellation is audited.
    """
    reason = (body.reason or "").strip() if body and body.reason else None
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.id, s.status::text AS status, s.start_at, s.end_at,
                   s.application_id, a.employer_id,
                   ap.user_id AS applicant_user_id,
                   COALESCE(j.title_normalized, j.title_raw) AS job_title
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants ap  ON ap.id = a.applicant_id
              JOIN public.jobs j         ON j.id = a.job_id
             WHERE s.id = $1
            """,
            slot_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Slot not found.")
        owns = await conn.fetchrow(
            "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
            user.user_id, row["employer_id"],
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if row["status"] not in ("proposed", "accepted"):
            raise HTTPException(
                status_code=409,
                detail=f"This slot is already {row['status']} and cannot be cancelled.",
            )

        async with conn.transaction():
            # Race guard: only flip if the status is still what we just read.
            upd = await conn.execute(
                """
                UPDATE public.interview_slots
                   SET status = 'cancelled', cancelled_at = NOW()
                 WHERE id = $1 AND status = $2::interview_slot_status_enum
                """,
                slot_id, row["status"],
            )
            if upd.endswith(" 0"):
                raise HTTPException(status_code=409, detail="This slot changed underneath you. Refresh and try again.")

            restored = await restore_application_stage(conn, row["application_id"])

            if row["applicant_user_id"]:
                start = row["start_at"]
                job = row["job_title"] or "your job"
                if row["status"] == "accepted" and start:
                    title = f"The {start:%a %-I:%M %p} interview for {job} was cancelled"
                elif row["status"] == "accepted":
                    title = f"Your interview for {job} was cancelled"
                else:
                    title = f"A proposed interview time for {job} was withdrawn"
                note_body = "The employer cancelled this time. Your application is still active."
                if reason:
                    note_body += f' Their note: "{reason}"'
                await notify(
                    conn,
                    recipient_user_id=str(row["applicant_user_id"]),
                    kind="interview_cancelled",
                    title=title,
                    body=note_body,
                    link_href=f"/applicant/applications/{row['application_id']}",
                    payload={
                        "application_id": str(row["application_id"]),
                        "slot_id": str(slot_id),
                        **({"reason": reason} if reason else {}),
                        **({"application_restored_to": restored} if restored else {}),
                    },
                    dedupe_key=f"interview_cancelled:{slot_id}",
                )

            await write_audit(
                conn,
                action="interview_slot_cancelled",
                actor_id=user.user_id, actor_role=user.role,
                entity_type="interview_slot", entity_id=str(slot_id),
                before={"status": row["status"]},
                after={"status": "cancelled", "application_restored_to": restored},
                metadata={"reason": reason} if reason else None,
            )

        fresh = await conn.fetchrow(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, s.interviewer_contact_id, s.interviewer_name, s.interviewer_email, s.interviewer_title, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.id = $1",
            slot_id,
        )
    return _slot_row(fresh)


# ---------------------------------------------------------------------------
# Slot history for one application (employer-owner, or admin read-only)
# ---------------------------------------------------------------------------

@emp_router.get("/applications/{application_id}/slots", response_model=list[SlotOut])
async def application_slots(
    application_id: UUID,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    async with get_db() as conn:
        app_row = await conn.fetchrow(
            "SELECT employer_id FROM public.applications WHERE id = $1", application_id,
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
                   (s.accepted_at IS NOT NULL) AS was_accepted,
                   s.location, s.meeting_url, s.notes,
                   s.interviewer_contact_id, s.interviewer_name, s.interviewer_email, s.interviewer_title,
                   j.title_raw AS job_title, e.name AS employer_name, NULL::text AS applicant_name
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants ap  ON ap.id = a.applicant_id
              JOIN public.jobs j         ON j.id = a.job_id
              JOIN public.employers e    ON e.id = a.employer_id
             WHERE ap.id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))
               AND ( s.status IN ('proposed', 'accepted')
                     -- Recently cancelled bookings stay visible so the
                     -- applicant sees the cancellation state, not a silent gap.
                     OR (s.status = 'cancelled' AND s.accepted_at IS NOT NULL
                         AND s.cancelled_at > NOW() - INTERVAL '14 days') )
          ORDER BY s.start_at
            """,
            user.user_id,
            user.view_as_applicant_id,
        )
    return [_slot_row(r) for r in rows]


@app_router.post("/interviews/{slot_id}/accept", response_model=SlotOut)
async def accept_slot(slot_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.id, s.application_id, s.status::text AS status, s.start_at, s.end_at,
                   s.location, s.meeting_url, s.notes,
                   s.interviewer_name, s.interviewer_title,
                   a.employer_id, a.job_id,
                   ap.user_id AS applicant_user_id,
                   CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name,
                   COALESCE(j.title_normalized, j.title_raw) AS job_title,
                   e.name AS employer_name,
                   ec.user_id AS employer_contact_user
              FROM public.interview_slots s
              JOIN public.applications a ON a.id = s.application_id
              JOIN public.applicants  ap ON ap.id = a.applicant_id
              JOIN public.jobs j         ON j.id = a.job_id
              JOIN public.employers e    ON e.id = a.employer_id
         LEFT JOIN public.employer_contacts ec ON ec.employer_id = a.employer_id
             WHERE s.id = $1
             ORDER BY ec.created_at LIMIT 1
            """,
            slot_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if str(row["applicant_user_id"]) != user.user_id:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if row["status"] != "proposed":
            raise HTTPException(status_code=409, detail=f"Slot is {row['status']} and can't be accepted.")

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
            # Interviewer line + add-to-calendar deep links ride in both
            # confirmation payloads, so the tray (and the future email worker)
            # can render "Add to calendar" without another round-trip.
            run_by = (_val(row, "interviewer_name") or "").strip()
            run_by_title = _val(row, "interviewer_title")
            interviewer_bits = {}
            if run_by:
                interviewer_bits = {
                    "interviewer_name": run_by,
                    **({"interviewer_title": run_by_title} if run_by_title else {}),
                }

            start_at, end_at = row["start_at"], _val(row, "end_at")
            location = _val(row, "location") or ""

            def _calendar_payload(summary: str, description: str) -> dict:
                if not (start_at and end_at):
                    return {}
                return {
                    "calendar_links": {
                        "google": google_calendar_link(
                            summary, start_at, end_at,
                            description=description, location=location,
                        ),
                        "outlook": outlook_calendar_link(
                            summary, start_at, end_at,
                            description=description, location=location,
                        ),
                        "outlook_office": outlook_calendar_link(
                            summary, start_at, end_at,
                            description=description, location=location, work=True,
                        ),
                    }
                }

            run_by_line = ""
            if run_by:
                run_by_line = f" Run by {run_by}" + (f" ({run_by_title})" if run_by_title else "") + "."

            if row["employer_contact_user"]:
                # Content template: who + when + which job, so the tray line is
                # actionable on its own ("Jane Smith confirmed Tue 10:00 AM — Welder").
                who = (row["applicant_name"] or "").strip() or "The applicant"
                start = row["start_at"]
                when = f"{start:%a %b %-d, %-I:%M %p} ({start.tzname() or 'UTC'})" if start else "the proposed time"
                emp_summary = f"Interview: {who} ({row['job_title'] or 'your job'})"
                emp_desc = f"Interview with {who}.{run_by_line}"
                await notify(
                    conn,
                    recipient_user_id=str(row["employer_contact_user"]),
                    kind="interview_accepted",
                    title=f"{who} confirmed {when} for {row['job_title'] or 'your job'}",
                    body="The other proposed times were released automatically." + run_by_line,
                    link_href=f"/employer/applications/{row['application_id']}",
                    payload={
                        "application_id": str(row['application_id']), "slot_id": str(slot_id),
                        **interviewer_bits,
                        **_calendar_payload(emp_summary, emp_desc),
                    },
                    dedupe_key=f"interview_accepted:{slot_id}",
                )

            # Applicant-side confirmation — their booked time with the same
            # calendar links (spec: confirmation notifications on both sides).
            employer_name = _val(row, "employer_name")
            app_summary = f"Interview: {row['job_title'] or 'Job'}" + (
                f" at {employer_name}" if employer_name else ""
            )
            app_desc = (f"Interview with {employer_name}." if employer_name else "Interview.") + run_by_line
            await notify(
                conn,
                recipient_user_id=str(row["applicant_user_id"]),
                kind="interview_accepted",
                title=f"Interview booked for {row['job_title'] or 'your job'}",
                body=("You'll meet " + run_by + (f", {run_by_title}" if run_by_title else "") + "."
                      if run_by else "Your interview time is confirmed."),
                link_href=f"/applicant/applications/{row['application_id']}",
                payload={
                    "application_id": str(row['application_id']), "slot_id": str(slot_id),
                    **interviewer_bits,
                    **_calendar_payload(app_summary, app_desc),
                },
                dedupe_key=f"interview_accepted_applicant:{slot_id}",
            )

        # Still inside the connection context — fetch the fresh row before release.
        fresh = await conn.fetchrow(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, s.interviewer_contact_id, s.interviewer_name, s.interviewer_email, s.interviewer_title, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.id = $1",
            slot_id,
        )
    return _slot_row(fresh)


@app_router.post("/interviews/{slot_id}/decline", response_model=SlotOut)
async def decline_slot(
    slot_id: UUID,
    body: Optional[DeclineIn] = None,
    user: CurrentUser = Depends(require_applicant),
):
    reason = (body.reason or "").strip() if body and body.reason else None
    async with get_db() as conn:
        applicant_user = await conn.fetchrow(
            "SELECT ap.user_id, s.status::text AS status, s.application_id FROM public.applicants ap JOIN public.applications a ON a.applicant_id = ap.id JOIN public.interview_slots s ON s.application_id = a.id WHERE s.id = $1",
            slot_id,
        )
        if not applicant_user or str(applicant_user["user_id"]) != user.user_id:
            raise HTTPException(status_code=404, detail="Slot not found.")
        if applicant_user["status"] != "proposed":
            raise HTTPException(status_code=409, detail=f"Slot is {applicant_user['status']} and can't be declined.")
        await conn.execute("UPDATE public.interview_slots SET status = 'declined', declined_at = NOW() WHERE id = $1", slot_id)

        # Notify the employer only when the LAST proposed slot is declined —
        # a full decline of the batch. Declining one of several stays quiet
        # (the employer sees the state on the application page), so the
        # applicant's "none of these work" flow produces exactly one
        # notification instead of one per slot.
        application_id = applicant_user["application_id"]
        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM public.interview_slots WHERE application_id = $1 AND status = 'proposed'",
            application_id,
        )
        if not remaining:
            emp_contact = await conn.fetchrow(
                """
                SELECT ec.user_id,
                       COALESCE(j.title_normalized, j.title_raw) AS job_title,
                       CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name
                  FROM public.applications a
                  JOIN public.jobs j ON j.id = a.job_id
                  JOIN public.applicants ap ON ap.id = a.applicant_id
             LEFT JOIN public.employer_contacts ec ON ec.employer_id = a.employer_id
                 WHERE a.id = $1
                 ORDER BY ec.created_at LIMIT 1
                """,
                application_id,
            )
            if emp_contact and emp_contact["user_id"]:
                # Content template: who + which job in the title; the
                # applicant's own words go in a labeled detail line.
                who = (emp_contact["applicant_name"] or "").strip() or "The applicant"
                note_body = "None of the proposed times worked. Propose a new set when you're ready."
                if reason:
                    note_body += f' Their note: "{reason}"'
                await notify(
                    conn,
                    recipient_user_id=str(emp_contact["user_id"]),
                    kind="interview_declined",
                    title=f"{who} declined the interview times for {emp_contact['job_title']}",
                    body=note_body,
                    link_href=f"/employer/applications/{application_id}",
                    payload={
                        "application_id": str(application_id),
                        "slot_id": str(slot_id),
                        **({"reason": reason} if reason else {}),
                    },
                    dedupe_key=f"interview_declined:{application_id}",
                )

        fresh = await conn.fetchrow(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, s.location, s.meeting_url, s.notes, s.interviewer_contact_id, s.interviewer_name, s.interviewer_email, s.interviewer_title, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.id = $1",
            slot_id,
        )
    return _slot_row(fresh)


# ---------------------------------------------------------------------------
async def _slots_for_application(application_id: UUID) -> list[SlotOut]:
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT s.id, s.application_id, s.start_at, s.end_at, s.status::text AS status, (s.accepted_at IS NOT NULL) AS was_accepted, s.location, s.meeting_url, s.notes, s.interviewer_contact_id, s.interviewer_name, s.interviewer_email, s.interviewer_title, NULL::text AS job_title, NULL::text AS employer_name, NULL::text AS applicant_name FROM public.interview_slots s WHERE s.application_id = $1 ORDER BY s.start_at",
            application_id,
        )
    return [_slot_row(r) for r in rows]


def _val(r, key):
    """Row accessor tolerant of both asyncpg Records and plain dicts that may
    omit optional columns (older callers/tests)."""
    try:
        return r[key]
    except (KeyError, IndexError):
        return None


def _slot_row(r) -> SlotOut:
    return SlotOut(
        id=r["id"],
        application_id=r["application_id"],
        start_at=r["start_at"].isoformat(),
        end_at=r["end_at"].isoformat(),
        status=r["status"],
        was_accepted=bool(_val(r, "was_accepted")),
        location=r["location"],
        meeting_url=r["meeting_url"],
        notes=r["notes"],
        job_title=_val(r, "job_title"),
        employer_name=_val(r, "employer_name"),
        applicant_name=_val(r, "applicant_name"),
        interviewer_contact_id=_val(r, "interviewer_contact_id"),
        interviewer_name=_val(r, "interviewer_name"),
        interviewer_email=_val(r, "interviewer_email"),
        interviewer_title=_val(r, "interviewer_title"),
    )
