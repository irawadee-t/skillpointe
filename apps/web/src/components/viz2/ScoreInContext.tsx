"use client";

/**
 * ScoreInContext — a compact one-row strip (~64px) showing where one match's
 * score sits inside a context population.
 *
 * Chart choice: a server-bucketed histogram silhouette (5-point buckets,
 * bucketed in SQL — raw rows never ship). Bars, not a smoothed density —
 * smoothing would invent observations. Each bucket stacks its eligibility
 * mix (muted statusTones hues) so "where the eligible matches live" is read
 * from the data, not asserted. Direct micro-labels name each status group at
 * its modal bucket; no legend.
 *
 * Sample-size honesty: populations under 20 render as a dot strip — every
 * observation drawn individually, labeled "n = 12" — because a 12-row
 * histogram silhouette would be a lie of smoothness.
 *
 * Annotations carry the insight: this match's score as a ▲ marker with a
 * tabular numeral, and the strong-fit label threshold (from the active
 * policy config) as a labeled hairline.
 */

import { useMemo } from "react";
import { scaleLinear } from "@visx/scale";
import { Bar, Line, Circle } from "@visx/shape";
import { Group } from "@visx/group";
import { useMeasuredWidth } from "@/components/viz/useMeasuredWidth";
import type { VizDistribution, VizThresholds } from "./types";

const HEIGHT = 64;
const BASELINE_Y = 46; // bars grow up from here; marker + label live below
const TOP_PAD = 12; // room for the threshold label
const INK = "#17171c";
const HAIRLINE = "#e7e5e2";
const SLATE_MUTED = "#5c5a55";

/** Muted, statusTones-consistent population fills (never text colors). */
const STATUS_FILL: Record<string, string> = {
  eligible: "rgba(74, 75, 47, 0.55)", // cohere-green (olive)
  near_fit: "rgba(157, 34, 53, 0.32)", // studio-maroon tint
  ineligible: "rgba(92, 90, 85, 0.22)", // slate-muted tint
};
const STATUS_TEXT: Record<string, string> = {
  eligible: "#4a4b2f",
  near_fit: "#9d2235",
  ineligible: "#5c5a55",
};
const STATUS_LABEL: Record<string, string> = {
  eligible: "eligible",
  near_fit: "near fit",
  ineligible: "ineligible",
};
const STACK_ORDER = ["ineligible", "near_fit", "eligible"] as const;

export interface ScoreInContextProps {
  distribution: VizDistribution;
  /** This match's score (policy-adjusted — the number the product shows). */
  score: number;
  thresholds: VizThresholds;
  /** Which population this is — controls the default caption copy. */
  mode: "applicant" | "job";
  /** Override the caption (e.g. localized copy). */
  caption?: string;
  className?: string;
}

export function ScoreInContext({
  distribution,
  score,
  thresholds,
  mode,
  caption,
  className,
}: ScoreInContextProps) {
  const [ref, width] = useMeasuredWidth();

  const captionText =
    caption ??
    (mode === "applicant"
      ? `Among the ${distribution.n.toLocaleString()} jobs scored for this applicant`
      : `Among ${distribution.n.toLocaleString()} candidates scored for this job`);

  const x = scaleLinear<number>({ domain: [0, 100], range: [0, Math.max(0, width)] });

  const maxTotal = useMemo(
    () =>
      Math.max(
        1,
        ...distribution.buckets.map((b) => b.eligible + b.near_fit + b.ineligible),
      ),
    [distribution.buckets],
  );
  const y = scaleLinear<number>({
    domain: [0, maxTotal],
    range: [0, BASELINE_Y - TOP_PAD],
  });

  /** Modal bucket per status, for direct labels (only groups ≥ 5% of n). */
  const groupLabels = useMemo(() => {
    if (distribution.mode !== "buckets" || distribution.n === 0) return [];
    const out: { status: string; cx: number }[] = [];
    for (const status of STACK_ORDER) {
      const total = distribution.buckets.reduce(
        (s, b) => s + (b[status] as number),
        0,
      );
      if (total < distribution.n * 0.05) continue;
      let best = distribution.buckets[0];
      for (const b of distribution.buckets)
        if ((b[status] as number) > (best[status] as number)) best = b;
      out.push({ status, cx: (best.x0 + best.x1) / 2 });
    }
    // Drop labels that would collide with a neighbor or the score marker.
    return out.filter((l, i) => {
      if (Math.abs(l.cx - score) < 9) return false;
      return out.every((m, j) => j >= i || Math.abs(m.cx - l.cx) >= 16);
    });
  }, [distribution, score]);

  /** Beeswarm-lite stacking for the small-n dot strip. */
  const dotStack = useMemo(() => {
    if (distribution.mode !== "points") return [];
    const seen = new Map<number, number>();
    return distribution.points.map((p) => {
      const slot = Math.round(p.score / 2.5);
      const level = seen.get(slot) ?? 0;
      seen.set(slot, level + 1);
      return { ...p, level };
    });
  }, [distribution]);

  const markerX = x(Math.max(0, Math.min(100, score)));
  const thresholdX = x(thresholds.strong_fit_min);
  // Floor to match the marketplace-wide score display convention.
  const scoreLabel = String(Math.floor(score));
  const isDots = distribution.mode === "points" || distribution.n < 20;

  const ariaLabel =
    `${captionText}: this match scores ${scoreLabel} of 100. ` +
    (distribution.median != null
      ? `The population median is ${Math.round(distribution.median)}. `
      : "") +
    `Strong fit begins at ${Math.round(thresholds.strong_fit_min)}.`;

  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-4">
        <span className="min-w-0 truncate text-[12px] text-slate-muted">{captionText}</span>
        <span className="shrink-0 text-[11px] tabular-nums text-slate-muted">
          n&nbsp;=&nbsp;{distribution.n.toLocaleString()}
        </span>
      </div>

      <div ref={ref} className="relative mt-1">
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={ariaLabel}
            className="block overflow-visible"
            data-testid="score-context-svg"
          >
            {/* baseline hairline — the one axis */}
            <Line
              from={{ x: 0, y: BASELINE_Y }}
              to={{ x: width, y: BASELINE_Y }}
              stroke={HAIRLINE}
              strokeWidth={1}
              shapeRendering="crispEdges"
            />

            {!isDots && (
              <Group data-testid="context-buckets">
                {distribution.buckets.map((b) => {
                  const bx = x(b.x0);
                  const bw = Math.max(0, x(b.x1) - x(b.x0) - 1);
                  let yCursor = BASELINE_Y;
                  return (
                    <Group key={b.x0}>
                      {STACK_ORDER.map((status) => {
                        const count = b[status] as number;
                        if (count <= 0) return null;
                        const h = y(count);
                        yCursor -= h;
                        return (
                          <Bar
                            key={status}
                            data-testid={`bucket-${b.x0}-${status}`}
                            data-count={count}
                            x={bx}
                            y={yCursor}
                            width={bw}
                            height={h}
                            fill={STATUS_FILL[status]}
                          />
                        );
                      })}
                    </Group>
                  );
                })}
                {groupLabels.map((l) => (
                  <text
                    key={l.status}
                    x={x(l.cx)}
                    y={TOP_PAD - 3}
                    textAnchor="middle"
                    fontSize={10}
                    fill={STATUS_TEXT[l.status]}
                  >
                    {STATUS_LABEL[l.status]}
                  </text>
                ))}
              </Group>
            )}

            {isDots && (
              <Group data-testid="context-points">
                {dotStack.map((p, i) => (
                  <Circle
                    key={i}
                    cx={x(p.score)}
                    cy={BASELINE_Y - 5 - p.level * 8}
                    r={3}
                    fill={STATUS_FILL[p.status] ?? STATUS_FILL.ineligible}
                    stroke="white"
                    strokeWidth={0.5}
                  />
                ))}
              </Group>
            )}

            {/* strong-fit threshold — labeled reference hairline */}
            {thresholds.strong_fit_min > 0 && (
              <Group data-testid="threshold-line">
                <Line
                  from={{ x: thresholdX, y: TOP_PAD - 1 }}
                  to={{ x: thresholdX, y: BASELINE_Y }}
                  stroke={SLATE_MUTED}
                  strokeWidth={1}
                  strokeDasharray="2,3"
                />
                <text
                  x={thresholdX}
                  y={TOP_PAD - 3}
                  textAnchor={thresholds.strong_fit_min > 82 ? "end" : "middle"}
                  fontSize={10}
                  fill={SLATE_MUTED}
                >
                  strong fit ≥ {Math.round(thresholds.strong_fit_min)}
                </text>
              </Group>
            )}

            {/* this match — ▲ marker + numeral below the baseline */}
            <Group data-testid="score-marker">
              <path
                d={`M ${markerX} ${BASELINE_Y + 2} l 4 6 l -8 0 z`}
                fill={INK}
              />
              <text
                x={markerX}
                y={BASELINE_Y + 17}
                textAnchor={markerX < 14 ? "start" : markerX > width - 14 ? "end" : "middle"}
                fontSize={11}
                fontWeight={600}
                fill={INK}
                className="tabular-nums"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {scoreLabel}
              </text>
            </Group>
          </svg>
        )}
      </div>
    </div>
  );
}
