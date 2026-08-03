"""
suggest.py — shared prefix-weighted suggestion helper.

One query shape powers every as-you-type suggestion dropdown (admin jobs
console, verified-worker keyword, applicant job browse): distinct labels
matching the query as a SUBSTRING, ordered so PREFIX matches rank first
("ge" surfaces "GE Vernova" above "Schneider Electric — Georgia"), capped
so the dropdown stays scannable.

The WHERE fragment each caller passes MUST be the same predicate family its
list endpoint filters by (predicate parity) — picking a suggestion has to
narrow the list exactly as typing the same text would. Role scoping
(consent gates, employer isolation) also lives in that fragment and is
asserted in tests/test_suggest_endpoints.py.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Suggestion(BaseModel):
    """One dropdown row. `label` is both the display text and (by default)
    the text applied to the surface's search filter on selection."""

    kind: str                    # job | employer | trade | credential | applicant
    label: str
    sublabel: str | None = None


class SuggestResponse(BaseModel):
    suggestions: list[Suggestion]


async def fetch_label_suggestions(
    conn: Any,
    *,
    kind: str,
    label_expr: str,
    from_clause: str,
    where: str = "TRUE",
    params: tuple[Any, ...] = (),
    q: str,
    limit: int,
) -> list[Suggestion]:
    """Distinct labels ILIKE %q%, prefix matches first, then alphabetical.

    `label_expr` / `from_clause` / `where` are trusted SQL fragments composed
    by the caller (never user input); `q` and `params` always bind.
    """
    text = q.strip()
    if not text:
        return []
    n = len(params)
    rows = await conn.fetch(
        f"SELECT {label_expr} AS label "
        f"{from_clause} "
        f"WHERE ({where}) AND {label_expr} ILIKE ${n + 1} "
        f"GROUP BY 1 "
        f"ORDER BY ({label_expr} ILIKE ${n + 2}) DESC, 1 "
        f"LIMIT ${n + 3}",
        *params,
        f"%{text}%",
        f"{text}%",
        limit,
    )
    return [
        Suggestion(kind=kind, label=r["label"])
        for r in rows
        if r["label"] and str(r["label"]).strip()
    ]


def cap_groups(groups: list[list[Suggestion]], total: int = 8) -> list[Suggestion]:
    """Merge ordered groups into one dropdown list of at most `total` rows.

    Earlier groups get priority, but every non-empty group keeps at least one
    row when possible so the grouping stays visible ("Jobs" AND "Employers"
    both appear for "ge", not eight job titles).
    """
    non_empty = [g for g in groups if g]
    if not non_empty:
        return []
    # Reserve one slot per non-empty group, then fill in group order.
    quotas = [1] * len(non_empty)
    remaining = total - len(non_empty)
    for i, g in enumerate(non_empty):
        if remaining <= 0:
            break
        extra = min(len(g) - quotas[i], remaining)
        quotas[i] += extra
        remaining -= extra
    out: list[Suggestion] = []
    for g, quota in zip(non_empty, quotas):
        out.extend(g[:quota])
    return out[:total]
