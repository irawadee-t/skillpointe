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


#: Every USPS state/territory code the platform serves. Feeds routinely put
#: country codes ("JP", "CN") or arbitrary tokens in the state slot — an
#: unvalidated uppercase pass-through let those masquerade as states and leak
#: into geography gating and the admin views.
US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV "
    "WI WY DC PR GU VI AS MP".split()
)

_STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE",
    "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "WASHINGTON DC": "DC", "DISTRICT OF COLUMBIA": "DC", "PUERTO RICO": "PR",
}


def coerce_state(value: str | None) -> str | None:
    """A real US state/territory code, or None — never a passthrough."""
    if value is None:
        return None
    v = str(value).strip().upper().rstrip(".")
    if not v:
        return None
    if v in US_STATES:
        return v
    return _STATE_NAMES.get(v)


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
