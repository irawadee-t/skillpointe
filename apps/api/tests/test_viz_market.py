"""
test_viz_market.py — marketplace-analytics endpoints in viz_analytics.py.

Covers:
  1. RBAC: all three /viz marketplace endpoints are admin-only (401/403).
  2. grid_cluster: cell merging, centroid math, label vote, family breakdown,
     null-coordinate skipping, volume sort.
  3. bucket_edges: width_bucket-compatible edge math + validation.
  4. build_annotation: computed from the numbers, honest empty state.
  5. /viz/score-distribution: zero-filled buckets, out-of-range clamping,
     thresholds read from the active config row (not hardcoded).
  6. /viz/supply-demand: imbalance-descending sort, zero-both families
     dropped, top cities attached to the right side.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.viz_analytics import (
    bucket_edges,
    build_annotation,
    grid_cluster,
)

MARKET_ROUTES = (
    "/viz/supply-demand",
    "/viz/supply-demand/geo",
    "/viz/score-distribution",
)


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


@pytest.fixture()
def as_admin():
    app.dependency_overrides[require_admin] = _admin_user
    yield
    app.dependency_overrides.clear()


def _mock_db(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.viz_analytics.get_db", return_value=ctx)


# ---------------------------------------------------------------------------
# 1. RBAC guards
# ---------------------------------------------------------------------------

class TestGuards:
    @pytest.mark.parametrize("route", MARKET_ROUTES)
    def test_unauthenticated_rejected(self, client, mock_supabase_client, route):
        app.dependency_overrides.clear()
        assert client.get(route).status_code in (401, 403)

    @pytest.mark.parametrize("route", MARKET_ROUTES)
    def test_non_admin_rejected(self, client, route):
        app.dependency_overrides.clear()
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="7e51b303-1f9e-4b0a-9d55-000000000002",
            email="worker@test.com",
            role="applicant",
            onboarding_complete=True,
        )
        try:
            assert client.get(route).status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 2. Cluster math
# ---------------------------------------------------------------------------

def _pt(lat, lng, kind="worker", city="Pittsburgh", state="pa",
        family_code="welding", family_name="Welding"):
    return {
        "lat": lat, "lng": lng, "kind": kind, "city": city, "state": state,
        "family_code": family_code, "family_name": family_name,
    }


class TestGridCluster:
    def test_nearby_points_merge_far_points_split(self):
        clusters = grid_cluster(
            [
                _pt(40.44, -80.00),                      # Pittsburgh
                _pt(40.50, -79.95, kind="job"),          # ~5 mi away → same cell
                _pt(33.75, -84.39, city="Atlanta", state="GA"),  # far → own cell
            ],
            cell_deg=0.5,
        )
        assert len(clusters) == 2
        pit = next(c for c in clusters if c["label"] == "Pittsburgh, PA")
        assert pit["workers"] == 1 and pit["jobs"] == 1

    def test_centroid_is_member_mean(self):
        clusters = grid_cluster([_pt(40.0, -80.0), _pt(40.2, -80.2)], cell_deg=0.5)
        assert len(clusters) == 1
        assert clusters[0]["lat"] == pytest.approx(40.1)
        assert clusters[0]["lng"] == pytest.approx(-80.1)

    def test_label_is_most_common_city_normalized(self):
        pts = [
            _pt(40.0, -80.0, city="  pittsburgh ", state="pa"),
            _pt(40.01, -80.01, city="Pittsburgh", state="PA"),
            _pt(40.02, -80.02, city="Carnegie", state="PA"),
        ]
        assert grid_cluster(pts)[0]["label"] == "Pittsburgh, PA"

    def test_family_breakdown_counts_both_sides(self):
        pts = [
            _pt(40.0, -80.0, family_code="welding", family_name="Welding"),
            _pt(40.0, -80.0, kind="job", family_code="welding", family_name="Welding"),
            _pt(40.0, -80.0, kind="job", family_code="hvac", family_name="HVAC"),
        ]
        fams = {f["code"]: f for f in grid_cluster(pts)[0]["families"]}
        assert fams["welding"] == {
            "code": "welding", "name": "Welding", "workers": 1, "jobs": 1,
        }
        assert fams["hvac"]["jobs"] == 1 and fams["hvac"]["workers"] == 0

    def test_null_coordinates_skipped_and_sorted_by_volume(self):
        pts = [
            _pt(None, None),
            _pt(40.0, -80.0),
            _pt(33.75, -84.39, city="Atlanta", state="GA"),
            _pt(33.76, -84.40, kind="job", city="Atlanta", state="GA"),
        ]
        clusters = grid_cluster(pts)
        assert [c["label"] for c in clusters] == ["Atlanta, GA", "Pittsburgh, PA"]
        assert sum(c["workers"] + c["jobs"] for c in clusters) == 3


# ---------------------------------------------------------------------------
# 3. Bucket math
# ---------------------------------------------------------------------------

class TestBucketEdges:
    def test_matches_width_bucket_semantics(self):
        edges = bucket_edges(0.0, 100.0, 50)
        assert len(edges) == 50
        assert edges[0] == (0.0, 2.0)
        assert edges[-1] == (98.0, 100.0)
        # contiguous, no gaps
        assert all(a[1] == pytest.approx(b[0]) for a, b in zip(edges, edges[1:]))

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            bucket_edges(0, 100, 0)
        with pytest.raises(ValueError):
            bucket_edges(100, 0, 10)


# ---------------------------------------------------------------------------
# 4. Annotation
# ---------------------------------------------------------------------------

class TestAnnotation:
    def test_computed_from_the_numbers(self):
        s = build_annotation(
            total=132778, p95=45.76, eligible=34,
            good_fit_min=60.0, share_below_good=0.9997,
        )
        assert "132,778" in s
        assert "below 46" in s
        assert "99.97%" in s        # near-1 shares keep precision, never a false 100%
        assert "34" in s
        assert "supply-limited" in s

    def test_true_full_share_says_100(self):
        s = build_annotation(
            total=10, p95=30.0, eligible=0, good_fit_min=60.0, share_below_good=1.0,
        )
        assert "100%" in s

    def test_empty_distribution_is_honest(self):
        assert build_annotation(0, None, 0, 60.0, None) == "No scored pairs yet."


# ---------------------------------------------------------------------------
# 5. /viz/score-distribution endpoint
# ---------------------------------------------------------------------------

class TestScoreDistribution:
    def test_zero_fill_clamping_and_config_thresholds(self, client, as_admin):
        conn = AsyncMock()
        # _active_match_labels → active config row present (NOT the defaults)
        conn.fetchval = AsyncMock(return_value={
            "moderate_fit_min": 35.0, "good_fit_min": 55.0, "strong_fit_min": 75.0,
        })
        conn.fetchrow = AsyncMock(return_value={
            "total": 100, "min": 0.0, "max": 100.0,
            "p95": 46.0, "share_below_good": 0.95,
        })
        conn.fetch = AsyncMock(side_effect=[
            # width_bucket rows: bucket 0 (below range) and nbins+1 (score=100)
            # must be clamped into the first/last real buckets.
            [{"b": 0, "n": 2}, {"b": 1, "n": 10}, {"b": 21, "n": 85}, {"b": 51, "n": 3}],
            [{"s": "eligible", "n": 5}, {"s": "near_fit", "n": 60},
             {"s": "ineligible", "n": 35}],
        ])
        with _mock_db(conn):
            r = client.get("/viz/score-distribution?nbins=50")
        assert r.status_code == 200
        body = r.json()

        assert body["thresholds"] == {
            "moderate_fit_min": 35.0, "good_fit_min": 55.0, "strong_fit_min": 75.0,
        }
        assert len(body["buckets"]) == 50           # zero-filled, dense
        assert body["buckets"][0]["count"] == 12    # 10 + clamped 2
        assert body["buckets"][-1]["count"] == 3    # clamped nbins+1
        assert body["buckets"][20]["count"] == 85
        assert body["buckets"][20]["x0"] == 40.0
        assert sum(b["count"] for b in body["buckets"]) == 100
        assert body["eligibility"]["eligible"] == 5
        assert "supply-limited" in body["annotation"]

    def test_nbins_validated(self, client, as_admin):
        assert client.get("/viz/score-distribution?nbins=5").status_code == 422
        assert client.get("/viz/score-distribution?nbins=500").status_code == 422


# ---------------------------------------------------------------------------
# 6. /viz/supply-demand endpoint
# ---------------------------------------------------------------------------

class TestSupplyDemand:
    def test_sorted_by_imbalance_zero_both_dropped_cities_attached(
        self, client, as_admin
    ):
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[
            # family counts
            [
                {"code": "aviation", "name": "Aviation", "workers": 23, "jobs": 0},
                {"code": "electrical", "name": "Electrical", "workers": 44, "jobs": 34},
                {"code": "automotive", "name": "Automotive", "workers": 62, "jobs": 20},
                {"code": "dormant", "name": "Dormant", "workers": 0, "jobs": 0},
            ],
            # worker top cities
            [{"code": "aviation", "city": "Mesa", "state": "AZ", "n": 6}],
            # job top cities
            [{"code": "electrical", "city": "Carrollton", "state": "GA", "n": 12}],
        ])
        with _mock_db(conn):
            r = client.get("/viz/supply-demand")
        assert r.status_code == 200
        body = r.json()

        codes = [f["code"] for f in body["families"]]
        # |62-20|=42 > |23-0|=23 > |44-34|=10; zero-both family dropped
        assert codes == ["automotive", "aviation", "electrical"]
        assert "dormant" not in codes

        aviation = body["families"][1]
        assert aviation["worker_cities"] == [
            {"city": "Mesa", "state": "AZ", "count": 6}
        ]
        assert aviation["job_cities"] == []
        assert body["total_workers"] == 129
        assert body["total_jobs"] == 54

    def test_geo_endpoint_clusters_rows(self, client, as_admin):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"kind": "worker", "lat": 40.44, "lng": -80.0, "city": "Pittsburgh",
             "state": "PA", "family_code": "welding", "family_name": "Welding"},
            {"kind": "job", "lat": 40.45, "lng": -80.01, "city": "Pittsburgh",
             "state": "PA", "family_code": "welding", "family_name": "Welding"},
        ])
        with _mock_db(conn):
            r = client.get("/viz/supply-demand/geo")
        assert r.status_code == 200
        body = r.json()
        assert len(body["clusters"]) == 1
        c = body["clusters"][0]
        assert c["label"] == "Pittsburgh, PA"
        assert c["workers"] == 1 and c["jobs"] == 1
        assert c["families"][0]["code"] == "welding"
        assert body["cell_deg"] == 0.5
