/**
 * Milestone flags — one-shot celebration tracker.
 *
 * Stored in localStorage under a single key so it's easy to reset in the
 * console (e.g. `localStorage.removeItem('sn.milestones.v1')`) and easy
 * to version-bump when we want to re-fire everyone.
 *
 * Usage:
 *   if (fireOnce("first_application_sent")) {
 *     setConfetti(true);
 *     toast.success("🎉 First application sent!");
 *   }
 */

const KEY = "sn.milestones.v1";

type FlagMap = Record<string, number>;

function flags(): FlagMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as FlagMap) : {};
  } catch {
    return {};
  }
}

function save(f: FlagMap): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(KEY, JSON.stringify(f)); }
  catch { /* silent — quota or private mode */ }
}

/** Fire a one-time milestone. Returns true the first time; false forever after. */
export function fireOnce(id: string): boolean {
  const f = flags();
  if (f[id]) return false;
  f[id] = Date.now();
  save(f);
  return true;
}

/** Peek at a milestone without firing it. */
export function hasFired(id: string): boolean {
  return Boolean(flags()[id]);
}

/** Escape hatch for tests / support tickets. Not exposed to any UI. */
export function _resetMilestones(): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(KEY); } catch { /* silent */ }
}
