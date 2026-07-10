"""
Hybrid relevance ranking for the verified-worker directory (pure).

Combines structured signals — verified-credential count and recency of activity —
with a free-text query match over trade + credential names. Returns a 0..1 score
so the directory ranks the most relevant, freshest, best-credentialed workers
first (and surfaces the score to employers), rather than a flat filter list.
"""
from __future__ import annotations

W_CREDENTIALS = 0.45
W_RECENCY = 0.25
W_QUERY = 0.30


def _recency_factor(days_since_active: int | None) -> float:
    if days_since_active is None:
        return 0.3
    if days_since_active <= 30:
        return 1.0
    if days_since_active <= 90:
        return 0.7
    if days_since_active <= 365:
        return 0.4
    return 0.1


def query_matches(q: str | None, trade: str | None, credential_names: list[str]) -> bool:
    if not q:
        return False
    ql = q.strip().lower()
    if not ql:
        return False
    if trade and ql in trade.lower():
        return True
    return any(ql in (c or "").lower() for c in credential_names)


def relevance_score(
    *,
    verified_count: int,
    days_since_active: int | None,
    q: str | None = None,
    trade: str | None = None,
    credential_names: list[str] | None = None,
) -> float:
    creds = min(verified_count, 5) / 5.0
    recency = _recency_factor(days_since_active)
    matched = query_matches(q, trade, credential_names or [])
    # When there's no query, redistribute its weight to the structured signals so
    # scores stay well-spread instead of capping low.
    if not q:
        score = (W_CREDENTIALS + W_QUERY * 0.6) * creds + (W_RECENCY + W_QUERY * 0.4) * recency
    else:
        score = W_CREDENTIALS * creds + W_RECENCY * recency + W_QUERY * (1.0 if matched else 0.0)
    return round(min(1.0, score), 3)
