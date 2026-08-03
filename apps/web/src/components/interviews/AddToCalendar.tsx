"use client";

/**
 * Add-to-calendar affordances for a confirmed interview — shared by the
 * applicant and employer detail pages so both sides get the identical trio:
 *
 *   Google Calendar · Outlook · .ics file
 *
 * (plus a quiet "work account" variant of the Outlook deep link, since
 * outlook.live.com and outlook.office.com are separate universes).
 *
 * The .ics UID is `interview-{slotId}@skillednation` — the SAME uid the
 * backend subscription feed emits, so a downloaded copy and a subscribed copy
 * dedupe to one event in the user's calendar.
 */

import { CalendarPlus, ExternalLink } from "lucide-react";

export interface CalendarEventInput {
  slotId: string;
  title: string;
  description: string;
  location?: string | null;
  meetingUrl?: string | null;
  startAt: string; // ISO
  endAt: string;   // ISO
}

/** UTC timestamp in the iCalendar basic format: 20260802T153000Z. */
function icsUtc(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/** Escape iCalendar TEXT values (RFC 5545 §3.3.11). */
function icsEscape(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

export function buildInterviewIcs(ev: CalendarEventInput): string {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//SKILLED Nation//Interview//EN",
    "BEGIN:VEVENT",
    `UID:interview-${ev.slotId}@skillednation`,
    `DTSTAMP:${icsUtc(new Date().toISOString())}`,
    `DTSTART:${icsUtc(ev.startAt)}`,
    `DTEND:${icsUtc(ev.endAt)}`,
    `SUMMARY:${icsEscape(ev.title)}`,
    ev.location ? `LOCATION:${icsEscape(ev.location)}` : null,
    `DESCRIPTION:${icsEscape(ev.description)}`,
    ev.meetingUrl ? `URL:${ev.meetingUrl}` : null,
    "STATUS:CONFIRMED",
    "END:VEVENT",
    "END:VCALENDAR",
  ].filter(Boolean) as string[];
  return lines.join("\r\n") + "\r\n";
}

export function googleCalendarUrl(ev: CalendarEventInput): string {
  const qs = new URLSearchParams({
    action: "TEMPLATE",
    text: ev.title,
    dates: `${icsUtc(ev.startAt)}/${icsUtc(ev.endAt)}`,
    details: ev.description,
  });
  if (ev.location) qs.set("location", ev.location);
  return `https://calendar.google.com/calendar/render?${qs.toString()}`;
}

export function outlookCalendarUrl(ev: CalendarEventInput, opts?: { work?: boolean }): string {
  const host = opts?.work ? "outlook.office.com" : "outlook.live.com";
  const qs = new URLSearchParams({
    path: "/calendar/action/compose",
    rru: "addevent",
    subject: ev.title,
    startdt: new Date(ev.startAt).toISOString(),
    enddt: new Date(ev.endAt).toISOString(),
    body: ev.description,
  });
  if (ev.location) qs.set("location", ev.location);
  return `https://${host}/calendar/0/deeplink/compose?${qs.toString()}`;
}

const PILL =
  "inline-flex items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1.5 text-caption font-medium text-cohere-ink transition-colors duration-200 hover:border-cohere-ink";

export function AddToCalendarButtons({ event, className = "" }: { event: CalendarEventInput; className?: string }) {
  function downloadIcs() {
    const blob = new Blob([buildInterviewIcs(event)], { type: "text/calendar;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "interview.ics";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <a href={googleCalendarUrl(event)} target="_blank" rel="noopener noreferrer" className={PILL}>
        Google Calendar <ExternalLink className="h-3 w-3" />
      </a>
      <a href={outlookCalendarUrl(event)} target="_blank" rel="noopener noreferrer" className={PILL}>
        Outlook <ExternalLink className="h-3 w-3" />
      </a>
      <button type="button" onClick={downloadIcs} className={PILL}>
        <CalendarPlus className="h-3.5 w-3.5" /> .ics file
      </button>
      <a
        href={outlookCalendarUrl(event, { work: true })}
        target="_blank"
        rel="noopener noreferrer"
        className="text-micro text-slate-muted underline-offset-2 hover:underline"
      >
        Outlook work account
      </a>
    </div>
  );
}
