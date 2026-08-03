/**
 * mapCluster.test.ts — pure clustering + geo helpers behind the browse-jobs
 * map (pin grid clustering, radius-fit zoom, popover pay formatting).
 */
import { describe, expect, it } from "vitest";

import {
  clusterPoints,
  formatPinPay,
  truncateLabel,
  zoomForRadiusMiles,
} from "@/lib/mapCluster";

describe("clusterPoints", () => {
  it("merges points that share a grid cell and keeps far points separate", () => {
    const points = [
      { id: "a", x: 10, y: 10 },
      { id: "b", x: 12, y: 11 }, // same 40px cell as a
      { id: "c", x: 300, y: 300 }, // far away
    ];
    const clusters = clusterPoints(points, 40);
    expect(clusters).toHaveLength(2);
    const big = clusters.find((c) => c.ids.length === 2)!;
    expect(big.ids).toEqual(["a", "b"]);
    expect(clusters.find((c) => c.ids.length === 1)!.ids).toEqual(["c"]);
  });

  it("places a cluster at the centroid of its members", () => {
    const clusters = clusterPoints(
      [
        { id: "a", x: 10, y: 20 },
        { id: "b", x: 30, y: 40 },
      ],
      100,
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].x).toBe(20);
    expect(clusters[0].y).toBe(30);
  });

  it("splits clusters apart as the cell shrinks (zooming in)", () => {
    const points = [
      { id: "a", x: 10, y: 10 },
      { id: "b", x: 45, y: 10 },
    ];
    // Zoomed out: one bubble. Zoomed in (cell = 36/k shrinks): two pins.
    expect(clusterPoints(points, 60)).toHaveLength(1);
    expect(clusterPoints(points, 12)).toHaveLength(2);
  });

  it("drops non-finite projections and handles a zero cell size", () => {
    const clusters = clusterPoints(
      [
        { id: "a", x: NaN, y: 10 },
        { id: "b", x: 5, y: 5 },
      ],
      40,
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].ids).toEqual(["b"]);
    // cellSize <= 0 degrades to "every point is its own pin"
    expect(clusterPoints([{ id: "x", x: 1, y: 1 }], 0)).toHaveLength(1);
  });

  it("is deterministic regardless of input order (sorted by grid key)", () => {
    const pts = [
      { id: "a", x: 500, y: 500 },
      { id: "b", x: 10, y: 10 },
    ];
    const forward = clusterPoints(pts, 40);
    const reversed = clusterPoints([...pts].reverse(), 40);
    expect(forward.map((c) => c.key)).toEqual(reversed.map((c) => c.key));
    expect(forward.map((c) => [c.x, c.y])).toEqual(reversed.map((c) => [c.x, c.y]));
  });
});

describe("zoomForRadiusMiles", () => {
  it("zooms in more for smaller radii, clamped to the 1-8x frame range", () => {
    expect(zoomForRadiusMiles(10)).toBe(8); // tight radius maxes out
    expect(zoomForRadiusMiles(250)).toBeCloseTo(3, 0);
    expect(zoomForRadiusMiles(5000)).toBe(1); // never below 1
    expect(zoomForRadiusMiles(50)).toBeGreaterThan(zoomForRadiusMiles(100));
  });

  it("returns the neutral zoom for invalid input", () => {
    expect(zoomForRadiusMiles(0)).toBe(1);
    expect(zoomForRadiusMiles(NaN)).toBe(1);
  });
});

describe("formatPinPay", () => {
  it("prefers cleaned raw pay text", () => {
    expect(
      formatPinPay({ pay_raw: "$\n27.68\nper hour", pay_min: 20, pay_max: 25, pay_type: "hourly" }),
    ).toBe("$27.68 per hour");
  });

  it("formats structured ranges", () => {
    expect(formatPinPay({ pay_raw: null, pay_min: 25, pay_max: 30, pay_type: "hourly" })).toBe(
      "$25–$30/hr",
    );
    expect(formatPinPay({ pay_raw: null, pay_min: 55000, pay_max: null, pay_type: "annual" })).toBe(
      "$55k/yr",
    );
    expect(formatPinPay({ pay_raw: null, pay_min: null, pay_max: null, pay_type: null })).toBeNull();
  });
});

describe("truncateLabel", () => {
  it("truncates with an ellipsis only when needed", () => {
    expect(truncateLabel("Electrician", 30)).toBe("Electrician");
    expect(truncateLabel("A very long electrician job title indeed", 20)).toMatch(/…$/);
    expect(truncateLabel("A very long electrician job title indeed", 20).length).toBeLessThanOrEqual(20);
  });
});
