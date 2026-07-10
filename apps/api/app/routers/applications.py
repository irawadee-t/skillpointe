"""
In-platform applications + screening questions.

Applicant-facing:
  GET  /applicant/me/jobs/{job_id}/screening      — Qs to answer before applying
  POST /applicant/me/jobs/{job_id}/apply          — submit (screening + cover note)
  GET  /applicant/me/applications                 — my apps
  GET  /applicant/me/applications/{id}            — with interview slots
  POST /applicant/me/applications/{id}/withdraw

Employer-facing:
  GET   /employer/me/jobs/{job_id}/screening      — configured Qs
  PUT   /employer/me/jobs/{job_id}/screening      — replace whole set (bulk)
  GET   /employer/me/applications                 — pipeline across jobs
  GET   /employer/me/jobs/{job_id}/applications
  GET   /employer/me/applications/{id}            — detail (marks viewed_at)
  PATCH /employer/me/applications/{id}            — status changes + notes
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_applicant, require_employer_or_admin, get_current_user
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.skilled_pro.notifications import notify
from app.util.crypto import decrypt_str, encrypt_str

# Ciphertext version tag we write today. See util/crypto.py for rotation notes.
_SCREENING_CIPHERTEXT_V = 1

logger = logging.getLogger(__name__)

applicant_router = APIRouter(prefix="/applicant/me", tags=["applicant"])
employer_router  = APIRouter(prefix="/employer/me",  tags=["employer"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ScreeningQuestion(BaseModel):
    id: Optional[UUID] = None
    position: int = 0
    kind: str                              # 'yes_no' | 'multiple_choice' | 'short_text'
    prompt: str = Field(..., min_length=3, max_length=280)
    options: list[str] = Field(default_factory=list)
    required_answer: Optional[str] = None
    is_knockout: bool = True


class ScreeningAnswer(BaseModel):
    question_id: UUID
    answer: str


class ApplyIn(BaseModel):
    answers: list[ScreeningAnswer] = Field(default_factory=list)
    cover_note: Optional[str] = Field(default=None, max_length=2000)


class ApplicationOut(BaseModel):
    id: UUID
    job_id: UUID
    job_title: str
    employer_id: UUID
    employer_name: Optional[str] = None
    applicant_id: UUID
    applicant_name: Optional[str] = None
    status: str
    knockout_failed: bool
    cover_note: Optional[str] = None
    submitted_at: str
    employer_viewed_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    decision_at: Optional[str] = None
    days_since_submitted: int
    resume_snapshot: dict = Field(default_factory=dict)
    screening_answers: list[dict] = Field(default_factory=list)


class ApplicationPatchIn(BaseModel):
    status: Optional[str] = None
    decision_note: Optional[str] = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Applicant: screening questions for a job
# ---------------------------------------------------------------------------

@applicant_router.get("/jobs/{job_id}/screening", response_model=list[ScreeningQuestion])
async def get_job_screening(job_id: UUID, _: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, position, kind::text, prompt, options, required_answer, is_knockout
              FROM public.job_screening_questions
             WHERE job_id = $1
          ORDER BY position, created_at
            """,
            job_id,
        )
    return [ScreeningQuestion(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Applicant: apply to a job
# ---------------------------------------------------------------------------

@applicant_router.post("/jobs/{job_id}/apply", response_model=ApplicationOut)
async def apply_to_job(
    job_id: UUID,
    body: ApplyIn,
    user: CurrentUser = Depends(require_applicant),
):
    async with get_db() as conn:
        # Applicant profile snapshot
        applicant = await conn.fetchrow(
            """
            SELECT id, first_name, last_name, phone, email, city, state,
                   program_name_raw, career_goals_raw, experience_raw, bio_raw
              FROM public.applicants
             WHERE user_id = $1
            """,
            user.user_id,
        )
        if not applicant:
            raise HTTPException(status_code=404, detail="Applicant profile not found.")

        job = await conn.fetchrow(
            """
            SELECT id, title_raw, employer_id
              FROM public.jobs
             WHERE id = $1
            """,
            job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        # Duplicate check
        existing = await conn.fetchrow(
            "SELECT id, status::text AS status FROM public.applications WHERE applicant_id = $1 AND job_id = $2",
            applicant["id"], job_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"You've already applied to this job (status: {existing['status']}).",
            )

        # Screening evaluation
        questions = await conn.fetch(
            "SELECT id, kind::text, prompt, required_answer, is_knockout FROM public.job_screening_questions WHERE job_id = $1",
            job_id,
        )
        q_by_id = {q["id"]: q for q in questions}
        answered_ids: set[UUID] = set()
        screening_records: list[dict] = []
        knockout_failed = False
        for a in body.answers:
            q = q_by_id.get(a.question_id)
            if not q:
                continue
            answered_ids.add(a.question_id)
            passed = True
            if q["is_knockout"] and q["required_answer"]:
                passed = (a.answer or "").strip().lower() == q["required_answer"].strip().lower()
                if not passed:
                    knockout_failed = True
            # Encrypt the answer at rest; question_id + prompt stay plaintext so
            # employers can view questions without a decrypt round-trip. See
            # applications.screening_answers_ciphertext_v.
            screening_records.append({
                "question_id": str(q["id"]),
                "prompt":      q["prompt"],
                "answer":      encrypt_str(a.answer),
                "knockout_pass": passed,
            })
        # Missing required answers also fail
        for q in questions:
            if q["id"] not in answered_ids and q["is_knockout"]:
                knockout_failed = True

        # Applicant top skills + certs — pull from credentials + extracted signals
        skills, certs = await _resume_extras(conn, applicant["id"])
        snapshot = {
            "first_name":       applicant["first_name"],
            "last_name":        applicant["last_name"],
            "phone":            applicant["phone"],
            "email":            applicant["email"],
            "city":             applicant["city"],
            "state":            applicant["state"],
            "program_name_raw": applicant["program_name_raw"],
            "career_goals_raw": applicant["career_goals_raw"],
            "experience_raw":   applicant["experience_raw"],
            "bio_raw":          applicant["bio_raw"],
            "skills":           skills,
            "certifications":   certs,
        }

        # Link to the existing match if any
        match_row = await conn.fetchrow(
            "SELECT id FROM public.matches WHERE applicant_id = $1 AND job_id = $2 LIMIT 1",
            applicant["id"], job_id,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO public.applications
              (applicant_id, job_id, employer_id, match_id, status,
               resume_snapshot, screening_answers, screening_answers_ciphertext_v,
               knockout_failed, cover_note)
            VALUES ($1, $2, $3, $4, 'submitted', $5, $6, $7, $8, $9)
            RETURNING id, submitted_at
            """,
            applicant["id"], job_id, job["employer_id"], match_row["id"] if match_row else None,
            snapshot, screening_records, _SCREENING_CIPHERTEXT_V,
            knockout_failed, body.cover_note,
        )

        # Notify the employer contact(s).
        contact = await conn.fetchrow(
            "SELECT user_id FROM public.employer_contacts WHERE employer_id = $1 ORDER BY created_at LIMIT 1",
            job["employer_id"],
        )
        if contact and contact["user_id"]:
            await notify(
                conn,
                recipient_user_id=str(contact["user_id"]),
                kind="application_submitted",
                title=f"New applicant for {job['title_raw']}",
                body=f"{applicant['first_name']} {applicant['last_name']} applied.",
                link_href=f"/employer/applications/{row['id']}",
                payload={"application_id": str(row['id']), "job_id": str(job_id), "knockout_failed": knockout_failed},
            )

    return await get_my_application(row["id"], user=user)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Applicant: my applications
# ---------------------------------------------------------------------------

@applicant_router.get("/applications", response_model=list[ApplicationOut])
async def list_my_applications(user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        rows = await conn.fetch(_APP_SELECT + " WHERE a.applicant_id = (SELECT id FROM public.applicants WHERE user_id = $1) ORDER BY a.submitted_at DESC",
                                user.user_id)
    return [_row_to_out(r) for r in rows]


@applicant_router.get("/applications/{application_id}", response_model=ApplicationOut)
async def get_my_application(application_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            _APP_SELECT + " WHERE a.id = $1 AND a.applicant_id = (SELECT id FROM public.applicants WHERE user_id = $2)",
            application_id, user.user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Application not found.")
    return _row_to_out(row)


@applicant_router.post("/applications/{application_id}/withdraw", response_model=ApplicationOut)
async def withdraw_application(application_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        upd = await conn.execute(
            """
            UPDATE public.applications
               SET status = 'withdrawn',
                   decision_at = NOW(),
                   updated_at = NOW()
             WHERE id = $1
               AND applicant_id = (SELECT id FROM public.applicants WHERE user_id = $2)
               AND status IN ('submitted', 'reviewed', 'shortlisted')
            """,
            application_id, user.user_id,
        )
        if upd.endswith(" 0"):
            raise HTTPException(status_code=409, detail="Cannot withdraw this application in its current state.")
    return await get_my_application(application_id, user=user)


# ---------------------------------------------------------------------------
# Employer: screening question editor
# ---------------------------------------------------------------------------

class ScreeningReplace(BaseModel):
    questions: list[ScreeningQuestion]


@employer_router.get("/jobs/{job_id}/screening", response_model=list[ScreeningQuestion])
async def get_screening(job_id: UUID, user: CurrentUser = Depends(require_employer_or_admin)):
    async with get_db() as conn:
        # Confirm ownership (unless admin)
        if user.role != "admin":
            owns = await conn.fetchrow(
                """
                SELECT 1 FROM public.jobs j
                  JOIN public.employer_contacts c ON c.employer_id = j.employer_id
                 WHERE j.id = $1 AND c.user_id = $2
                """,
                job_id, user.user_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Job not found.")

        rows = await conn.fetch(
            "SELECT id, position, kind::text, prompt, options, required_answer, is_knockout FROM public.job_screening_questions WHERE job_id = $1 ORDER BY position, created_at",
            job_id,
        )
    return [ScreeningQuestion(**dict(r)) for r in rows]


@employer_router.put("/jobs/{job_id}/screening", response_model=list[ScreeningQuestion])
async def replace_screening(
    job_id: UUID,
    body: ScreeningReplace,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    if len(body.questions) > 5:
        raise HTTPException(status_code=400, detail="At most 5 screening questions per job.")

    async with get_db() as conn:
        if user.role != "admin":
            owns = await conn.fetchrow(
                """
                SELECT 1 FROM public.jobs j
                  JOIN public.employer_contacts c ON c.employer_id = j.employer_id
                 WHERE j.id = $1 AND c.user_id = $2
                """,
                job_id, user.user_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Job not found.")

        async with conn.transaction():
            await conn.execute("DELETE FROM public.job_screening_questions WHERE job_id = $1", job_id)
            for i, q in enumerate(body.questions):
                await conn.execute(
                    """
                    INSERT INTO public.job_screening_questions
                      (job_id, position, kind, prompt, options, required_answer, is_knockout)
                    VALUES ($1, $2, $3::screening_question_kind_enum, $4, $5, $6, $7)
                    """,
                    job_id, i, q.kind, q.prompt.strip(), q.options, q.required_answer, q.is_knockout,
                )

    return await get_screening(job_id, user=user)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Employer: pipeline
# ---------------------------------------------------------------------------

@employer_router.get("/applications", response_model=list[ApplicationOut])
async def list_employer_applications(
    status: Optional[str] = None,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    async with get_db() as conn:
        emp_row = await conn.fetchrow(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
            user.user_id,
        )
        if not emp_row and user.role != "admin":
            raise HTTPException(status_code=404, detail="Employer profile not found.")

        params: list = []
        where = ["1=1"]
        idx = 1
        if user.role != "admin":
            where.append(f"a.employer_id = ${idx}")
            params.append(emp_row["employer_id"])
            idx += 1
        if status:
            where.append(f"a.status = ${idx}::application_status_enum")
            params.append(status)
            idx += 1

        rows = await conn.fetch(
            _APP_SELECT + f" WHERE {' AND '.join(where)} ORDER BY a.submitted_at DESC LIMIT 500",
            *params,
        )
    return [_row_to_out(r) for r in rows]


@employer_router.get("/jobs/{job_id}/applications", response_model=list[ApplicationOut])
async def list_job_applications(job_id: UUID, user: CurrentUser = Depends(require_employer_or_admin)):
    async with get_db() as conn:
        rows = await conn.fetch(_APP_SELECT + " WHERE a.job_id = $1 ORDER BY a.submitted_at DESC", job_id)
    return [_row_to_out(r) for r in rows]


@employer_router.get("/applications/{application_id}", response_model=ApplicationOut)
async def get_employer_application(
    application_id: UUID,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    async with get_db() as conn:
        row = await conn.fetchrow(_APP_SELECT + " WHERE a.id = $1", application_id)
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")

        # Ownership check unless admin
        if user.role != "admin":
            owns = await conn.fetchrow(
                "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, row["employer_id"],
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Application not found.")

        # First view — record for SLA + notify applicant
        if row["employer_viewed_at"] is None:
            await conn.execute(
                """UPDATE public.applications
                      SET employer_viewed_at = NOW(),
                          status = CASE WHEN status = 'submitted' THEN 'reviewed'::application_status_enum ELSE status END,
                          reviewed_at = COALESCE(reviewed_at, NOW()),
                          updated_at = NOW()
                    WHERE id = $1""",
                application_id,
            )
            applicant_user = await conn.fetchrow(
                "SELECT user_id FROM public.applicants WHERE id = $1", row["applicant_id"],
            )
            if applicant_user and applicant_user["user_id"]:
                await notify(
                    conn,
                    recipient_user_id=str(applicant_user["user_id"]),
                    kind="application_viewed",
                    title=f"Employer viewed your application",
                    body=f"{row['employer_name'] or 'The employer'} looked at your application for {row['job_title']}.",
                    link_href=f"/applicant/applications/{application_id}",
                    payload={"application_id": str(application_id)},
                )
            # Re-fetch row so the response reflects the state change
            row = await conn.fetchrow(_APP_SELECT + " WHERE a.id = $1", application_id)

    return _row_to_out(row)


@employer_router.patch("/applications/{application_id}", response_model=ApplicationOut)
async def patch_employer_application(
    application_id: UUID,
    body: ApplicationPatchIn,
    user: CurrentUser = Depends(require_employer_or_admin),
):
    valid = {"reviewed", "shortlisted", "interviewing", "offered", "hired", "rejected"}
    if body.status and body.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")

    async with get_db() as conn:
        row = await conn.fetchrow("SELECT employer_id, applicant_id, job_id FROM public.applications WHERE id = $1", application_id)
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user.role != "admin":
            owns = await conn.fetchrow(
                "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, row["employer_id"],
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Application not found.")

        set_parts = ["updated_at = NOW()"]
        args: list = []
        idx = 1
        if body.status:
            set_parts.append(f"status = ${idx}::application_status_enum")
            args.append(body.status)
            idx += 1
            if body.status in ("hired", "rejected"):
                set_parts.append("decision_at = NOW()")
        if body.decision_note is not None:
            set_parts.append(f"decision_note = ${idx}")
            args.append(body.decision_note)
            idx += 1
        args.append(application_id)
        await conn.execute(
            f"UPDATE public.applications SET {', '.join(set_parts)} WHERE id = ${idx}",
            *args,
        )

    return await get_employer_application(application_id, user=user)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APP_SELECT = """
SELECT a.id, a.job_id, a.employer_id, a.applicant_id, a.match_id,
       a.status::text AS status, a.knockout_failed, a.cover_note,
       a.submitted_at, a.employer_viewed_at, a.reviewed_at, a.decision_at,
       a.resume_snapshot, a.screening_answers,
       j.title_raw AS job_title,
       e.name      AS employer_name,
       ap.first_name AS applicant_first, ap.last_name AS applicant_last
  FROM public.applications a
  JOIN public.jobs       j  ON j.id  = a.job_id
  JOIN public.employers  e  ON e.id  = a.employer_id
  JOIN public.applicants ap ON ap.id = a.applicant_id
"""


def _row_to_out(r) -> ApplicationOut:
    now_days = 0
    if r["submitted_at"]:
        from datetime import datetime, timezone
        delta = datetime.now(timezone.utc) - r["submitted_at"]
        now_days = max(0, delta.days)
    fname = (r["applicant_first"] or "").strip()
    lname = (r["applicant_last"] or "").strip()

    # Decrypt screening answers on read. Legacy plaintext rows (v=0) pass
    # through decrypt_str untouched.
    raw_answers = r["screening_answers"] or []
    decrypted_answers: list[dict] = []
    for a in raw_answers:
        if isinstance(a, dict) and "answer" in a:
            decrypted_answers.append({**a, "answer": decrypt_str(a.get("answer"))})
        else:
            decrypted_answers.append(a)

    return ApplicationOut(
        id=r["id"],
        job_id=r["job_id"],
        job_title=r["job_title"],
        employer_id=r["employer_id"],
        employer_name=r["employer_name"],
        applicant_id=r["applicant_id"],
        applicant_name=f"{fname} {lname}".strip() or None,
        status=r["status"],
        knockout_failed=r["knockout_failed"],
        cover_note=r["cover_note"],
        submitted_at=r["submitted_at"].isoformat(),
        employer_viewed_at=r["employer_viewed_at"].isoformat() if r["employer_viewed_at"] else None,
        reviewed_at=r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
        decision_at=r["decision_at"].isoformat() if r["decision_at"] else None,
        days_since_submitted=now_days,
        resume_snapshot=r["resume_snapshot"] or {},
        screening_answers=decrypted_answers,
    )


async def _resume_extras(conn, applicant_id: UUID) -> tuple[list[str], list[str]]:
    """Return (skills, certifications) for the resume snapshot."""
    creds = await conn.fetch(
        "SELECT canonical_name FROM public.credentials WHERE applicant_id = $1 ORDER BY verification_level DESC LIMIT 20",
        applicant_id,
    )
    certs = [c["canonical_name"] for c in creds if c["canonical_name"]]
    # Skills from extracted_applicant_signals if present
    signals = await conn.fetchrow(
        "SELECT skills_extracted FROM public.extracted_applicant_signals WHERE applicant_id = $1 ORDER BY created_at DESC LIMIT 1",
        applicant_id,
    )
    skills: list[str] = []
    if signals and signals["skills_extracted"]:
        raw = signals["skills_extracted"]
        if isinstance(raw, list):
            skills = [s.get("skill") if isinstance(s, dict) else str(s) for s in raw[:15]]
        skills = [s for s in skills if s]
    return skills, certs
