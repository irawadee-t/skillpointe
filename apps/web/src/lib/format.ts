/**
 * format.ts — canonical human-readable value formatting for the product.
 *
 * The ONE way to render a calendar date in the UI:
 *
 *   formatDate("2026-07-14")        → "Jul 14, 2026"
 *   formatDateShort("2026-07-14")   → "Jul 14" (year appended only if ≠ current year)
 *   formatDateRange(a, b)           → "Jul 14, 2024 – Jul 8, 2026"
 *
 * Date-only strings ("YYYY-MM-DD") are parsed as LOCAL dates — never via
 * `new Date("YYYY-MM-DD")`, which is UTC midnight and shifts a day west of
 * Greenwich. Full ISO timestamps parse normally.
 *
 * Relative helpers (re-exported from lib/time.ts so both import paths work):
 *   formatRelative(iso) → "just now" | "5m ago" | "3h ago" | "2d ago" | "Mar 15"
 *   formatDay(iso)      → "Fri, Mar 15"
 *   formatDayTime(iso)  → "Fri, Mar 15 · 2:30 PM"
 *   formatTime(iso)     → "2:30 PM"
 */

export {
  formatRelative,
  formatDay,
  formatDayTime,
  formatTime,
  formatDurationMin,
} from "./time";

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Parse an ISO date or datetime string; date-only strings become LOCAL dates. */
export function parseDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const m = DATE_ONLY.exec(iso.trim());
  const d = m
    ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
    : new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

/** "Jul 14, 2026" — the canonical date rendering. Empty string for bad input. */
export function formatDate(iso?: string | null): string {
  const d = parseDate(iso);
  if (!d) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** "Jul 14" this year, "Jul 14, 2025" otherwise. */
export function formatDateShort(iso?: string | null): string {
  const d = parseDate(iso);
  if (!d) return "";
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

/** "Jul 14, 2024 – Jul 8, 2026" (either side optional). */
export function formatDateRange(start?: string | null, end?: string | null): string {
  const a = formatDate(start);
  const b = formatDate(end);
  if (a && b) return `${a} – ${b}`;
  return a || b || "";
}

/** True when the date is strictly before today (local). */
export function isPastDate(iso?: string | null): boolean {
  const d = parseDate(iso);
  if (!d) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return d.getTime() < today.getTime();
}

/** True when both dates parse and end < start (an impossible range). */
export function isImpossibleRange(start?: string | null, end?: string | null): boolean {
  const a = parseDate(start);
  const b = parseDate(end);
  return Boolean(a && b && b.getTime() < a.getTime());
}
