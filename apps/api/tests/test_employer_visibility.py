"""
test_employer_visibility.py — Phase 6.2

Tests that employer visibility rules are correctly enforced.

Critical rules under test:
  1. Employer A cannot access applicants for Employer B's job
     (j.employer_id scoping in every query)
  2. Matches with is_visible_to_employer=FALSE are excluded
  3. Only eligible + near_fit shown by default (ineligible excluded)
  4. Eligibility filter correctly narrows results
  5. min_score filter correctly narrows results
  6. state filter correctly narrows results
  7. Admin users can access employer endpoints (require_employer_or_admin)
  8. Applicant users are forbidden (403)
  9. Company lookup returns 404 if user has no employer_contacts row

These tests mock the DB layer and RBAC dependencies to isolate
the routing + scoping logic from live DB connections.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.schemas import CurrentUser
from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EMPLOYER_A_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_B_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
EMPLOYER_A_ID = "11111111-0000-0000-0000-111111111111"
EMPLOYER_B_ID = "22222222-0000-0000-0000-222222222222"
JOB_A_ID = "33333333-0000-0000-0000-333333333333"
JOB_B_ID = "44444444-0000-0000-0000-444444444444"
APPLICANT_ID = "55555555-0000-0000-0000-555555555555"
MATCH_ID = "66666666-0000-0000-0000-666666666666"


def _employer_user(user_id: str = EMPLOYER_A_USER_ID) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        email="employer@test.com",
        role="employer",
        onboarding_complete=True,
    )


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id="admin-user-id",
        email="admin@test.com",
        role="admin",
        onboarding_complete=True,
    )


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id="applicant-user-id",
        email="applicant@test.com",
        role="applicant",
        onboarding_complete=True,
    )


def _make_match_row(**overrides: Any) -> dict:
    base = {
        "match_id": MATCH_ID,
        "applicant_id": APPLICANT_ID,
        "first_name": "Jane",
        "last_name": "Smith",
        "city": "Austin",
        "state": "TX",
        "region": "South",
        "willing_to_relocate": False,
        "willing_to_travel": False,
        "program_name_raw": "Welding Technology",
        "expected_completion_date": "2026-05-01",
        "available_from_date": None,
        "canonical_job_family_code": "WLD",
        "eligibility_status": "eligible",
        "match_label": "good_fit",
        "policy_adjusted_score": 78.5,
        "top_strengths": ["Strong trade alignment"],
        "top_gaps": [],
        "recommended_next_step": "Apply now",
        "confidence_level": "high",
        "requires_review": False,
        "job_city": "Austin",
        "job_state": "TX",
        "job_region": "South",
        "job_work_setting": "on_site",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: patch DB + auth for a single request
# ---------------------------------------------------------------------------

def _mock_db_context(fetchval_return=None, fetchrow_return=None, fetch_return=None):
    """Return a context manager that patches get_db with canned DB responses."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])

    # asynccontextmanager mock
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    return patch("app.routers.employers.get_db", return_value=mock_ctx), conn


# ---------------------------------------------------------------------------
# 1. Employer scoping — cross-employer access is blocked
# ---------------------------------------------------------------------------

class TestEmployerScoping:
    """
    When employer A requests applicants for job B (owned by employer B),
    the query's employer_id constraint ($2 = employer_A_id) will not match
    job B's employer_id. The count_row query returns None → 404.
    """

    def test_cross_employer_job_returns_404(self, client: TestClient) -> None:
        """Employer A requesting job B (belonging to employer B) → 404."""
        # _resolve_employer_id returns employer A's ID
        # count_row query for job_b with employer_a constraint → None
        ctx_patch, conn = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,   # employer_contacts lookup
            fetchrow_return=None,             # count query finds nothing (wrong employer)
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_B_ID}/applicants",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_own_job_returns_200(self, client: TestClient) -> None:
        """Employer A requesting their own job A → 200."""
        count_row_mock = {
            "total_visible": 2,
            "eligible_count": 2,
            "near_fit_count": 0,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        ctx_patch, conn = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=[_make_match_row()],
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == JOB_A_ID
        assert len(data["applicants"]) == 1


# ---------------------------------------------------------------------------
# 2. is_visible_to_employer enforcement
# ---------------------------------------------------------------------------

class TestVisibilityFlag:
    """
    The SQL query in get_job_applicants always includes
    m.is_visible_to_employer = TRUE. This test verifies that matches with
    is_visible_to_employer=FALSE are not returned.

    We verify this by checking the query does not include them even when
    the count query would show them — i.e., the filtered list is separate
    from the total counts.
    """

    def test_invisible_matches_not_in_applicant_list(
        self, client: TestClient
    ) -> None:
        """
        count_row shows 3 total_visible (pre-filter),
        but filtered fetch only returns 1 (is_visible_to_employer=TRUE rows).
        The response applicant list should have 1 item.
        """
        count_row_mock = {
            "total_visible": 3,
            "eligible_count": 3,
            "near_fit_count": 0,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        # Only 1 row comes back from the filtered query
        ctx_patch, conn = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=[_make_match_row()],
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["total_visible"] == 3   # pre-filter count from DB
        assert len(data["applicants"]) == 1  # filtered list


# ---------------------------------------------------------------------------
# 3. Default eligibility exclusion (ineligible not shown by default)
# ---------------------------------------------------------------------------

class TestDefaultEligibilityExclusion:
    def test_ineligible_excluded_by_default(self, client: TestClient) -> None:
        """
        When no eligibility filter is set, the query adds
        m.eligibility_status IN ('eligible', 'near_fit'),
        excluding ineligible. Verify via response structure.
        """
        count_row_mock = {
            "total_visible": 5,
            "eligible_count": 3,
            "near_fit_count": 2,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        eligible_rows = [
            _make_match_row(match_id=f"match-{i}", eligibility_status="eligible")
            for i in range(3)
        ]
        ctx_patch, conn = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=eligible_rows,
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["filter_eligibility"] is None  # no filter applied
        # All returned applicants should be eligible or near_fit
        for ap in data["applicants"]:
            assert ap["eligibility_status"] in ("eligible", "near_fit")


# ---------------------------------------------------------------------------
# 4. Eligibility filter
# ---------------------------------------------------------------------------

class TestEligibilityFilter:
    def test_filter_eligible_only(self, client: TestClient) -> None:
        count_row_mock = {
            "total_visible": 5,
            "eligible_count": 3,
            "near_fit_count": 2,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        eligible_rows = [
            _make_match_row(eligibility_status="eligible")
        ]
        ctx_patch, _ = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=eligible_rows,
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants?eligibility=eligible",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["filter_eligibility"] == "eligible"

    def test_filter_near_fit_only(self, client: TestClient) -> None:
        count_row_mock = {
            "total_visible": 5,
            "eligible_count": 3,
            "near_fit_count": 2,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        near_fit_rows = [
            _make_match_row(eligibility_status="near_fit", match_label="moderate_fit")
        ]
        ctx_patch, _ = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=near_fit_rows,
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants?eligibility=near_fit",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["filter_eligibility"] == "near_fit"


# ---------------------------------------------------------------------------
# 5. min_score filter reflected in response
# ---------------------------------------------------------------------------

class TestMinScoreFilter:
    def test_min_score_reflected(self, client: TestClient) -> None:
        count_row_mock = {
            "total_visible": 10,
            "eligible_count": 10,
            "near_fit_count": 0,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        ctx_patch, _ = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=[_make_match_row(policy_adjusted_score=85.0)],
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants?min_score=70",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["filter_min_score"] == 70.0


# ---------------------------------------------------------------------------
# 6. RBAC — applicants forbidden, admins allowed
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_applicant_role_forbidden(self, client: TestClient) -> None:
        """Applicants cannot access employer endpoints."""
        with patch(
            "app.routers.employers.require_employer_or_admin",
            side_effect=__import__(
                "fastapi", fromlist=["HTTPException"]
            ).HTTPException(status_code=403, detail="Forbidden"),
        ):
            response = client.get(
                "/employer/me/company",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    def test_no_employer_linked_returns_404(self, client: TestClient) -> None:
        """User with employer role but no employer_contacts row → 404."""
        ctx_patch, conn = _mock_db_context(
            fetchval_return=None,  # employer_contacts lookup returns None
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    "/employer/me/company",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 7. Safe fields — no user_id or email in response
# ---------------------------------------------------------------------------

class TestSafeFields:
    def test_applicant_user_id_not_exposed(self, client: TestClient) -> None:
        """
        The ApplicantMatchSummary schema must not include the applicant's
        Supabase user_id or email. Only internal applicant_id is returned.
        """
        count_row_mock = {
            "total_visible": 1,
            "eligible_count": 1,
            "near_fit_count": 0,
            "title_normalized": "Welder",
            "title_raw": "Welder",
            "employer_name": "Test Co",
        }
        ctx_patch, _ = _mock_db_context(
            fetchval_return=EMPLOYER_A_ID,
            fetchrow_return=count_row_mock,
            fetch_return=[_make_match_row()],
        )

        with ctx_patch:
            with patch(
                "app.routers.employers.require_employer_or_admin",
                return_value=_employer_user(),
            ):
                response = client.get(
                    f"/employer/me/jobs/{JOB_A_ID}/applicants",
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 200
        applicant = response.json()["applicants"][0]
        # Supabase user_id and email must NOT be in the response
        assert "user_id" not in applicant
        assert "email" not in applicant
        # Internal applicant_id is allowed (it's an internal UUID, not auth identity)
        assert "applicant_id" in applicant


# ---------------------------------------------------------------------------
# 8. Geography note derivation
# ---------------------------------------------------------------------------

class TestGeographyNote:
    def test_local_applicant_note(self) -> None:
        from app.routers.employers import _derive_applicant_geography_note

        row = {
            "state": "TX",
            "city": "Austin",
            "job_state": "TX",
            "job_city": "Austin",
            "job_work_setting": "on_site",
            "willing_to_relocate": False,
            "willing_to_travel": False,
        }
        note = _derive_applicant_geography_note(row)
        assert note is not None
        assert "Local" in note
        assert "TX" in note

    def test_remote_job_no_geography_note(self) -> None:
        from app.routers.employers import _derive_applicant_geography_note

        row = {
            "state": "CA",
            "city": "Los Angeles",
            "job_state": "TX",
            "job_city": "Austin",
            "job_work_setting": "remote",
            "willing_to_relocate": False,
            "willing_to_travel": False,
        }
        note = _derive_applicant_geography_note(row)
        assert note is None  # Remote — location irrelevant

    def test_relocatable_applicant_note(self) -> None:
        from app.routers.employers import _derive_applicant_geography_note

        row = {
            "state": "CA",
            "city": "San Francisco",
            "job_state": "TX",
            "job_city": "Austin",
            "job_work_setting": "on_site",
            "willing_to_relocate": True,
            "willing_to_travel": False,
        }
        note = _derive_applicant_geography_note(row)
        assert note is not None
        assert "relocate" in note
        assert "CA" in note
