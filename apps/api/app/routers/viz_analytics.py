"""
viz_analytics.py — additive, read-only endpoints backing the bespoke match
explanation visualizations (apps/web/src/components/viz2/).

    GET /viz/matches/{match_id}/explanation

Serves everything the "Why this score" piece needs in one payload:
  - the match core (scores, tier, gates, strengths/gaps/missing items)
  - the 9 dimension scores (weight, raw, weighted, rationale, null handling)
  - label thresholds from the ACTIVE policy config (never hardcoded client-side)
  - two server-bucketed context distributions (SQL width_bucket — the 132k-row
    matches table never leaves the database):
      applicant — where this score sits among all jobs scored for the applicant
      job       — where it sits among all candidates scored for the job

Authorization (read-only; mirrors existing guards):
  - the applicant who owns the match (visibility flag enforced, like the
    applicant match-detail endpoint)
  - the employer who owns the job (resolved via employer_contacts, like
    employers.py `_resolve_employer_id`)
  - admin (read-only by nature of the endpoint)
Anything else → 404, never revealing whether the match exists.

This file is shared by multiple viz endpoints — append new /viz/* routes below,
do not restructure existing ones.
"""
from __future__ import annotations

import json
import sys
import uuid as _uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin, require_authenticated
from app.auth.schemas import CurrentUser
from app.db import get_db

# packages/ import path (matching config is pure python, no DB I/O inside) —
# same shim as matching_admin.py so the code-default ScoringConfig is the
# threshold fallback when no policy_configs row is active.
# Walk only existing parents: the deploy layout can be flatter than the repo
# (Railway Root Directory = apps/api), where parents[4] does not exist.
for _parent in Path(__file__).resolve().parents:
    _pkg = _parent / "packages"
    if _pkg.is_dir():
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        break

# packages/ is not shipped in every deploy. Fall back to the documented
# defaults rather than crashing the whole app at import.
try:
    from matching.config import load_config  # noqa: E402
except ImportError:  # pragma: no cover - deploy-layout dependent
    load_config = None

router = APIRouter(prefix="/viz", tags=["viz"])

# ---------------------------------------------------------------------------
# Distribution constants
# ---------------------------------------------------------------------------

#: Number of equal-width score buckets over [0, 100].
BUCKET_COUNT = 20

#: Populations smaller than this are served as raw points (dot strip) instead
#: of a density silhouette — a 12-row histogram is a lie of smoothness.
SMALL_N = 20

_STATUSES = ("eligible", "near_fit", "ineligible")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VizGate(BaseModel):
    gate_name: str
    result: str
    reason: str
    severity: str | None = None


class VizDimension(BaseModel):
    dimension: str
    weight: float
    raw_score: float
    weighted_score: float
    rationale: str | None = None
    null_handling_applied: bool = False


class VizBucket(BaseModel):
    x0: float
    x1: float
    eligible: int
    near_fit: int
    ineligible: int


class VizPoint(BaseModel):
    score: float
    status: str


class VizDistribution(BaseModel):
    n: int
    mode: Literal["buckets", "points"]
    bucket_width: float = 100.0 / BUCKET_COUNT
    buckets: list[VizBucket] = Field(default_factory=list)
    points: list[VizPoint] = Field(default_factory=list)
    median: float | None = None


class VizThresholds(BaseModel):
    strong_fit_min: float
    good_fit_min: float


class VizMatchCore(BaseModel):
    match_id: str
    job_id: str
    job_title: str
    employer_name: str
    eligibility_status: str
    match_label: str | None = None
    match_tier: str | None = None
    tier_reason: str | None = None
    policy_adjusted_score: float | None = None
    base_fit_score: float | None = None
    distance_miles: float | None = None
    confidence_level: str | None = None
    top_strengths: list[str] = Field(default_factory=list)
    top_gaps: list[str] = Field(default_factory=list)
    required_missing_items: list[str] = Field(default_factory=list)
    recommended_next_step: str | None = None
    gates: list[VizGate] = Field(default_factory=list)


class MatchExplanationResponse(BaseModel):
    match: VizMatchCore
    dimensions: list[VizDimension]
    thresholds: VizThresholds
    context_applicant: VizDistribution
    context_job: VizDistribution


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_viz_explanation.py)
# ---------------------------------------------------------------------------

def assemble_buckets(rows: list[dict[str, Any]]) -> list[VizBucket]:
    """
    Fold SQL `width_bucket(score, 0, 100, BUCKET_COUNT)` group rows into a
    dense, ordered list of BUCKET_COUNT buckets.

    width_bucket edge semantics: a score of exactly 100 lands in bucket
    BUCKET_COUNT + 1 and anything below 0 in bucket 0 — both are clamped into
    the nearest real bucket so no observation is ever dropped.
    """
    counts: dict[int, dict[str, int]] = {
        b: dict.fromkeys(_STATUSES, 0) for b in range(1, BUCKET_COUNT + 1)
    }
    for row in rows:
        b = min(max(int(row["bucket"]), 1), BUCKET_COUNT)
        for key in _STATUSES:
            counts[b][key] += int(row.get(key) or 0)

    width = 100.0 / BUCKET_COUNT
    return [
        VizBucket(x0=(b - 1) * width, x1=b * width, **counts[b])
        for b in range(1, BUCKET_COUNT + 1)
    ]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_list(value: Any) -> list[str]:
    """jsonb columns may arrive as list, JSON string, or None."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


def parse_label_thresholds(raw: Any) -> VizThresholds:
    """Parse a policy config's match_labels blob; fall back to code defaults."""
    labels: dict[str, Any] = {}
    if isinstance(raw, str):
        try:
            labels = json.loads(raw) or {}
        except (ValueError, TypeError):
            labels = {}
    elif isinstance(raw, dict):
        labels = raw
    return VizThresholds(
        strong_fit_min=float(labels.get("strong_fit_min", 80.0)),
        good_fit_min=float(labels.get("good_fit_min", 60.0)),
    )


# ---------------------------------------------------------------------------
# Distribution query (server-side bucketing — never ships raw rows at scale)
# ---------------------------------------------------------------------------

async def _fetch_distribution(
    conn: Any, where_column: str, entity_id: Any
) -> VizDistribution:
    """
    Bucketed score distribution over public.matches filtered by
    `where_column` ∈ {applicant_id, job_id}. Small populations (< SMALL_N)
    return every point so the client can render an honest dot strip.
    """
    if where_column not in ("applicant_id", "job_id"):  # defense in depth
        raise ValueError(f"Bad distribution column: {where_column}")

    head = await conn.fetchrow(
        f"""
        SELECT count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY policy_adjusted_score) AS median
        FROM public.matches
        WHERE {where_column} = $1::uuid AND policy_adjusted_score IS NOT NULL
        """,
        entity_id,
    )
    n = int(head["n"] or 0) if head else 0
    median = _safe_float(head["median"]) if head else None

    if n == 0:
        return VizDistribution(n=0, mode="points", median=None)

    if n < SMALL_N:
        point_rows = await conn.fetch(
            f"""
            SELECT policy_adjusted_score AS score, eligibility_status::text AS status
            FROM public.matches
            WHERE {where_column} = $1::uuid AND policy_adjusted_score IS NOT NULL
            ORDER BY policy_adjusted_score
            """,
            entity_id,
        )
        points = [
            VizPoint(score=float(r["score"]), status=r["status"]) for r in point_rows
        ]
        return VizDistribution(n=n, mode="points", points=points, median=median)

    bucket_rows = await conn.fetch(
        f"""
        SELECT width_bucket(policy_adjusted_score, 0, 100, {BUCKET_COUNT}) AS bucket,
               count(*) FILTER (WHERE eligibility_status = 'eligible')   AS eligible,
               count(*) FILTER (WHERE eligibility_status = 'near_fit')   AS near_fit,
               count(*) FILTER (WHERE eligibility_status = 'ineligible') AS ineligible
        FROM public.matches
        WHERE {where_column} = $1::uuid AND policy_adjusted_score IS NOT NULL
        GROUP BY bucket
        ORDER BY bucket
        """,
        entity_id,
    )
    buckets = assemble_buckets([dict(r) for r in bucket_rows])
    return VizDistribution(n=n, mode="buckets", buckets=buckets, median=median)


# ---------------------------------------------------------------------------
# GET /viz/matches/{match_id}/explanation
# ---------------------------------------------------------------------------

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
)


@router.get(
    "/matches/{match_id}/explanation", response_model=MatchExplanationResponse
)
async def get_match_explanation(
    match_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> MatchExplanationResponse:
    """Full explanation payload for one match — see module docstring."""
    try:
        _uuid.UUID(match_id)
    except ValueError:
        raise _NOT_FOUND

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                m.id::text            AS match_id,
                m.applicant_id,
                m.job_id::text        AS job_id,
                m.eligibility_status::text,
                m.match_label::text,
                m.match_tier,
                m.tier_reason,
                m.policy_adjusted_score,
                m.base_fit_score,
                m.distance_miles,
                m.confidence_level::text,
                m.top_strengths,
                m.top_gaps,
                m.required_missing_items,
                m.recommended_next_step,
                m.hard_gate_rationale,
                m.is_visible_to_applicant,
                j.title_normalized,
                j.title_raw,
                j.employer_id,
                e.name                AS employer_name
            FROM public.matches m
            JOIN public.jobs j      ON j.id = m.job_id
            JOIN public.employers e ON e.id = j.employer_id
            WHERE m.id = $1::uuid
            """,
            match_id,
        )
        if not row:
            raise _NOT_FOUND

        # ── Authorization ────────────────────────────────────────────────
        if current_user.is_admin:
            pass  # read-only endpoint; admin may inspect any match
        elif current_user.role == "applicant":
            applicant_id = await conn.fetchval(
                "SELECT id FROM public.applicants WHERE user_id = $1::uuid",
                current_user.user_id,
            )
            if (
                applicant_id is None
                or applicant_id != row["applicant_id"]
                or not row["is_visible_to_applicant"]
            ):
                raise _NOT_FOUND
        elif current_user.role == "employer":
            employer_id = await conn.fetchval(
                "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
                current_user.user_id,
            )
            if employer_id is None or employer_id != row["employer_id"]:
                raise _NOT_FOUND
        else:
            raise _NOT_FOUND

        # ── Dimension scores (same query shape as the match detail) ──────
        from app.skilled_pro.live_dimensions import fetch_or_compute_dimensions
        dim_rows = await fetch_or_compute_dimensions(conn, match_id)

        # ── Label thresholds from the ACTIVE policy config ───────────────
        thresholds_raw = await conn.fetchval(
            """
            SELECT config -> 'match_labels'
            FROM public.policy_configs
            WHERE is_active = TRUE
            ORDER BY activated_at DESC NULLS LAST
            LIMIT 1
            """
        )

        # ── Context distributions (bucketed in SQL) ──────────────────────
        context_applicant = await _fetch_distribution(
            conn, "applicant_id", row["applicant_id"]
        )
        context_job = await _fetch_distribution(conn, "job_id", row["job_id"])

    gate_raw = row["hard_gate_rationale"]
    if isinstance(gate_raw, str):
        try:
            gate_raw = json.loads(gate_raw)
        except (ValueError, TypeError):
            gate_raw = {}
    gates = [
        VizGate(
            gate_name=name,
            result=str(detail.get("result", "")),
            reason=str(detail.get("reason", "")),
            severity=detail.get("severity"),
        )
        for name, detail in (gate_raw or {}).items()
        if isinstance(detail, dict)
    ]

    dimensions = [
        VizDimension(
            dimension=d["dimension"],
            weight=float(d["weight"]),
            raw_score=float(d["raw_score"]),
            weighted_score=float(d["weighted_score"]),
            rationale=d["rationale"],
            null_handling_applied=bool(d["null_handling_applied"]),
        )
        for d in dim_rows
    ]

    return MatchExplanationResponse(
        match=VizMatchCore(
            match_id=row["match_id"],
            job_id=row["job_id"],
            job_title=row["title_normalized"] or row["title_raw"] or "Untitled",
            employer_name=row["employer_name"] or "Unknown",
            eligibility_status=row["eligibility_status"],
            match_label=row["match_label"],
            match_tier=row["match_tier"],
            tier_reason=row["tier_reason"],
            policy_adjusted_score=_safe_float(row["policy_adjusted_score"]),
            base_fit_score=_safe_float(row["base_fit_score"]),
            distance_miles=_safe_float(row["distance_miles"]),
            confidence_level=row["confidence_level"],
            top_strengths=_safe_list(row["top_strengths"]),
            top_gaps=_safe_list(row["top_gaps"]),
            required_missing_items=_safe_list(row["required_missing_items"]),
            recommended_next_step=row["recommended_next_step"],
            gates=gates,
        ),
        dimensions=dimensions,
        thresholds=parse_label_thresholds(thresholds_raw),
        context_applicant=context_applicant,
        context_job=context_job,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Marketplace analytics — supply vs demand + score distribution (admin-only)
#
#   GET /viz/supply-demand        — workers vs active jobs per canonical
#                                   family, top cities each side (diverging
#                                   bars; the imbalance IS the story)
#   GET /viz/supply-demand/geo    — metro clusters (0.5° grid ≈ 35 mi) with
#                                   worker/job counts + per-family breakdown
#   GET /viz/score-distribution   — width_bucket histogram over ALL
#                                   matches.base_fit_score rows; band
#                                   thresholds from the ACTIVE matching
#                                   config; annotation computed from the data
#
# Pure helpers (grid_cluster, bucket_edges, build_annotation) carry the math
# so tests/test_viz_market.py covers it without a database.
# ═══════════════════════════════════════════════════════════════════════════

# ~0.5° of latitude ≈ 35 miles — one metro reads as one mark, distinct metros
# stay separate. The client renders whatever grain the server chooses.
DEFAULT_CELL_DEG = 0.5


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_viz_market.py)
# ---------------------------------------------------------------------------

def grid_cluster(
    points: list[dict[str, Any]],
    cell_deg: float = DEFAULT_CELL_DEG,
) -> list[dict[str, Any]]:
    """Cluster (lat, lng) points onto a fixed grid of `cell_deg` cells.

    Each input point is a dict with: lat, lng, kind ("worker" | "job"),
    city, state, family_code, family_name. Points missing coordinates are
    skipped. Output clusters carry the mean centroid, the most common
    "City, ST" label among members, worker/job totals, and a per-family
    breakdown — sorted by combined volume descending.
    """
    cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for p in points:
        lat, lng = p.get("lat"), p.get("lng")
        if lat is None or lng is None:
            continue
        key = (round(float(lat) / cell_deg), round(float(lng) / cell_deg))
        cells[key].append(p)

    clusters: list[dict[str, Any]] = []
    for key, members in cells.items():
        workers = sum(1 for m in members if m["kind"] == "worker")
        jobs = sum(1 for m in members if m["kind"] == "job")

        labels = Counter(
            f"{str(m['city']).strip().title()}, {str(m['state']).strip().upper()}"
            for m in members
            if m.get("city") and m.get("state")
        )
        label = labels.most_common(1)[0][0] if labels else "Unknown"

        fam: dict[str, dict[str, Any]] = {}
        for m in members:
            code = m.get("family_code")
            if not code:
                continue
            entry = fam.setdefault(
                code,
                {"code": code, "name": m.get("family_name") or code, "workers": 0, "jobs": 0},
            )
            entry["workers" if m["kind"] == "worker" else "jobs"] += 1

        clusters.append(
            {
                "key": f"{key[0]}:{key[1]}",
                "label": label,
                "lat": sum(float(m["lat"]) for m in members) / len(members),
                "lng": sum(float(m["lng"]) for m in members) / len(members),
                "workers": workers,
                "jobs": jobs,
                "families": sorted(
                    fam.values(), key=lambda f: -(f["workers"] + f["jobs"])
                ),
            }
        )

    clusters.sort(key=lambda c: -(c["workers"] + c["jobs"]))
    return clusters


def bucket_edges(lo: float, hi: float, nbins: int) -> list[tuple[float, float]]:
    """The [x0, x1) edges Postgres width_bucket(x, lo, hi, nbins) uses for
    buckets 1..nbins. Kept in one place so the SQL and the response agree."""
    if nbins <= 0 or hi <= lo:
        raise ValueError("bucket_edges requires nbins > 0 and hi > lo")
    w = (hi - lo) / nbins
    return [(lo + i * w, lo + (i + 1) * w) for i in range(nbins)]


def build_annotation(
    total: int,
    p95: float | None,
    eligible: int,
    good_fit_min: float,
    share_below_good: float | None,
) -> str:
    """One honest sentence computed from the live distribution — never canned."""
    if total == 0 or p95 is None:
        return "No scored pairs yet."
    if share_below_good is None:
        pct_good = "most"
    elif share_below_good >= 0.995 and share_below_good < 1.0:
        # 99.97% must never round up to a false "100%".
        pct_good = f"{share_below_good * 100:.2f}%"
    else:
        pct_good = f"{share_below_good * 100:.0f}%"
    return (
        f"95% of the {total:,} scored pairs sit below {p95:.0f} of 100, "
        f"{pct_good} below the good-fit line ({good_fit_min:.0f}), and only "
        f"{eligible:,} clear every hard gate; the market is supply-limited, "
        "not quality-limited."
    )


async def _active_match_labels(conn: Any) -> dict[str, float]:
    """All three match-label thresholds from the ACTIVE policy_configs row,
    falling back to the code-default ScoringConfig. Never hardcoded."""
    raw = await conn.fetchval(
        """
        SELECT config -> 'match_labels'
        FROM public.policy_configs
        WHERE is_active = TRUE
        ORDER BY activated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    if isinstance(raw, dict) and raw:
        return {
            "moderate_fit_min": float(raw.get("moderate_fit_min", 40.0)),
            "good_fit_min": float(raw.get("good_fit_min", 60.0)),
            "strong_fit_min": float(raw.get("strong_fit_min", 80.0)),
        }
    if load_config is None:
        # Matching package absent in this deploy; use the documented defaults.
        return {"moderate_fit_min": 40.0, "good_fit_min": 60.0, "strong_fit_min": 80.0}
    cfg = load_config()
    return {
        "moderate_fit_min": float(cfg.match_labels.moderate_fit_min),
        "good_fit_min": float(cfg.match_labels.good_fit_min),
        "strong_fit_min": float(cfg.match_labels.strong_fit_min),
    }


# ---------------------------------------------------------------------------
# Schemas — marketplace analytics
# ---------------------------------------------------------------------------

class CityCount(BaseModel):
    city: str
    state: str
    count: int


class FamilySupplyDemand(BaseModel):
    code: str
    name: str
    workers: int
    jobs: int
    worker_cities: list[CityCount] = Field(default_factory=list)
    job_cities: list[CityCount] = Field(default_factory=list)


class SupplyDemandResponse(BaseModel):
    families: list[FamilySupplyDemand]
    total_workers: int
    total_jobs: int


class ClusterFamily(BaseModel):
    code: str
    name: str
    workers: int
    jobs: int


class GeoCluster(BaseModel):
    key: str
    label: str
    lat: float
    lng: float
    workers: int
    jobs: int
    families: list[ClusterFamily] = Field(default_factory=list)


class SupplyDemandGeoResponse(BaseModel):
    clusters: list[GeoCluster]
    cell_deg: float


class ScoreBucket(BaseModel):
    x0: float
    x1: float
    count: int


class ScoreDistributionResponse(BaseModel):
    total: int
    min: float | None
    max: float | None
    p95: float | None
    buckets: list[ScoreBucket]
    thresholds: dict[str, float]
    eligibility: dict[str, int]
    annotation: str


# ---------------------------------------------------------------------------
# GET /viz/supply-demand
# ---------------------------------------------------------------------------

_FAMILY_COUNTS_SQL = """
    SELECT jf.code, jf.name,
           COUNT(DISTINCT a.id) AS workers,
           COUNT(DISTINCT j.id) AS jobs
    FROM public.canonical_job_families jf
    LEFT JOIN public.applicants a ON a.canonical_job_family_id = jf.id
    LEFT JOIN public.jobs j
           ON j.canonical_job_family_id = jf.id AND j.is_active = TRUE
    GROUP BY jf.code, jf.name
"""

_TOP_CITIES_SQL = """
    SELECT code, city, state, n FROM (
        SELECT jf.code,
               initcap(trim(t.city)) AS city,
               upper(trim(t.state))  AS state,
               COUNT(*) AS n,
               ROW_NUMBER() OVER (
                   PARTITION BY jf.code ORDER BY COUNT(*) DESC, initcap(trim(t.city))
               ) AS rn
        FROM {table} t
        JOIN public.canonical_job_families jf ON jf.id = t.canonical_job_family_id
        WHERE t.city IS NOT NULL AND t.city <> '' AND t.state IS NOT NULL {extra}
        GROUP BY jf.code, initcap(trim(t.city)), upper(trim(t.state))
    ) ranked
    WHERE rn <= 3
"""


@router.get("/supply-demand", response_model=SupplyDemandResponse)
async def supply_demand(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> SupplyDemandResponse:
    """Workers vs active jobs per canonical family + top 3 cities per side.

    Sorted by absolute imbalance descending — the imbalance IS the story.
    Families with zero on both sides are dropped (no data, no ink).
    """
    async with get_db() as conn:
        fam_rows = await conn.fetch(_FAMILY_COUNTS_SQL)
        worker_city_rows = await conn.fetch(
            _TOP_CITIES_SQL.format(table="public.applicants", extra="")
        )
        job_city_rows = await conn.fetch(
            _TOP_CITIES_SQL.format(table="public.jobs", extra="AND t.is_active = TRUE")
        )

    worker_cities: dict[str, list[CityCount]] = defaultdict(list)
    for r in worker_city_rows:
        worker_cities[r["code"]].append(
            CityCount(city=r["city"], state=r["state"], count=int(r["n"]))
        )
    job_cities: dict[str, list[CityCount]] = defaultdict(list)
    for r in job_city_rows:
        job_cities[r["code"]].append(
            CityCount(city=r["city"], state=r["state"], count=int(r["n"]))
        )

    families = [
        FamilySupplyDemand(
            code=r["code"],
            name=r["name"],
            workers=int(r["workers"] or 0),
            jobs=int(r["jobs"] or 0),
            worker_cities=worker_cities.get(r["code"], []),
            job_cities=job_cities.get(r["code"], []),
        )
        for r in fam_rows
        if int(r["workers"] or 0) + int(r["jobs"] or 0) > 0
    ]
    families.sort(key=lambda f: (-abs(f.workers - f.jobs), -(f.workers + f.jobs)))

    return SupplyDemandResponse(
        families=families,
        total_workers=sum(f.workers for f in families),
        total_jobs=sum(f.jobs for f in families),
    )


# ---------------------------------------------------------------------------
# GET /viz/supply-demand/geo
# ---------------------------------------------------------------------------

_GEO_POINTS_SQL = """
    SELECT 'worker' AS kind, a.lat, a.lng, a.city, a.state,
           jf.code AS family_code, jf.name AS family_name
    FROM public.applicants a
    LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
    WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL
    UNION ALL
    SELECT 'job' AS kind, j.lat, j.lng, j.city, j.state,
           jf.code AS family_code, jf.name AS family_name
    FROM public.jobs j
    LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
    WHERE j.is_active = TRUE AND j.lat IS NOT NULL AND j.lng IS NOT NULL
"""


@router.get("/supply-demand/geo", response_model=SupplyDemandGeoResponse)
async def supply_demand_geo(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> SupplyDemandGeoResponse:
    """Metro clusters (0.5° grid ≈ 35 mi) with worker/job counts and a
    per-family breakdown, for the two-sided geographic view."""
    async with get_db() as conn:
        rows = await conn.fetch(_GEO_POINTS_SQL)

    clusters = grid_cluster([dict(r) for r in rows], cell_deg=DEFAULT_CELL_DEG)
    return SupplyDemandGeoResponse(
        clusters=[GeoCluster(**c) for c in clusters],
        cell_deg=DEFAULT_CELL_DEG,
    )


# ---------------------------------------------------------------------------
# GET /viz/score-distribution
# ---------------------------------------------------------------------------

@router.get("/score-distribution", response_model=ScoreDistributionResponse)
async def score_distribution(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    nbins: int = Query(default=50, ge=10, le=100),
) -> ScoreDistributionResponse:
    """Histogram of ALL matches.base_fit_score values, bucketed server-side
    (width_bucket) so 132k+ rows never cross the wire. Band thresholds come
    from the active matching config; the annotation is computed live."""
    async with get_db() as conn:
        thresholds = await _active_match_labels(conn)
        good_min = thresholds["good_fit_min"]

        stats = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   MIN(base_fit_score)::float AS min,
                   MAX(base_fit_score)::float AS max,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY base_fit_score)::float AS p95,
                   AVG((base_fit_score < $1)::int)::float AS share_below_good
            FROM public.matches
            WHERE base_fit_score IS NOT NULL
            """,
            good_min,
        )
        bucket_rows = await conn.fetch(
            """
            SELECT width_bucket(base_fit_score, 0, 100, $1::int) AS b, COUNT(*) AS n
            FROM public.matches
            WHERE base_fit_score IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """,
            nbins,
        )
        elig_rows = await conn.fetch(
            """
            SELECT eligibility_status::text AS s, COUNT(*) AS n
            FROM public.matches GROUP BY 1
            """
        )

    total = int(stats["total"] or 0) if stats else 0
    counts: dict[int, int] = {int(r["b"]): int(r["n"]) for r in bucket_rows}
    buckets = [
        ScoreBucket(x0=x0, x1=x1, count=counts.get(i + 1, 0))
        for i, (x0, x1) in enumerate(bucket_edges(0.0, 100.0, nbins))
    ]
    # width_bucket sends out-of-range values to buckets 0 and nbins+1; base_fit
    # is bounded [0, 100] (100 itself lands in nbins+1) — clamp so nothing is
    # ever dropped from the histogram.
    if counts.get(0):
        buckets[0].count += counts[0]
    if counts.get(nbins + 1):
        buckets[-1].count += counts[nbins + 1]

    eligibility = {r["s"]: int(r["n"]) for r in elig_rows}
    return ScoreDistributionResponse(
        total=total,
        min=stats["min"] if stats else None,
        max=stats["max"] if stats else None,
        p95=stats["p95"] if stats else None,
        buckets=buckets,
        thresholds=thresholds,
        eligibility=eligibility,
        annotation=build_annotation(
            total=total,
            p95=stats["p95"] if stats else None,
            eligible=eligibility.get("eligible", 0),
            good_fit_min=good_min,
            share_below_good=stats["share_below_good"] if stats else None,
        ),
    )
