"use client";

import { useEffect, useState } from "react";
import { interpolateRgb, scaleLinear } from "d3";
import { useMeasuredWidth } from "./useMeasuredWidth";

const INK = "#17171c";
const ACCENT = "#9D2235";
const HAIRLINE = "#e7e5e2";
const SLATE = "#33322f";
const SLATE_MUTED = "#5c5a55";

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
}

const ROW_H = 58; // vertical rhythm per stage
const BAR_H = 20;
const BAR_Y = 24; // bar offset within a row
const COUNT_PAD = 96; // space reserved right of the longest bar for the count

/**
 * MarketplaceFunnel — typographic stage progression.
 *
 * Each stage is a line of text (label left, share right) over a proportional
 * bar; bar fills step from ink to the brand accent as the funnel narrows, and
 * hairline connectors trace the drop-off between stages. Direct labels only —
 * no axes, no gridlines, no legend.
 */
export function MarketplaceFunnel({
  stages,
  className,
}: {
  stages: FunnelStage[];
  className?: string;
}) {
  const [ref, width] = useMeasuredWidth();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!stages || stages.length === 0) {
    return (
      <div className={className}>
        <div className="border-t border-hairline pt-3 text-caption text-slate-muted">
          No stage data yet.
        </div>
      </div>
    );
  }

  const n = stages.length;
  const max = Math.max(1, ...stages.map((s) => s.count));
  const first = Math.max(1, stages[0]?.count ?? 1);
  const w = Math.max(width, 280);
  const x = scaleLinear().domain([0, max]).range([0, Math.max(40, w - COUNT_PAD)]);
  const color = interpolateRgb(INK, ACCENT);
  const height = (n - 1) * ROW_H + BAR_Y + BAR_H + 2;

  const ease = "cubic-bezier(0.16, 1, 0.3, 1)"; // ease-cohere (tailwind.config.ts)

  return (
    <div ref={ref} className={className}>
      <svg
        width={w}
        height={height}
        role="img"
        aria-label={`Funnel: ${stages.map((s) => `${s.label} ${s.count}`).join(", ")}`}
        style={{ display: "block", maxWidth: "100%" }}
      >
        {stages.map((s, i) => {
          const y0 = i * ROW_H;
          const barW = s.count > 0 ? Math.max(2, x(s.count)) : 2;
          const share = Math.round((s.count / first) * 100);
          const next = stages[i + 1];
          const nextW = next && next.count > 0 ? Math.max(2, x(next.count)) : 2;

          return (
            <g key={s.key}>
              {/* stage label */}
              <text x={0} y={y0 + 14} fontSize={13.5} fontWeight={500} fill={INK}>
                {s.label}
              </text>

              {/* share of first stage, right-aligned, quiet */}
              {i > 0 && (
                <text
                  x={w}
                  y={y0 + 14}
                  fontSize={12}
                  fill={SLATE_MUTED}
                  textAnchor="end"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {share}%
                </text>
              )}

              {/* proportional bar, ink stepping toward accent */}
              <rect
                x={0}
                y={y0 + BAR_Y}
                width={barW}
                height={BAR_H}
                rx={3}
                fill={s.count > 0 ? color(n === 1 ? 1 : i / (n - 1)) : HAIRLINE}
                style={{
                  transformBox: "fill-box",
                  transformOrigin: "left center",
                  transform: mounted ? "scaleX(1)" : "scaleX(0)",
                  transition: `transform 400ms ${ease}`,
                }}
              />

              {/* count, directly labeled at the bar's end */}
              <text
                x={barW + 10}
                y={y0 + BAR_Y + BAR_H / 2 + 4.5}
                fontSize={13}
                fontWeight={600}
                fill={SLATE}
                style={{
                  fontVariantNumeric: "tabular-nums",
                  opacity: mounted ? 1 : 0,
                  transition: `opacity 250ms ${ease} 200ms`,
                }}
              >
                {s.count.toLocaleString()}
              </text>

              {/* hairline connector tracing the drop-off to the next stage */}
              {next && (
                <line
                  x1={barW}
                  y1={y0 + BAR_Y + BAR_H}
                  x2={nextW}
                  y2={y0 + ROW_H + BAR_Y}
                  stroke={HAIRLINE}
                  strokeWidth={1}
                  style={{
                    opacity: mounted ? 1 : 0,
                    transition: `opacity 250ms ${ease} 250ms`,
                  }}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
