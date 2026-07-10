"""
Granular consent evaluation.

A worker controls three INDEPENDENT consent scopes per data category:

    DISPLAY            show on my public/SKILLED profile
    INTERNAL_USE       SKILLED may use it internally (matching, analytics)
    EXTERNAL_SHARING   share with third parties via SKILLED ID — gated further by
                       the *category* of requester (employer, staffing, jobboard,
                       background_check, government, ...)

Defaults are deny: nothing is shared externally unless the worker explicitly
opted in for that requester category. Every consent decision is recorded as an
immutable, signed consent record (see signing.py) so external sharing is
cryptographically auditable.

Pure logic — unit-tested without DB/network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ConsentScope(str, Enum):
    DISPLAY = "display"
    INTERNAL_USE = "internal_use"
    EXTERNAL_SHARING = "external_sharing"


class RequesterCategory(str, Enum):
    EMPLOYER = "employer"
    STAFFING_AGENCY = "staffing_agency"
    JOB_BOARD = "job_board"            # Glassdoor / Indeed
    BACKGROUND_CHECK = "background_check"
    GOVERNMENT = "government"
    UNION = "union"
    OTHER = "other"


@dataclass(frozen=True)
class ConsentState:
    """A worker's current consent settings for a single data category."""
    display: bool = False
    internal_use: bool = True   # internal platform use opted in at signup (revocable)
    # External sharing is per requester-category; absence/False => denied.
    external_sharing: frozenset[RequesterCategory] = field(default_factory=frozenset)

    def allows(self, scope: ConsentScope, requester: RequesterCategory | None = None) -> bool:
        if scope == ConsentScope.DISPLAY:
            return self.display
        if scope == ConsentScope.INTERNAL_USE:
            return self.internal_use
        if scope == ConsentScope.EXTERNAL_SHARING:
            if requester is None:
                # No specific requester => only true if ANY external sharing is allowed.
                return len(self.external_sharing) > 0
            return requester in self.external_sharing
        return False


def can_share_externally(state: ConsentState, requester: RequesterCategory) -> bool:
    """Convenience: may this data category be returned to ``requester`` via SKILLED ID?"""
    return state.allows(ConsentScope.EXTERNAL_SHARING, requester)


def filter_categories_for_requester(
    states: dict[str, ConsentState],
    requester: RequesterCategory,
) -> list[str]:
    """
    Given {category -> ConsentState}, return the categories this requester is
    permitted to receive. This is the data-minimization gate applied to every
    SKILLED ID response.
    """
    return [cat for cat, st in states.items() if can_share_externally(st, requester)]


def parse_external_sharing(values: Iterable[str]) -> frozenset[RequesterCategory]:
    """Tolerantly parse requester-category strings (e.g. from JSONB) into the enum."""
    out: set[RequesterCategory] = set()
    for v in values or []:
        try:
            out.add(RequesterCategory(v))
        except ValueError:
            continue
    return frozenset(out)
