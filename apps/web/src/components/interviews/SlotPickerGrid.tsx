"use client";

/**
 * SlotPickerGrid — when2meet-style grid for proposing interview times.
 *
 * Rolling 7-day window starting today (not a calendar week) × 30-minute rows
 * (7:00 AM – 7:00 PM). Click a cell to propose a slot
 * starting there (length = the duration select); click-drag down/across paints
 * several; clicking a painted slot removes it. Past cells and cells beyond the
 * five-slot cap are inert. Every cell is a real button with a descriptive
 * aria-label, and arrow keys move focus around the grid, so the picker stays
 * fully keyboard- and screen-reader-operable. A chronological "selected times"
 * chip list mirrors the grid below it.
 *
 * Motion per the design contract: press feedback via a quick scale on the cell
 * (150ms ease-out), no bounce, and everything honors prefers-reduced-motion
 * via the motion-reduce: variants.
 *
 * Calendar overlay: when the signed-in user has a calendar connection
 * (Google / Outlook / local demo — see /account/settings#calendar), their
 * busy times for the visible week render as quiet diagonal-hatched blocks
 * BEHIND the cells. Proposed slots stay paintable over them — a busy cell
 * warns ("overlaps your calendar"), it never blocks. The grid self-fetches
 * the session token so no parent needs to thread props.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";

import {
  CalendarConnection, CalendarProviders,
  disconnectCalendarConnection, getCalendarBusy, getCalendarConnections,
  getCalendarProviders,
} from "@/lib/api/transactions";
import {
  BusyInterval, cellIsBusy, isBusyRunStart, normalizeBusy, overlapsBusy,
} from "@/lib/interviews/busyOverlay";
import { createClient } from "@/lib/supabase/client";

export interface PickedSlot {
  start: Date;
  durationMin: number;
}

const START_HOUR = 7;   // 7:00 AM
const END_HOUR = 19;    // grid ends at 7:00 PM
const STEP_MIN = 30;
const ROWS = ((END_HOUR - START_HOUR) * 60) / STEP_MIN; // 24
const DAYS = 7;

const DURATIONS = [15, 30, 45, 60] as const;

// ---------------------------------------------------------------------------
// date helpers (all local time — slots are sent to the API as ISO instants)
// ---------------------------------------------------------------------------

function startOfDay(d: Date): Date {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  return out;
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}

function cellStart(weekStart: Date, dayIx: number, rowIx: number): Date {
  const out = addDays(weekStart, dayIx);
  out.setHours(START_HOUR, 0, 0, 0);
  return new Date(out.getTime() + rowIx * STEP_MIN * 60_000);
}

function fmtTime(d: Date): string {
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmtDay(d: Date): string {
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function slotLabel(s: PickedSlot): string {
  const end = new Date(s.start.getTime() + s.durationMin * 60_000);
  return `${fmtDay(s.start)}, ${fmtTime(s.start)}–${fmtTime(end)}`;
}

/** "Central Time"-style label for the browser's zone; falls back to the IANA name. */
export function browserTimeZoneLabel(): string {
  try {
    const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "longGeneric" }).formatToParts(new Date());
    const name = parts.find((p) => p.type === "timeZoneName")?.value;
    if (name && !/^GMT/.test(name)) return name;
  } catch { /* older engines */ }
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone.replace(/_/g, " ");
  } catch {
    return "local time";
  }
}

// ---------------------------------------------------------------------------
// Calendar overlay hook — session token, connections, and per-week busy data
// ---------------------------------------------------------------------------

/** Diagonal hatch for busy blocks — quiet stone, readable in both themes. */
const BUSY_HATCH =
  "repeating-linear-gradient(135deg, rgba(87,83,78,0.12) 0 3px, transparent 3px 8px)";

function useCalendarOverlay(weekStart: Date) {
  const [token, setToken] = useState<string | null>(null);
  const [providers, setProviders] = useState<CalendarProviders | null>(null);
  const [connections, setConnections] = useState<CalendarConnection[] | null>(null);
  const [busy, setBusy] = useState<BusyInterval[]>([]);
  const [checking, setChecking] = useState(false);
  // Per-week cache so navigating back a week renders instantly (the backend
  // also caches ~2min; this just avoids re-flashing blocks).
  const weekCache = useRef<Map<number, BusyInterval[]>>(new Map());

  useEffect(() => {
    let alive = true;
    createClient().auth.getSession().then(({ data }) => {
      if (alive) setToken(data.session?.access_token ?? null);
    });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    Promise.all([
      getCalendarConnections(token).catch(() => [] as CalendarConnection[]),
      getCalendarProviders(token).catch(() => null),
    ]).then(([conns, provs]) => {
      if (!alive) return;
      setConnections(conns);
      setProviders(provs);
    });
    return () => { alive = false; };
  }, [token]);

  const weekKey = weekStart.getTime();
  const hasConnections = (connections?.length ?? 0) > 0;

  useEffect(() => {
    if (!token || !hasConnections) { setBusy([]); return; }
    const cached = weekCache.current.get(weekKey);
    if (cached) { setBusy(cached); return; }
    let alive = true;
    setChecking(true);
    const start = new Date(weekKey);
    const end = new Date(weekKey + DAYS * 24 * 60 * 60_000);
    getCalendarBusy(token, start.toISOString(), end.toISOString(), new Date().getTimezoneOffset())
      .then((res) => {
        if (!alive) return;
        const normalized = normalizeBusy(res.busy);
        weekCache.current.set(weekKey, normalized);
        setBusy(normalized);
      })
      .catch(() => { if (alive) setBusy([]); })
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, [token, hasConnections, weekKey]);

  const disconnect = useCallback(async (connectionId: string) => {
    if (!token) return;
    try {
      await disconnectCalendarConnection(token, connectionId);
      weekCache.current.clear();
      setBusy([]);
      setConnections((prev) => (prev ?? []).filter((c) => c.id !== connectionId));
    } catch {
      // Leave state as-is; the settings page offers the full management UI.
    }
  }, [token]);

  return { providers, connections, busy, checking, disconnect };
}

// ---------------------------------------------------------------------------

export function SlotPickerGrid({
  slots,
  onChange,
  maxSlots = 5,
}: {
  slots: PickedSlot[];
  onChange: (next: PickedSlot[]) => void;
  maxSlots?: number;
}) {
  const [weekOffset, setWeekOffset] = useState(0);
  const [duration, setDuration] = useState<number>(30);
  // Drag paint mode: null = not dragging.
  const dragMode = useRef<"add" | "remove" | null>(null);
  // Roving-tabindex focus coordinates.
  const [focusCell, setFocusCell] = useState<[number, number]>([0, 6]); // Mon 10:00
  const cellRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  // "now" is captured per render tick; a minute-level timer keeps past-cell
  // state honest if the panel stays open across a boundary.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const up = () => { dragMode.current = null; };
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, []);

  // Rolling window: the default view is the next 7 days STARTING TODAY (not a
  // Mon–Sun calendar week), so the soonest proposable times are always visible.
  const weekStart = useMemo(() => addDays(startOfDay(now), weekOffset * 7), [now, weekOffset]);
  const days = useMemo(() => Array.from({ length: DAYS }, (_, i) => addDays(weekStart, i)), [weekStart]);
  const atCap = slots.length >= maxSlots;

  // Calendar overlay: the user's own busy times for the visible week.
  const overlay = useCalendarOverlay(weekStart);
  const busyIntervals = overlay.busy;

  /** The selected slot covering this cell's time range, if any. */
  const coveringSlot = useCallback(
    (start: Date): PickedSlot | undefined => {
      const cellEnd = start.getTime() + STEP_MIN * 60_000;
      return slots.find((s) => {
        const sEnd = s.start.getTime() + s.durationMin * 60_000;
        return s.start.getTime() < cellEnd && sEnd > start.getTime();
      });
    },
    [slots],
  );

  const addSlot = useCallback(
    (start: Date) => {
      onChange(
        [...slots, { start, durationMin: duration }].sort((a, b) => a.start.getTime() - b.start.getTime()),
      );
    },
    [slots, duration, onChange],
  );

  const removeSlot = useCallback(
    (slot: PickedSlot) => {
      onChange(slots.filter((s) => s !== slot));
    },
    [slots, onChange],
  );

  function handleCellDown(dayIx: number, rowIx: number) {
    const start = cellStart(weekStart, dayIx, rowIx);
    if (start <= now) return;
    const covered = coveringSlot(start);
    if (covered) {
      dragMode.current = "remove";
      removeSlot(covered);
    } else {
      if (atCap) return;
      dragMode.current = "add";
      addSlot(start);
    }
    setFocusCell([dayIx, rowIx]);
  }

  function handleCellEnter(dayIx: number, rowIx: number) {
    if (!dragMode.current) return;
    const start = cellStart(weekStart, dayIx, rowIx);
    if (start <= now) return;
    const covered = coveringSlot(start);
    if (dragMode.current === "add" && !covered && slots.length < maxSlots) addSlot(start);
    if (dragMode.current === "remove" && covered) removeSlot(covered);
  }

  function handleKeyDown(e: React.KeyboardEvent, dayIx: number, rowIx: number) {
    const moves: Record<string, [number, number]> = {
      ArrowUp: [dayIx, rowIx - 1],
      ArrowDown: [dayIx, rowIx + 1],
      ArrowLeft: [dayIx - 1, rowIx],
      ArrowRight: [dayIx + 1, rowIx],
    };
    const next = moves[e.key];
    if (!next) return;
    e.preventDefault();
    const [d, r] = next;
    if (d < 0 || d >= DAYS || r < 0 || r >= ROWS) return;
    setFocusCell([d, r]);
    cellRefs.current.get(`${d}:${r}`)?.focus();
  }

  const weekLabel =
    weekOffset === 0 ? "Next 7 days" : `From ${fmtDay(days[0])}`;
  const rangeLabel = `${days[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${days[6].toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;

  return (
    <div className="select-none">
      {/* Toolbar: week nav + duration */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setWeekOffset((w) => Math.max(0, w - 1))}
            disabled={weekOffset === 0}
            aria-label="Previous 7 days"
            className="rounded-full border border-hairline bg-white p-1.5 text-slate transition-colors duration-150 hover:text-cohere-ink disabled:opacity-35"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setWeekOffset((w) => w + 1)}
            aria-label="Next 7 days"
            className="rounded-full border border-hairline bg-white p-1.5 text-slate transition-colors duration-150 hover:text-cohere-ink"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <span className="ml-1 text-body font-medium text-cohere-ink">{weekLabel}</span>
          <span className="text-caption text-slate-muted">· {rangeLabel}</span>
        </div>
        <label className="flex items-center gap-2 text-caption text-slate">
          Length
          <select
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            className="input-cohere w-auto py-1 text-caption"
          >
            {DURATIONS.map((d) => (
              <option key={d} value={d}>{d === 60 ? "1 hour" : `${d} min`}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Calendar overlay status — a fixed-height line so nothing below
          shifts when the connection info arrives or a check runs. */}
      <div className="mt-2 flex h-5 min-w-0 items-center gap-1.5 text-micro text-slate-muted">
        {overlay.connections && overlay.connections.length > 0 ? (
          <>
            <span className="truncate">
              Showing your calendar:{" "}
              <span className="text-slate">
                {overlay.connections[0].account_email || overlay.connections[0].provider}
              </span>
              {overlay.connections.length > 1 && <> +{overlay.connections.length - 1} more</>}
            </span>
            {overlay.checking && (
              <Loader2 className="h-3 w-3 shrink-0 animate-spin motion-reduce:animate-none" aria-label="Checking your calendar" />
            )}
            <span aria-hidden>·</span>
            {overlay.connections.length === 1 ? (
              <button
                type="button"
                onClick={() => overlay.disconnect(overlay.connections![0].id)}
                className="shrink-0 underline underline-offset-2 transition-colors duration-150 hover:text-cohere-ink"
              >
                Disconnect
              </button>
            ) : (
              <a
                href="/account/settings#calendar"
                className="shrink-0 underline underline-offset-2 transition-colors duration-150 hover:text-cohere-ink"
              >
                Manage
              </a>
            )}
          </>
        ) : overlay.connections &&
          (overlay.providers?.google_configured ||
            overlay.providers?.outlook_configured ||
            overlay.providers?.demo_available) ? (
          <a
            href="/account/settings#calendar"
            className="truncate underline underline-offset-2 transition-colors duration-150 hover:text-cohere-ink"
          >
            {overlay.providers?.google_configured || overlay.providers?.outlook_configured
              ? "Connect Google or Outlook to see your availability"
              : "Connect a calendar to see your availability"}
          </a>
        ) : null}
      </div>

      {/* The grid */}
      <div
        role="grid"
        aria-label="Weekly time grid: pick interview times"
        className="mt-2 overflow-x-auto rounded-[10px] border border-hairline bg-white"
      >
        <div className="min-w-[560px]">
          {/* Day headers */}
          <div className="grid border-b border-hairline" style={{ gridTemplateColumns: "56px repeat(7, 1fr)" }}>
            <div />
            {days.map((d, i) => {
              const isToday = d.toDateString() === now.toDateString();
              return (
                <div key={i} className={`px-1 py-2 text-center text-micro ${isToday ? "font-semibold text-cohere-ink" : "text-slate"}`}>
                  {d.toLocaleDateString(undefined, { weekday: "short" })}
                  <span className="ml-1 tabular-nums text-slate-muted">{d.getDate()}</span>
                </div>
              );
            })}
          </div>

          {Array.from({ length: ROWS }, (_, rowIx) => {
            const rowTime = cellStart(weekStart, 0, rowIx);
            const onHour = rowTime.getMinutes() === 0;
            return (
              <div key={rowIx} className="grid" style={{ gridTemplateColumns: "56px repeat(7, 1fr)" }}>
                <div className={`relative border-r border-hairline pr-1.5 text-right text-[10px] tabular-nums text-slate-muted ${onHour ? "" : "text-transparent"}`}>
                  <span className="relative -top-[6px]">{onHour ? fmtTime(rowTime) : ""}</span>
                </div>
                {days.map((_, dayIx) => {
                  const start = cellStart(weekStart, dayIx, rowIx);
                  const past = start <= now;
                  const covered = coveringSlot(start);
                  const isStart = covered && covered.start.getTime() === start.getTime();
                  const inert = past || (!covered && atCap);
                  const end = new Date(start.getTime() + duration * 60_000);
                  // Calendar overlay — quiet hatched blocks behind the cells.
                  const busyHere = !past && cellIsBusy(start.getTime(), STEP_MIN, busyIntervals);
                  const busyRunStart =
                    busyHere && isBusyRunStart(start.getTime(), STEP_MIN, busyIntervals, rowIx === 0);
                  const busySuffix = busyHere ? " — busy in your calendar" : "";
                  const label = covered
                    ? `Remove proposed time ${slotLabel(covered)}${busyHere ? " (overlaps your calendar)" : ""}`
                    : past
                      ? `${fmtDay(start)}, ${fmtTime(start)} (this time has passed)`
                      : `Propose ${fmtDay(start)}, ${fmtTime(start)}–${fmtTime(end)}${busySuffix}`;
                  const key = `${dayIx}:${rowIx}`;
                  const focused = focusCell[0] === dayIx && focusCell[1] === rowIx;
                  return (
                    <button
                      key={key}
                      ref={(el) => { if (el) cellRefs.current.set(key, el); else cellRefs.current.delete(key); }}
                      type="button"
                      role="gridcell"
                      aria-label={label}
                      aria-disabled={inert || undefined}
                      aria-selected={!!covered}
                      tabIndex={focused ? 0 : -1}
                      onPointerDown={(e) => { e.preventDefault(); handleCellDown(dayIx, rowIx); }}
                      onPointerEnter={() => handleCellEnter(dayIx, rowIx)}
                      onKeyDown={(e) => {
                        handleKeyDown(e, dayIx, rowIx);
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleCellDown(dayIx, rowIx); }
                      }}
                      onFocus={() => setFocusCell([dayIx, rowIx])}
                      style={busyHere && !covered ? { backgroundImage: BUSY_HATCH } : undefined}
                      className={[
                        "relative h-6 border-b border-r border-hairline/60 text-[10px] leading-none",
                        "transition-[background-color,transform] duration-150 ease-out motion-reduce:transition-none",
                        onHour ? "border-t-hairline" : "",
                        covered
                          ? "bg-ink text-white active:scale-[0.96] motion-reduce:active:scale-100"
                          : past
                            ? "cursor-default bg-stone/30 text-transparent"
                            : busyHere
                              ? atCap
                                ? "cursor-default bg-stone/40"
                                : "bg-stone/40 hover:bg-stone active:scale-[0.96] motion-reduce:active:scale-100"
                              : atCap
                                ? "cursor-default bg-white"
                                : "bg-white hover:bg-stone active:scale-[0.96] motion-reduce:active:scale-100",
                        "focus-visible:z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-cohere-ink",
                      ].join(" ")}
                    >
                      {isStart ? (
                        <span className="pointer-events-none tabular-nums">{fmtTime(covered.start)}</span>
                      ) : busyRunStart && !covered ? (
                        <span className="pointer-events-none text-[9px] font-medium text-slate-muted">Busy</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <p className="mt-2 text-micro text-slate-muted">
        Times shown in {browserTimeZoneLabel()}. Click a cell to propose it. Drag to paint several. Click again to remove.
      </p>

      {/* Selected times — the accessible, chronological mirror of the grid */}
      <div className="mt-3">
        <div className="flex items-baseline justify-between">
          <span className="text-caption font-medium text-cohere-ink">
            Selected times <span className="tabular-nums text-slate-muted">({slots.length} of {maxSlots})</span>
          </span>
          {atCap && <span className="text-micro text-slate-muted">Up to five. Remove one to add another.</span>}
        </div>
        {slots.length === 0 ? (
          <p className="mt-1.5 text-caption text-slate-muted">Nothing yet. Pick a few times the applicant can choose from.</p>
        ) : (
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {slots.map((s) => {
              const overlapsCal = overlapsBusy(
                s.start.getTime(),
                s.start.getTime() + s.durationMin * 60_000,
                busyIntervals,
              );
              return (
                <li key={s.start.toISOString()}>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-white py-1 pl-3 pr-1.5 text-caption text-cohere-ink">
                    {slotLabel(s)}
                    {overlapsCal && (
                      <span className="text-micro text-slate-muted">· overlaps your calendar</span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeSlot(s)}
                      aria-label={`Remove ${slotLabel(s)}${overlapsCal ? " (overlaps your calendar)" : ""}`}
                      className="rounded-full p-0.5 text-slate-muted transition-colors duration-150 hover:bg-stone hover:text-cohere-ink"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
