"use client";

import { useEffect, useId, useState } from "react";
import { area as d3area, line as d3line, scaleLinear } from "d3";
import { useMeasuredWidth } from "./useMeasuredWidth";

const INK = "#17171c";
const ACCENT = "#9D2235";
const HAIRLINE = "#e7e5e2";
const SLATE_MUTED = "#5c5a55";

export interface TrendPoint {
  label: string;
  value: number;
}

/**
 * TrendLine — a minimal accent line over a hairline baseline.
 *
 * No gridlines, no y-axis: the current value is labeled directly at the end
 * dot, 3–4 quiet x tick labels orient the reader in time. One left-to-right
 * reveal on entrance (≤400ms), then still. Hover shows a quiet white sheet.
 *
 * `format` is declarative (not a function) so server components can pass it:
 * "percent" treats values as 0–1 fractions.
 */
export function TrendLine({
  points,
  height = 120,
  domainMax,
  format = "number",
  ariaLabel = "Trend over time",
  className,
}: {
  points: TrendPoint[];
  height?: number;
  domainMax?: number;
  format?: "number" | "percent";
  ariaLabel?: string;
  className?: string;
}) {
  const formatValue = (v: number) =>
    format === "percent" ? `${Math.round(v * 100)}%` : v.toLocaleString();
  const [ref, width] = useMeasuredWidth();
  const [mounted, setMounted] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const clipId = useId();
  useEffect(() => setMounted(true), []);

  if (!points || points.length === 0) {
    return (
      <div className={className}>
        <div className="border-t border-hairline pt-3 text-caption text-slate-muted">
          No data yet.
        </div>
      </div>
    );
  }

  const w = Math.max(width, 240);
  const n = points.length;
  const last = points[n - 1];
  const endLabel = formatValue(last.value);
  const padL = 4;
  const padR = 8;
  const padT = 18;
  const padB = 24;

  const dataMax = Math.max(...points.map((p) => p.value));
  const yMax = Math.max(domainMax ?? 0, dataMax, 1e-9);
  const x = scaleLinear().domain([0, Math.max(1, n - 1)]).range([padL, w - padR]);
  const y = scaleLinear().domain([0, yMax]).range([height - padB, padT]);

  const linePath =
    d3line<TrendPoint>()
      .x((_, i) => x(i))
      .y((p) => y(p.value))(points) ?? "";
  const areaPath =
    d3area<TrendPoint>()
      .x((_, i) => x(i))
      .y0(height - padB)
      .y1((p) => y(p.value))(points) ?? "";

  // 3–4 orienting tick labels, always including first and last.
  const tickIdx = Array.from(
    new Set(
      n <= 4
        ? points.map((_, i) => i)
        : [0, Math.round((n - 1) / 3), Math.round(((n - 1) * 2) / 3), n - 1],
    ),
  );

  const ease = "cubic-bezier(0.16, 1, 0.3, 1)"; // ease-cohere (tailwind.config.ts)
  const endX = x(n - 1);
  const endY = y(last.value);
  const hovered = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className={`relative ${className ?? ""}`}>
      <svg
        width={w}
        height={height}
        role="img"
        aria-label={`${ariaLabel}: latest ${endLabel}`}
        style={{ display: "block", maxWidth: "100%" }}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - rect.left;
          const i = Math.round(x.invert(px));
          setHover(Math.max(0, Math.min(n - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={clipId}>
            <rect
              x={0}
              y={0}
              width={w}
              height={height}
              style={{
                transformBox: "fill-box",
                transformOrigin: "left center",
                transform: mounted ? "scaleX(1)" : "scaleX(0)",
                transition: `transform 400ms ${ease}`,
              }}
            />
          </clipPath>
        </defs>

        {/* hairline baseline */}
        <line
          x1={padL}
          y1={height - padB + 0.5}
          x2={w - padR}
          y2={height - padB + 0.5}
          stroke={HAIRLINE}
          strokeWidth={1}
        />

        <g clipPath={`url(#${clipId})`}>
          {n > 1 && <path d={areaPath} fill={ACCENT} fillOpacity={0.06} />}
          {n > 1 && (
            <path
              d={linePath}
              fill="none"
              stroke={ACCENT}
              strokeWidth={1.75}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}
        </g>

        {/* hover guide — hairline vertical + accent dot */}
        {hovered && (
          <g>
            <line
              x1={x(hover!)}
              y1={padT}
              x2={x(hover!)}
              y2={height - padB}
              stroke={HAIRLINE}
              strokeWidth={1}
            />
            <circle cx={x(hover!)} cy={y(hovered.value)} r={3.5} fill={ACCENT} />
          </g>
        )}

        {/* end dot + directly-labeled current value */}
        <circle
          cx={endX}
          cy={endY}
          r={3.5}
          fill={ACCENT}
          style={{ opacity: mounted ? 1 : 0, transition: `opacity 200ms ${ease} 300ms` }}
        />
        <text
          x={Math.min(endX, w - 4)}
          y={Math.max(12, endY - 10)}
          fontSize={12.5}
          fontWeight={600}
          fill={INK}
          textAnchor="end"
          style={{
            fontVariantNumeric: "tabular-nums",
            opacity: mounted ? 1 : 0,
            transition: `opacity 200ms ${ease} 300ms`,
          }}
        >
          {endLabel}
        </text>

        {/* 3–4 x tick labels */}
        {tickIdx.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={height - 6}
            fontSize={11}
            fill={SLATE_MUTED}
            textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
          >
            {points[i].label}
          </text>
        ))}
      </svg>

      {/* quiet white-sheet tooltip */}
      {hovered && (
        <div
          className="pointer-events-none absolute z-10 whitespace-nowrap rounded-[8px] border border-hairline bg-white px-3 py-1.5 shadow-subtle"
          style={{
            left: Math.max(0, Math.min(x(hover!) - 40, w - 110)),
            top: Math.max(0, y(hovered.value) - 54),
          }}
        >
          <p className="text-micro text-slate-muted">{hovered.label}</p>
          <p className="text-caption tabular-nums text-cohere-ink">
            {formatValue(hovered.value)}
          </p>
        </div>
      )}
    </div>
  );
}
