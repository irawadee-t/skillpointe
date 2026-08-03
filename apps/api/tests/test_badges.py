"""
test_badges.py — GET /applicant/me/badges

Covers the two things that matter for an achievement system built on real data:
  - counting badges tier correctly and report the timestamp of the row that
    actually earned them (the 10th application, not "now")
  - an UNEARNED badge reports honest progress ("7 of 10"), never a locked
    mystery with progress 0

Mock-DB style (same approach as test_interest_signal.py): patch get_db in the
router module and override the auth dependency.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.badges import build_badges

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=APPLICANT_USER_ID,
        email="applicant@test.local",
        role="applicant",
        onboarding_complete=True,
    )


def _profile_row(**overrides: Any) -> dict[str, Any]:
    """A profile that scores 100 on _compute_completeness unless stripped."""
    row: dict[str, Any] = {
        "id": APPLICANT_ID,
        "first_name": "Jane",
        "last_name": "Doe",
        "program_name_raw": "Industrial Maintenance",
        "city": "Carrollton",
        "state": "GA",
        "willing_to_relocate": False,
        "willing_to_travel": False,
        "expected_completion_date": "2026-05-01",
        "available_from_date": None,
        "enrollment_status": "enrolled",
        "degree_type": "certificate",
        "school_name": "West Georgia Tech",
        "program_field": "Industrial",
        "gpa": 3.4,
        "travel_preference": "within_state",
        "relocation_preference": "stay_current",
        "age_range": "25-34",
        "gender": None,
        "has_internship": True,
        "canonical_job_family_code": "IND_MAINT",
    }
    row.update(overrides)
    return row


def _activity(**overrides: Any) -> dict[str, Any]:
    act: dict[str, Any] = {
        "application_count": 0,
        "application_ts": [],
        "credential_count": 0,
        "credential_ts": [],
        "verified_credential_count": 0,
        "first_verified_credential_at": None,
        "saved_job_count": 0,
        "saved_job_ts": [],
        "first_chat_at": None,
        "first_employer_message_at": None,
        "first_hire_at": None,
        "profile_completed_at": None,
    }
    act.update(overrides)
    return act


def _by_key(badges: list[Any]) -> dict[str, Any]:
    return {b.key: b for b in badges}


# ---------------------------------------------------------------------------
# Counting logic
# ---------------------------------------------------------------------------

def test_ten_applications_earned_at_is_the_tenth_application() -> None:
    stamps = [BASE + timedelta(days=i) for i in range(10)]
    badges = _by_key(
        build_badges(
            _profile_row(),
            _activity(application_count=10, application_ts=stamps),
        )
    )

    first = badges["first_application"]
    assert first.earned is True
    assert first.progress.current == 1 and first.progress.target == 1
    # earned on the FIRST application, not the latest
    assert first.earned_at == stamps[0].isoformat()

    ten = badges["ten_applications"]
    assert ten.earned is True
    assert ten.progress.current == 10 and ten.progress.target == 10
    # earned at the moment the 10th landed
    assert ten.earned_at == stamps[9].isoformat()


def test_unearned_badge_reports_honest_progress() -> None:
    stamps = [BASE + timedelta(days=i) for i in range(7)]
    badges = _by_key(
        build_badges(
            _profile_row(),
            _activity(application_count=7, application_ts=stamps),
        )
    )

    ten = badges["ten_applications"]
    assert ten.earned is False
    assert ten.earned_at is None
    # "7 of 10" — a goal, not a locked mystery
    assert (ten.progress.current, ten.progress.target) == (7, 10)

    # A badge with zero activity is still honest about its target.
    hired = badges["hired"]
    assert hired.earned is False
    assert (hired.progress.current, hired.progress.target) == (0, 1)

    # Five-credential tier with three on file.
    creds = build_badges(
        _profile_row(),
        _activity(credential_count=3, credential_ts=stamps[:3]),
    )
    five = _by_key(creds)["five_credentials"]
    assert five.earned is False
    assert (five.progress.current, five.progress.target) == (3, 5)
    assert _by_key(creds)["first_credential"].earned is True


def test_profile_badge_thresholds_at_eighty() -> None:
    full = _by_key(build_badges(_profile_row(), _activity()))["profile_complete"]
    assert full.earned is True
    assert full.progress.target == 80

    # Strip the heavily weighted fields to drop below 80.
    thin = _by_key(
        build_badges(
            _profile_row(
                canonical_job_family_code=None,
                state=None,
                city=None,
                expected_completion_date=None,
                available_from_date=None,
            ),
            _activity(),
        )
    )["profile_complete"]
    assert thin.earned is False
    assert thin.progress.current < 80


def test_verified_credential_requires_verification_level() -> None:
    # Six self-reported credentials, none verified.
    badges = _by_key(
        build_badges(
            _profile_row(),
            _activity(
                credential_count=6,
                credential_ts=[BASE + timedelta(days=i) for i in range(5)],
                verified_credential_count=0,
                first_verified_credential_at=None,
            ),
        )
    )
    assert badges["five_credentials"].earned is True
    assert badges["credential_verified"].earned is False

    verified_at = BASE + timedelta(days=30)
    badges = _by_key(
        build_badges(
            _profile_row(),
            _activity(
                credential_count=6,
                verified_credential_count=1,
                first_verified_credential_at=verified_at,
            ),
        )
    )
    assert badges["credential_verified"].earned is True
    assert badges["credential_verified"].earned_at == verified_at.isoformat()


# ---------------------------------------------------------------------------
# Endpoint wiring
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[require_applicant] = _applicant_user
    yield
    app.dependency_overrides.pop(require_applicant, None)


def test_endpoint_returns_all_badges_with_counts(client: TestClient) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        side_effect=[
            _profile_row(),
            _activity(
                application_count=7,
                application_ts=[BASE + timedelta(days=i) for i in range(7)],
                credential_count=6,
                credential_ts=[BASE + timedelta(days=i) for i in range(5)],
                first_chat_at=BASE,
            ),
        ]
    )
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.badges.get_db", return_value=ctx):
        res = client.get("/applicant/me/badges")

    assert res.status_code == 200
    body = res.json()
    assert body["total_count"] == len(body["badges"]) == 10
    keyed = {b["key"]: b for b in body["badges"]}
    assert keyed["ten_applications"] == {
        **keyed["ten_applications"],
        "earned": False,
        "earned_at": None,
        "progress": {"current": 7, "target": 10},
    }
    assert keyed["planning_chat"]["earned"] is True
    assert body["earned_count"] == sum(1 for b in body["badges"] if b["earned"])
    # No badge may be earned without a timestamp — every source records one.
    for b in body["badges"]:
        if b["earned"] and b["key"] != "profile_complete":
            assert b["earned_at"], f"{b['key']} earned without a timestamp"


def test_endpoint_404_when_no_applicant_profile(client: TestClient) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.badges.get_db", return_value=ctx):
        res = client.get("/applicant/me/badges")

    assert res.status_code == 404
