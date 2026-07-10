/**
 * Human-readable time helpers used across the app.
 *
 *   formatRelative(iso)   → "just now" | "5m" | "3h" | "2d ago" | "Mar 15"
 *   formatWhen(iso)       → same as relative but with weekday for near future
 *   formatDay(iso)        → "Fri, Mar 15"
 *   formatDayTime(iso)    → "Fri, Mar 15 · 2:30 PM"
 *   formatTime(iso)       → "2:30 PM"
 *   formatDurationMin(n)  → "45 min" | "1 hr 15 min" | "3 hr"
 */

export function formatRelative(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const diffMs = Date.now() - t;
  const past = diffMs >= 0;
  const abs = Math.abs(diffMs);
  const min = Math.floor(abs / 60_000);
  if (min < 1) return past ? "just now" : "in a moment";
  if (min < 60) return past ? `${min}m ago` : `in ${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return past ? `${hr}h ago` : `in ${hr}h`;
  const d = Math.floor(hr / 24);
  if (d < 7)  return past ? `${d}d ago` : `in ${d}d`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDay(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function formatTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function formatDayTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return `${formatDay(iso)} · ${formatTime(iso)}`;
}

export function formatDurationMin(minutes: number): string {
  if (!minutes || minutes < 1) return "";
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const rem = minutes - h * 60;
  if (rem === 0) return `${h} hr`;
  return `${h} hr ${rem} min`;
}

export function timeOfDayGreeting(name?: string | null): string {
  const h = new Date().getHours();
  const period =
    h < 5  ? "night owl" :
    h < 12 ? "morning" :
    h < 17 ? "afternoon" :
    h < 21 ? "evening" : "night";
  const greeting = period === "night owl" ? "Working late" : `Good ${period}`;
  return name ? `${greeting}, ${name.split(" ")[0]}.` : `${greeting}.`;
}
