"""
test_matching_admin.py — /admin/matching config API (Phase 9).

Covers:
  1. RBAC: non-admin rejected on every route.
  2. GET /admin/matching/config returns a complete, current-schema config
     (missing new sections filled from code defaults).
  3. POST /preview validates the candidate config (422 with named errors),
     and computes honest old-vs-new sample math.
  4. POST /activate refuses invalid configs, writes a NEW versioned
     policy_configs row, deactivates the old one, writes audit_logs, and
     fires the recompute.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.config import ScoringConfig, config_to_dict

from app.auth.dependencies import require_admin, require_applicant
from app.auth.schemas import CurrentUser
from app.main import app


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id="7e51b303-1f9e-4b0a-9d55-000000000001",
        email="admin@test.com",
        role="admin",
        onboarding_complete=True,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _overrides():
    app.dependency_overrides[require_admin] = _admin_user
    yield
    app.dependency_overrides.clear()


def _mock_db(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.matching_admin.get_db", return_value=ctx)


def _tx_conn() -> AsyncMock:
    """AsyncMock conn whose .transaction() works as an async context manager."""
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _valid_config() -> dict:
    return config_to_dict(ScoringConfig())


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_non_admin_rejected(self, client):
        from app.auth.dependencies import get_current_user
        app.dependency_overrides.clear()
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="7e51b303-1f9e-4b0a-9d55-000000000002",
            email="worker@test.com", role="applicant", onboarding_complete=True,
        )
        r = client.get("/admin/matching/config")
        assert r.status_code == 403

    def test_unauthenticated_rejected(self, client, mock_supabase_client):
        app.dependency_overrides.clear()
        assert client.get("/admin/matching/config").status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /admin/matching/config
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_returns_complete_config_with_defaults_filled(self, client):
        conn = AsyncMock()
        # Stored active row predates the new sections — GET must fill them.
        conn.fetchrow = AsyncMock(side_effect=[
            {  # active policy row
                "id": "pc-1", "version": "v1", "description": "seed",
                "config": {"version": "v1", "structured_score": {"weights": {
                    "trade_program_alignment": 25, "geography_alignment": 20,
                    "credential_readiness": 15, "timing_readiness": 10,
                    "experience_internship_alignment": 10, "industry_alignment": 5,
                    "compensation_alignment": 5, "work_style_signal_alignment": 5,
                    "employer_soft_pref_alignment": 5}}},
                "activated_at": "2026-03-17", "activated_by": None,
                "created_at": "2026-03-17",
            },
            {"kind": "full", "status": "complete", "started_at": "x",
             "completed_at": "y", "error": None},                # last run
            {"total": 132444, "eligible": 37, "near_fit": 4015,
             "nearby_tier": 0, "applicants_with_any_tier": 100},  # distribution
        ])
        conn.fetch = AsyncMock(return_value=[])  # history
        with _mock_db(conn):
            r = client.get("/admin/matching/config")
        assert r.status_code == 200
        body = r.json()
        cfg = body["config"]
        # New sections present even though the stored row lacks them
        assert cfg["relaxation"]["min_results"] == 5
        assert cfg["match_labels"]["strong_fit_min"] == 80
        assert cfg["gates"]["geography_feasibility"] is True
        assert cfg["geography_relaxation"]["relax_unknown_prefs"] is True
        assert body["active"]["version"] == "v1"
        assert body["last_recompute"]["status"] == "complete"


# ---------------------------------------------------------------------------
# POST /admin/matching/preview
# ---------------------------------------------------------------------------

class TestPreview:
    def test_invalid_weights_rejected_with_named_errors(self, client):
        bad = _valid_config()
        bad["structured_score"]["weights"]["trade_program_alignment"] = 90
        r = client.post("/admin/matching/preview", json={"config": bad})
        assert r.status_code == 422
        assert "sum to 100" in r.json()["detail"]

    def test_normalize_flag_rescues_drifted_weights(self, client):
        drifted = _valid_config()
        drifted["structured_score"]["weights"]["trade_program_alignment"] = 90
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[[], [], [], []])  # sample, jobs, employers, old
        conn.fetchval = AsyncMock(return_value=337)
        with _mock_db(conn):
            r = client.post(
                "/admin/matching/preview",
                json={"config": drifted, "normalize": True},
            )
        assert r.status_code == 200

    def test_preview_math_old_vs_new(self, client):
        """Sampled applicant near a job in another trade: old side (from the
        matches table) shows nothing; new side (relaxation on) shows the
        nearby tier — an honest, labeled diff."""
        applicant_row = {
            "id": "aaaaaaaa-0000-0000-0000-000000000001",
            "first_name": "Scholar", "last_name": "0037",
            "program_name_raw": "Nursing", "state": "CT", "region": "northeast",
            "city": "Shelton", "willing_to_relocate": False,
            "willing_to_travel": False, "commute_radius_miles": None,
            "lat": 41.30, "lng": -73.10, "experience_raw": None, "bio_raw": None,
            "career_goals_raw": None, "expected_completion_date": None,
            "available_from_date": None, "travel_preference": None,
            "relocation_preference": "stay_current", "relocation_states": None,
            "has_internship": None, "internship_details": None,
            "essay_background": None, "essay_impact": None,
            "enrollment_status": None, "career_path": None, "program_field": None,
            "canonical_job_family_code": "nursing",
        }
        job_row = {
            "id": "bbbbbbbb-0000-0000-0000-000000000001",
            "employer_id": "cccccccc-0000-0000-0000-000000000001",
            "title_raw": "Assembler", "title_normalized": "Assembler",
            "description_raw": "Assembly role", "requirements_raw": None,
            "preferred_qualifications_raw": None, "state": "CT",
            "region": "northeast", "city": "Bridgeport", "lat": 41.19,
            "lng": -73.20, "work_setting": "on_site", "travel_requirement": None,
            "pay_min": 20, "pay_max": 25, "pay_type": "hourly",
            "required_credentials": None, "experience_level": "entry",
            "canonical_job_family_code": "manufacturing",
            "required_experience_years": None,
        }
        employer_row = {"id": "cccccccc-0000-0000-0000-000000000001",
                        "name": "Acme", "is_partner": False}
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[
            [applicant_row],   # sample
            [job_row],         # jobs
            [employer_row],    # employers
            [],                # old matches (none surfaced today)
        ])
        conn.fetchval = AsyncMock(return_value=337)
        with _mock_db(conn):
            r = client.post(
                "/admin/matching/preview",
                json={"config": _valid_config(), "sample_size": 3},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["old_totals"]["nearby"] == 0
        assert body["new_totals"]["nearby"] == 1
        assert body["new_totals"]["eligible"] == 0   # no nonsense promotion
        spot = body["spotlight"][0]
        assert spot["new"]["top"][0]["match_tier"] == "nearby"
        assert spot["new"]["top"][0]["eligibility_status"] == "ineligible"


# ---------------------------------------------------------------------------
# POST /admin/matching/activate
# ---------------------------------------------------------------------------

class TestActivate:
    def test_invalid_config_never_activates(self, client):
        bad = _valid_config()
        bad["match_labels"] = {"strong_fit_min": 10, "good_fit_min": 60,
                               "moderate_fit_min": 40}
        r = client.post("/admin/matching/activate",
                        json={"config": bad, "note": "should fail"})
        assert r.status_code == 422

    def test_activate_versions_audits_and_recomputes(self, client):
        conn = _tx_conn()
        conn.fetchrow = AsyncMock(side_effect=[
            None,   # _fetch_active_config_dict: no active row
            {"id": "pc-2", "version": "v2", "activated_at": "2026-08-01"},  # insert
        ])
        conn.fetch = AsyncMock(return_value=[{"version": "v1"}])  # versions
        conn.execute = AsyncMock()
        recompute = AsyncMock()
        with _mock_db(conn), patch(
            "app.worker.scheduler._locked_recompute", recompute
        ):
            r = client.post(
                "/admin/matching/activate",
                json={"config": _valid_config(), "note": "tighten labels"},
            )
        assert r.status_code == 201
        body = r.json()
        assert body["version"] == "v2"
        assert body["recompute_started"] is True

        # Old active row deactivated + new row inserted
        executed_sql = " ".join(
            str(c.args[0]) for c in conn.execute.call_args_list
        )
        assert "is_active = FALSE" in executed_sql
        insert_call = conn.fetchrow.call_args_list[1]
        assert "INSERT INTO public.policy_configs" in insert_call.args[0]
        # The config param must be cast text->jsonb: a bare ::jsonb makes
        # asyncpg store a jsonb STRING scalar, breaking config->'...' lookups.
        assert "::text::jsonb" in insert_call.args[0]
        stored = json.loads(insert_call.args[2])
        assert stored["relaxation"]["min_results"] == 5
        assert stored["version"] == "v2"
        # Audit row written (write_audit uses conn.execute with audit_logs)
        assert "audit_logs" in executed_sql
        # Recompute fired
        recompute.assert_called_once()
