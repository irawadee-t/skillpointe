"""
badges.py — Earned achievement badges for an applicant.

GET /applicant/me/badges

Every badge here is computed from data the product ALREADY writes. There are no
dormant placeholders: each badge names the table (and the writer) that backs it.

  profile_complete       applicants.*            -> _compute_completeness() >= 80
                         engagement_events        'profile_completed' (applicants.py)
  first_credential       credentials              rows (credentials.py POST)
  credential_verified    credentials              verification_level >= 1
                                                  (credential_verify.py / ingest.py)
  five_credentials       credentials              rows >= 5
  first_application      applications             rows (applications.py apply)
  ten_applications       applications             rows >= 10
  ten_jobs_saved         saved_jobs               rows (applicants.py interest signal)
  planning_chat          chat_messages role=user  (chat.py)
  first_employer_message direct_messages          sender_role='applicant' (messaging.py)
  hired                  hire_outcomes            rows (employers.py hire)

Everything is fetched in TWO round-trips: one profile row (for completeness)
and one combined activity query built from scalar subqueries. Counting badges
also carry the ordered timestamps of the first N qualifying rows so the
earned_at is the moment the badge was actually reached, not "now".
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.routers.applicants import _compute_completeness

router = APIRouter(prefix="/applicant/me", tags=["badges"])

# Highest tier per counting source — bounds the timestamp arrays we pull back.
_MAX_APPLICATION_TIER = 10
_MAX_CREDENTIAL_TIER = 5
_MAX_SAVED_TIER = 10

PROFILE_TARGET = 80


class BadgeProgress(BaseModel):
    current: int
    target: int


class Badge(BaseModel):
    key: str
    title: str
    description: str
    earned: bool
    earned_at: Optional[str] = None
    progress: BadgeProgress


class BadgesResponse(BaseModel):
    badges: list[Badge]
    earned_count: int
    total_count: int


# ---------------------------------------------------------------------------
# SQL — one combined activity query (no N+1)
# ---------------------------------------------------------------------------

_PROFILE_SQL = """
    SELECT
        a.id,
        a.first_name, a.last_name, a.program_name_raw,
        a.city, a.state,
        a.willing_to_relocate, a.willing_to_travel,
        a.expected_completion_date, a.available_from_date,
        a.enrollment_status::text, a.degree_type::text,
        a.school_name, a.program_field, a.gpa,
        a.travel_preference::text, a.relocation_preference::text,
        a.age_range, a.gender, a.has_internship,
        jf.code AS canonical_job_family_code
    FROM public.applicants a
    LEFT JOIN public.canonical_job_families jf
        ON jf.id = a.canonical_job_family_id
    WHERE a.id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))
"""

_ACTIVITY_SQL = f"""
    SELECT
        (SELECT count(*) FROM public.applications
          WHERE applicant_id = $1) AS application_count,
        (SELECT coalesce(array_agg(t.ts ORDER BY t.ts), '{{}}') FROM (
            SELECT submitted_at AS ts FROM public.applications
             WHERE applicant_id = $1
             ORDER BY submitted_at LIMIT {_MAX_APPLICATION_TIER}
         ) t) AS application_ts,

        (SELECT count(*) FROM public.credentials
          WHERE applicant_id = $1) AS credential_count,
        (SELECT coalesce(array_agg(t.ts ORDER BY t.ts), '{{}}') FROM (
            SELECT created_at AS ts FROM public.credentials
             WHERE applicant_id = $1
             ORDER BY created_at LIMIT {_MAX_CREDENTIAL_TIER}
         ) t) AS credential_ts,

        (SELECT count(*) FROM public.credentials
          WHERE applicant_id = $1 AND verification_level >= 1)
            AS verified_credential_count,
        (SELECT min(updated_at) FROM public.credentials
          WHERE applicant_id = $1 AND verification_level >= 1)
            AS first_verified_credential_at,

        (SELECT count(*) FROM public.saved_jobs
          WHERE applicant_id = $1) AS saved_job_count,
        (SELECT coalesce(array_agg(t.ts ORDER BY t.ts), '{{}}') FROM (
            SELECT saved_at AS ts FROM public.saved_jobs
             WHERE applicant_id = $1
             ORDER BY saved_at LIMIT {_MAX_SAVED_TIER}
         ) t) AS saved_job_ts,

        (SELECT min(cm.created_at)
           FROM public.chat_sessions cs
           JOIN public.chat_messages cm ON cm.session_id = cs.id
          WHERE cs.applicant_id = $1 AND cm.role = 'user') AS first_chat_at,

        (SELECT min(dm.created_at)
           FROM public.conversations cv
           JOIN public.direct_messages dm ON dm.conversation_id = cv.id
          WHERE cv.applicant_id = $1 AND dm.sender_role = 'applicant')
            AS first_employer_message_at,

        (SELECT min(created_at) FROM public.hire_outcomes
          WHERE applicant_id = $1) AS first_hire_at,

        (SELECT min(created_at) FROM public.engagement_events
          WHERE applicant_id = $1 AND event_type = 'profile_completed')
            AS profile_completed_at
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _nth(timestamps: Sequence[Any] | None, n: int) -> Optional[str]:
    """ISO timestamp of the n-th (1-based) qualifying row, if it exists."""
    if not timestamps or len(timestamps) < n:
        return None
    return _iso(timestamps[n - 1])


def _count_badge(
    key: str,
    title: str,
    description: str,
    count: int,
    target: int,
    timestamps: Sequence[Any] | None,
) -> Badge:
    earned = count >= target
    return Badge(
        key=key,
        title=title,
        description=description,
        earned=earned,
        earned_at=_nth(timestamps, target) if earned else None,
        progress=BadgeProgress(current=min(count, target), target=target),
    )


def _flag_badge(
    key: str,
    title: str,
    description: str,
    at: Any,
) -> Badge:
    earned = at is not None
    return Badge(
        key=key,
        title=title,
        description=description,
        earned=earned,
        earned_at=_iso(at) if earned else None,
        progress=BadgeProgress(current=1 if earned else 0, target=1),
    )


def build_badges(profile_row: dict[str, Any], activity: dict[str, Any]) -> list[Badge]:
    """Pure badge assembly — unit-testable without a database."""
    completeness = _compute_completeness(profile_row)
    profile_earned = completeness >= PROFILE_TARGET

    application_count = int(activity.get("application_count") or 0)
    application_ts = activity.get("application_ts") or []
    credential_count = int(activity.get("credential_count") or 0)
    credential_ts = activity.get("credential_ts") or []
    verified_count = int(activity.get("verified_credential_count") or 0)
    saved_count = int(activity.get("saved_job_count") or 0)
    saved_ts = activity.get("saved_job_ts") or []

    return [
        Badge(
            key="profile_complete",
            title="Profile complete",
            description="Your profile is filled in enough to rank against every job.",
            earned=profile_earned,
            earned_at=_iso(activity.get("profile_completed_at")) if profile_earned else None,
            progress=BadgeProgress(
                current=min(completeness, PROFILE_TARGET), target=PROFILE_TARGET
            ),
        ),
        _count_badge(
            "first_credential",
            "First credential on file",
            "You added a certificate, license, or card to your record.",
            credential_count, 1, credential_ts,
        ),
        _count_badge(
            "five_credentials",
            "Five credentials on file",
            "A full set of credentials employers can check.",
            credential_count, 5, credential_ts,
        ),
        _flag_badge(
            "credential_verified",
            "Verified credential",
            "One of your credentials was confirmed by the issuer or SKILLED.",
            activity.get("first_verified_credential_at") if verified_count > 0 else None,
        ),
        _count_badge(
            "ten_jobs_saved",
            "Ten jobs shortlisted",
            "You marked ten jobs worth a closer look.",
            saved_count, 10, saved_ts,
        ),
        _count_badge(
            "first_application",
            "First application sent",
            "You applied to your first job through SKILLED.",
            application_count, 1, application_ts,
        ),
        _count_badge(
            "ten_applications",
            "Ten applications in",
            "Ten applications submitted, the volume that usually lands offers.",
            application_count, 10, application_ts,
        ),
        _flag_badge(
            "planning_chat",
            "Planning session started",
            "You worked through a job with the planning assistant.",
            activity.get("first_chat_at"),
        ),
        _flag_badge(
            "first_employer_message",
            "Talking to an employer",
            "You sent your first message to a hiring employer.",
            activity.get("first_employer_message_at"),
        ),
        _flag_badge(
            "hired",
            "Hired",
            "An employer reported hiring you for a job you found here.",
            activity.get("first_hire_at"),
        ),
    ]


# ---------------------------------------------------------------------------
# GET /applicant/me/badges
# ---------------------------------------------------------------------------

@router.get("/badges", response_model=BadgesResponse)
async def get_my_badges(
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> BadgesResponse:
    """Return every badge with honest progress toward the ones not yet earned."""
    async with get_db() as conn:
        profile_row = await conn.fetchrow(
            _PROFILE_SQL, current_user.user_id, current_user.view_as_applicant_id
        )
        if not profile_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Applicant profile not found.",
            )
        activity = await conn.fetchrow(_ACTIVITY_SQL, profile_row["id"])

    badges = build_badges(dict(profile_row), dict(activity) if activity else {})
    return BadgesResponse(
        badges=badges,
        earned_count=sum(1 for b in badges if b.earned),
        total_count=len(badges),
    )


__all__: list[str] = ["router", "build_badges", "Badge", "BadgeProgress"]
