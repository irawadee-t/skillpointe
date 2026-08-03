"""
In-platform applications + screening questions.

Applicant-facing:
  GET  /applicant/me/jobs/{job_id}/screening      — Qs to answer before applying
  GET  /applicant/me/jobs/{job_id}/apply-context  — everything the apply sheet needs
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
  POST  /employer/me/applications/{id}/revert     — real undo for decisions
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import (
    require_applicant,
    require_employer_only,
    require_employer_or_admin,
)
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
    answer: str = Field(max_length=2000)


class ProfileInlineUpdates(BaseModel):
    """
    Fields the applicant may complete inline inside the apply sheet.
    Saved back to the profile (labeled as such in the UI) before snapshotting.
    """
    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=50)
    program_name_raw: Optional[str] = Field(default=None, max_length=200)
    available_from_date: Optional[str] = None
    expected_completion_date: Optional[str] = None

    @classmethod
    def _parse_iso(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        from datetime import date as _date
        _date.fromisoformat(v)  # raises ValueError → 422
        return v

    def non_empty_updates(self) -> dict:
        """Whitelisted, trimmed, non-empty fields only."""
        out: dict = {}
        for key, val in self.model_dump().items():
            if val is None:
                continue
            val = val.strip()
            if not val:
                continue
            if key in ("available_from_date", "expected_completion_date"):
                from datetime import date as _date
                try:
                    val = _date.fromisoformat(val)
                except ValueError:
                    continue
            out[key] = val
        return out


class ApplyIn(BaseModel):
    answers: list[ScreeningAnswer] = Field(default_factory=list, max_length=20)
    cover_note: Optional[str] = Field(default=None, max_length=2000)
    profile_updates: Optional[ProfileInlineUpdates] = None


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
    # Posting honesty: FALSE when the job went inactive (source removal,
    # paused/filled/closed by the employer) after this application was made.
    # The applicant timeline stays intact; the UI adds an honest notice.
    job_active: bool = True
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
# Apply context — one round-trip powering the apply sheet
# ---------------------------------------------------------------------------

# Profile-sourced groups an employer may require. Human labels are used in
# server-side 422 messages so the client and API speak the same language.
PROFILE_GROUP_LABELS: dict[str, str] = {
    "contact":     "contact info",
    "location":    "location",
    "program":     "program or trade",
    "availability": "availability",
    "credentials": "credentials",
    "resume":      "resume",
}


class ApplyContextProfile(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    program: Optional[str] = None
    available_from_date: Optional[str] = None
    expected_completion_date: Optional[str] = None
    credentials: list[str] = Field(default_factory=list)
    resume_filename: Optional[str] = None


class AlreadyAppliedInfo(BaseModel):
    id: UUID
    status: str
    submitted_at: str
    # A withdrawn application may be re-submitted exactly once.
    can_reapply: bool


class ApplyContext(BaseModel):
    job_id: UUID
    job_title: str
    employer_name: Optional[str] = None
    job_active: bool
    internal_apply_enabled: bool
    external_url: Optional[str] = None
    already_applied: Optional[AlreadyAppliedInfo] = None
    required_fields: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    profile: ApplyContextProfile
    questions: list[ScreeningQuestion] = Field(default_factory=list)


def _missing_groups(
    required: list[str],
    prof: dict,
    *,
    has_resume: bool,
    credential_count: int,
) -> list[str]:
    """Which required profile groups the applicant hasn't satisfied yet."""
    missing: list[str] = []
    if "contact" in required and not (prof.get("phone") or prof.get("email")):
        missing.append("contact")
    if "location" in required and not (prof.get("city") and prof.get("state")):
        missing.append("location")
    if "program" in required and not (
        prof.get("program_name_raw") or prof.get("program_field") or prof.get("career_path")
    ):
        missing.append("program")
    if "availability" in required and not (
        prof.get("available_from_date") or prof.get("expected_completion_date")
    ):
        missing.append("availability")
    if "credentials" in required and credential_count == 0:
        missing.append("credentials")
    if "resume" in required and not has_resume:
        missing.append("resume")
    return missing


_APPLICANT_SNAPSHOT_SQL = """
    SELECT id, first_name, last_name, phone, email, city, state,
           program_name_raw, program_field, career_path,
           available_from_date, expected_completion_date,
           career_goals_raw, experience_raw, bio_raw
      FROM public.applicants
     WHERE ($2::uuid IS NOT NULL AND id = $2::uuid)
        OR ($2::uuid IS NULL AND user_id = $1::uuid)
"""

_JOB_APPLY_SQL = """
    SELECT j.id, j.title_raw, j.employer_id, j.is_active, j.source_url,
           j.required_profile_fields,
           e.name AS employer_name,
           COALESCE(j.accepts_internal_applications,
                    e.accepts_internal_applications_default,
                    FALSE) AS internal_apply_enabled
      FROM public.jobs j
      LEFT JOIN public.employers e ON e.id = j.employer_id
     WHERE j.id = $1
"""


@applicant_router.get("/jobs/{job_id}/apply-context", response_model=ApplyContext)
async def get_apply_context(job_id: UUID, user: CurrentUser = Depends(require_applicant)):
    """Everything the one-click apply sheet needs, in one round-trip."""
    async with get_db() as conn:
        job = await conn.fetchrow(_JOB_APPLY_SQL, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        applicant = await conn.fetchrow(
            _APPLICANT_SNAPSHOT_SQL, user.user_id, user.view_as_applicant_id
        )
        prof = dict(applicant) if applicant else {}

        existing = None
        if applicant:
            existing = await conn.fetchrow(
                """
                SELECT id, status::text AS status, submitted_at, reapply_count
                  FROM public.applications
                 WHERE applicant_id = $1 AND job_id = $2
                """,
                applicant["id"], job_id,
            )

        required = list(job["required_profile_fields"] or [])
        creds: list[str] = []
        resume_filename = None
        if applicant:
            cred_rows = await conn.fetch(
                "SELECT canonical_name FROM public.credentials WHERE applicant_id = $1 ORDER BY verification_level DESC LIMIT 20",
                applicant["id"],
            )
            creds = [c["canonical_name"] for c in cred_rows if c["canonical_name"]]
            resume_filename = await conn.fetchval(
                "SELECT filename FROM public.applicant_resume_uploads WHERE applicant_id = $1 ORDER BY created_at DESC LIMIT 1",
                applicant["id"],
            )

        questions = await conn.fetch(
            "SELECT id, position, kind::text, prompt, options, required_answer, is_knockout FROM public.job_screening_questions WHERE job_id = $1 ORDER BY position, created_at",
            job_id,
        )

    missing = _missing_groups(
        required, prof, has_resume=resume_filename is not None, credential_count=len(creds)
    )

    return ApplyContext(
        job_id=job_id,
        job_title=job["title_raw"],
        employer_name=job["employer_name"],
        job_active=bool(job["is_active"]),
        internal_apply_enabled=bool(job["internal_apply_enabled"]),
        external_url=job["source_url"],
        already_applied=AlreadyAppliedInfo(
            id=existing["id"],
            status=existing["status"],
            submitted_at=existing["submitted_at"].isoformat(),
            can_reapply=existing["status"] == "withdrawn" and (existing["reapply_count"] or 0) == 0,
        ) if existing else None,
        required_fields=required,
        missing_required=missing,
        profile=ApplyContextProfile(
            first_name=prof.get("first_name"),
            last_name=prof.get("last_name"),
            phone=prof.get("phone"),
            email=prof.get("email"),
            city=prof.get("city"),
            state=prof.get("state"),
            program=prof.get("program_name_raw") or prof.get("program_field") or prof.get("career_path"),
            available_from_date=prof["available_from_date"].isoformat() if prof.get("available_from_date") else None,
            expected_completion_date=prof["expected_completion_date"].isoformat() if prof.get("expected_completion_date") else None,
            credentials=creds,
            resume_filename=resume_filename,
        ),
        questions=[ScreeningQuestion(**dict(q)) for q in questions],
    )


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
        # Applicant profile snapshot. Note: admin view-as resolves to the target
        # applicant for READS elsewhere, but apply must never be performed on an
        # applicant's behalf — resolve strictly by the caller's own user_id.
        applicant = await conn.fetchrow(
            """
            SELECT id, first_name, last_name, phone, email, city, state,
                   program_name_raw, program_field, career_path,
                   available_from_date, expected_completion_date,
                   career_goals_raw, experience_raw, bio_raw
              FROM public.applicants
             WHERE user_id = $1
            """,
            user.user_id,
        )
        if not applicant:
            raise HTTPException(status_code=404, detail="Applicant profile not found.")

        job = await conn.fetchrow(_JOB_APPLY_SQL, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if not job["is_active"]:
            # The job went inactive between page load and submit — honest error,
            # no orphan application row.
            raise HTTPException(
                status_code=409,
                detail="This job is no longer accepting applications.",
            )
        if not job["internal_apply_enabled"]:
            raise HTTPException(
                status_code=409,
                detail="This job doesn't accept applications on SKILLED Nation. Use the employer's site to apply.",
            )

        # Duplicate check. A withdrawn application may be re-submitted exactly
        # once — the row is reactivated in place (see reapply_count).
        existing = await conn.fetchrow(
            "SELECT id, status::text AS status, reapply_count FROM public.applications WHERE applicant_id = $1 AND job_id = $2",
            applicant["id"], job_id,
        )
        reapply_id = None
        if existing:
            if existing["status"] == "withdrawn" and (existing["reapply_count"] or 0) == 0:
                reapply_id = existing["id"]
            elif existing["status"] == "withdrawn":
                raise HTTPException(
                    status_code=409,
                    detail="You withdrew and re-applied to this job once already. That's the limit.",
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"You've already applied to this job (status: {existing['status']}).",
                )

        # Inline profile completion — saved back to the profile before
        # snapshotting, so the sheet never bounces the user to the profile page.
        prof = dict(applicant)
        if body.profile_updates:
            updates = body.profile_updates.non_empty_updates()
            if updates:
                set_clauses = [f"{col} = ${i + 2}" for i, col in enumerate(updates)]
                await conn.execute(
                    f"UPDATE public.applicants SET {', '.join(set_clauses)}, "
                    "updated_at = NOW(), profile_last_updated_at = NOW() WHERE id = $1",
                    applicant["id"], *updates.values(),
                )
                prof.update(updates)

        # Screening evaluation
        questions = await conn.fetch(
            "SELECT id, kind::text, prompt, required_answer, is_knockout FROM public.job_screening_questions WHERE job_id = $1",
            job_id,
        )
        q_by_id = {q["id"]: q for q in questions}
        answers_by_qid = {a.question_id: a for a in body.answers}

        # Required questions must be ANSWERED (422 — parity with the client
        # validation). A wrong answer still submits, flagged as knockout_failed,
        # so the employer can see it and decide.
        unanswered = [
            q["prompt"] for q in questions
            if q["is_knockout"] and not (answers_by_qid.get(q["id"]) and answers_by_qid[q["id"]].answer.strip())
        ]
        if unanswered:
            raise HTTPException(
                status_code=422,
                detail="Please answer the required question(s): " + "; ".join(unanswered),
            )

        screening_records: list[dict] = []
        knockout_failed = False
        for a in body.answers:
            q = q_by_id.get(a.question_id)
            if not q:
                continue
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

        # Employer-required profile groups — validated AFTER inline updates so
        # the sheet's inline-complete path satisfies them in the same request.
        required = list(job["required_profile_fields"] or [])
        resume_filename = None
        if "resume" in required:
            resume_filename = await conn.fetchval(
                "SELECT filename FROM public.applicant_resume_uploads WHERE applicant_id = $1 ORDER BY created_at DESC LIMIT 1",
                applicant["id"],
            )
        credential_count = 0
        if "credentials" in required:
            credential_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.credentials WHERE applicant_id = $1",
                applicant["id"],
            ) or 0
        missing = _missing_groups(
            required, prof,
            has_resume=resume_filename is not None,
            credential_count=int(credential_count),
        )
        if missing:
            labels = [PROFILE_GROUP_LABELS.get(m, m) for m in missing]
            raise HTTPException(
                status_code=422,
                detail="This employer requires: " + ", ".join(labels) + ". Complete those in the apply form.",
            )

        # Applicant top skills + certs — pull from credentials + extracted signals
        skills, certs, certs_detail = await _resume_extras(conn, applicant["id"])
        # Consent snapshot — the review step in the sheet is the consent moment.
        # This exact payload is what the employer sees, frozen at submit time;
        # later profile edits never rewrite it.
        snapshot = {
            "first_name":       prof.get("first_name"),
            "last_name":        prof.get("last_name"),
            "phone":            prof.get("phone"),
            "email":            prof.get("email"),
            "city":             prof.get("city"),
            "state":            prof.get("state"),
            "program_name_raw": prof.get("program_name_raw") or prof.get("program_field") or prof.get("career_path"),
            "available_from_date": prof["available_from_date"].isoformat() if prof.get("available_from_date") else None,
            "expected_completion_date": prof["expected_completion_date"].isoformat() if prof.get("expected_completion_date") else None,
            "career_goals_raw": prof.get("career_goals_raw"),
            "experience_raw":   prof.get("experience_raw"),
            "bio_raw":          prof.get("bio_raw"),
            "skills":           skills,
            "certifications":   certs,
            # Deduped names + verification levels so the employer's decision
            # surface can render the trust affix. Older snapshots lack this
            # key; the frontend falls back to the plain list above.
            "certifications_detail": certs_detail,
            "resume_filename":  resume_filename,
            "shared_fields":    required,
        }

        # Link to the existing match if any
        match_row = await conn.fetchrow(
            "SELECT id FROM public.matches WHERE applicant_id = $1 AND job_id = $2 LIMIT 1",
            applicant["id"], job_id,
        )

        if reapply_id is not None:
            # Withdrawn → one re-apply: reactivate the same row with a fresh
            # snapshot and answers. The status/reapply_count guard makes a
            # concurrent double re-apply a no-op for the loser.
            row = await conn.fetchrow(
                """
                UPDATE public.applications
                   SET status = 'submitted',
                       resume_snapshot = $2,
                       screening_answers = $3,
                       screening_answers_ciphertext_v = $4,
                       knockout_failed = $5,
                       cover_note = $6,
                       shared_fields = $7,
                       submitted_at = NOW(),
                       employer_viewed_at = NULL,
                       reviewed_at = NULL,
                       decision_at = NULL,
                       decision_note = NULL,
                       reapply_count = reapply_count + 1,
                       updated_at = NOW()
                 WHERE id = $1 AND status = 'withdrawn' AND reapply_count = 0
                RETURNING id, submitted_at
                """,
                reapply_id, snapshot, screening_records, _SCREENING_CIPHERTEXT_V,
                knockout_failed, body.cover_note, required,
            )
            if row is None:
                raise HTTPException(status_code=409, detail="You've already re-applied to this job.")
        else:
            # ON CONFLICT DO NOTHING makes this idempotent under a concurrent
            # double-submit that slips past the read-check above: the second insert
            # is a no-op (returns no row) rather than a 500 on the unique constraint.
            row = await conn.fetchrow(
                """
                INSERT INTO public.applications
                  (applicant_id, job_id, employer_id, match_id, status,
                   resume_snapshot, screening_answers, screening_answers_ciphertext_v,
                   knockout_failed, cover_note, shared_fields)
                VALUES ($1, $2, $3, $4, 'submitted', $5, $6, $7, $8, $9, $10)
                ON CONFLICT (applicant_id, job_id) DO NOTHING
                RETURNING id, submitted_at
                """,
                applicant["id"], job_id, job["employer_id"], match_row["id"] if match_row else None,
                snapshot, screening_records, _SCREENING_CIPHERTEXT_V,
                knockout_failed, body.cover_note, required,
            )
            if row is None:
                # A concurrent request won the race — treat as already applied.
                raise HTTPException(status_code=409, detail="You've already applied to this job.")

        # Instrument the funnel's "application submitted" step — written in the
        # same connection as the business insert so the metric can never drift
        # from the applications table. (Admin engagement analytics read this.)
        # Exactly once per submission: every code path above either raised or
        # produced exactly one inserted/reactivated row. External applies log
        # apply_click elsewhere — the two event streams never overlap.
        await conn.execute(
            """
            INSERT INTO public.engagement_events
              (applicant_id, job_id, match_id, event_type, event_data)
            VALUES ($1, $2, $3, 'application_submitted', $4::jsonb)
            """,
            applicant["id"], job_id, match_row["id"] if match_row else None,
            {
                "application_id": str(row["id"]),
                "knockout_failed": knockout_failed,
                "reapply": reapply_id is not None,
            },
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
                title=f"{applicant['first_name']} {applicant['last_name']} applied to {job['title_raw']}",
                body="Review their snapshot and move them forward or propose interview times.",
                link_href=f"/employer/applications/{row['id']}",
                payload={"application_id": str(row['id']), "job_id": str(job_id), "knockout_failed": knockout_failed},
                dedupe_key=f"application_submitted:{row['id']}",
            )

    return await get_my_application(row["id"], user=user)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Applicant: my applications
# ---------------------------------------------------------------------------

@applicant_router.get("/applications", response_model=list[ApplicationOut])
async def list_my_applications(user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        rows = await conn.fetch(_APP_SELECT + " WHERE a.applicant_id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid)) ORDER BY a.submitted_at DESC",
                                user.user_id, user.view_as_applicant_id)
    return [_row_to_out(r) for r in rows]


@applicant_router.get("/applications/{application_id}", response_model=ApplicationOut)
async def get_my_application(application_id: UUID, user: CurrentUser = Depends(require_applicant)):
    async with get_db() as conn:
        row = await conn.fetchrow(
            _APP_SELECT + " WHERE a.id = $1 AND a.applicant_id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))",
            application_id, user.user_id, user.view_as_applicant_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Application not found.")
    return _row_to_out(row)


@applicant_router.post("/applications/{application_id}/withdraw", response_model=ApplicationOut)
async def withdraw_application(application_id: UUID, user: CurrentUser = Depends(require_applicant)):
    """Withdraw an application.

    Allowed from submitted/reviewed/shortlisted, and from interviewing — in
    which case every open interview slot (proposed or accepted) is cancelled
    server-side via the same path the employer cancel endpoint uses, and the
    employer's withdrawal notification carries that context. 'offered' stays
    blocked with an honest message; terminal states 409.
    """
    from app.routers.interviews import cancel_open_slots

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT a.id, a.status::text AS status
              FROM public.applications a
             WHERE a.id = $1
               AND a.applicant_id = (SELECT id FROM public.applicants WHERE user_id = $2)
            """,
            application_id, user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")
        current = row["status"]
        if current == "offered":
            raise HTTPException(
                status_code=409,
                detail="You have an offer on this application. Message the employer instead of withdrawing.",
            )
        if current not in ("submitted", "reviewed", "shortlisted", "interviewing"):
            raise HTTPException(status_code=409, detail="Cannot withdraw this application in its current state.")

        cancelled_slots: list = []
        async with conn.transaction():
            # Race guard: only withdraw if the status is still what we read.
            upd = await conn.execute(
                """
                UPDATE public.applications
                   SET status = 'withdrawn',
                       decision_at = NOW(),
                       updated_at = NOW()
                 WHERE id = $1
                   AND status = $2::application_status_enum
                """,
                application_id, current,
            )
            if upd.endswith(" 0"):
                raise HTTPException(status_code=409, detail="Cannot withdraw this application in its current state.")

            if current == "interviewing":
                # An interview the applicant walked away from must not linger
                # as booked on the employer's side or in calendar feeds.
                cancelled_slots = await cancel_open_slots(conn, application_id)

        # Tell the employer contact — a withdrawal they only discover on their
        # next manual refresh is a cross-role propagation gap. Notification
        # trouble must never 500 the withdrawal itself.
        try:
            info = await conn.fetchrow(
                """
                SELECT COALESCE(j.title_normalized, j.title_raw) AS job_title,
                       CONCAT(ap.first_name, ' ', ap.last_name) AS applicant_name,
                       (SELECT ec.user_id FROM public.employer_contacts ec
                         WHERE ec.employer_id = a.employer_id
                         ORDER BY ec.created_at LIMIT 1) AS employer_user
                  FROM public.applications a
                  JOIN public.applicants ap ON ap.id = a.applicant_id
                  JOIN public.jobs j        ON j.id = a.job_id
                 WHERE a.id = $1
                """,
                application_id,
            )
            if info and info["employer_user"]:
                note_body = "Their application is no longer active."
                booked = [s for s in cancelled_slots if s["was_accepted"]]
                if booked:
                    start = booked[0]["start_at"]
                    when = f"{start:%a %b %-d, %-I:%M %p}" if start else "The booked time"
                    note_body += f" The {when} interview was cancelled."
                elif cancelled_slots:
                    note_body += " The proposed interview times were released."
                await notify(
                    conn,
                    recipient_user_id=str(info["employer_user"]),
                    kind="application_withdrawn",
                    title=f"{(info['applicant_name'] or 'An applicant').strip()} withdrew from {info['job_title'] or 'job'}",
                    body=note_body,
                    link_href=f"/employer/applications/{application_id}",
                    payload={
                        "application_id": str(application_id),
                        **({"cancelled_interview_slots": len(cancelled_slots)} if cancelled_slots else {}),
                    },
                    dedupe_key=f"application_withdrawn:{application_id}",
                )
        except Exception as exc:
            logger.warning("Withdraw notification failed for %s: %s", application_id, exc)
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
    # Employer-only: admin views pipelines read-only, never edits an employer's
    # screening questions on their behalf (see CLAUDE.md "admin cannot act as employer").
    user: CurrentUser = Depends(require_employer_only),
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
                    title="Employer viewed your application",
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
    # Employer-only: hiring/rejecting a candidate is an employer decision; admin
    # must not set an application to hired/rejected on an employer's behalf.
    user: CurrentUser = Depends(require_employer_only),
):
    valid = {"reviewed", "shortlisted", "interviewing", "offered", "hired", "rejected"}
    if body.status and body.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")

    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT employer_id, applicant_id, job_id, match_id, status::text AS status "
            "FROM public.applications WHERE id = $1",
            application_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user.role != "admin":
            owns = await conn.fetchrow(
                "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, row["employer_id"],
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Application not found.")

        status_changing = bool(body.status) and body.status != row["status"]

        set_parts = ["updated_at = NOW()"]
        args: list = []
        idx = 1
        if body.status:
            set_parts.append(f"status = ${idx}::application_status_enum")
            args.append(body.status)
            idx += 1
            if status_changing:
                # Remember where we came from so the decision is truly
                # reversible (POST …/revert). SET reads the OLD row value.
                set_parts.append("previous_status = status")
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

        # Marking hired IS the hire report: record the outcome + analytics
        # event exactly like /employer/me/jobs/{jid}/candidates/{aid}/hire so
        # the analytics ("hired" tiles, hire_reported events) stay one truth.
        # Only on an actual transition — re-PATCHing 'hired' is a no-op here.
        if body.status == "hired" and status_changing:
            await _record_hire(conn, row, user, application_id)

        # An employer decision the applicant never hears about is a propagation
        # bug: tell them on shortlist/hire/reject. Deduped per (application,
        # status) so a revert + re-decide inside the window doesn't spam.
        # Notification trouble must never 500 the decision itself — log and move on.
        if status_changing and body.status in _STATUS_NOTIFY:
            try:
                await _notify_applicant_status(conn, application_id, body.status)
            except Exception as exc:
                logger.warning("Applicant status notification failed for %s: %s", application_id, exc)

    return await get_employer_application(application_id, user=user)


# Applicant-facing copy per employer decision. Interviewing transitions are
# announced by the interview panel itself (interview_proposed et al.), and
# "offered" has no product surface yet — so those stay out of this map.
_STATUS_NOTIFY: dict[str, tuple[str, str, str]] = {
    # status -> (kind, title template, body template); {job} is replaced.
    "shortlisted": (
        "application_shortlisted",
        "You were shortlisted for {job}",
        "{employer} moved your application forward. Keep an eye out for interview times.",
    ),
    "hired": (
        "application_hired",
        "You were hired for {job}",
        "{employer} marked you as hired. Congratulations.",
    ),
    "rejected": (
        "application_rejected",
        "Update on your {job} application",
        "{employer} decided not to move forward this time. Your other matches are still open.",
    ),
}


# Quiet window before the applicant hears about a rejection. The employer's
# undo toast lives ~10s; delivering the bad news after 15s means an undone
# rejection never pinged anyone (the revert deletes the pending row).
# Positive news (shortlist/hire) stays instant.
REJECT_NOTIFY_DELAY_SECONDS = 15


async def _notify_applicant_status(conn, application_id: UUID, new_status: str) -> None:
    kind, title_tpl, body_tpl = _STATUS_NOTIFY[new_status]
    info = await conn.fetchrow(
        """
        SELECT ap.user_id, COALESCE(j.title_normalized, j.title_raw) AS job_title,
               e.name AS employer_name
          FROM public.applications a
          JOIN public.applicants ap ON ap.id = a.applicant_id
          JOIN public.jobs j        ON j.id = a.job_id
          JOIN public.employers e   ON e.id = a.employer_id
         WHERE a.id = $1
        """,
        application_id,
    )
    if not info or not info["user_id"]:
        return
    job = info["job_title"] or "the job"
    employer = info["employer_name"] or "The employer"
    deliver_after = None
    if new_status == "rejected":
        from datetime import datetime, timedelta, timezone
        deliver_after = datetime.now(timezone.utc) + timedelta(seconds=REJECT_NOTIFY_DELAY_SECONDS)
    await notify(
        conn,
        recipient_user_id=str(info["user_id"]),
        kind=kind,
        title=title_tpl.format(job=job, employer=employer),
        body=body_tpl.format(job=job, employer=employer),
        link_href=f"/applicant/applications/{application_id}",
        payload={"application_id": str(application_id), "status": new_status},
        dedupe_key=f"application_status:{application_id}:{new_status}",
        deliver_after=deliver_after,
    )


async def _record_hire(conn, row, user: CurrentUser, application_id: UUID) -> None:
    """Upsert hire_outcomes + log the hire_reported engagement event for an
    application that just transitioned to 'hired'."""
    await conn.execute(
        """
        INSERT INTO public.hire_outcomes
          (applicant_id, job_id, employer_id, match_id, outcome_type, hire_date, reported_by)
        VALUES ($1, $2, $3, $4, 'hired', CURRENT_DATE, $5)
        ON CONFLICT (applicant_id, job_id) DO UPDATE
          SET outcome_type = 'hired',
              hire_date    = COALESCE(public.hire_outcomes.hire_date, EXCLUDED.hire_date),
              reported_by  = EXCLUDED.reported_by,
              updated_at   = NOW()
        """,
        row["applicant_id"], row["job_id"], row["employer_id"], row["match_id"],
        user.user_id,
    )
    await conn.execute(
        """
        INSERT INTO public.engagement_events
          (employer_id, job_id, applicant_id, match_id, event_type, event_data)
        VALUES ($1, $2, $3, $4, 'hire_reported', $5::jsonb)
        """,
        row["employer_id"], row["job_id"], row["applicant_id"], row["match_id"],
        {"outcome_type": "hired", "application_id": str(application_id)},
    )


# ---------------------------------------------------------------------------
# Employer: revert a decision — REAL undo
# ---------------------------------------------------------------------------

# Statuses an employer may revert, and the stages a revert may land on.
_REVERTIBLE = {"shortlisted", "rejected", "hired"}
_SAFE_REVERT_TARGETS = {"submitted", "reviewed", "shortlisted", "interviewing", "offered"}


@employer_router.post("/applications/{application_id}/revert", response_model=ApplicationOut)
async def revert_employer_application(
    application_id: UUID,
    # Employer-only (same rationale as PATCH): reverting a hiring decision is
    # an employer act; admin views pipelines read-only.
    user: CurrentUser = Depends(require_employer_only),
):
    """
    Undo the employer's last decision on an application:

      shortlisted → back to its previous stage (fallback: reviewed)
      rejected    → reopened at its previous stage; decision note archived
                    to audit_logs and cleared from the row
      hired       → back to its previous stage; the hire_outcomes row is
                    deleted and the original hire_reported engagement
                    event(s) removed so analytics stay TRUE
      interviewing → 409: governed by the interview supersede/cancel flow
      anything else → 409: nothing to revert

    Every revert writes an audit_logs row (action=application_status_reverted)
    with full from/to state. The applicant is NOT notified of the revert —
    their timeline simply shows the restored stage.

    Notification decision: reverts are silent, and the rejection notification
    itself sits in a quiet window (deliver_after, see
    REJECT_NOTIFY_DELAY_SECONDS). A revert inside that window deletes the
    pending row, so an undone rejection never produces a "you were rejected"
    artifact on the applicant side.
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT employer_id, applicant_id, job_id, match_id,
                   status::text AS status, previous_status::text AS previous_status,
                   decision_note, decision_at
              FROM public.applications
             WHERE id = $1
            """,
            application_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user.role != "admin":
            owns = await conn.fetchrow(
                "SELECT 1 FROM public.employer_contacts WHERE user_id = $1 AND employer_id = $2",
                user.user_id, row["employer_id"],
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Application not found.")

        current = row["status"]
        if current == "interviewing":
            raise HTTPException(
                status_code=409,
                detail="Interview stages are managed on the interview panel. Supersede or cancel the proposed times instead.",
            )
        if current not in _REVERTIBLE:
            raise HTTPException(status_code=409, detail="Nothing to revert on this application.")

        prev = row["previous_status"]
        target = prev if (prev in _SAFE_REVERT_TARGETS and prev != current) else "reviewed"

        # Guarded, race-safe transition: only flips if the status is still the
        # one we just read. A concurrent revert/patch makes this a 409, never
        # a double-apply.
        upd = await conn.execute(
            """
            UPDATE public.applications
               SET status = $2::application_status_enum,
                   previous_status = NULL,
                   decision_at = NULL,
                   decision_note = NULL,
                   updated_at = NOW()
             WHERE id = $1 AND status = $3::application_status_enum
            """,
            application_id, target, current,
        )
        if upd.endswith(" 0"):
            raise HTTPException(status_code=409, detail="This application changed underneath you. Refresh and try again.")

        removed_notifications = 0
        if current == "rejected":
            # The rejection notification sits in a quiet window
            # (deliver_after ~15s ahead). A revert inside that window deletes
            # the pending row, so an undone rejection never reaches the
            # applicant. Already-delivered rows are left alone — the applicant
            # saw real history; their timeline shows the restored stage.
            del_res = await conn.execute(
                """
                DELETE FROM public.notifications
                 WHERE kind = 'application_rejected'
                   AND deliver_after IS NOT NULL AND deliver_after > NOW()
                   AND payload->>'application_id' = $1
                """,
                str(application_id),
            )
            try:
                removed_notifications = int(del_res.split(" ")[-1])
            except (ValueError, AttributeError):
                removed_notifications = 0

        removed_outcome = None
        removed_events = 0
        if current == "hired":
            # Void the hire so analytics stay TRUE: delete the outcome row and
            # the original hire_reported event(s) for this triple. Both are
            # captured in the audit row below before removal.
            removed_outcome = await conn.fetchrow(
                """
                DELETE FROM public.hire_outcomes
                 WHERE applicant_id = $1 AND job_id = $2 AND employer_id = $3
                RETURNING id, outcome_type, hire_date, reported_wage_annual
                """,
                row["applicant_id"], row["job_id"], row["employer_id"],
            )
            del_res = await conn.execute(
                """
                DELETE FROM public.engagement_events
                 WHERE event_type = 'hire_reported'
                   AND applicant_id = $1 AND job_id = $2 AND employer_id = $3
                """,
                row["applicant_id"], row["job_id"], row["employer_id"],
            )
            try:
                removed_events = int(del_res.split(" ")[-1])
            except (ValueError, AttributeError):
                removed_events = 0

        # Auditable, always.
        await conn.execute(
            """
            INSERT INTO public.audit_logs
              (actor_id, actor_role, action, entity_type, entity_id, before_state, after_state, metadata)
            VALUES ($1::uuid, $2, 'application_status_reverted', 'application', $3::uuid, $4::jsonb, $5::jsonb, $6::jsonb)
            """,
            user.user_id, user.role, application_id,
            {
                "status": current,
                "decision_note": row["decision_note"],
                "decision_at": row["decision_at"].isoformat() if row["decision_at"] else None,
                "hire_outcome": dict_or_none(removed_outcome),
            },
            {"status": target},
            {
                "removed_hire_reported_events": removed_events,
                "removed_pending_notifications": removed_notifications,
            },
        )

    return await get_employer_application(application_id, user=user)


def dict_or_none(record) -> Optional[dict]:
    if record is None:
        return None
    out = dict(record)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APP_SELECT = """
SELECT a.id, a.job_id, a.employer_id, a.applicant_id, a.match_id,
       a.status::text AS status, a.knockout_failed, a.cover_note,
       a.submitted_at, a.employer_viewed_at, a.reviewed_at, a.decision_at,
       a.resume_snapshot, a.screening_answers,
       j.title_raw AS job_title,
       j.is_active AS job_active,
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
        # Older fakes/rows without the column default to "still active".
        job_active=bool(r["job_active"]) if "job_active" in r.keys() else True,
        cover_note=r["cover_note"],
        submitted_at=r["submitted_at"].isoformat(),
        employer_viewed_at=r["employer_viewed_at"].isoformat() if r["employer_viewed_at"] else None,
        reviewed_at=r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
        decision_at=r["decision_at"].isoformat() if r["decision_at"] else None,
        days_since_submitted=now_days,
        resume_snapshot=r["resume_snapshot"] or {},
        screening_answers=decrypted_answers,
    )


async def _resume_extras(conn, applicant_id: UUID) -> tuple[list[str], list[str], list[dict]]:
    """Return (skills, certifications, certifications_detail) for the resume
    snapshot. Credentials are deduped by canonical name, keeping the highest
    verification level, so the employer decision surface can show the trust
    affix (SKILLED-verified / Institution-verified / Self-reported)."""
    creds = await conn.fetch(
        """
        SELECT canonical_name, MAX(verification_level) AS verification_level
        FROM public.credentials
        WHERE applicant_id = $1 AND canonical_name IS NOT NULL
        GROUP BY canonical_name
        ORDER BY 2 DESC, 1
        LIMIT 20
        """,
        applicant_id,
    )
    certs = [c["canonical_name"] for c in creds if c["canonical_name"]]
    certs_detail = [
        {"name": c["canonical_name"], "verification_level": int(c["verification_level"] or 0)}
        for c in creds
        if c["canonical_name"]
    ]
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
    return skills, certs, certs_detail
