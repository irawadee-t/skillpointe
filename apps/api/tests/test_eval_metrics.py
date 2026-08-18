"""
Tests for packages/matching/eval_metrics.py — offline ranking metrics.

All expected values are hand-computed; the arithmetic is shown in comments.
"""
import sys
from pathlib import Path

import pytest

# Allow importing from packages/matching
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.eval_metrics import (
    catalog_coverage_at_k,
    gini_of_exposure,
    hit_rate_at_k,
    kendall_tau,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

# ---------------------------------------------------------------------------
# precision_at_k
# ---------------------------------------------------------------------------

class TestPrecisionAtK:
    def test_hand_computed(self):
        # top-3 of [a, b, c, d] = [a, b, c]; relevant ∩ top-3 = {a, c} → 2/3
        assert precision_at_k({"a", "c", "d"}, ["a", "b", "c", "d"], 3) == pytest.approx(2 / 3)

    def test_perfect(self):
        assert precision_at_k({"a", "b"}, ["a", "b"], 2) == 1.0

    def test_denominator_is_k_when_ranked_shorter(self):
        # Only 2 items ranked but k=5: 2 hits / 5 slots = 0.4 (Recommenders convention)
        assert precision_at_k({"a", "b"}, ["a", "b"], 5) == pytest.approx(0.4)

    def test_empty_relevant(self):
        assert precision_at_k(set(), ["a", "b"], 2) == 0.0

    def test_empty_ranked(self):
        assert precision_at_k({"a"}, [], 3) == 0.0

    def test_k_zero_undefined(self):
        assert precision_at_k({"a"}, ["a"], 0) is None

    def test_duplicates_counted_once(self):
        # ranked [a, a, b] dedupes to [a, b]; top-3 hits = {a} → 1/3
        assert precision_at_k({"a"}, ["a", "a", "b"], 3) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------

class TestRecallAtK:
    def test_hand_computed(self):
        # top-2 = [a, b]; hits = {a} of relevant {a, c} → 1/2
        assert recall_at_k({"a", "c"}, ["a", "b", "c"], 2) == pytest.approx(0.5)

    def test_full_recall(self):
        assert recall_at_k({"a", "c"}, ["a", "c", "b"], 3) == 1.0

    def test_empty_relevant_undefined(self):
        assert recall_at_k(set(), ["a"], 1) is None

    def test_empty_ranked(self):
        assert recall_at_k({"a"}, [], 1) == 0.0

    def test_k_zero_undefined(self):
        assert recall_at_k({"a"}, ["a"], 0) is None


# ---------------------------------------------------------------------------
# hit_rate_at_k
# ---------------------------------------------------------------------------

class TestHitRateAtK:
    def test_hit(self):
        assert hit_rate_at_k({"c"}, ["a", "b", "c"], 3) == 1.0

    def test_miss_outside_k(self):
        assert hit_rate_at_k({"c"}, ["a", "b", "c"], 2) == 0.0

    def test_empty_relevant_undefined(self):
        assert hit_rate_at_k(set(), ["a"], 1) is None

    def test_empty_ranked(self):
        assert hit_rate_at_k({"a"}, [], 1) == 0.0


# ---------------------------------------------------------------------------
# ndcg_at_k
# ---------------------------------------------------------------------------

class TestNdcgAtK:
    def test_hand_computed_three_items(self):
        # grades: a=3, b=2, c=0; ranked = [b, a, c]; k=3; gain = 2^g - 1
        #   DCG  = (2^2-1)/log2(2) + (2^3-1)/log2(3) + (2^0-1)/log2(4)
        #        = 3/1 + 7/1.5849625007 + 0/2
        #        = 3 + 4.4165082750 = 7.4165082750
        #   IDCG = ideal order [a, b] (c has grade 0, excluded)
        #        = 7/log2(2) + 3/log2(3) = 7 + 1.8927892607 = 8.8927892607
        #   NDCG = 7.4165082750 / 8.8927892607 = 0.8339912324
        grades = {"a": 3.0, "b": 2.0, "c": 0.0}
        assert ndcg_at_k(grades, ["b", "a", "c"], 3) == pytest.approx(0.8339912324, abs=1e-9)

    def test_ideal_order_is_one(self):
        grades = {"a": 3.0, "b": 2.0, "c": 1.0}
        assert ndcg_at_k(grades, ["a", "b", "c"], 3) == pytest.approx(1.0)

    def test_ideal_includes_unranked_items(self):
        # b (grade 2) is never ranked, but IDCG still counts it:
        #   DCG  = (2^3-1)/log2(2) = 7
        #   IDCG = 7/log2(2) + 3/log2(3) = 8.8927892607
        #   NDCG = 7 / 8.8927892607 = 0.7871546030
        grades = {"a": 3.0, "b": 2.0}
        assert ndcg_at_k(grades, ["a"], 3) == pytest.approx(0.7871546030, abs=1e-9)

    def test_all_zero_grades_undefined(self):
        assert ndcg_at_k({"a": 0.0, "b": 0.0}, ["a", "b"], 2) is None

    def test_empty_grades_undefined(self):
        assert ndcg_at_k({}, ["a", "b"], 2) is None

    def test_empty_ranked_is_zero(self):
        assert ndcg_at_k({"a": 3.0}, [], 3) == 0.0

    def test_all_tied_grades_any_order_is_one(self):
        # With identical grades, every ordering is ideal.
        grades = {"a": 2.0, "b": 2.0, "c": 2.0}
        assert ndcg_at_k(grades, ["c", "a", "b"], 3) == pytest.approx(1.0)

    def test_k_truncates(self):
        # k=1: DCG = gain of first item only; IDCG = gain of best item.
        # ranked [b, a]: DCG = 3/1; IDCG = 7/1 → 3/7
        grades = {"a": 3.0, "b": 2.0}
        assert ndcg_at_k(grades, ["b", "a"], 1) == pytest.approx(3 / 7)

    def test_k_zero_undefined(self):
        assert ndcg_at_k({"a": 1.0}, ["a"], 0) is None

    def test_single_item(self):
        assert ndcg_at_k({"a": 1.0}, ["a"], 5) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# mrr
# ---------------------------------------------------------------------------

class TestMrr:
    def test_first_position(self):
        assert mrr({"a"}, ["a", "b"]) == 1.0

    def test_third_position(self):
        assert mrr({"c"}, ["a", "b", "c"]) == pytest.approx(1 / 3)

    def test_earliest_relevant_wins(self):
        assert mrr({"b", "c"}, ["a", "b", "c"]) == pytest.approx(1 / 2)

    def test_no_relevant_found(self):
        assert mrr({"z"}, ["a", "b"]) == 0.0

    def test_empty_relevant_undefined(self):
        assert mrr(set(), ["a"]) is None

    def test_empty_ranked(self):
        assert mrr({"a"}, []) == 0.0


# ---------------------------------------------------------------------------
# kendall_tau
# ---------------------------------------------------------------------------

class TestKendallTau:
    def test_identical(self):
        assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)

    def test_reversed(self):
        assert kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == pytest.approx(-1.0)

    def test_hand_computed_one_swap(self):
        # a=[a,b,c] vs b=[a,c,b]: pairs (a,b) and (a,c) concordant, (b,c)
        # discordant → (2 - 1) / 3 = 1/3
        assert kendall_tau(["a", "b", "c"], ["a", "c", "b"]) == pytest.approx(1 / 3)

    def test_common_items_only(self):
        # Common items {a, c}; both order a before c → tau = 1 over 1 pair
        assert kendall_tau(["a", "x", "c"], ["a", "c", "y"]) == pytest.approx(1.0)

    def test_fewer_than_two_common(self):
        assert kendall_tau(["a", "b"], ["b", "z"]) is None
        assert kendall_tau(["a"], ["z"]) is None
        assert kendall_tau([], []) is None


# ---------------------------------------------------------------------------
# catalog_coverage_at_k
# ---------------------------------------------------------------------------

class TestCatalogCoverage:
    def test_hand_computed(self):
        # top-2 of each: {a, b} ∪ {b, c} = {a, b, c}; catalog 10 → 0.3
        rankings = [["a", "b", "x"], ["b", "c", "y"]]
        assert catalog_coverage_at_k(rankings, 10, 2) == pytest.approx(0.3)

    def test_full_coverage(self):
        assert catalog_coverage_at_k([["a"], ["b"]], 2, 1) == 1.0

    def test_empty_rankings(self):
        assert catalog_coverage_at_k([], 10, 5) == 0.0

    def test_zero_catalog_undefined(self):
        assert catalog_coverage_at_k([["a"]], 0, 1) is None

    def test_k_zero_undefined(self):
        assert catalog_coverage_at_k([["a"]], 10, 0) is None


# ---------------------------------------------------------------------------
# gini_of_exposure
# ---------------------------------------------------------------------------

class TestGiniOfExposure:
    def test_perfect_equality(self):
        # Every item exposed exactly once → G = 0
        rankings = [["a", "b"], ["c", "d"]]
        assert gini_of_exposure(rankings, 2) == pytest.approx(0.0)

    def test_hand_computed_unequal(self):
        # top-1 of three rankings: a, a, b → counts sorted [1, 2], n=2, Σ=3
        #   G = [(2·1-3)·1 + (2·2-3)·2] / (2·3) = (-1 + 2) / 6 = 1/6
        rankings = [["a", "x"], ["a", "y"], ["b", "z"]]
        assert gini_of_exposure(rankings, 1) == pytest.approx(1 / 6)

    def test_single_item_zero(self):
        # One exposed item: n=1 → weighted term (2·1-1-1)·x = 0 → G = 0
        assert gini_of_exposure([["a"]], 1) == pytest.approx(0.0)

    def test_empty_undefined(self):
        assert gini_of_exposure([], 5) is None
        assert gini_of_exposure([[]], 5) is None

    def test_k_zero_undefined(self):
        assert gini_of_exposure([["a"]], 0) is None
