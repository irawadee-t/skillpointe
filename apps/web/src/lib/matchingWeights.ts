/**
 * Pure math for the /admin/matching weight mixer.
 *
 * The nine dimension weights must sum to 100. The mixer follows the
 * Ableton/Lightroom pattern: moving one fader redistributes the delta
 * proportionally across the UNLOCKED remaining dimensions, so the total is
 * invariant while dragging; locked dimensions never move. All outputs are
 * rounded to tenths with largest-remainder apportionment so the invariant
 * holds exactly (no float drift), values never go negative, and results are
 * deterministic (ties break by key order).
 */

const TENTHS = 10;

const toTenths = (x: number): number => Math.round((Number(x) || 0) * TENTHS);

export function sumWeights(weights: Record<string, number>): number {
  const t = Object.values(weights).reduce((a, b) => a + toTenths(b), 0);
  return t / TENTHS;
}

/**
 * Largest-remainder apportionment: round each float target down to tenths,
 * then hand the leftover tenth-units to the largest fractional remainders
 * until the block total is exactly `totalTenths`. Ties break by the order of
 * `targets` (stable sort), making the result deterministic.
 */
function apportion(targets: Array<[string, number]>, totalTenths: number): Map<string, number> {
  const rows = targets.map(([key, value]) => {
    const t = value * TENTHS;
    const floor = Math.max(0, Math.floor(t + 1e-7));
    return { key, floor, rem: t - floor };
  });
  let leftover = totalTenths - rows.reduce((a, r) => a + r.floor, 0);
  if (leftover > 0) {
    const order = [...rows].sort((a, b) => b.rem - a.rem);
    let i = 0;
    while (leftover > 0 && order.length > 0) {
      order[i % order.length].floor += 1;
      leftover -= 1;
      i += 1;
    }
  } else if (leftover < 0) {
    const order = [...rows].sort((a, b) => a.rem - b.rem);
    let i = 0;
    let guard = 0;
    while (leftover < 0 && order.length > 0 && guard < 10_000) {
      const row = order[i % order.length];
      if (row.floor > 0) {
        row.floor -= 1;
        leftover += 1;
      }
      i += 1;
      guard += 1;
    }
  }
  return new Map(rows.map((r) => [r.key, r.floor / TENTHS]));
}

/**
 * Set `key` to `rawValue` and absorb the delta across the unlocked remaining
 * dimensions, proportionally to their current values (equal split when they
 * are all zero). Invariants:
 *  - the total of all weights is unchanged (to a tenth, exactly);
 *  - locked keys are returned byte-identical;
 *  - no weight goes below 0 — `rawValue` is clamped to what the unlocked
 *    absorbers can supply;
 *  - if nothing can absorb (every other key locked), the key is pinned.
 */
export function redistribute(
  weights: Record<string, number>,
  key: string,
  rawValue: number,
  locked: ReadonlySet<string> = new Set(),
): Record<string, number> {
  if (!(key in weights) || locked.has(key)) return { ...weights };
  const absorbers = Object.keys(weights).filter((k) => k !== key && !locked.has(k));
  const old = Number(weights[key]) || 0;
  if (absorbers.length === 0) return { ...weights };

  const absorberTotal = absorbers.reduce((a, k) => a + (Number(weights[k]) || 0), 0);
  // The unlocked block's total is invariant: this key can take at most the
  // whole block (absorbers floor at 0) and at least 0.
  const value = Math.min(Math.max(rawValue, 0), old + absorberTotal);
  const delta = value - old;

  const out: Record<string, number> = { ...weights };
  const valueT = toTenths(value);
  out[key] = valueT / TENTHS;

  const targets: Array<[string, number]> = absorbers.map((k) => {
    const w = Number(weights[k]) || 0;
    return [k, absorberTotal > 0 ? w - delta * (w / absorberTotal) : -delta / absorbers.length];
  });
  const blockT = toTenths(old) + absorbers.reduce((a, k) => a + toTenths(weights[k]), 0);
  const rounded = apportion(targets, blockT - valueT);
  for (const [k, v] of rounded) out[k] = v;
  return out;
}

/**
 * Scale the unlocked weights so the total is exactly 100, keeping locked
 * weights untouched. Proportional when the unlocked block is non-zero, equal
 * split otherwise. If the locked block alone is ≥ 100, unlocked go to 0 (the
 * sum indicator keeps reporting the overshoot — unlocking is the fix).
 */
export function normalizeTo100(
  weights: Record<string, number>,
  locked: ReadonlySet<string> = new Set(),
): Record<string, number> {
  const keys = Object.keys(weights);
  const unlocked = keys.filter((k) => !locked.has(k));
  if (unlocked.length === 0) return { ...weights };

  const lockedT = keys
    .filter((k) => locked.has(k))
    .reduce((a, k) => a + toTenths(weights[k]), 0);
  const targetT = Math.max(0, 100 * TENTHS - lockedT);
  const unlockedTotal = unlocked.reduce((a, k) => a + (Number(weights[k]) || 0), 0);

  const targets: Array<[string, number]> = unlocked.map((k) => {
    const w = Number(weights[k]) || 0;
    return [
      k,
      unlockedTotal > 0 ? (w * (targetT / TENTHS)) / unlockedTotal : targetT / TENTHS / unlocked.length,
    ];
  });
  const out: Record<string, number> = { ...weights };
  for (const [k, v] of apportion(targets, targetT)) out[k] = v;
  return out;
}
