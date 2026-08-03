import { describe, expect, it } from "vitest";

import {
  cellIsBusy,
  isBusyRunStart,
  normalizeBusy,
  overlapsBusy,
} from "@/lib/interviews/busyOverlay";

const T0 = Date.parse("2026-08-10T09:00:00Z");
const HOUR = 60 * 60_000;
const iso = (ms: number) => new Date(ms).toISOString();

describe("normalizeBusy", () => {
  it("parses, sorts, and merges overlapping intervals", () => {
    const out = normalizeBusy([
      { start: iso(T0 + 2 * HOUR), end: iso(T0 + 3 * HOUR) },
      { start: iso(T0), end: iso(T0 + HOUR) },
      { start: iso(T0 + 0.5 * HOUR), end: iso(T0 + 1.5 * HOUR) },
    ]);
    expect(out).toEqual([
      { startMs: T0, endMs: T0 + 1.5 * HOUR },
      { startMs: T0 + 2 * HOUR, endMs: T0 + 3 * HOUR },
    ]);
  });

  it("merges touching intervals into one block", () => {
    const out = normalizeBusy([
      { start: iso(T0), end: iso(T0 + HOUR) },
      { start: iso(T0 + HOUR), end: iso(T0 + 2 * HOUR) },
    ]);
    expect(out).toEqual([{ startMs: T0, endMs: T0 + 2 * HOUR }]);
  });

  it("keeps a cross-day interval intact and swallows contained ones", () => {
    const nightStart = Date.parse("2026-08-10T22:00:00Z");
    const nightEnd = Date.parse("2026-08-11T08:00:00Z");
    const out = normalizeBusy([
      { start: "2026-08-11T01:00:00Z", end: "2026-08-11T02:00:00Z" },
      { start: iso(nightStart), end: iso(nightEnd) },
    ]);
    expect(out).toEqual([{ startMs: nightStart, endMs: nightEnd }]);
  });

  it("drops invalid and inverted intervals", () => {
    const out = normalizeBusy([
      { start: "not-a-date", end: iso(T0) },
      { start: iso(T0 + HOUR), end: iso(T0) },
      { start: iso(T0), end: iso(T0) },
    ]);
    expect(out).toEqual([]);
  });
});

describe("overlapsBusy", () => {
  const busy = normalizeBusy([{ start: iso(T0), end: iso(T0 + HOUR) }]);

  it("detects a real overlap", () => {
    expect(overlapsBusy(T0 + 30 * 60_000, T0 + 90 * 60_000, busy)).toBe(true);
    expect(overlapsBusy(T0 - HOUR, T0 + 1, busy)).toBe(true);
  });

  it("touching endpoints do not overlap (back-to-back is fine)", () => {
    expect(overlapsBusy(T0 + HOUR, T0 + 2 * HOUR, busy)).toBe(false);
    expect(overlapsBusy(T0 - HOUR, T0, busy)).toBe(false);
  });

  it("empty busy list never overlaps", () => {
    expect(overlapsBusy(T0, T0 + HOUR, [])).toBe(false);
  });
});

describe("cellIsBusy — interval → 30-min cell mapping", () => {
  // Meeting 09:15–09:45 covers the 09:00 and 09:30 cells, not 08:30 or 10:00.
  const busy = normalizeBusy([
    { start: "2026-08-10T09:15:00Z", end: "2026-08-10T09:45:00Z" },
  ]);
  const cell = (h: number, m: number) => Date.parse(`2026-08-10T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00Z`);

  it("marks exactly the cells the interval touches", () => {
    expect(cellIsBusy(cell(8, 30), 30, busy)).toBe(false);
    expect(cellIsBusy(cell(9, 0), 30, busy)).toBe(true);
    expect(cellIsBusy(cell(9, 30), 30, busy)).toBe(true);
    expect(cellIsBusy(cell(10, 0), 30, busy)).toBe(false);
  });

  it("a cross-day block marks the first cells of the next morning", () => {
    const overnight = normalizeBusy([
      { start: "2026-08-10T22:00:00Z", end: "2026-08-11T07:30:00Z" },
    ]);
    expect(cellIsBusy(Date.parse("2026-08-11T07:00:00Z"), 30, overnight)).toBe(true);
    expect(cellIsBusy(Date.parse("2026-08-11T07:30:00Z"), 30, overnight)).toBe(false);
  });
});

describe("isBusyRunStart — the 'Busy' label appears once per block", () => {
  const busy = normalizeBusy([
    { start: "2026-08-10T09:00:00Z", end: "2026-08-10T11:00:00Z" },
  ]);
  const at = (s: string) => Date.parse(s);

  it("labels only the first cell of a run", () => {
    expect(isBusyRunStart(at("2026-08-10T09:00:00Z"), 30, busy, false)).toBe(true);
    expect(isBusyRunStart(at("2026-08-10T09:30:00Z"), 30, busy, false)).toBe(false);
    expect(isBusyRunStart(at("2026-08-10T10:30:00Z"), 30, busy, false)).toBe(false);
  });

  it("a block flowing over the top of the grid labels the first visible row", () => {
    expect(isBusyRunStart(at("2026-08-10T09:30:00Z"), 30, busy, true)).toBe(true);
  });

  it("non-busy cells are never run starts", () => {
    expect(isBusyRunStart(at("2026-08-10T11:00:00Z"), 30, busy, true)).toBe(false);
  });
});
