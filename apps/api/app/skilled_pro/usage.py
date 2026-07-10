"""
Usage analytics helpers for the SKILLED ID partner console.

Pure date/series logic kept out of the router so it's unit-testable. The DB
returns sparse per-day counts; charts need a dense, zero-filled, ordered series.
"""
from __future__ import annotations

from datetime import date, timedelta


def fill_daily_series(
    counts_by_day: dict[str, int],
    days: int,
    today: date,
) -> list[dict[str, int | str]]:
    """
    Return a dense ascending series of the last ``days`` days (inclusive of
    today), each as {"date": "YYYY-MM-DD", "count": int}, zero-filling any day
    absent from ``counts_by_day`` (keyed by ISO date string).
    """
    if days < 1:
        return []
    start = today - timedelta(days=days - 1)
    out: list[dict[str, int | str]] = []
    for i in range(days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        out.append({"date": key, "count": int(counts_by_day.get(key, 0))})
    return out
