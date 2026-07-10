"""Unit tests for the SKILLED ID usage time-series helper."""
from datetime import date

from app.skilled_pro.usage import fill_daily_series


def test_zero_fills_and_orders_ascending():
    s = fill_daily_series({"2026-06-25": 3, "2026-06-27": 5}, days=3, today=date(2026, 6, 27))
    assert s == [
        {"date": "2026-06-25", "count": 3},
        {"date": "2026-06-26", "count": 0},
        {"date": "2026-06-27", "count": 5},
    ]


def test_length_matches_days_and_ends_today():
    s = fill_daily_series({}, days=30, today=date(2026, 6, 27))
    assert len(s) == 30
    assert s[-1] == {"date": "2026-06-27", "count": 0}
    assert s[0]["date"] == "2026-05-29"


def test_ignores_out_of_window_days():
    s = fill_daily_series({"2026-01-01": 99}, days=2, today=date(2026, 6, 27))
    assert all(row["count"] == 0 for row in s)


def test_zero_days_is_empty():
    assert fill_daily_series({"x": 1}, days=0, today=date(2026, 6, 27)) == []
