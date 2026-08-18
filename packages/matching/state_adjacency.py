"""US state adjacency — candidate-generation support for border commutes.

The geography GATE already treats commute radius as crossing state lines
(Camden, NJ -> Philadelphia, PA passes on distance). The candidate prefilter
was same-state only, so those pairs were never generated and the gate never
got to rule on them — a silent recall hole that left 98% of zero-match
applicants (11.6k people, 2026-08 audit) without candidates that exist one
state over. Prefilter expansion uses this map; the gate remains the decider.

Land-border adjacency for the 48 contiguous states + DC. AK/HI have no
neighbors. Four Corners diagonal touches (AZ-CO, NM-UT) are excluded — a
point touch is not a commute.
"""
from __future__ import annotations

_EDGES: list[tuple[str, str]] = [
    ("AL", "FL"), ("AL", "GA"), ("AL", "MS"), ("AL", "TN"),
    ("AR", "LA"), ("AR", "MO"), ("AR", "MS"), ("AR", "OK"), ("AR", "TN"), ("AR", "TX"),
    ("AZ", "CA"), ("AZ", "NM"), ("AZ", "NV"), ("AZ", "UT"),
    ("CA", "NV"), ("CA", "OR"),
    ("CO", "KS"), ("CO", "NE"), ("CO", "NM"), ("CO", "OK"), ("CO", "UT"), ("CO", "WY"),
    ("CT", "MA"), ("CT", "NY"), ("CT", "RI"),
    ("DC", "MD"), ("DC", "VA"),
    ("DE", "MD"), ("DE", "NJ"), ("DE", "PA"),
    ("FL", "GA"),
    ("GA", "NC"), ("GA", "SC"), ("GA", "TN"),
    ("IA", "IL"), ("IA", "MN"), ("IA", "MO"), ("IA", "NE"), ("IA", "SD"), ("IA", "WI"),
    ("ID", "MT"), ("ID", "NV"), ("ID", "OR"), ("ID", "UT"), ("ID", "WA"), ("ID", "WY"),
    ("IL", "IN"), ("IL", "KY"), ("IL", "MO"), ("IL", "WI"),
    ("IN", "KY"), ("IN", "MI"), ("IN", "OH"),
    ("KS", "MO"), ("KS", "NE"), ("KS", "OK"),
    ("KY", "MO"), ("KY", "OH"), ("KY", "TN"), ("KY", "VA"), ("KY", "WV"),
    ("LA", "MS"), ("LA", "TX"),
    ("MA", "NH"), ("MA", "NY"), ("MA", "RI"), ("MA", "VT"),
    ("MD", "PA"), ("MD", "VA"), ("MD", "WV"),
    ("ME", "NH"),
    ("MI", "OH"), ("MI", "WI"),
    ("MN", "ND"), ("MN", "SD"), ("MN", "WI"),
    ("MO", "NE"), ("MO", "OK"), ("MO", "TN"),
    ("MS", "TN"),
    ("MT", "ND"), ("MT", "SD"), ("MT", "WY"),
    ("NC", "SC"), ("NC", "TN"), ("NC", "VA"),
    ("ND", "SD"),
    ("NE", "SD"), ("NE", "WY"),
    ("NH", "VT"),
    ("NJ", "NY"), ("NJ", "PA"),
    ("NM", "OK"), ("NM", "TX"),
    ("NV", "OR"), ("NV", "UT"),
    ("NY", "PA"), ("NY", "VT"),
    ("OH", "PA"), ("OH", "WV"),
    ("OK", "TX"),
    ("OR", "WA"),
    ("PA", "WV"),
    ("SD", "WY"),
    ("TN", "VA"),
    ("UT", "WY"),
    ("VA", "WV"),
]

ADJACENT: dict[str, frozenset[str]] = {}
_tmp: dict[str, set[str]] = {}
for _a, _b in _EDGES:
    _tmp.setdefault(_a, set()).add(_b)
    _tmp.setdefault(_b, set()).add(_a)
ADJACENT = {s: frozenset(n) for s, n in _tmp.items()}
del _tmp


def neighbors(state: str | None) -> frozenset[str]:
    """Adjacent states for a two-letter code; empty for unknown/AK/HI/None."""
    if not state:
        return frozenset()
    return ADJACENT.get(state.strip().upper(), frozenset())


def is_adjacent(state_a: str | None, state_b: str | None) -> bool:
    if not state_a or not state_b:
        return False
    return state_b.strip().upper() in neighbors(state_a)
