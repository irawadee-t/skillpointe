"""
test_viz_explanation.py — GET /viz/matches/{match_id}/explanation

Covers:
  - bucket math: width_bucket fold (dense 20 buckets, edge clamping of
    bucket 0 and bucket 21, status counts preserved)
  - small-n honesty: n < SMALL_N returns mode="points" with every point
  - auth matrix: applicant owner / other applicant / employer owner / other
    employer / admin / institution / hidden-from-applicant
  - null-handling passthrough: null_handling_applied survives to the payload
  - threshold parsing: active policy config wins, defaults otherwise

Mock-DB style (same approach as test_interest_signal.py): patch get_db in the
router module, override the auth dependency, assert on the JSON returned.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_authenticated
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.viz_analytics import (
    BUCKET_COUNT,
    assemble_buckets,
    parse_label_thresholds,
)

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
ADMIN_USER_ID = "cccccccc-0000-0000-0000-cccccccccccc"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
OTHER_APPLICANT_ID = "11111111-9999-0000-0000-111111111111"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"
OTHER_EMPLOYER_ID = "22222222-9999-0000-0000-222222222222"
JOB_ID = "33333333-0000-0000-0000-333333333333"
MATCH_ID = "77777777-0000-0000-0000-777777777777"

URL = f"/viz/matches/{MATCH_ID}/explanation"


# ---------------------------------------------------------------------------
# Pure bucket-math tests
# ---------------------------------------------------------------------------

class TestAssembleBuckets:
    def test_dense_and_ordered(self):
        buckets = assemble_buckets(
            [
                {"bucket": 3, "eligible": 0, "near_fit": 2, "ineligible": 5},
                {"bucket": 15, "eligible": 7, "near_fit": 0, "ineligible": 0},
            ]
        )
        assert len(buckets) == BUCKET_COUNT
        # Every bucket spans exactly 100 / BUCKET_COUNT points, zero-based.
        assert buckets[0].x0 == 0.0 and buckets[-1].x1 == 100.0
        assert buckets[2].x0 == 10.0 and buckets[2].x1 == 15.0
        assert buckets[2].near_fit == 2 and buckets[2].ineligible == 5
        assert buckets[14].eligible == 7
        # Untouched buckets are present with zero counts (dense output).
        assert buckets[0].eligible == buckets[0].near_fit == buckets[0].ineligible == 0

    def test_edge_buckets_clamped(self):
        # width_bucket returns BUCKET_COUNT + 1 for score == 100 and 0 for < 0;
        # both must fold into the nearest real bucket, never be dropped.
        buckets = assemble_buckets(
            [
                {"bucket": BUCKET_COUNT + 1, "eligible": 3, "near_fit": 0, "ineligible": 0},
                {"bucket": BUCKET_COUNT, "eligible": 1, "near_fit": 0, "ineligible": 0},
                {"bucket": 0, "eligible": 0, "near_fit": 0, "ineligible": 4},
            ]
        )
        assert buckets[-1].eligible == 4  # 3 clamped + 1 native
        assert buckets[0].ineligible == 4
        total = sum(b.eligible + b.near_fit + b.ineligible for b in buckets)
        assert total == 8  # nothing dropped

    def test_none_counts_are_zero(self):
        buckets = assemble_buckets(
            [{"bucket": 5, "eligible": None, "near_fit": 1, "ineligible": None}]
        )
        assert buckets[4].eligible == 0
        assert buckets[4].near_fit == 1


class TestParseThresholds:
    def test_defaults_when_missing(self):
        t = parse_label_thresholds(None)
        assert t.strong_fit_min == 80.0 and t.good_fit_min == 60.0

    def test_json_string_from_db(self):
        t = parse_label_thresholds('{"strong_fit_min": 85, "good_fit_min": 55}')
        assert t.strong_fit_min == 85.0 and t.good_fit_min == 55.0

    def test_garbage_falls_back(self):
        t = parse_label_thresholds("not json")
        assert t.strong_fit_min == 80.0 and t.good_fit_min == 60.0


# ---------------------------------------------------------------------------
# Endpoint fixtures
# ---------------------------------------------------------------------------

def _user(role: str, user_id: str) -> CurrentUser:
    return CurrentUser(
        user_id=user_id, email=f"{role}@test.local", role=role, onboarding_complete=True
    )


def _match_row(visible: bool = True) -> dict[str, Any]:
    return {
        "match_id": MATCH_ID,
        "applicant_id": APPLICANT_ID,
        "job_id": JOB_ID,
        "eligibility_status": "near_fit",
        "match_label": "moderate_fit",
        "match_tier": "strict",
        "tier_reason": None,
        "policy_adjusted_score": 47.5,
        "base_fit_score": 47.5,
        "distance_miles": 18.2,
        "confidence_level": "medium",
        "top_strengths": ["Welding program aligns with the trade"],
        "top_gaps": ["OSHA 10 not yet earned"],
        "required_missing_items": ["OSHA 10"],
        "recommended_next_step": "Complete OSHA 10 certification",
        "hard_gate_rationale": {
            "required_credential_compatibility": {
                "result": "near_fit",
                "reason": "Missing OSHA 10 (attainable)",
                "severity": "soft",
            }
        },
        "is_visible_to_applicant": visible,
        "title_normalized": "Welder I",
        "title_raw": "Welder",
        "employer_id": EMPLOYER_ID,
        "employer_name": "Southwire",
    }


def _dim_rows() -> list[dict[str, Any]]:
    return [
        {
            "dimension": "trade_program_alignment",
            "weight": 25.0,
            "raw_score": 80.0,
            "weighted_score": 20.0,
            "rationale": "Welding program maps directly to this job family",
            "null_handling_applied": False,
        },
        {
            "dimension": "compensation_alignment",
            "weight": 5.0,
            "raw_score": 50.0,
            "weighted_score": 2.5,
            "rationale": "No desired pay on file; neutral default used",
            "null_handling_applied": True,
        },
    ]


def _head_row(n: int) -> dict[str, Any]:
    return {"n": n, "median": 42.0}


def _bucket_rows() -> list[dict[str, Any]]:
    return [
        {"bucket": 8, "eligible": 0, "near_fit": 30, "ineligible": 10},
        {"bucket": 14, "eligible": 25, "near_fit": 0, "ineligible": 0},
    ]


def _point_rows(k: int) -> list[dict[str, Any]]:
    return [{"score": 10.0 + i, "status": "near_fit"} for i in range(k)]


def _mock_conn(
    fetchrow_side: list[Any],
    fetchval_side: list[Any] | None = None,
    fetch_side: list[Any] | None = None,
):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    if fetchval_side is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    if fetch_side is not None:
        conn.fetch = AsyncMock(side_effect=fetch_side)
    return conn


def _patch_db(conn: AsyncMock):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.viz_analytics.get_db", return_value=ctx)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[require_authenticated] = lambda: user


def _happy_conn(visible: bool = True, n_each: int = 65) -> AsyncMock:
    """Conn scripted for the full happy path (both contexts bucketed)."""
    return _mock_conn(
        # fetchrow: match row, applicant head, job head
        fetchrow_side=[_match_row(visible), _head_row(n_each), _head_row(n_each)],
        # fetchval: (maybe applicant/employer resolution first) + thresholds —
        # tests that need resolution build their own conn.
        fetchval_side=[None],
        # fetch: dimensions, applicant buckets, job buckets
        fetch_side=[_dim_rows(), _bucket_rows(), _bucket_rows()],
    )


# ---------------------------------------------------------------------------
# Auth matrix
# ---------------------------------------------------------------------------

class TestAuthMatrix:
    def test_admin_ok(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _happy_conn()
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 200
        body = res.json()
        assert body["match"]["match_id"] == MATCH_ID
        assert body["context_applicant"]["mode"] == "buckets"

    def test_applicant_owner_ok(self, client: TestClient):
        _as(_user("applicant", APPLICANT_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(), _head_row(65), _head_row(65)],
            fetchval_side=[APPLICANT_ID, None],  # applicant lookup, thresholds
            fetch_side=[_dim_rows(), _bucket_rows(), _bucket_rows()],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 200

    def test_other_applicant_404(self, client: TestClient):
        _as(_user("applicant", APPLICANT_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row()],
            fetchval_side=[OTHER_APPLICANT_ID],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 404

    def test_applicant_hidden_match_404(self, client: TestClient):
        # is_visible_to_applicant=FALSE must 404 for the owner applicant too.
        _as(_user("applicant", APPLICANT_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(visible=False)],
            fetchval_side=[APPLICANT_ID],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 404

    def test_employer_owner_ok(self, client: TestClient):
        _as(_user("employer", EMPLOYER_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(), _head_row(65), _head_row(65)],
            fetchval_side=[EMPLOYER_ID, None],  # employer lookup, thresholds
            fetch_side=[_dim_rows(), _bucket_rows(), _bucket_rows()],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 200

    def test_other_employer_404(self, client: TestClient):
        _as(_user("employer", EMPLOYER_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row()],
            fetchval_side=[OTHER_EMPLOYER_ID],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 404

    def test_hidden_match_still_ok_for_employer(self, client: TestClient):
        # Visibility flag governs the APPLICANT surface only; the employer
        # who owns the job may still read the explanation.
        _as(_user("employer", EMPLOYER_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(visible=False), _head_row(65), _head_row(65)],
            fetchval_side=[EMPLOYER_ID, None],
            fetch_side=[_dim_rows(), _bucket_rows(), _bucket_rows()],
        )
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 200

    def test_other_role_404(self, client: TestClient):
        _as(_user("institution", "dddddddd-0000-0000-0000-dddddddddddd"))
        conn = _mock_conn(fetchrow_side=[_match_row()])
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 404

    def test_unknown_match_404(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _mock_conn(fetchrow_side=[None])
        with _patch_db(conn):
            res = client.get(URL)
        assert res.status_code == 404

    def test_malformed_uuid_404(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        res = client.get("/viz/matches/not-a-uuid/explanation")
        assert res.status_code == 404

    def test_unauthenticated_401_or_403(self, client: TestClient):
        res = client.get(URL)  # no override, no Authorization header
        assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Payload correctness
# ---------------------------------------------------------------------------

class TestPayload:
    def test_null_handling_passthrough_and_dimensions(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _happy_conn()
        with _patch_db(conn):
            body = client.get(URL).json()
        dims = {d["dimension"]: d for d in body["dimensions"]}
        assert dims["trade_program_alignment"]["null_handling_applied"] is False
        assert dims["compensation_alignment"]["null_handling_applied"] is True
        assert dims["trade_program_alignment"]["weight"] == 25.0
        assert dims["trade_program_alignment"]["weighted_score"] == 20.0
        # Gates and gap lists pass through for the levers component.
        assert body["match"]["required_missing_items"] == ["OSHA 10"]
        assert body["match"]["gates"][0]["gate_name"] == "required_credential_compatibility"

    def test_bucket_payload_shape(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _happy_conn()
        with _patch_db(conn):
            body = client.get(URL).json()
        dist = body["context_applicant"]
        assert dist["mode"] == "buckets"
        assert dist["n"] == 65
        assert dist["median"] == 42.0
        assert len(dist["buckets"]) == BUCKET_COUNT
        b8 = dist["buckets"][7]
        assert (b8["x0"], b8["x1"]) == (35.0, 40.0)
        assert b8["near_fit"] == 30 and b8["ineligible"] == 10

    def test_small_population_returns_points(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(), _head_row(12), _head_row(65)],
            fetchval_side=[None],
            fetch_side=[_dim_rows(), _point_rows(12), _bucket_rows()],
        )
        with _patch_db(conn):
            body = client.get(URL).json()
        dist = body["context_applicant"]
        assert dist["mode"] == "points"
        assert dist["n"] == 12
        assert len(dist["points"]) == 12
        assert dist["buckets"] == []
        # The job context is independently bucketed.
        assert body["context_job"]["mode"] == "buckets"

    def test_thresholds_from_active_config(self, client: TestClient):
        _as(_user("admin", ADMIN_USER_ID))
        conn = _mock_conn(
            fetchrow_side=[_match_row(), _head_row(65), _head_row(65)],
            fetchval_side=['{"strong_fit_min": 85, "good_fit_min": 55}'],
            fetch_side=[_dim_rows(), _bucket_rows(), _bucket_rows()],
        )
        with _patch_db(conn):
            body = client.get(URL).json()
        assert body["thresholds"] == {"strong_fit_min": 85.0, "good_fit_min": 55.0}
