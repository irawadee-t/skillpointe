"""
coerce.py — type coercion helpers for raw import values.

All functions return (value, warning_message).
If coercion fails or input is blank, value is None and warning explains why.
"""
from __future__ import annotations

import re
from datetime import date


_BOOL_TRUE  = {"y", "yes", "true", "1", "x", "✓", "✔", "on", "t"}
_BOOL_FALSE = {"n", "no", "false", "0", "", "off", "f", "none", "n/a", "-"}


def coerce_bool(value: str | None, field_name: str = "") -> tuple[bool | None, str | None]:
    """
    Convert common boolean-ish strings to True / False.
    Returns (bool_or_None, warning_or_None).
    """
    if value is None:
        return None, None
    v = str(value).strip().lower()
    if v in _BOOL_TRUE:
        return True, None
    if v in _BOOL_FALSE:
        return False, None
    warn = f"Unrecognised boolean value for {field_name!r}: {value!r} — defaulting to False"
    return False, warn


def coerce_date(value: str | None, field_name: str = "") -> tuple[date | None, str | None]:
    """
    Parse a date string flexibly.  Returns (date_or_None, warning_or_None).
    """
    if value is None:
        return None, None
    v = str(value).strip()
    if not v or v.lower() in ("none", "n/a", "-", ""):
        return None, None
    try:
        from dateutil import parser as dp
        parsed = dp.parse(v, dayfirst=False)
        return parsed.date(), None
    except Exception:
        warn = f"Could not parse date for {field_name!r}: {value!r} — stored as None"
        return None, warn


def coerce_int(value: str | None, field_name: str = "") -> tuple[int | None, str | None]:
    """Parse an integer, returning None + warning on failure."""
    if value is None:
        return None, None
    v = str(value).strip()
    if not v or v.lower() in ("none", "n/a", "-"):
        return None, None
    # Strip common non-numeric chars (miles, mi, etc.)
    v_clean = re.sub(r"[^\d]", "", v)
    if not v_clean:
        return None, f"Could not parse integer for {field_name!r}: {value!r}"
    try:
        return int(v_clean), None
    except ValueError:
        return None, f"Could not parse integer for {field_name!r}: {value!r}"


def coerce_text(value: str | None) -> str | None:
    """Strip whitespace; return None for blank/None values."""
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def coerce_state(value: str | None) -> str | None:
    """Uppercase and strip a US state code."""
    if value is None:
        return None
    v = str(value).strip().upper()
    return v if v else None


def split_full_name(value: str | None) -> tuple[str | None, str | None]:
    """
    Split 'First Last' or 'Last, First' into (first_name, last_name).
    Returns (None, None) for blank input.
    """
    if not value:
        return None, None
    v = value.strip()
    if "," in v:
        # "Last, First" format
        parts = [p.strip() for p in v.split(",", 1)]
        return parts[1] or None, parts[0] or None
    parts = v.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]
