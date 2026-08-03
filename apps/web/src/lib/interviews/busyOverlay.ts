/**
 * busyOverlay — pure interval math for the SlotPickerGrid calendar overlay.
 *
 * The backend (/me/calendar/busy) already merges intervals across the user's
 * connections, but the client normalizes again defensively (drop invalid,
 * sort, merge) so the grid never renders overlapping or inverted blocks no
 * matter what arrives. All math is in epoch milliseconds; parsing ISO strings
 * happens exactly once at the boundary.
 */

export interface BusyInterval {
  startMs: number;
  endMs: number;
}

/** Parse + clean raw API intervals: drop unparseable/inverted, sort, merge
 *  overlapping or touching intervals (which may span days). */
export function normalizeBusy(raw: { start: string; end: string }[]): BusyInterval[] {
  const parsed: BusyInterval[] = [];
  for (const item of raw) {
    const startMs = Date.parse(item.start);
    const endMs = Date.parse(item.end);
    if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs <= startMs) continue;
    parsed.push({ startMs, endMs });
  }
  parsed.sort((a, b) => a.startMs - b.startMs);
  const merged: BusyInterval[] = [];
  for (const iv of parsed) {
    const last = merged[merged.length - 1];
    if (last && iv.startMs <= last.endMs) {
      if (iv.endMs > last.endMs) last.endMs = iv.endMs;
    } else {
      merged.push({ ...iv });
    }
  }
  return merged;
}

/** Strict overlap between [startMs, endMs) and any busy interval — touching
 *  endpoints (meeting ends 10:00, slot starts 10:00) do NOT count. */
export function overlapsBusy(startMs: number, endMs: number, busy: BusyInterval[]): boolean {
  for (const iv of busy) {
    if (iv.startMs >= endMs) break; // sorted — nothing later can overlap
    if (iv.endMs > startMs) return true;
  }
  return false;
}

/** Is the 30-minute grid cell starting at cellStartMs busy? */
export function cellIsBusy(cellStartMs: number, stepMin: number, busy: BusyInterval[]): boolean {
  return overlapsBusy(cellStartMs, cellStartMs + stepMin * 60_000, busy);
}

/**
 * Is this cell the FIRST busy cell of a vertical run in its day column?
 * (The "Busy" text label renders only on run starts so a 3-hour block reads
 * as one quiet region, not 6 shouting cells.)
 */
export function isBusyRunStart(
  cellStartMs: number,
  stepMin: number,
  busy: BusyInterval[],
  isFirstRowOfDay: boolean,
): boolean {
  if (!cellIsBusy(cellStartMs, stepMin, busy)) return false;
  if (isFirstRowOfDay) return true;
  return !cellIsBusy(cellStartMs - stepMin * 60_000, stepMin, busy);
}
