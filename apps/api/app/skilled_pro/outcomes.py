"""
SKILLED Foundation outcomes analytics — pure aggregation + privacy logic.

Takes per-applicant outcome rows (from the applicant_outcomes view) and computes
WIOA-style cohort metrics: employment (placement) rate, median earnings,
credential attainment rate, median time-to-hire. Applies k-anonymity suppression
so any externally-shared feed never exposes a small cohort.

All pure (no I/O) — unit-tested. The router supplies rows and chooses k.
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable

DEFAULT_K = 10  # minimum cohort size before metrics may be published


def median_int(values: Iterable[float | int | None]) -> int | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return int(round(statistics.median(nums)))


def rate(numerator: int, denominator: int) -> float | None:
    """Fraction in [0,1], rounded to 3 dp. None when there's no denominator."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 3)


def _metrics_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    placed = [r for r in rows if r.get("placed")]
    attained = [r for r in rows if (r.get("credential_count") or 0) > 0]
    return {
        "n": n,
        "placed": len(placed),
        "employment_rate": rate(len(placed), n),
        "median_wage": median_int(r.get("wage") for r in placed),
        "attainment_rate": rate(len(attained), n),
        "median_time_to_hire_days": median_int(r.get("time_to_hire_days") for r in placed),
    }


def overall_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline numbers across everyone served (no suppression — admin view)."""
    m = _metrics_for(rows)
    m["total_served"] = m.pop("n")
    return m


def aggregate_cohorts(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    """
    Group rows by a single dimension ('program' | 'region' | 'cohort_year') and
    compute metrics per cohort. Returned sorted by cohort size desc.
    """
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for r in rows:
        key = r.get(group_by)
        if key is None:
            key = "Unspecified"
        buckets.setdefault(key, []).append(r)

    cohorts = [{"cohort": str(key), **_metrics_for(group)} for key, group in buckets.items()]
    cohorts.sort(key=lambda c: c["n"], reverse=True)
    return cohorts


def apply_k_anonymity(cohorts: list[dict[str, Any]], k: int = DEFAULT_K) -> list[dict[str, Any]]:
    """
    For a publishable feed: any cohort with n < k is suppressed — its metrics are
    nulled and flagged. Cohort existence + that it's suppressed is disclosed (so
    totals reconcile), but no rates/wages leak for a small group.
    """
    out: list[dict[str, Any]] = []
    for c in cohorts:
        if c["n"] < k:
            out.append({
                "cohort": c["cohort"],
                "n": c["n"],
                "suppressed": True,
                "employment_rate": None,
                "median_wage": None,
                "attainment_rate": None,
                "median_time_to_hire_days": None,
            })
        else:
            out.append({**c, "suppressed": False})
    return out
