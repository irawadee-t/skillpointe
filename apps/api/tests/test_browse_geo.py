"""
test_browse_geo.py — geo params on the applicant browse endpoints.

Covers:
  1. app.util.geo.haversine_miles against known geodesic city-pair distances.
  2. SQL <-> Python formula parity: the exact SQL text haversine_sql() renders
     is evaluated with Python math and must agree with haversine_miles — the
     radius filter Postgres runs IS the reference haversine.
  3. GET /jobs/browse: radius predicate parity between count and data queries,
     the no-coords OR-branch (jobs without coordinates stay in the list),
     distance select + nearest-first ordering, and 422 validation for
     half-specified geo params.
  4. GET /jobs/browse/pins: coordinates-required predicate, light payload
     shape, radius narrowing, and the honest without_coords count.
"""
from __future__ import annotations

import math
import re
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_authenticated
from app.auth.schemas import CurrentUser
from app.main import app
from app.util.geo import EARTH_RADIUS_MILES, haversine_miles, haversine_sql

# Known city centroids (same fixtures as test_geo_radius.py)
AUSTIN = (30.2672, -97.7431)
ROUND_ROCK = (30.5083, -97.6789)     # ~17 mi from Austin
SAN_ANTONIO = (29.4241, -98.4936)    # ~74 mi from Austin
NYC = (40.7128, -74.0060)
LA = (34.0522, -118.2437)
CHICAGO = (41.8781, -87.6298)
HOUSTON = (29.7604, -95.3698)


# ---------------------------------------------------------------------------
# 1. Python reference haversine
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b, expected_miles", [
    (NYC, LA, 2445.6),
    (CHICAGO, HOUSTON, 940.0),
    (AUSTIN, SAN_ANTONIO, 73.6),
])
def test_haversine_known_city_pairs(a, b, expected_miles):
    assert haversine_miles(*a, *b) == pytest.approx(expected_miles, rel=0.01)


def test_haversine_zero_and_symmetry():
    assert haversine_miles(*AUSTIN, *AUSTIN) == pytest.approx(0.0, abs=1e-9)
    assert haversine_miles(*AUSTIN, *NYC) == pytest.approx(haversine_miles(*NYC, *AUSTIN))


# ---------------------------------------------------------------------------
# 2. SQL formula == Python formula
# ---------------------------------------------------------------------------

def _eval_sql_distance(center: tuple[float, float], row: tuple[float, float]) -> float:
    """Evaluate the SQL text with Python math — proves the predicate Postgres
    executes is the same function as the reference haversine."""
    sql = haversine_sql("$1", "$2", lat_col="j.lat", lng_col="j.lng")
    expr = (
        sql.replace("$1", repr(center[0]))
        .replace("$2", repr(center[1]))
        .replace("j.lat", repr(row[0]))
        .replace("j.lng", repr(row[1]))
        .replace("power", "pow")
    )
    namespace = {
        "asin": math.asin, "sqrt": math.sqrt, "pow": pow,
        "sin": math.sin, "cos": math.cos, "radians": math.radians,
    }
    return eval(expr, {"__builtins__": {}}, namespace)  # noqa: S307 — our own SQL text


@pytest.mark.parametrize("center, row", [
    (AUSTIN, ROUND_ROCK),
    (AUSTIN, SAN_ANTONIO),
    (NYC, LA),
    (CHICAGO, HOUSTON),
    (AUSTIN, AUSTIN),
])
def test_sql_formula_matches_python_haversine(center, row):
    assert _eval_sql_distance(center, row) == pytest.approx(
        haversine_miles(*center, *row), rel=1e-9
    )


def test_sql_uses_shared_earth_radius():
    assert str(EARTH_RADIUS_MILES) in haversine_sql("$1", "$2")


# ---------------------------------------------------------------------------
# Endpoint harness — captured SQL, no DB
# ---------------------------------------------------------------------------

class _FakeConn:
    """Records every query + args; returns canned rows."""

    def __init__(self, rows=None, scalars=None):
        self.calls: list[tuple[str, tuple]] = []
        self._rows = rows or []
        self._scalars = list(scalars or [])

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return self._scalars.pop(0) if self._scalars else 0

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return None

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return self._rows


def _fake_db(conn: _FakeConn):
    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx


async def _passthrough_cache(key, ttl, produce):
    return await produce()


def _applicant() -> CurrentUser:
    return CurrentUser(
        user_id="applicant-user-id", email="a@t.co", role="applicant",
        onboarding_complete=True,
    )


@pytest.fixture()
def client():
    app.dependency_overrides[require_authenticated] = _applicant
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


PIN_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "title_raw": "Electrician", "employer_name": "GE Vernova",
    "city": "Austin", "state": "TX", "lat": 30.27, "lng": -97.74,
    "pay_min": 25, "pay_max": 30, "pay_type": "hourly", "pay_raw": None,
    "source_url": "https://example.com/j/1", "internal_apply": True,
    "distance_miles": 3.2,
}


# ---------------------------------------------------------------------------
# 3. GET /jobs/browse with geo params
# ---------------------------------------------------------------------------

class TestBrowseGeo:
    def test_radius_predicate_in_both_count_and_data(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            r = client.get(
                "/jobs/browse",
                params={"near_lat": AUSTIN[0], "near_lng": AUSTIN[1], "radius_miles": 50},
            )
        assert r.status_code == 200
        count_sql, count_args = conn.calls[0]
        data_sql, data_args = conn.calls[1]

        predicate = "j.lat IS NULL OR j.lng IS NULL OR 2 * 3958.8 * asin"
        assert predicate in _norm(count_sql), "count query must filter by radius"
        assert predicate in _norm(data_sql), "data query must filter by radius"
        # Center + radius are bound in both queries
        assert AUSTIN[0] in count_args and AUSTIN[1] in count_args and 50 in count_args
        assert AUSTIN[0] in data_args and AUSTIN[1] in data_args and 50 in data_args

    def test_no_coords_jobs_stay_in_list(self, client):
        """The radius predicate must be an OR with the NULL-coordinate branch —
        jobs without a mapped location are never dropped from the list."""
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get(
                "/jobs/browse",
                params={"near_lat": 30.0, "near_lng": -97.0, "radius_miles": 25},
            )
        data_sql, _ = conn.calls[1]
        assert "(j.lat IS NULL OR j.lng IS NULL OR" in _norm(data_sql)

    def test_center_adds_distance_select_and_nearest_first_order(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse", params={"near_lat": 30.0, "near_lng": -97.0})
        data_sql, _ = conn.calls[1]
        assert "AS distance_miles" in data_sql
        assert "ORDER BY distance_miles ASC NULLS LAST" in _norm(data_sql)

    def test_no_geo_params_keeps_legacy_order_and_null_distance(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            r = client.get("/jobs/browse")
        assert r.status_code == 200
        count_sql, count_args = conn.calls[0]
        data_sql, _ = conn.calls[1]
        assert "asin" not in count_sql
        assert "NULL::float AS distance_miles" in data_sql
        assert "ORDER BY j.posted_date DESC NULLS LAST" in _norm(data_sql)
        assert count_args == ()

    def test_radius_without_center_422(self, client):
        r = client.get("/jobs/browse", params={"radius_miles": 50})
        assert r.status_code == 422

    def test_half_center_422(self, client):
        assert client.get("/jobs/browse", params={"near_lat": 30.0}).status_code == 422
        assert client.get("/jobs/browse", params={"near_lng": -97.0}).status_code == 422

    def test_out_of_range_center_422(self, client):
        r = client.get(
            "/jobs/browse", params={"near_lat": 91, "near_lng": 0, "radius_miles": 10},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 4. GET /jobs/browse/pins
# ---------------------------------------------------------------------------

class TestBrowsePins:
    def test_pins_require_coordinates(self, client):
        conn = _FakeConn(rows=[PIN_ROW], scalars=[3, 12])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            r = client.get("/jobs/browse/pins")
        assert r.status_code == 200
        data_sql = conn.calls[-1][0]
        assert "j.lat IS NOT NULL" in data_sql
        assert "j.lng IS NOT NULL" in data_sql

    def test_pins_payload_shape(self, client):
        conn = _FakeConn(rows=[PIN_ROW], scalars=[3, 12])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            body = client.get(
                "/jobs/browse/pins",
                params={"near_lat": AUSTIN[0], "near_lng": AUSTIN[1], "radius_miles": 50},
            ).json()

        assert set(body.keys()) == {"pins", "total", "without_coords"}
        assert body["without_coords"] == 3
        assert body["total"] == 12
        pin = body["pins"][0]
        assert set(pin.keys()) == {
            "job_id", "title", "employer_name", "city", "state", "lat", "lng",
            "pay_min", "pay_max", "pay_type", "pay_raw", "source_url",
            "internal_apply", "distance_miles",
        }
        assert pin["lat"] == 30.27 and pin["lng"] == -97.74
        assert pin["distance_miles"] == 3.2
        # Light payload: no description fields ever
        assert "description" not in pin and "requirements" not in pin

    def test_pins_radius_predicate_and_shared_filters(self, client):
        conn = _FakeConn(rows=[], scalars=[0, 0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get(
                "/jobs/browse/pins",
                params={
                    "trade": "electrical", "state": "TX",
                    "near_lat": AUSTIN[0], "near_lng": AUSTIN[1], "radius_miles": 50,
                },
            )
        data_sql, data_args = conn.calls[-1]
        # Same filter predicates as /jobs/browse (shared builder)
        assert "jf.code = $1" in data_sql
        assert "UPPER(j.state) = UPPER($2)" in data_sql
        # Radius applies as a hard predicate (no NULL branch — pins need coords)
        assert "asin" in data_sql and "<= $5" in data_sql
        assert "j.lat IS NULL OR" not in data_sql
        assert data_args == ("electrical", "TX", AUSTIN[0], AUSTIN[1], 50.0)

    def test_pins_geo_validation_mirrors_browse(self, client):
        assert client.get("/jobs/browse/pins", params={"radius_miles": 5}).status_code == 422
        assert client.get("/jobs/browse/pins", params={"near_lat": 1}).status_code == 422

    def test_pins_capped_at_500(self, client):
        conn = _FakeConn(rows=[], scalars=[0, 0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse/pins")
        data_sql = conn.calls[-1][0]
        assert "LIMIT 500" in data_sql


# ---------------------------------------------------------------------------
# 5. bbox (map-viewport) scope — /jobs/browse and /jobs/browse/pins
# ---------------------------------------------------------------------------

# Roughly the Austin metro viewport.
BBOX = "-98.2,29.8,-97.2,30.8"
BBOX_CLAUSE = "(j.lng >= $1 AND j.lng <= $2 AND j.lat >= $3 AND j.lat <= $4)"


class TestBrowseBbox:
    def test_bbox_predicate_in_both_count_and_data(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            r = client.get("/jobs/browse", params={"bbox": BBOX})
        assert r.status_code == 200
        count_sql, count_args = conn.calls[0]
        data_sql, data_args = conn.calls[1]
        assert BBOX_CLAUSE in _norm(count_sql), "count query must scope to the viewport"
        assert BBOX_CLAUSE in _norm(data_sql), "data query must scope to the viewport"
        # minLng, maxLng, minLat, maxLat bound identically in both queries
        assert count_args[:4] == (-98.2, -97.2, 29.8, 30.8)
        assert data_args[:4] == (-98.2, -97.2, 29.8, 30.8)

    def test_bbox_excludes_jobs_without_coordinates(self, client):
        """Viewport scope is honest: a job with no coordinates cannot be in
        the viewport, so the plain bbox predicate has NO NULL-coordinate
        branch (range comparisons exclude NULL rows by SQL semantics)."""
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse", params={"bbox": BBOX})
        data_sql, _ = conn.calls[1]
        assert "j.lat IS NULL" not in _norm(data_sql)
        assert "asin" not in data_sql  # no haversine in viewport scope

    def test_include_unmapped_readmits_no_coords_jobs_after_mapped(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get(
                "/jobs/browse", params={"bbox": BBOX, "include_unmapped": "true"},
            )
        count_sql, _ = conn.calls[0]
        data_sql, _ = conn.calls[1]
        wrapped = f"({BBOX_CLAUSE} OR j.lat IS NULL OR j.lng IS NULL)"
        assert wrapped in _norm(count_sql)
        assert wrapped in _norm(data_sql)
        # Mapped jobs first, the unmapped appendix after
        assert "ORDER BY (j.lat IS NULL OR j.lng IS NULL) ASC" in _norm(data_sql)

    def test_bbox_combines_with_other_filters(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get(
                "/jobs/browse",
                params={"trade": "electrical", "state": "TX", "bbox": BBOX},
            )
        data_sql, data_args = conn.calls[1]
        assert "jf.code = $1" in data_sql
        assert "UPPER(j.state) = UPPER($2)" in data_sql
        assert "(j.lng >= $3 AND j.lng <= $4 AND j.lat >= $5 AND j.lat <= $6)" in _norm(data_sql)
        assert data_args[:6] == ("electrical", "TX", -98.2, -97.2, 29.8, 30.8)

    def test_bbox_orders_newest_first(self, client):
        conn = _FakeConn(scalars=[0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse", params={"bbox": BBOX})
        data_sql, _ = conn.calls[1]
        assert "ORDER BY j.posted_date DESC NULLS LAST" in _norm(data_sql)

    @pytest.mark.parametrize("bad", [
        "1,2,3",                    # wrong arity
        "a,b,c,d",                  # not numbers
        "-98.2,29.8,-97.2",         # wrong arity
        "-97.2,29.8,-98.2,30.8",    # minLng >= maxLng
        "-98.2,30.8,-97.2,29.8",    # minLat >= maxLat
        "-198,29.8,-97.2,30.8",     # out of range
    ])
    def test_malformed_bbox_422(self, client, bad):
        assert client.get("/jobs/browse", params={"bbox": bad}).status_code == 422
        assert client.get("/jobs/browse/pins", params={"bbox": bad}).status_code == 422

    def test_bbox_and_radius_scopes_are_exclusive(self, client):
        for path in ("/jobs/browse", "/jobs/browse/pins"):
            r = client.get(path, params={
                "bbox": BBOX,
                "near_lat": AUSTIN[0], "near_lng": AUSTIN[1], "radius_miles": 50,
            })
            assert r.status_code == 422
            r = client.get(path, params={
                "bbox": BBOX, "near_lat": AUSTIN[0], "near_lng": AUSTIN[1],
            })
            assert r.status_code == 422


class TestPinsBbox:
    def test_pins_bbox_predicate_matches_browse(self, client):
        """Predicate parity: the pins query renders the exact same bbox clause
        text (same placeholder numbers — both start from the same shared
        filter builder) as /jobs/browse."""
        browse_conn = _FakeConn(scalars=[0])
        pins_conn = _FakeConn(rows=[], scalars=[0, 0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(browse_conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse", params={"bbox": BBOX})
        with (
            patch("app.routers.jobs.get_db", _fake_db(pins_conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse/pins", params={"bbox": BBOX})
        browse_sql = _norm(browse_conn.calls[1][0])
        pins_sql = _norm(pins_conn.calls[-1][0])
        assert BBOX_CLAUSE in browse_sql
        assert BBOX_CLAUSE in pins_sql
        assert browse_conn.calls[1][1][:4] == pins_conn.calls[-1][1][:4]

    def test_pins_bbox_keeps_coordinates_required(self, client):
        conn = _FakeConn(rows=[], scalars=[0, 0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            client.get("/jobs/browse/pins", params={"bbox": BBOX})
        data_sql = _norm(conn.calls[-1][0])
        assert "j.lat IS NOT NULL" in data_sql and "j.lng IS NOT NULL" in data_sql
        assert BBOX_CLAUSE in data_sql

    def test_pins_coverage_count_ignores_bbox(self, client):
        """without_coords answers "how many filtered jobs are unmappable" —
        a viewport cannot include or exclude a job that has no coordinates,
        so the coverage query must not carry the bbox predicate."""
        conn = _FakeConn(rows=[], scalars=[7, 0])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            body = client.get("/jobs/browse/pins", params={"bbox": BBOX}).json()
        coverage_sql, coverage_args = conn.calls[0]
        assert "j.lng >=" not in coverage_sql
        assert coverage_args == ()
        assert body["without_coords"] == 7

    def test_pins_bbox_narrows_total(self, client):
        conn = _FakeConn(rows=[PIN_ROW], scalars=[3, 12])
        with (
            patch("app.routers.jobs.get_db", _fake_db(conn)),
            patch("app.routers.jobs.cached_json", _passthrough_cache),
        ):
            body = client.get("/jobs/browse/pins", params={"bbox": BBOX}).json()
        # pin count query carries the bbox args
        count_sql, count_args = conn.calls[1]
        assert BBOX_CLAUSE in _norm(count_sql)
        assert count_args[:4] == (-98.2, -97.2, 29.8, 30.8)
        assert body["total"] == 12
