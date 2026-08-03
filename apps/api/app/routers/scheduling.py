"""
Delegated interview scheduling — "let them pick the times."

When the person running the interview is a teammate, the proposing employer
can hand slot-picking to them instead of painting a grid on their behalf.
That creates a scheduling request; the teammate gets an in-app notification
plus a deep-link email, opens the same propose flow, and sends times — the
applicant flow proceeds exactly as a normal proposal.

  POST /employer/me/applications/{app_id}/scheduling-request   — create (delegate)
  GET  /employer/me/applications/{app_id}/scheduling-request   — pending one (or null)
  GET  /employer/me/scheduling-requests                        — my inbox + sent
  POST /employer/me/scheduling-requests/{id}/cancel            — originator/owner/admin

Fulfilment happens in the propose endpoint (app/routers/interviews.py): when
the assignee proposes times, the pending request flips to 'fulfilled' and the
originator is notified; when anyone else on the team proposes first, the
request is cancelled as superseded and the assignee is told it's no longer
needed. One pending request per application (DB-enforced).
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import require_employer_only
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.skilled_pro.email_templates import branded_email
from app.skilled_pro.notifications import notify
from app.skilled_pro.senders import send_email
from app.util.audit import write_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employer/me", tags=["employer"])

# Org roles that may cancel a request they didn't create.
MANAGER_ROLES = ("owner", "admin")


# ---------------------------------------------------------------------------
class SchedulingRequestCreateIn(BaseModel):
    assignee_contact_id: UUID
    note: Optional[str] = Field(default=None, max_length=2000)


class SchedulingRequestOut(BaseModel):
    id: UUID
    application_id: UUID
    status: str
    note: Optional[str] = None
    created_at: str
    assignee_contact_id: UUID
    assignee_name: Optional[str] = None
    assignee_email: Optional[str] = None
    requested_by_me: bool = False
    assigned_to_me: bool = False
    requester_name: Optional[str] = None
    applicant_name: Optional[str] = None
    job_title: Optional[str] = None


class SchedulingInboxOut(BaseModel):
    # Requests waiting on ME to propose times.
    assigned_to_me: list[SchedulingRequestOut]
    # Requests I created that are still waiting on someone else.
    waiting_on_others: list[SchedulingRequestOut]


# ---------------------------------------------------------------------------
_REQUEST_SELECT = """
    SELECT sr.id, sr.application_id, sr.status, sr.note, sr.created_at,
           sr.assignee_contact_id, sr.requested_by,
           au.email AS assignee_email,
           COALESCE(NULLIF(au.raw_user_meta_data->>'full_name', ''), au.email) AS assignee_name,
           COALESCE(NULLIF(ru.raw_user_meta_data->>'full_name', ''), ru.email) AS requester_name,
           CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name,
           COALESCE(j.title_normalized, j.title_raw) AS job_title
      FROM public.scheduling_requests sr
      JOIN public.employer_contacts ac ON ac.id = sr.assignee_contact_id
      JOIN auth.users au ON au.id = ac.user_id
 LEFT JOIN auth.users ru ON ru.id = sr.requested_by
      JOIN public.applications a ON a.id = sr.application_id
      JOIN public.applicants ap ON ap.id = a.applicant_id
      JOIN public.jobs j ON j.id = a.job_id
"""


def _row_out(r, *, my_user_id: str, my_contact_id: Optional[str]) -> SchedulingRequestOut:
    return SchedulingRequestOut(
        id=r["id"],
        application_id=r["application_id"],
        status=r["status"],
        note=r["note"],
        created_at=r["created_at"].isoformat(),
        assignee_contact_id=r["assignee_contact_id"],
        assignee_name=r["assignee_name"],
        assignee_email=r["assignee_email"],
        requested_by_me=str(r["requested_by"]) == str(my_user_id),
        assigned_to_me=my_contact_id is not None
        and str(r["assignee_contact_id"]) == str(my_contact_id),
        requester_name=r["requester_name"],
        applicant_name=(r["applicant_name"] or "").strip() or None,
        job_title=r["job_title"],
    )


async def _my_contact(conn, user: CurrentUser):
    row = await conn.fetchrow(
        "SELECT id, employer_id, role FROM public.employer_contacts WHERE user_id = $1",
        user.user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employer profile not found.")
    return row


# ---------------------------------------------------------------------------
@router.post(
    "/applications/{application_id}/scheduling-request",
    response_model=SchedulingRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduling_request(
    application_id: UUID,
    body: SchedulingRequestCreateIn,
    user: CurrentUser = Depends(require_employer_only),
):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        app_row = await conn.fetchrow(
            """
            SELECT a.id, a.employer_id,
                   CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name,
                   COALESCE(j.title_normalized, j.title_raw) AS job_title
              FROM public.applications a
              JOIN public.applicants ap ON ap.id = a.applicant_id
              JOIN public.jobs j ON j.id = a.job_id
             WHERE a.id = $1
            """,
            application_id,
        )
        if not app_row or str(app_row["employer_id"]) != str(me["employer_id"]):
            raise HTTPException(status_code=404, detail="Application not found.")

        assignee = await conn.fetchrow(
            """
            SELECT ec.id, ec.user_id, u.email,
                   COALESCE(NULLIF(u.raw_user_meta_data->>'full_name', ''), u.email) AS name
              FROM public.employer_contacts ec
              JOIN auth.users u ON u.id = ec.user_id
             WHERE ec.id = $1 AND ec.employer_id = $2
            """,
            body.assignee_contact_id, me["employer_id"],
        )
        if not assignee:
            raise HTTPException(status_code=400, detail="That person isn't on your team.")
        if str(assignee["id"]) == str(me["id"]):
            raise HTTPException(
                status_code=400,
                detail="That's you — just propose the times directly.",
            )

        existing = await conn.fetchval(
            "SELECT 1 FROM public.scheduling_requests WHERE application_id = $1 AND status = 'pending'",
            application_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Someone is already lined up to propose times for this application. Cancel that request first.",
            )

        note = (body.note or "").strip() or None
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO public.scheduling_requests
                  (application_id, employer_id, requested_by, assignee_contact_id, note)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, created_at
                """,
                application_id, me["employer_id"], user.user_id, assignee["id"], note,
            )
            requester_name = await conn.fetchval(
                "SELECT COALESCE(NULLIF(raw_user_meta_data->>'full_name', ''), email) FROM auth.users WHERE id = $1",
                user.user_id,
            ) or user.email
            applicant_name = (app_row["applicant_name"] or "").strip() or "the applicant"
            await notify(
                conn,
                recipient_user_id=str(assignee["user_id"]),
                kind="scheduling_requested",
                title=f"Propose interview times for {applicant_name} ({app_row['job_title']})",
                body=f"{requester_name} asked you to pick the times — you're running this interview."
                + (f' Note: "{note}"' if note else ""),
                link_href=f"/employer/applications/{application_id}",
                payload={
                    "application_id": str(application_id),
                    "scheduling_request_id": str(row["id"]),
                },
                dedupe_key=f"scheduling_requested:{row['id']}",
            )
            await write_audit(
                conn,
                action="scheduling_request_created",
                actor_id=user.user_id, actor_role=user.role,
                entity_type="scheduling_request", entity_id=str(row["id"]),
                after={
                    "application_id": str(application_id),
                    "assignee_contact_id": str(assignee["id"]),
                },
            )

    # Deep-link email to the assignee (out-of-band; best-effort, never blocks).
    url = f"{get_settings().web_origin}/employer/applications/{application_id}"
    html, text = branded_email(
        preheader=f"{requester_name} asked you to propose interview times.",
        heading=f"Propose times for {applicant_name}",
        paragraphs=[
            f"{requester_name} lined you up to run the interview with "
            f"{applicant_name} for the {app_row['job_title']} role — and asked "
            "you to pick the times, since it's your calendar.",
            "Open the application, choose 3-5 times that work for you, and "
            "the applicant picks one.",
        ]
        + ([f'Note from {requester_name}: "{note}"'] if note else []),
        cta_label="Propose interview times",
        cta_url=url,
        footer_note="You're getting this because you're on the hiring team for this role.",
    )
    result = await send_email(
        assignee["email"],
        f"Propose times for {applicant_name} ({app_row['job_title']})",
        text,
        html=html,
    )
    if not result.delivered:
        logger.warning(
            "Scheduling-request email to %s not delivered: %s", assignee["email"], result.detail
        )

    return await get_scheduling_request_for_application(application_id, user)  # type: ignore[return-value]


@router.get(
    "/applications/{application_id}/scheduling-request",
    response_model=Optional[SchedulingRequestOut],
)
async def get_scheduling_request_for_application(
    application_id: UUID,
    user: CurrentUser = Depends(require_employer_only),
):
    """The pending request for this application, or null."""
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        row = await conn.fetchrow(
            _REQUEST_SELECT + " WHERE sr.application_id = $1 AND sr.employer_id = $2 AND sr.status = 'pending'",
            application_id, me["employer_id"],
        )
    if not row:
        return None
    return _row_out(row, my_user_id=user.user_id, my_contact_id=str(me["id"]))


@router.get("/scheduling-requests", response_model=SchedulingInboxOut)
async def list_scheduling_requests(user: CurrentUser = Depends(require_employer_only)):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        rows = await conn.fetch(
            _REQUEST_SELECT
            + """
             WHERE sr.employer_id = $1 AND sr.status = 'pending'
          ORDER BY sr.created_at
            """,
            me["employer_id"],
        )
    mine = str(me["id"])
    out = [_row_out(r, my_user_id=user.user_id, my_contact_id=mine) for r in rows]
    return SchedulingInboxOut(
        assigned_to_me=[r for r in out if r.assigned_to_me],
        waiting_on_others=[r for r in out if r.requested_by_me and not r.assigned_to_me],
    )


@router.post("/scheduling-requests/{request_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scheduling_request(
    request_id: UUID,
    user: CurrentUser = Depends(require_employer_only),
):
    async with get_db() as conn:
        me = await _my_contact(conn, user)
        row = await conn.fetchrow(
            _REQUEST_SELECT + " WHERE sr.id = $1 AND sr.employer_id = $2",
            request_id, me["employer_id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Scheduling request not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"This request is already {row['status']}.")
        is_originator = str(row["requested_by"]) == str(user.user_id)
        if not is_originator and me["role"] not in MANAGER_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Only the person who created this request (or an owner/admin) can cancel it.",
            )

        async with conn.transaction():
            upd = await conn.execute(
                """
                UPDATE public.scheduling_requests
                   SET status = 'cancelled', cancelled_at = NOW(), cancelled_reason = 'cancelled_by_team'
                 WHERE id = $1 AND status = 'pending'
                """,
                request_id,
            )
            if upd.endswith(" 0"):
                raise HTTPException(status_code=409, detail="This request changed underneath you. Refresh and try again.")

            # Tell the assignee it's off their plate (unless they cancelled it
            # themselves via an admin role).
            assignee_user = await conn.fetchval(
                "SELECT user_id FROM public.employer_contacts WHERE id = $1",
                row["assignee_contact_id"],
            )
            if assignee_user and str(assignee_user) != str(user.user_id):
                who = (row["applicant_name"] or "").strip() or "the applicant"
                await notify(
                    conn,
                    recipient_user_id=str(assignee_user),
                    kind="scheduling_cancelled",
                    title=f"No need to propose times for {who} ({row['job_title']})",
                    body="The scheduling request was cancelled.",
                    link_href=f"/employer/applications/{row['application_id']}",
                    payload={"application_id": str(row["application_id"]), "scheduling_request_id": str(request_id)},
                    dedupe_key=f"scheduling_cancelled:{request_id}",
                )
            await write_audit(
                conn,
                action="scheduling_request_cancelled",
                actor_id=user.user_id, actor_role=user.role,
                entity_type="scheduling_request", entity_id=str(request_id),
                before={"status": "pending"},
                after={"status": "cancelled"},
            )
