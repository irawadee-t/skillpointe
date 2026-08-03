/**
 * ScoreInContext data-accuracy tests: bucket segment heights proportional to
 * counts, small-n honesty (dot strip), labeled threshold + marker.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreInContext } from "../ScoreInContext";
import type { VizBucket, VizDistribution } from "../types";

const THRESHOLDS = { strong_fit_min: 80, good_fit_min: 60 };

function emptyBuckets(): VizBucket[] {
  return Array.from({ length: 20 }, (_, i) => ({
    x0: i * 5,
    x1: (i + 1) * 5,
    eligible: 0,
    near_fit: 0,
    ineligible: 0,
  }));
}

function bucketDist(): VizDistribution {
  const buckets = emptyBuckets();
  buckets[3].ineligible = 40; // 15–20
  buckets[8].near_fit = 20; // 40–45
  buckets[8].ineligible = 10;
  buckets[14].eligible = 10; // 70–75
  return {
    n: 80,
    mode: "buckets",
    bucket_width: 5,
    buckets,
    points: [],
    median: 22,
  };
}

function pointDist(k: number): VizDistribution {
  return {
    n: k,
    mode: "points",
    bucket_width: 5,
    buckets: [],
    points: Array.from({ length: k }, (_, i) => ({
      score: 10 + i * 5,
      status: i % 2 ? "near_fit" : "ineligible",
    })),
    median: 30,
  };
}

describe("ScoreInContext buckets mode", () => {
  it("segment heights are proportional to counts", () => {
    render(
      <ScoreInContext
        distribution={bucketDist()}
        score={72}
        thresholds={THRESHOLDS}
        mode="applicant"
      />,
    );
    const h = (sel: string) =>
      Number(document.querySelector(sel)?.getAttribute("height"));
    const h40 = h('[data-testid="bucket-15-ineligible"]'); // count 40 (max)
    const h20 = h('[data-testid="bucket-40-near_fit"]');
    const h10 = h('[data-testid="bucket-70-eligible"]');
    expect(h40).toBeGreaterThan(0);
    expect(h20).toBeCloseTo(h40 / 2, 5);
    expect(h10).toBeCloseTo(h40 / 4, 5);
  });

  it("stacks mixed buckets without overlap (total = sum of parts)", () => {
    render(
      <ScoreInContext
        distribution={bucketDist()}
        score={72}
        thresholds={THRESHOLDS}
        mode="applicant"
      />,
    );
    const near = document.querySelector('[data-testid="bucket-40-near_fit"]')!;
    const inel = document.querySelector('[data-testid="bucket-40-ineligible"]')!;
    const nearTop = Number(near.getAttribute("y"));
    const inelTop = Number(inel.getAttribute("y"));
    const inelH = Number(inel.getAttribute("height"));
    // near_fit sits directly on top of the ineligible segment
    expect(nearTop + Number(near.getAttribute("height"))).toBeCloseTo(inelTop, 5);
    expect(inelTop + inelH).toBeCloseTo(46, 5); // baseline
  });

  it("labels the threshold and this match's score", () => {
    render(
      <ScoreInContext
        distribution={bucketDist()}
        score={72}
        thresholds={THRESHOLDS}
        mode="applicant"
      />,
    );
    expect(screen.getByText(/strong fit ≥ 80/)).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText(/n\s*=\s*80/)).toBeInTheDocument();
  });
});

describe("ScoreInContext small-n honesty", () => {
  it("renders every point as a dot when n < 20", () => {
    render(
      <ScoreInContext
        distribution={pointDist(12)}
        score={45}
        thresholds={THRESHOLDS}
        mode="job"
      />,
    );
    expect(
      document.querySelectorAll('[data-testid="context-points"] circle'),
    ).toHaveLength(12);
    expect(
      document.querySelector('[data-testid="context-buckets"]'),
    ).toBeNull();
    expect(screen.getByText(/n\s*=\s*12/)).toBeInTheDocument();
  });
});

describe("ScoreInContext a11y", () => {
  it("exposes a self-describing img role", () => {
    render(
      <ScoreInContext
        distribution={bucketDist()}
        score={72}
        thresholds={THRESHOLDS}
        mode="applicant"
      />,
    );
    const svg = screen.getByRole("img");
    expect(svg.getAttribute("aria-label")).toContain("scores 72 of 100");
    expect(svg.getAttribute("aria-label")).toContain("median is 22");
  });
});
