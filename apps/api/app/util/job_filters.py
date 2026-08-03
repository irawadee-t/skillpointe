"""
Shared predicate builder for granular job-posting filters.

Used by BOTH the admin jobs console (/admin/jobs) and the employer jobs list
(/employer/me/jobs) so the two surfaces filter identically. All predicates
assume the standard aliases:

    j  -> public.jobs
    e  -> public.employers            (LEFT JOIN on j.employer_id)
    jf -> public.canonical_job_families (LEFT JOIN on j.canonical_job_family_id)

Every filter appends ONE predicate string to `conditions` (AND across facets)
and binds values positionally into `params` — OR semantics within a
multi-select via `= ANY($n::text[])`. The caller embeds the joined conditions
into BOTH its COUNT query and its list query, which is what guarantees
count/list predicate parity (tested in tests/test_granular_job_filters.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException

# A job "has candidates" in the same sense the employer candidate list uses:
# visible-to-ranking matches that are eligible or near_fit. Keeping the
# predicate identical to the candidate surfaces avoids count drift.
CANDIDATES_EXPR = (
    "(SELECT COUNT(*) FROM public.matches mc "
    "WHERE mc.job_id = j.id AND mc.eligibility_status IN ('eligible', 'near_fit'))"
)

CANDIDATE_BANDS = {
    "none": f"{CANDIDATES_EXPR} = 0",
    "1_9": f"{CANDIDATES_EXPR} BETWEEN 1 AND 9",
    "10_49": f"{CANDIDATES_EXPR} BETWEEN 10 AND 49",
    "over_50": f"{CANDIDATES_EXPR} >= 50",
}

# "Stale" = still marked active but nothing has confirmed it recently.
# Freshness signal: link-check time, else the posting date, else row creation.
STALE_PRED = (
    "COALESCE(j.last_verified_at, j.posted_date::timestamptz, j.created_at) "
    "< now() - INTERVAL '60 days'"
)

STATUS_PREDS = {
    "active": "j.is_active = TRUE",
    "inactive": "j.is_active = FALSE",
    "stale": f"(j.is_active = TRUE AND {STALE_PRED})",
    # Lifecycle statuses (jobs.status; kept in sync with is_active by trigger)
    "paused": "j.status = 'paused'",
    "filled": "j.status = 'filled'",
    "closed": "j.status = 'closed'",
}

APPLY_LINK_PREDS = {
    "ok": "j.apply_link_status = 'ok'",
    "broken": "j.apply_link_status = 'broken'",
    "unchecked": "j.apply_link_status IS NULL",
}

SORTS = {
    "newest": "j.created_at DESC",
    "posted": "j.posted_date DESC NULLS LAST, j.created_at DESC",
    "title": "COALESCE(j.title_normalized, j.title_raw) ASC",
    "pay": "COALESCE(j.pay_max, j.pay_min) DESC NULLS LAST, j.created_at DESC",
}


@dataclass
class JobFilterParams:
    """Parsed filter values (multi-selects already split from CSV)."""
    q: Optional[str] = None
    families: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    city: Optional[str] = None
    employment_types: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    source_sites: list[str] = field(default_factory=list)
    status: Optional[str] = None            # active | inactive | stale
    apply_link: Optional[str] = None        # ok | broken | unchecked
    has_pay: Optional[bool] = None
    pay_gte: Optional[float] = None
    internal_apply: Optional[bool] = None   # only when the column exists
    posted_from: Optional[date] = None
    posted_to: Optional[date] = None
    created_from: Optional[date] = None
    created_to: Optional[date] = None
    candidates: Optional[str] = None        # none | 1_9 | 10_49 | over_50


def build_job_conditions(
    fp: JobFilterParams,
    params: list[Any],
    *,
    internal_apply_supported: bool = False,
) -> list[str]:
    """Append bind params and return the predicate list (caller ANDs them)."""
    conditions: list[str] = []

    def bind(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    if fp.q:
        ph = bind(f"%{fp.q}%")
        conditions.append(
            f"(j.title_raw ILIKE {ph} OR j.title_normalized ILIKE {ph} OR e.name ILIKE {ph})"
        )
    if fp.families:
        conditions.append(f"jf.code = ANY({bind(fp.families)}::text[])")
    if fp.industries:
        # A job's industry comes from its employer's industry, or — when the
        # taxonomy carries one — the canonical family's industries array.
        ph = bind(fp.industries)
        conditions.append(
            f"(TRIM(e.industry) = ANY({ph}::text[]) OR jf.industries && {ph}::text[])"
        )
    if fp.states:
        conditions.append(f"UPPER(j.state) = ANY({bind(fp.states)}::text[])")
    if fp.city:
        conditions.append(f"j.city ILIKE {bind(f'%{fp.city}%')}")
    if fp.employment_types:
        conditions.append(f"j.employment_type = ANY({bind(fp.employment_types)}::text[])")
    if fp.sources:
        conditions.append(f"j.source = ANY({bind(fp.sources)}::text[])")
    if fp.source_sites:
        conditions.append(f"j.source_site = ANY({bind(fp.source_sites)}::text[])")
    if fp.status:
        pred = STATUS_PREDS.get(fp.status)
        if pred is None:
            raise HTTPException(422, f"status must be one of: {', '.join(STATUS_PREDS)}")
        conditions.append(pred)
    if fp.apply_link:
        pred = APPLY_LINK_PREDS.get(fp.apply_link)
        if pred is None:
            raise HTTPException(422, f"apply_link must be one of: {', '.join(APPLY_LINK_PREDS)}")
        conditions.append(pred)
    if fp.has_pay is not None:
        pred = "(j.pay_min IS NOT NULL OR j.pay_max IS NOT NULL OR NULLIF(TRIM(j.pay_raw), '') IS NOT NULL)"
        conditions.append(pred if fp.has_pay else f"NOT {pred}")
    if fp.pay_gte is not None:
        # "Can pay at least X" against structured pay — raw-text-only pay
        # can't be compared numerically and is excluded by this filter.
        conditions.append(f"COALESCE(j.pay_max, j.pay_min) >= {bind(fp.pay_gte)}")
    if fp.internal_apply is not None:
        if not internal_apply_supported:
            raise HTTPException(
                422, "internal_apply filtering is not available on this deployment"
            )
        conditions.append(f"COALESCE(j.accepts_internal_applications, FALSE) = {bind(fp.internal_apply)}")
    if fp.posted_from:
        conditions.append(f"j.posted_date >= {bind(fp.posted_from)}")
    if fp.posted_to:
        conditions.append(f"j.posted_date <= {bind(fp.posted_to)}")
    if fp.created_from:
        conditions.append(f"j.created_at >= {bind(fp.created_from)}")
    if fp.created_to:
        conditions.append(f"j.created_at < {bind(fp.created_to)} + INTERVAL '1 day'")
    if fp.candidates:
        pred = CANDIDATE_BANDS.get(fp.candidates)
        if pred is None:
            raise HTTPException(422, f"candidates must be one of: {', '.join(CANDIDATE_BANDS)}")
        conditions.append(pred)

    return conditions


def resolve_sort(sort: str) -> str:
    order = SORTS.get(sort)
    if order is None:
        raise HTTPException(422, f"sort must be one of: {', '.join(SORTS)}")
    return order
