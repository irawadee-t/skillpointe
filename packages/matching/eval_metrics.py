"""
eval_metrics.py — offline ranking-evaluation metrics for the matching engine.

Pure Python, dependency-free, no DB I/O. Metric definitions follow the
conventions used by Microsoft Recommenders / recometrics.

All functions are deterministic and total: no exceptions on empty or
degenerate input. Where a metric is mathematically undefined the function
returns None (documented per function); otherwise it returns a float.

Conventions
-----------
- ``ranked`` is a list of item ids in rank order (best first). Duplicate
  items are counted once at their first (best) position.
- ``relevant`` is a set of item ids considered relevant (binary relevance).
- ``grades`` maps item id -> non-negative relevance grade (graded relevance);
  items absent from the dict have grade 0.
- ``k`` is the cutoff; ``k <= 0`` is undefined and returns None.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet


def _top_k(ranked: Sequence, k: int) -> list:
    """First k items of ``ranked`` with duplicates removed (first occurrence kept)."""
    seen = set()
    out = []
    for item in ranked:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) == k:
            break
    return out


def precision_at_k(relevant: AbstractSet, ranked: Sequence, k: int) -> float | None:
    """
    Precision@k = |top-k(ranked) ∩ relevant| / k.

    The denominator is always k (Recommenders convention), so a ranking
    shorter than k is penalized for the missing slots.

    Returns None if k <= 0. Returns 0.0 if ``ranked`` or ``relevant`` is empty.
    """
    if k <= 0:
        return None
    if not ranked or not relevant:
        return 0.0
    hits = sum(1 for item in _top_k(ranked, k) if item in relevant)
    return hits / k


def recall_at_k(relevant: AbstractSet, ranked: Sequence, k: int) -> float | None:
    """
    Recall@k = |top-k(ranked) ∩ relevant| / |relevant|.

    Returns None if k <= 0 or ``relevant`` is empty (undefined denominator).
    Returns 0.0 if ``ranked`` is empty.
    """
    if k <= 0 or not relevant:
        return None
    if not ranked:
        return 0.0
    hits = sum(1 for item in _top_k(ranked, k) if item in relevant)
    return hits / len(relevant)


def hit_rate_at_k(relevant: AbstractSet, ranked: Sequence, k: int) -> float | None:
    """
    HitRate@k = 1.0 if top-k(ranked) contains at least one relevant item, else 0.0.

    Returns None if k <= 0 or ``relevant`` is empty (nothing can ever hit).
    Returns 0.0 if ``ranked`` is empty.
    """
    if k <= 0 or not relevant:
        return None
    if not ranked:
        return 0.0
    return 1.0 if any(item in relevant for item in _top_k(ranked, k)) else 0.0


def ndcg_at_k(grades: Mapping, ranked: Sequence, k: int) -> float | None:
    """
    NDCG@k with exponential gain and log2 discount (Recommenders default):

        DCG@k  = Σ_{i=1..k} (2^grade(item_i) - 1) / log2(i + 1)
        IDCG@k = DCG@k of the ideal ordering (grades sorted descending)
        NDCG@k = DCG@k / IDCG@k

    where i is the 1-based rank. Items absent from ``grades`` have grade 0.
    The ideal ordering is taken over all graded items (not just those ranked).

    Returns None if k <= 0 or if IDCG is 0 (no positively graded items —
    the metric is undefined). Returns 0.0 if ``ranked`` is empty but positive
    grades exist.
    """
    if k <= 0:
        return None
    ideal = sorted((g for g in grades.values() if g > 0), reverse=True)[:k]
    idcg = sum((2.0 ** g - 1.0) / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    if idcg <= 0.0:
        return None
    dcg = sum(
        (2.0 ** grades.get(item, 0.0) - 1.0) / math.log2(i + 1)
        for i, item in enumerate(_top_k(ranked, k), start=1)
    )
    return dcg / idcg


def mrr(relevant: AbstractSet, ranked: Sequence) -> float | None:
    """
    Reciprocal rank = 1 / (1-based rank of the first relevant item in ``ranked``).

    (The mean over a sample of queries is the caller's job.)

    Returns None if ``relevant`` is empty (undefined). Returns 0.0 if no
    relevant item appears in ``ranked`` (including empty ``ranked``).
    """
    if not relevant:
        return None
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def kendall_tau(rank_a: Sequence, rank_b: Sequence) -> float | None:
    """
    Kendall's tau-a between two rankings, computed over their common items:

        tau = (concordant_pairs - discordant_pairs) / (n * (n - 1) / 2)

    where n is the number of common items and a pair is concordant when both
    rankings order it the same way. Positions within each list are tie-free
    by construction (position = rank).

    Returns None if fewer than 2 common items.
    """
    pos_a = {item: i for i, item in enumerate(rank_a)}
    pos_b = {item: i for i, item in enumerate(rank_b)}
    common = [item for item in rank_a if item in pos_b]
    n = len(common)
    if n < 2:
        return None
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            x, y = common[i], common[j]
            a_order = pos_a[x] - pos_a[y]
            b_order = pos_b[x] - pos_b[y]
            if a_order * b_order > 0:
                concordant += 1
            else:
                discordant += 1
    return (concordant - discordant) / (n * (n - 1) / 2)


def catalog_coverage_at_k(
    list_of_rankings: Iterable[Sequence], catalog_size: int, k: int
) -> float | None:
    """
    Catalog coverage@k = |distinct items appearing in any top-k| / catalog_size.

    Measures what fraction of the catalog the system actually surfaces.

    Returns None if k <= 0 or catalog_size <= 0. Returns 0.0 for an empty
    set of rankings.
    """
    if k <= 0 or catalog_size <= 0:
        return None
    surfaced = set()
    for ranking in list_of_rankings:
        surfaced.update(_top_k(ranking, k))
    return len(surfaced) / catalog_size


def gini_of_exposure(list_of_rankings: Iterable[Sequence], k: int) -> float | None:
    """
    Gini coefficient of item exposure counts within the top-k of each ranking.

    Each appearance of an item in a ranking's top-k counts as one exposure.
    With exposure counts x_1 <= x_2 <= ... <= x_n over the n items that
    received any exposure, the standard (sorted-form) Gini is:

        G = Σ_{i=1..n} (2i - n - 1) * x_i / (n * Σ x_i)

    0.0 = perfectly equal exposure, → 1.0 = exposure concentrated on one item.
    Computed over exposed items only (items never shown do not enter n).

    Returns None if k <= 0 or no item received any exposure.
    """
    if k <= 0:
        return None
    counts: Counter = Counter()
    for ranking in list_of_rankings:
        counts.update(_top_k(ranking, k))
    if not counts:
        return None
    xs = sorted(counts.values())
    n = len(xs)
    total = sum(xs)
    if total == 0:
        return None
    weighted = sum((2 * i - n - 1) * x for i, x in enumerate(xs, start=1))
    return weighted / (n * total)
