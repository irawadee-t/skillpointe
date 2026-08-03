"""
iCalendar (RFC 5545) generation for the interview calendar feed.

Pure functions, no DB or network — fully unit-testable. The feed is a standard
METHOD:PUBLISH VCALENDAR that Google Calendar, Outlook, and Apple Calendar can
all subscribe to via URL. Update/cancel propagation relies on two invariants:

  * UID is stable per slot (``interview-{slot_id}@skillednation``) and matches
    the UID the web client writes into one-off .ics downloads, so a subscribed
    copy and a downloaded copy dedupe to the same event.
  * SEQUENCE bumps (0 = confirmed, 1 = cancelled) and STATUS:CANCELLED tell
    subscribers a previously confirmed interview was called off.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

PRODID = "-//SKILLED Nation//Interview Feed//EN"


@dataclass(frozen=True)
class FeedEvent:
    uid: str
    start_at: datetime
    end_at: datetime
    summary: str
    description: str = ""
    location: str = ""
    url: str = ""
    cancelled: bool = False


def ics_escape(value: str) -> str:
    """Escape iCalendar TEXT values (RFC 5545 §3.3.11)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def ics_utc(dt: datetime) -> str:
    """UTC timestamp in iCalendar basic format: 20260802T153000Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> list[str]:
    """RFC 5545 §3.1 line folding: max 75 octets per line, continuation
    lines start with a single space. Folding on character boundaries is
    accepted by all mainstream clients."""
    out: list[str] = []
    while len(line.encode("utf-8")) > 75:
        # Walk back from ~74 chars until the prefix fits in 75 octets.
        cut = min(len(line), 74)
        while len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return out


# ---------------------------------------------------------------------------
# Add-to-calendar deep links (used in notification payloads; the web client
# builds the same links for its buttons)
# ---------------------------------------------------------------------------

def google_calendar_link(
    summary: str, start_at: datetime, end_at: datetime,
    *, description: str = "", location: str = "",
) -> str:
    qs = {
        "action": "TEMPLATE",
        "text": summary,
        "dates": f"{ics_utc(start_at)}/{ics_utc(end_at)}",
    }
    if description:
        qs["details"] = description
    if location:
        qs["location"] = location
    return f"https://calendar.google.com/calendar/render?{urlencode(qs)}"


def outlook_calendar_link(
    summary: str, start_at: datetime, end_at: datetime,
    *, description: str = "", location: str = "", work: bool = False,
) -> str:
    """Outlook web deep link. ``work=False`` → outlook.live.com (personal),
    ``work=True`` → outlook.office.com (work/school)."""
    host = "outlook.office.com" if work else "outlook.live.com"
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    if end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=timezone.utc)
    qs = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": summary,
        "startdt": start_at.astimezone(timezone.utc).isoformat(),
        "enddt": end_at.astimezone(timezone.utc).isoformat(),
    }
    if description:
        qs["body"] = description
    if location:
        qs["location"] = location
    return f"https://{host}/calendar/0/deeplink/compose?{urlencode(qs)}"


def build_feed_ics(
    events: list[FeedEvent],
    *,
    calendar_name: str = "SKILLED interviews",
    now: Optional[datetime] = None,
) -> str:
    """Render a full subscription calendar. Deterministic given ``now``."""
    stamp = ics_utc(now or datetime.now(timezone.utc))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        "X-PUBLISHED-TTL:PT15M",
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{ics_utc(ev.start_at)}",
            f"DTEND:{ics_utc(ev.end_at)}",
            f"SUMMARY:{ics_escape(ev.summary)}",
        ]
        if ev.location:
            lines.append(f"LOCATION:{ics_escape(ev.location)}")
        if ev.description:
            lines.append(f"DESCRIPTION:{ics_escape(ev.description)}")
        if ev.url:
            lines.append(f"URL:{ev.url}")
        lines.append(f"SEQUENCE:{1 if ev.cancelled else 0}")
        lines.append(f"STATUS:{'CANCELLED' if ev.cancelled else 'CONFIRMED'}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
