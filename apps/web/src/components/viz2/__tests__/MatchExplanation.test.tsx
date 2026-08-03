/**
 * Composite + levers tests: figure semantics, data-table fallback, and the
 * honesty rule that levers never fabricate point estimates.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchExplanation } from "../MatchExplanation";
import { deriveLevers } from "../ImprovementLevers";
import type {
  MatchExplanationData,
  VizDimension,
  VizMatchCore,
} from "../types";

const MATCH: VizMatchCore = {
  match_id: "m1",
  job_id: "j1",
  job_title: "Welder I",
  employer_name: "Southwire",
  eligibility_status: "near_fit",
  match_label: "moderate_fit",
  match_tier: "strict",
  tier_reason: null,
  policy_adjusted_score: 47.5,
  base_fit_score: 47.5,
  distance_miles: 18.2,
  confidence_level: "medium",
  top_strengths: ["Welding program aligns with the trade"],
  top_gaps: ["OSHA 10 not yet earned", "Availability is 22 months out"],
  required_missing_items: ["OSHA 10"],
  recommended_next_step: "complete OSHA 10 certification",
  gates: [
    {
      gate_name: "required_credential_compatibility",
      result: "near_fit",
      reason: "Missing OSHA 10 (attainable)",
      severity: "soft",
    },
  ],
};

const DIMS: VizDimension[] = [
  {
    dimension: "trade_program_alignment",
    weight: 25,
    raw_score: 80,
    weighted_score: 20,
    rationale: "welding program maps directly",
    null_handling_applied: false,
  },
  {
    dimension: "compensation_alignment",
    weight: 5,
    raw_score: 50,
    weighted_score: 2.5,
    rationale: "no desired pay on file",
    null_handling_applied: true,
  },
];

const DATA: MatchExplanationData = {
  match: MATCH,
  dimensions: DIMS,
  thresholds: { strong_fit_min: 80, good_fit_min: 60 },
  context_applicant: {
    n: 0,
    mode: "points",
    bucket_width: 5,
    buckets: [],
    points: [],
    median: null,
  },
  context_job: {
    n: 0,
    mode: "points",
    bucket_width: 5,
    buckets: [],
    points: [],
    median: null,
  },
};

describe("MatchExplanation composite", () => {
  it("is a labeled figure with heading and score sentence", () => {
    render(<MatchExplanation data={DATA} />);
    const figure = screen.getByRole("figure");
    expect(figure).toHaveAccessibleName(/Why this score/);
    // Floored, not rounded — display matches the marketplace-wide floor convention.
    expect(screen.getByText("47")).toBeInTheDocument();
    expect(screen.getByText(/moderate fit/)).toBeInTheDocument();
  });

  it("provides a data-table fallback with every dimension", () => {
    render(<MatchExplanation data={DATA} />);
    expect(screen.getByText("View as data table")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("Trade and program alignment");
    expect(table).toHaveTextContent("Compensation (estimated)");
  });

  it("omits the context strip when the population is empty", () => {
    render(<MatchExplanation data={DATA} />);
    expect(document.querySelector('[data-testid="score-context-svg"]')).toBeNull();
  });
});

describe("deriveLevers honesty", () => {
  it("derives levers only from stored data, with no point estimates", () => {
    const levers = deriveLevers(MATCH, DIMS);
    const all = levers.map((l) => `${l.text} ${l.detail ?? ""}`).join(" | ");
    expect(all).toContain("Earn or upload OSHA 10");
    expect(all).toContain("Missing OSHA 10 (attainable)");
    expect(all).toContain("Add your desired pay");
    // FORBIDDEN: fabricated "+N points" predictions
    expect(all).not.toMatch(/\+\s*\d+(\.\d+)?\s*(points?|pts)/i);
  });

  it("does not template sentence-like required items", () => {
    const levers = deriveLevers(
      {
        ...MATCH,
        required_missing_items: [
          "this is a HVAC role, your training is in nursing",
        ],
        top_gaps: [],
        gates: [],
      },
      [],
    );
    expect(levers[0].text).toBe(
      "This is a HVAC role, your training is in nursing",
    );
    expect(levers[0].text).not.toContain("Earn or upload");
  });

  it("keeps uncovered top_gaps and drops ones already covered", () => {
    const levers = deriveLevers(MATCH, DIMS);
    const texts = levers.map((l) => l.text);
    expect(texts).toContain("Availability is 22 months out");
    // "OSHA 10 not yet earned" mentions the missing item → covered, not duplicated
    expect(texts).not.toContain("OSHA 10 not yet earned");
  });
});
