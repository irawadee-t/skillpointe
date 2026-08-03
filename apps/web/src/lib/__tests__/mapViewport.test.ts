import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCAL_ZOOM,
  FULL_US_BBOX,
  bboxParam,
  browseProjection,
  defaultLocalView,
  parseBboxParam,
  viewForBbox,
  viewportBbox,
} from "@/lib/mapViewport";

const AUSTIN = { lat: 30.2672, lng: -97.7431 };
const HOUSTON = { lat: 29.7604, lng: -95.3698 };

describe("viewportBbox", () => {
  it("frames the center and shrinks as zoom grows", () => {
    const wide = viewportBbox({ ...AUSTIN, zoom: 4 });
    const tight = viewportBbox({ ...AUSTIN, zoom: 8 });
    expect(wide).not.toBeNull();
    expect(tight).not.toBeNull();
    for (const b of [wide!, tight!]) {
      expect(b.minLng).toBeLessThan(AUSTIN.lng);
      expect(b.maxLng).toBeGreaterThan(AUSTIN.lng);
      expect(b.minLat).toBeLessThan(AUSTIN.lat);
      expect(b.maxLat).toBeGreaterThan(AUSTIN.lat);
    }
    expect(tight!.maxLng - tight!.minLng).toBeLessThan(wide!.maxLng - wide!.minLng);
    expect(tight!.maxLat - tight!.minLat).toBeLessThan(wide!.maxLat - wide!.minLat);
  });

  it("keeps a metro-ish extent at the default local zoom", () => {
    const b = viewportBbox(defaultLocalView(AUSTIN))!;
    // Max zoom (8) frames roughly 300-450 miles across — the tightest the
    // shared US frame supports, matching the 50 mi radius pill's fit.
    const lngSpanMiles = (b.maxLng - b.minLng) * 60; // ~60 mi/deg lng at 30N
    expect(lngSpanMiles).toBeGreaterThan(150);
    expect(lngSpanMiles).toBeLessThan(500);
    expect(DEFAULT_LOCAL_ZOOM).toBe(8);
  });

  it("returns null when the center does not project (off-map)", () => {
    expect(viewportBbox({ lat: 48.85, lng: 2.35, zoom: 6 })).toBeNull(); // Paris
  });

  it("never smears a mainland viewport across the inset panels", () => {
    // At zoom 3 around Austin the Hawaii inset panel edges into the frame;
    // the mainland-conic bbox must not stretch to -157 longitude.
    const b = viewportBbox({ ...AUSTIN, zoom: 3 })!;
    expect(b.minLng).toBeGreaterThan(-125);
  });

  it("is the full US extent at zoom 1 (maximum extent, insets included)", () => {
    const proj = browseProjection();
    const center = proj.invert!([980 / 2, 560 / 2])!;
    const b = viewportBbox({ lng: center[0], lat: center[1], zoom: 1 })!;
    expect(b).toEqual(FULL_US_BBOX);
    // Hawaii and Puerto Rico coordinates are in scope at maximum extent
    expect(b.minLng).toBeLessThanOrEqual(-158.1);
    expect(b.minLat).toBeLessThanOrEqual(18.2);
  });

  it("round-trips the full extent back to the home frame", () => {
    const v = viewForBbox(FULL_US_BBOX)!;
    expect(v.zoom).toBe(1);
  });
});

describe("viewForBbox round trip", () => {
  it("recovers approximately the same center and zoom", () => {
    for (const center of [AUSTIN, HOUSTON]) {
      for (const zoom of [3, 5, 8]) {
        const b = viewportBbox({ ...center, zoom })!;
        const v = viewForBbox(b)!;
        expect(v.lng).toBeCloseTo(center.lng, 0);
        expect(v.lat).toBeCloseTo(center.lat, 0);
        // The sampled bbox is the extent of what's visible, so the fitted
        // zoom lands at or slightly below the original.
        expect(v.zoom).toBeGreaterThan(zoom * 0.7);
        expect(v.zoom).toBeLessThanOrEqual(zoom * 1.05);
      }
    }
  });
});

describe("bbox param round trip", () => {
  it("serializes at 3 decimals and parses back", () => {
    const b = viewportBbox({ ...AUSTIN, zoom: 8 })!;
    const s = bboxParam(b);
    expect(s).toMatch(/^-?\d+\.\d{3},-?\d+\.\d{3},-?\d+\.\d{3},-?\d+\.\d{3}$/);
    const parsed = parseBboxParam(s)!;
    expect(parsed.minLng).toBeCloseTo(b.minLng, 3);
    expect(parsed.maxLat).toBeCloseTo(b.maxLat, 3);
  });

  it("rejects malformed values", () => {
    expect(parseBboxParam(null)).toBeNull();
    expect(parseBboxParam("")).toBeNull();
    expect(parseBboxParam("1,2,3")).toBeNull();
    expect(parseBboxParam("a,b,c,d")).toBeNull();
    expect(parseBboxParam("-97.2,29.8,-98.2,30.8")).toBeNull(); // min >= max
    expect(parseBboxParam("-198,29.8,-97.2,30.8")).toBeNull(); // out of range
  });
});
