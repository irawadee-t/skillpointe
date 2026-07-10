"""Unit tests for verified-worker hybrid relevance ranking."""
from app.skilled_pro import ranking


def test_query_matches_trade_and_credentials():
    assert ranking.query_matches("weld", "Welding", []) is True
    assert ranking.query_matches("epa", None, ["EPA 608 Certification"]) is True
    assert ranking.query_matches("plumb", "Welding", ["EPA 608"]) is False
    assert ranking.query_matches(None, "Welding", ["EPA"]) is False


def test_more_credentials_and_recency_rank_higher():
    fresh_many = ranking.relevance_score(verified_count=5, days_since_active=5)
    stale_few = ranking.relevance_score(verified_count=1, days_since_active=400)
    assert fresh_many > stale_few
    assert 0.0 <= stale_few <= fresh_many <= 1.0


def test_query_match_boosts_score():
    matched = ranking.relevance_score(
        verified_count=2, days_since_active=20, q="weld", trade="Welding", credential_names=[])
    missed = ranking.relevance_score(
        verified_count=2, days_since_active=20, q="weld", trade="Plumbing", credential_names=[])
    assert matched > missed


def test_no_query_redistributes_weight():
    # Without a query, a strong structured profile should still score high.
    s = ranking.relevance_score(verified_count=5, days_since_active=10)
    assert s >= 0.9


def test_score_is_bounded():
    s = ranking.relevance_score(
        verified_count=99, days_since_active=0, q="x", trade="x", credential_names=["x"])
    assert s <= 1.0
