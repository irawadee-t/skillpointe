"use client";

/**
 * MatchDrivers — driver-contribution capacity bars for the 9 scored
 * dimensions of one match.
 *
 * Encoding (honest by construction):
 *   track length  = the dimension's WEIGHT (its capacity — a weight-25
 *                   dimension owns visibly more real estate than a weight-5)
 *   filled length = raw_score% of that capacity, i.e. filled px are directly
 *                   proportional to weighted_score (the actual contribution)
 *   zero baseline, shared linear scale, uniform bar height — length is the
 *   only encoding, so the visual comparison IS the arithmetic one.
 *
 * Labels ARE the axis: dimension name + stored rationale on the left, the
 * contribution ("15 of 25") directly at the row's end. No gridlines, no axis
 * lines, no legend. Null-handled dimensions render hatched with an
 * "estimated" affix; dimensions tied to an unpassed hard gate use the
 * attention tone (hue + the gate context in the rationale — never color
 * alone). Bars are keyboard-focusable; hover/focus reveals the full stored
 * rationale in a quiet white hairline tooltip.
 */

import { useEffect, useId, useMemo, useState } from "react";
import { scaleLinear } from "@visx/scale";
import { Bar } from "@visx/shape";
import { Group } from "@visx/group";
import { useMeasuredWidth } from "@/components/viz/useMeasuredWidth";
import {
  attentionDimensions,
  dimensionLabel,
  fmt1,
  sentenceCase,
  type VizDimension,
  type VizGate,
} from "./types";

const BAR_HEIGHT = 12;
const ROW_SVG_HEIGHT = BAR_HEIGHT;

/** Ink for ordinary fills; the single attention accent for gate-flagged. */
const INK = "#17171c";
const ATTENTION = "#9d2235";
const TRACK = "#f2f2f1"; // stone — the capacity outline is quiet but real data

export interface MatchDriversProps {
  dimensions: VizDimension[];
  gates?: VizGate[];
  className?: string;
}

export function MatchDrivers({ dimensions, gates = [], className }: MatchDriversProps) {
  const patternId = useId().replaceAll(":", "");
  const [rootRef, rootWidth] = useMeasuredWidth();
  const [barAreaRef, barAreaWidth] = useMeasuredWidth();
  // Container-driven (not viewport-driven) stacking: when the component is
  // mounted in a narrow card, labels move above the bars so the bars keep
  // usable length. 460px keeps 375px-wide mounts readable.
  const stacked = rootWidth > 0 && rootWidth < 460;
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    // setTimeout, not rAF: rAF stalls in hidden/background tabs, which would
    // leave fills at scaleX(0) until the tab is fronted.
    const id = setTimeout(() => setMounted(true), 30);
    return () => clearTimeout(id);
  }, []);

  const sorted = useMemo(
    () => [...dimensions].sort((a, b) => b.weighted_score - a.weighted_score),
    [dimensions],
  );
  const attention = useMemo(() => attentionDimensions(gates), [gates]);

  const maxWeight = Math.max(1, ...sorted.map((d) => d.weight));
  const capacityScale = scaleLinear<number>({
    domain: [0, maxWeight],
    range: [0, Math.max(0, barAreaWidth)],
  });

  if (sorted.length === 0) {
    return (
      <p className={`text-caption text-slate-muted ${className ?? ""}`}>
        No dimension breakdown is on file for this match yet.
      </p>
    );
  }

  return (
    <div className={className} ref={rootRef}>
      {/* Hidden shared defs: diagonal hatch for estimated (null-handled) fills */}
      <svg width={0} height={0} aria-hidden="true" focusable="false" className="absolute">
        <defs>
          <pattern
            id={`${patternId}-hatch-ink`}
            width={5}
            height={5}
            patternTransform="rotate(45)"
            patternUnits="userSpaceOnUse"
          >
            <rect width={5} height={5} fill={INK} opacity={0.14} />
            <rect width={2.25} height={5} fill={INK} opacity={0.62} />
          </pattern>
          <pattern
            id={`${patternId}-hatch-attention`}
            width={5}
            height={5}
            patternTransform="rotate(45)"
            patternUnits="userSpaceOnUse"
          >
            <rect width={5} height={5} fill={ATTENTION} opacity={0.14} />
            <rect width={2.25} height={5} fill={ATTENTION} opacity={0.62} />
          </pattern>
        </defs>
      </svg>

      <ul className="m-0 list-none p-0">
        {sorted.map((d, i) => {
          const isAttention = attention.has(d.dimension);
          const capacity = capacityScale(d.weight);
          const fillFraction = Math.max(0, Math.min(1, d.raw_score / 100));
          const filled = capacity * fillFraction;
          const fill = d.null_handling_applied
            ? `url(#${patternId}-hatch-${isAttention ? "attention" : "ink"})`
            : isAttention
              ? ATTENTION
              : INK;
          const rationale = d.rationale ? sentenceCase(d.rationale) : null;
          const isOpen = open === d.dimension;
          const contributionText = `${fmt1(d.weighted_score)} of ${fmt1(d.weight)}`;
          const ariaLabel = [
            dimensionLabel(d.dimension),
            `contributes ${contributionText} possible points`,
            d.null_handling_applied ? "estimated from a neutral default" : null,
            isAttention ? "flagged by a hard gate" : null,
            rationale,
          ]
            .filter(Boolean)
            .join(". ");

          return (
            <li
              key={d.dimension}
              className={`grid items-center gap-x-5 gap-y-1 py-2.5 ${
                stacked ? "grid-cols-1" : "grid-cols-[minmax(150px,220px)_1fr]"
              } ${i > 0 ? "border-t border-hairline" : ""}`}
            >
              <div className="min-w-0">
                <div className="flex items-baseline gap-1.5">
                  <span
                    className={`text-[13px] font-medium leading-tight ${
                      isAttention ? "text-studio-maroon" : "text-cohere-ink"
                    }`}
                  >
                    {dimensionLabel(d.dimension)}
                  </span>
                  {d.null_handling_applied && (
                    <span className="whitespace-nowrap text-[11px] text-slate-muted">
                      estimated
                    </span>
                  )}
                </div>
                {rationale && !stacked && (
                  <div
                    className="truncate text-[12px] leading-snug text-slate-muted"
                    title={rationale}
                  >
                    {rationale}
                  </div>
                )}
              </div>

              <div className="relative flex min-w-0 items-center gap-3">
                <div ref={i === 0 ? barAreaRef : undefined} className="relative min-w-0 flex-1">
                  {/* Row 0 measures; all rows share the measured width. */}
                  <button
                    type="button"
                    tabIndex={0}
                    aria-label={ariaLabel}
                    aria-expanded={isOpen}
                    className="block w-full cursor-default rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-studio-maroon/40 focus-visible:ring-offset-2"
                    onMouseEnter={() => setOpen(d.dimension)}
                    onMouseLeave={() => setOpen((v) => (v === d.dimension ? null : v))}
                    onFocus={() => setOpen(d.dimension)}
                    onBlur={() => setOpen((v) => (v === d.dimension ? null : v))}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setOpen(null);
                    }}
                  >
                    <svg
                      width="100%"
                      height={ROW_SVG_HEIGHT}
                      role="img"
                      aria-hidden="true"
                      focusable="false"
                      className="block"
                      data-testid="driver-row-svg"
                    >
                      <Group>
                        {/* capacity track = weight */}
                        <Bar
                          data-testid="driver-capacity"
                          data-dimension={d.dimension}
                          data-weight={d.weight}
                          x={0}
                          y={0}
                          width={Math.max(0, capacity)}
                          height={BAR_HEIGHT}
                          rx={2}
                          fill={TRACK}
                        />
                        {/* fill = raw_score% of capacity → length ∝ weighted_score */}
                        <Bar
                          data-testid="driver-fill"
                          data-dimension={d.dimension}
                          data-weighted-score={d.weighted_score}
                          x={0}
                          y={0}
                          width={Math.max(0, filled)}
                          height={BAR_HEIGHT}
                          rx={2}
                          fill={fill}
                          style={{
                            transform: mounted ? "scaleX(1)" : "scaleX(0)",
                            transformOrigin: "0 50%",
                          }}
                          className="transition-transform duration-[400ms] ease-out motion-reduce:transition-none"
                        />
                      </Group>
                    </svg>
                  </button>

                  {isOpen && rationale && (
                    <div
                      role="tooltip"
                      className="absolute bottom-full left-0 z-20 mb-2 w-max max-w-[min(20rem,80vw)] rounded-[8px] border border-hairline bg-white px-3 py-2 text-[12px] leading-snug text-slate shadow-float"
                    >
                      <span className="font-medium text-cohere-ink">
                        {dimensionLabel(d.dimension)}
                        {": "}
                      </span>
                      {rationale}
                      {d.null_handling_applied && (
                        <span className="text-slate-muted">
                          {" "}
                          (estimated, a neutral default was used)
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <span className="w-[72px] shrink-0 whitespace-nowrap text-right text-[12px] tabular-nums text-slate">
                  {contributionText}
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      <p className="mt-2 text-[11px] leading-snug text-slate-muted">
        Track length is the dimension&apos;s weight; the dark fill is the points earned
        within it. Hatched fills are estimated from neutral defaults.
      </p>
    </div>
  );
}
