/**
 * mapCluster — pure helpers for the browse-jobs map.
 *
 * Grid clustering in PROJECTED map space: points that would overlap at the
 * current zoom collapse into count bubbles ("12") that expand as you zoom in.
 * Pure functions (no DOM, no d3) so they are unit-testable — see
 * src/lib/__tests__/mapCluster.test.ts.
 */

export interface ProjectedPoint {
  id: string;
  x: number;
  y: number;
}

export interface PinCluster {
  key: string;
  /** Centroid of the member points (projected coordinates). */
  x: number;
  y: number;
  ids: string[];
}

/**
 * Cluster points on a square grid of `cellSize` (projected units). Callers
 * pass `basePixels / zoomFactor` so the SCREEN cell size stays constant while
 * zooming — zooming in shrinks the projected cell, so clusters split apart.
 * Deterministic: output ordered by grid key; member ids keep input order.
 */
export function clusterPoints(points: ProjectedPoint[], cellSize: number): PinCluster[] {
  if (cellSize <= 0) {
    return points.map((p) => ({ key: p.id, x: p.x, y: p.y, ids: [p.id] }));
  }
  const buckets = new Map<string, ProjectedPoint[]>();
  for (const p of points) {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) continue;
    const key = `${Math.floor(p.x / cellSize)}:${Math.floor(p.y / cellSize)}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(p);
    else buckets.set(key, [p]);
  }
  const clusters: PinCluster[] = [];
  for (const [key, members] of buckets) {
    let sx = 0;
    let sy = 0;
    for (const m of members) {
      sx += m.x;
      sy += m.y;
    }
    clusters.push({
      key,
      x: sx / members.length,
      y: sy / members.length,
      ids: members.map((m) => m.id),
    });
  }
  clusters.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return clusters;
}

/** Approximate degrees of great-circle arc per mile (69 mi ≈ 1°). */
export const MILES_PER_DEGREE = 69.0;

/**
 * Zoom factor that fits a radius circle comfortably in the US map frame.
 * The base frame (zoom 1) spans roughly 3,000 miles of continental US, so a
 * circle of diameter 2R should occupy about half the frame. Clamped to the
 * frame's 1–8x zoom range.
 */
export function zoomForRadiusMiles(radiusMiles: number): number {
  if (!Number.isFinite(radiusMiles) || radiusMiles <= 0) return 1;
  const zoom = 3000 / (4 * radiusMiles);
  return Math.max(1, Math.min(8, zoom));
}

/** "$25–$30/hr", "$55k/yr", raw pay text cleaned of line-snapped whitespace. */
export function formatPinPay(pin: {
  pay_raw: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
}): string | null {
  if (pin.pay_raw && pin.pay_raw.trim()) {
    return pin.pay_raw.replace(/\s+/g, " ").replace(/([$€£])\s+(?=\d)/g, "$1").trim();
  }
  if (pin.pay_min === null || pin.pay_min === undefined) return null;
  const suffix = pin.pay_type === "hourly" ? "/hr" : pin.pay_type === "annual" ? "/yr" : "";
  const fmt = (n: number) =>
    pin.pay_type === "annual" ? `$${(n / 1000).toFixed(0)}k` : `$${n.toFixed(0)}`;
  if (pin.pay_max !== null && pin.pay_max !== undefined && pin.pay_max !== pin.pay_min) {
    return `${fmt(pin.pay_min)}–${fmt(pin.pay_max)}${suffix}`;
  }
  return `${fmt(pin.pay_min)}${suffix}`;
}

/** Truncate for the SVG popover (no CSS ellipsis inside <text>). */
export function truncateLabel(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, Math.max(0, max - 1)).trimEnd()}…` : s;
}
