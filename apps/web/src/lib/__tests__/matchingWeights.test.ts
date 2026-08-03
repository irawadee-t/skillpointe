/**
 * Pins the weight-mixer math for /admin/matching:
 *  - redistribute keeps the total invariant (to a tenth, exactly) while one
 *    dimension moves, absorbing the delta proportionally across UNLOCKED
 *    dimensions only;
 *  - locked dimensions never change; a fully-locked remainder pins the key;
 *  - values clamp at 0 and at the unlocked block's total — never negative;
 *  - normalizeTo100 lands exactly on 100 while respecting locks.
 */
import { describe, expect, it } from "vitest";
import { normalizeTo100, redistribute, sumWeights } from "../matchingWeights";

const BASE: Record<string, number> = {
  trade_program_alignment: 25,
  geography_alignment: 20,
  credential_readiness: 15,
  timing_readiness: 10,
  experience_internship_alignment: 10,
  industry_alignment: 5,
  compensation_alignment: 5,
  work_style_signal_alignment: 5,
  employer_soft_pref_alignment: 5,
};

const sum = (w: Record<string, number>) => sumWeights(w);

describe("redistribute", () => {
  it("keeps the total at exactly 100 when one weight moves", () => {
    const next = redistribute(BASE, "trade_program_alignment", 40);
    expect(next.trade_program_alignment).toBe(40);
    expect(sum(next)).toBe(100);
  });

  it("absorbs the delta proportionally to current values", () => {
    // Drop trade 25 -> 15: the +10 spreads over the other 75 points, so each
    // absorber grows by w * 10/75.
    const next = redistribute(BASE, "trade_program_alignment", 15);
    expect(next.geography_alignment).toBeCloseTo(20 + 20 * (10 / 75), 1);
    expect(next.industry_alignment).toBeCloseTo(5 + 5 * (10 / 75), 1);
    expect(sum(next)).toBe(100);
  });

  it("never touches locked dimensions", () => {
    const locked = new Set(["geography_alignment", "credential_readiness"]);
    const next = redistribute(BASE, "trade_program_alignment", 45, locked);
    expect(next.geography_alignment).toBe(20);
    expect(next.credential_readiness).toBe(15);
    expect(next.trade_program_alignment).toBe(45);
    expect(sum(next)).toBe(100);
  });

  it("returns the input unchanged when the moved key is locked", () => {
    const next = redistribute(BASE, "geography_alignment", 90, new Set(["geography_alignment"]));
    expect(next).toEqual(BASE);
  });

  it("pins the key when every other dimension is locked", () => {
    const locked = new Set(Object.keys(BASE).filter((k) => k !== "industry_alignment"));
    const next = redistribute(BASE, "industry_alignment", 50, locked);
    expect(next).toEqual(BASE);
  });

  it("clamps at the unlocked block total — absorbers floor at 0, never negative", () => {
    const locked = new Set(["geography_alignment"]); // 20 locked
    const next = redistribute(BASE, "trade_program_alignment", 99, locked);
    // Unlocked block = 100 - 20 = 80; the key can take at most all of it.
    expect(next.trade_program_alignment).toBe(80);
    expect(next.geography_alignment).toBe(20);
    for (const v of Object.values(next)) expect(v).toBeGreaterThanOrEqual(0);
    expect(sum(next)).toBe(100);
  });

  it("clamps below at 0", () => {
    const next = redistribute(BASE, "trade_program_alignment", -10);
    expect(next.trade_program_alignment).toBe(0);
    expect(sum(next)).toBe(100);
  });

  it("splits equally when all absorbers are at 0", () => {
    const w = { a: 100, b: 0, c: 0, d: 0 };
    const next = redistribute(w, "a", 70);
    expect(next).toEqual({ a: 70, b: 10, c: 10, d: 10 });
  });

  it("preserves a non-100 total instead of silently fixing it", () => {
    const w = { a: 30, b: 30, c: 30 }; // sums to 90
    const next = redistribute(w, "a", 50);
    expect(sum(next)).toBe(90);
  });

  it("handles fractional weights without float drift", () => {
    let w: Record<string, number> = { ...BASE };
    // Simulate a drag: many successive small moves on different keys.
    const keys = Object.keys(BASE);
    for (let i = 0; i < 200; i += 1) {
      const key = keys[i % keys.length];
      const target = (w[key] + ((i * 7) % 13) - 6 + 100) % 60;
      w = redistribute(w, key, target);
      expect(sum(w)).toBe(100);
      for (const v of Object.values(w)) {
        expect(v).toBeGreaterThanOrEqual(0);
        // tenth precision only
        expect(Math.round(v * 10) / 10).toBe(v);
      }
    }
  });

  it("respects locks under fuzzed drags", () => {
    const locked = new Set(["timing_readiness", "compensation_alignment"]);
    let w: Record<string, number> = { ...BASE };
    const movable = Object.keys(BASE).filter((k) => !locked.has(k));
    for (let i = 0; i < 100; i += 1) {
      const key = movable[i % movable.length];
      w = redistribute(w, key, (i * 11) % 55, locked);
      expect(w.timing_readiness).toBe(10);
      expect(w.compensation_alignment).toBe(5);
      expect(sum(w)).toBe(100);
    }
  });

  it("is deterministic for tie-breaking remainders", () => {
    const w = { a: 10, b: 10, c: 10, d: 70 };
    const first = redistribute(w, "d", 65);
    const second = redistribute(w, "d", 65);
    expect(first).toEqual(second);
    expect(sum(first)).toBe(100);
  });
});

describe("normalizeTo100", () => {
  it("scales proportionally to exactly 100", () => {
    const w = { a: 30, b: 30, c: 30 }; // 90
    const next = normalizeTo100(w);
    expect(sum(next)).toBe(100);
    // 100/3 per key at tenth precision: the extra tenth goes to the first key.
    expect(next.a).toBe(33.4);
    expect(next.b).toBe(33.3);
    expect(next.c).toBe(33.3);
  });

  it("keeps locked weights and scales only the rest", () => {
    const w = { a: 50, b: 40, c: 40 }; // 130
    const next = normalizeTo100(w, new Set(["a"]));
    expect(next.a).toBe(50);
    expect(next.b).toBe(25);
    expect(next.c).toBe(25);
    expect(sum(next)).toBe(100);
  });

  it("splits equally when the unlocked block is all zero", () => {
    const w = { a: 60, b: 0, c: 0 };
    const next = normalizeTo100(w, new Set(["a"]));
    expect(next).toEqual({ a: 60, b: 20, c: 20 });
  });

  it("floors unlocked at 0 when the locked block is already over 100", () => {
    const w = { a: 120, b: 10, c: 10 };
    const next = normalizeTo100(w, new Set(["a"]));
    expect(next.a).toBe(120);
    expect(next.b).toBe(0);
    expect(next.c).toBe(0);
  });

  it("no-ops when everything is locked", () => {
    const w = { a: 40, b: 40 };
    expect(normalizeTo100(w, new Set(["a", "b"]))).toEqual(w);
  });

  it("matches the legacy behavior with no locks (proportional, exact 100)", () => {
    const w = { ...BASE, trade_program_alignment: 30 }; // 105
    const next = normalizeTo100(w);
    expect(sum(next)).toBe(100);
  });
});
