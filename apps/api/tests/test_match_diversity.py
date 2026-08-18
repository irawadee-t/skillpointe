"""Per-employer soft cap on ranked match pages."""
from app.routers.applicants import _diversify_page


def _rows(*employers):
    return [{"employer_name": e, "job_id": i} for i, e in enumerate(employers)]


def test_no_cap_hit_keeps_order():
    rows = _rows("A", "B", "C", "A", "B")
    assert [r["employer_name"] for r in _diversify_page(rows)] == ["A", "B", "C", "A", "B"]


def test_fourth_from_same_employer_moves_to_end():
    rows = _rows("A", "A", "A", "A", "B")
    out = [r["employer_name"] for r in _diversify_page(rows)]
    assert out == ["A", "A", "A", "B", "A"]


def test_page_membership_unchanged():
    rows = _rows("A", "A", "A", "A", "A", "B", "C")
    out = _diversify_page(rows)
    assert sorted(r["job_id"] for r in out) == sorted(r["job_id"] for r in rows)


def test_overflow_preserves_relative_order():
    rows = _rows("A", "A", "A", "A", "A", "B")
    out = [r["job_id"] for r in _diversify_page(rows)]
    assert out == [0, 1, 2, 5, 3, 4]
