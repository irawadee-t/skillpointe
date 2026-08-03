/**
 * mapViewport — pure geography for the browse-jobs map viewport scope.
 *
 * The browse map (UsMapFrame) renders a geoAlbersUsa projection in a fixed
 * 980x560 frame; the ZoomableGroup transform is fully described by a
 * geographic center + zoom factor k. These helpers convert between that
 * (center, zoom) view state and the geographic bounding box the viewport
 * frames, and (de)serialize the bbox for the URL and the API.
 *
 * Shared by the SERVER page (default "start near the applicant" framing and
 * URL restore) and the CLIENT (search-as-you-move refetches) — one bbox
 * math, tested in src/lib/__tests__/mapViewport.test.ts. No DOM.
 */

import { geoAlbers, geoAlbersUsa } from "d3";
import type { GeoProjection } from "d3";
import { zoomForRadiusMiles } from "@/lib/mapCluster";

/** Frame + projection constants — the single source UsMapFrame renders with. */
export const MAP_WIDTH = 980;
export const MAP_HEIGHT = 560;
export const MAP_SCALE = 1100;

/** Geographic view state of the map: center + zoom factor (1 = whole US). */
export interface MapView {
  lng: number;
  lat: number;
  zoom: number;
}

/** Geographic bounding box: what the map viewport frames. */
export interface GeoBbox {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
}

/** The default "start near the applicant" framing reuses the radius-fit math
 *  the 50 mi pill uses (clamps to the frame's max zoom). */
export const DEFAULT_LOCAL_RADIUS_MILES = 50;
export const DEFAULT_LOCAL_ZOOM = zoomForRadiusMiles(DEFAULT_LOCAL_RADIUS_MILES);

export function browseProjection(): GeoProjection {
  return geoAlbersUsa()
    .scale(MAP_SCALE)
    .translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]);
}

/** The mainland (lower-48) panel of geoAlbersUsa IS d3's default geoAlbers
 *  (same rotate/center/parallels), so this conic inverts EVERY frame point
 *  smoothly — no nulls between the Alaska/Hawaii inset panels. */
function conusProjection(): GeoProjection {
  return geoAlbers()
    .scale(MAP_SCALE)
    .translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]);
}

/** At (or near) full zoom-out the whole composite frame is visible, insets
 *  included — the maximum extent covers every US coordinate, so Alaska,
 *  Hawaii, and Puerto Rico jobs are honestly in scope there. */
export const FULL_US_BBOX: GeoBbox = { minLng: -180, minLat: 15, maxLng: -60, maxLat: 72 };
const FULL_FRAME_ZOOM = 1.06;

/**
 * Geographic bbox of the viewport at (center, zoom).
 *
 * The ZoomableGroup maps projected point p to screen s = (p - c)·k + F/2
 * where c = projection(center) and F the frame size, so the visible projected
 * rect is c ± F/(2k). Sampling inverts a 5x5 grid through the MAINLAND conic:
 * geoAlbersUsa's inset panels (Alaska/Hawaii) can sit inside a mainland
 * viewport and would smear the box across the Pacific, and a lat/lng
 * rectangle cannot represent a viewport with insets without absorbing
 * everything in between. Zoomed in, the insets are map furniture and the
 * mainland rectangle is the honest scope; at full zoom-out the maximum
 * extent (FULL_US_BBOX) includes them. Returns null when the center itself
 * doesn't project (off-map).
 */
export function viewportBbox(view: MapView): GeoBbox | null {
  if (!Number.isFinite(view.zoom) || view.zoom <= 0) return null;
  if (view.zoom <= FULL_FRAME_ZOOM) return { ...FULL_US_BBOX };

  // Validity gate through the composite projection: off-US centers are
  // rejected (the conic would happily invert them).
  if (!browseProjection()([view.lng, view.lat])) return null;
  const conus = conusProjection();
  const c = conus([view.lng, view.lat]);
  if (!c) return null;

  const halfW = MAP_WIDTH / (2 * view.zoom);
  const halfH = MAP_HEIGHT / (2 * view.zoom);

  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  const STEPS = 4; // 5x5 grid — the conic's curved graticule means the
  // extremes sit mid-edge, not only at corners.
  for (let i = 0; i <= STEPS; i++) {
    for (let j = 0; j <= STEPS; j++) {
      const px = c[0] - halfW + (2 * halfW * i) / STEPS;
      const py = c[1] - halfH + (2 * halfH * j) / STEPS;
      const g = conus.invert?.([px, py]);
      if (!g || !Number.isFinite(g[0]) || !Number.isFinite(g[1])) continue;
      if (g[0] < minLng) minLng = g[0];
      if (g[0] > maxLng) maxLng = g[0];
      if (g[1] < minLat) minLat = g[1];
      if (g[1] > maxLat) maxLat = g[1];
    }
  }
  if (minLng >= maxLng || minLat >= maxLat) return null;
  return {
    minLng: Math.max(-180, minLng),
    minLat: Math.max(-90, minLat),
    maxLng: Math.min(180, maxLng),
    maxLat: Math.min(90, maxLat),
  };
}

/** View (center + zoom) that frames the given bbox — the inverse of
 *  viewportBbox, used to restore the map from a URL bbox. */
export function viewForBbox(bbox: GeoBbox): MapView | null {
  // The maximum extent (or anything that covers it) is the home frame.
  if (
    bbox.minLng <= FULL_US_BBOX.minLng && bbox.maxLng >= FULL_US_BBOX.maxLng &&
    bbox.minLat <= FULL_US_BBOX.minLat && bbox.maxLat >= FULL_US_BBOX.maxLat
  ) {
    const home = browseProjection().invert?.([MAP_WIDTH / 2, MAP_HEIGHT / 2]);
    return home ? { lng: home[0], lat: home[1], zoom: 1 } : null;
  }
  const conus = conusProjection();
  const corners: Array<[number, number]> = [
    [bbox.minLng, bbox.minLat],
    [bbox.minLng, bbox.maxLat],
    [bbox.maxLng, bbox.minLat],
    [bbox.maxLng, bbox.maxLat],
    [(bbox.minLng + bbox.maxLng) / 2, bbox.minLat],
    [(bbox.minLng + bbox.maxLng) / 2, bbox.maxLat],
  ];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let valid = 0;
  for (const corner of corners) {
    const p = conus(corner);
    if (!p || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
    valid += 1;
    if (p[0] < minX) minX = p[0];
    if (p[0] > maxX) maxX = p[0];
    if (p[1] < minY) minY = p[1];
    if (p[1] > maxY) maxY = p[1];
  }
  if (valid < 2 || minX >= maxX || minY >= maxY) return null;
  const zoom = Math.max(1, Math.min(8, Math.min(MAP_WIDTH / (maxX - minX), MAP_HEIGHT / (maxY - minY))));
  const center = conus.invert?.([(minX + maxX) / 2, (minY + maxY) / 2]);
  if (!center) return null;
  return { lng: center[0], lat: center[1], zoom };
}

/** Serialize for the URL and the API: minLng,minLat,maxLng,maxLat at 3
 *  decimals (~110 m — plenty for a viewport, keeps URLs short and stable). */
export function bboxParam(bbox: GeoBbox): string {
  const f = (n: number) => n.toFixed(3);
  return `${f(bbox.minLng)},${f(bbox.minLat)},${f(bbox.maxLng)},${f(bbox.maxLat)}`;
}

/** Parse a URL bbox param; null when absent or malformed (the server rejects
 *  malformed values with 422 — the page treats them as "no viewport"). */
export function parseBboxParam(raw: string | null | undefined): GeoBbox | null {
  if (!raw) return null;
  const parts = raw.split(",").map((p) => Number.parseFloat(p));
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;
  const [minLng, minLat, maxLng, maxLat] = parts;
  if (minLng >= maxLng || minLat >= maxLat) return null;
  if (Math.abs(minLng) > 180 || Math.abs(maxLng) > 180) return null;
  if (Math.abs(minLat) > 90 || Math.abs(maxLat) > 90) return null;
  return { minLng, minLat, maxLng, maxLat };
}

/** Default framing around the applicant's home coordinates. */
export function defaultLocalView(center: { lat: number; lng: number }): MapView {
  return { lng: center.lng, lat: center.lat, zoom: DEFAULT_LOCAL_ZOOM };
}
