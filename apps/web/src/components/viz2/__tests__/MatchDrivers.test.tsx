/**
 * MatchDrivers data-accuracy + a11y tests (data-viz-2025 testing pattern):
 * rendered bar geometry must be exactly proportional to weights and scores —
 * the visual comparison IS the arithmetic one.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchDrivers } from "../MatchDrivers";
import { TEST_WIDTH } from "./setup";
import type { VizDimension, VizGate } from "../types";

const DIMS: VizDimension[] = [
  {
    dimension: "trade_program_alignment",
    weight: 25,
    raw_score: 60,
    weighted_score: 15,
    rationale: "adjacent families: applicant=automotive, job=manufacturing",
    null_handling_applied: false,
  },
  {
    dimension: "geography_alignment",
    weight: 20,
    raw_score: 20,
    weighted_score: 4,
    rationale: "~1106 mi away, beyond your 50 mi radius",
    null_handling_applied: false,
  },
  {
    dimension: "compensation_alignment",
    weight: 5,
    raw_score: 70,
    weighted_score: 3.5,
    rationale: "no pay data on job (null default)",
    null_handling_applied: true,
  },
];

const GATES: VizGate[] = [
  {
    gate_name: "geography_feasibility",
    result: "fail",
    reason: "Beyond commute radius",
    severity: "critical",
  },
];

function capacityOf(dimension: string): number {
  const el = document.querySelector(
    `[data-testid="driver-capacity"][data-dimension="${dimension}"]`,
  );
  return Number(el?.getAttribute("width"));
}

function fillOf(dimension: string): number {
  const el = document.querySelector(
    `[data-testid="driver-fill"][data-dimension="${dimension}"]`,
  );
  return Number(el?.getAttribute("width"));
}

describe("MatchDrivers geometry", () => {
  it("track width is proportional to weight (capacity encoding)", () => {
    render(<MatchDrivers dimensions={DIMS} gates={[]} />);
    // max weight (25) spans the full measured bar area
    expect(capacityOf("trade_program_alignment")).toBeCloseTo(TEST_WIDTH, 5);
    // weight 20 = 20/25 of it; weight 5 = 5/25
    expect(capacityOf("geography_alignment")).toBeCloseTo(
      (20 / 25) * TEST_WIDTH,
      5,
    );
    expect(capacityOf("compensation_alignment")).toBeCloseTo(
      (5 / 25) * TEST_WIDTH,
      5,
    );
  });

  it("fill width is proportional to weighted contribution", () => {
    render(<MatchDrivers dimensions={DIMS} gates={[]} />);
    // fill = capacity * raw/100 → px per weighted point is one shared constant
    const pxPerPoint = TEST_WIDTH / 25;
    expect(fillOf("trade_program_alignment")).toBeCloseTo(15 * pxPerPoint, 5);
    expect(fillOf("geography_alignment")).toBeCloseTo(4 * pxPerPoint, 5);
    expect(fillOf("compensation_alignment")).toBeCloseTo(3.5 * pxPerPoint, 5);
  });

  it("sorts rows by weighted contribution, descending", () => {
    render(<MatchDrivers dimensions={DIMS} gates={[]} />);
    const fills = [
      ...document.querySelectorAll('[data-testid="driver-fill"]'),
    ].map((el) => Number(el.getAttribute("data-weighted-score")));
    expect(fills).toEqual([15, 4, 3.5]);
  });

  it("renders null-handled fills hatched with an estimated affix", () => {
    render(<MatchDrivers dimensions={DIMS} gates={[]} />);
    const fill = document.querySelector(
      '[data-testid="driver-fill"][data-dimension="compensation_alignment"]',
    );
    expect(fill?.getAttribute("fill")).toMatch(/^url\(#.*hatch/);
    expect(screen.getByText("estimated")).toBeInTheDocument();
  });

  it("uses the attention tone only for gate-flagged dimensions", () => {
    render(<MatchDrivers dimensions={DIMS} gates={GATES} />);
    const geo = document.querySelector(
      '[data-testid="driver-fill"][data-dimension="geography_alignment"]',
    );
    const trade = document.querySelector(
      '[data-testid="driver-fill"][data-dimension="trade_program_alignment"]',
    );
    expect(geo?.getAttribute("fill")).toBe("#9d2235");
    expect(trade?.getAttribute("fill")).toBe("#17171c");
  });
});

describe("MatchDrivers a11y", () => {
  it("each bar is a focusable control with a self-describing label", () => {
    render(<MatchDrivers dimensions={DIMS} gates={GATES} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    const geoButton = buttons.find((b) =>
      b.getAttribute("aria-label")?.startsWith("Geography"),
    );
    expect(geoButton?.getAttribute("aria-label")).toContain("4 of 20");
    expect(geoButton?.getAttribute("aria-label")).toContain("hard gate");
  });

  it("shows the full rationale tooltip on keyboard focus", () => {
    render(<MatchDrivers dimensions={DIMS} gates={[]} />);
    const btn = screen
      .getAllByRole("button")
      .find((b) => b.getAttribute("aria-label")?.startsWith("Geography"))!;
    fireEvent.focus(btn);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "~1106 mi away, beyond your 50 mi radius",
    );
    fireEvent.blur(btn);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
