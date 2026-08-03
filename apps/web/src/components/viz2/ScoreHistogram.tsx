"use client";

/**
 * ScoreHistogram — the match-quality distribution: all ~132k base_fit scores,
 * server-bucketed, rendered on Canvas (the >1000-points rule; buckets stand
 * in for the population, and Canvas keeps redraw + hover free of DOM churn).
 *
 * Chart choice: the question is "is the market short on quality or short on
 * supply?" — a histogram with the ACTIVE config's band thresholds drawn as
 * labeled reference lines answers it in one glance, and the server-computed
 * annotation says it in words.
 *
 * Contract compliance: single-hue lightness ramp toward the brand maroon
 * (colorblind-safe — no red-green pairing), hairline baseline with 3 tick
 * labels, direct-labeled peak, no gridline cage, one ≤400ms entrance
 * (reduced-motion aware), devicePixelRatio-crisp, aria description +
 * data-table fallback. Counts are linear; the reference lines + annotation
 * carry the story even when high-score bands are visually small.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { useMeasuredWidth } from "@/components/viz/useMeasuredWidth";
import type { ScoreDistributionResponse } from "./marketData";

const HEIGHT = 240;
const MARGIN = { top: 34, right: 8, bottom: 22, left: 8 };

// Single-hue lightness ramp, low → high score band (never red-green).
const BAND_FILLS = {
  belowModerate: "#c9c5bd", // low fit — light neutral (context, de-emphasized)
  moderate: "#a89ba0", // moderate band — desaturated mid
  good: "#b8586b", // good band — maroon, lightened
  strong: "#9d2235", // strong band — full brand maroon
} as const;

const THRESHOLD_LABELS: Record<string, string> = {
  moderate_fit_min: "Moderate",
  good_fit_min: "Good fit",
  strong_fit_min: "Strong fit",
};

interface Props {
  data: ScoreDistributionResponse;
  className?: string;
}

function bandFill(x0: number, t: Record<string, number>): string {
  if (x0 >= (t.strong_fit_min ?? 80)) return BAND_FILLS.strong;
  if (x0 >= (t.good_fit_min ?? 60)) return BAND_FILLS.good;
  if (x0 >= (t.moderate_fit_min ?? 40)) return BAND_FILLS.moderate;
  return BAND_FILLS.belowModerate;
}

export function ScoreHistogram({ data, className }: Props) {
  const [ref, width] = useMeasuredWidth();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const progressRef = useRef(0); // entrance progress 0→1
  const rafRef = useRef<number>(0);

  const { buckets, thresholds, total, annotation } = data;
  const maxCount = useMemo(
    () => Math.max(1, ...buckets.map((b) => b.count)),
    [buckets],
  );
  const peak = useMemo(
    () =>
      buckets.reduce(
        (best, b, i) => (b.count > buckets[best].count ? i : best),
        0,
      ),
    [buckets],
  );

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(HEIGHT * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${HEIGHT}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, HEIGHT);

    const innerW = width - MARGIN.left - MARGIN.right;
    const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;
    const x = scaleLinear().domain([0, 100]).range([MARGIN.left, MARGIN.left + innerW]);
    const y = scaleLinear().domain([0, maxCount]).range([0, innerH]);
    const baseline = MARGIN.top + innerH;
    const p = progressRef.current;

    // Bars
    for (let i = 0; i < buckets.length; i++) {
      const b = buckets[i];
      if (b.count === 0) continue;
      const h = Math.max(1, y(Math.max(1, b.count)) * p);
      const bx = x(b.x0);
      const bw = Math.max(1, x(b.x1) - x(b.x0) - 1);
      ctx.fillStyle = bandFill(b.x0, thresholds);
      ctx.globalAlpha = hoverIdx === null || hoverIdx === i ? 1 : 0.45;
      ctx.fillRect(bx, baseline - h, bw, h);
    }
    ctx.globalAlpha = 1;

    // Hairline baseline (the one axis line)
    ctx.strokeStyle = "#e7e5e2";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(MARGIN.left, baseline + 0.5);
    ctx.lineTo(MARGIN.left + innerW, baseline + 0.5);
    ctx.stroke();

    // 3 tick labels, no gridlines
    ctx.fillStyle = "#5c5a55";
    ctx.font =
      "11px var(--font-body, Inter), system-ui, -apple-system, sans-serif";
    ctx.textBaseline = "top";
    for (const t of [0, 50, 100]) {
      ctx.textAlign = t === 0 ? "left" : t === 100 ? "right" : "center";
      ctx.fillText(String(t), x(t), baseline + 6);
    }

    // Labeled threshold reference lines from the ACTIVE config
    for (const [key, value] of Object.entries(thresholds)) {
      const label = THRESHOLD_LABELS[key];
      if (!label || value == null) continue;
      const tx = x(value);
      ctx.strokeStyle = "#9c9892";
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(tx + 0.5, MARGIN.top - 4);
      ctx.lineTo(tx + 0.5, baseline);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#33322f";
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      ctx.fillText(`${label} ${Math.round(value)}`, tx + 4, MARGIN.top - 8);
    }

    // Direct-label the peak
    const pb = buckets[peak];
    if (pb && pb.count > 0) {
      const px = (x(pb.x0) + x(pb.x1)) / 2;
      const ph = Math.max(1, y(Math.max(1, pb.count)) * p);
      ctx.textAlign = "center";
      ctx.textBaseline = "alphabetic";
      ctx.font =
        "600 11px var(--font-body, Inter), system-ui, -apple-system, sans-serif";
      const labelX = Math.min(
        Math.max(px, MARGIN.left + 70),
        width - MARGIN.right - 70,
      );
      // Keep the peak label clear of the threshold-label row; halo it so it
      // stays readable if it lands over a bar or a reference line.
      const labelY = Math.max(baseline - ph - 6, MARGIN.top + 16);
      const text = `${pb.count.toLocaleString()} pairs at ${Math.round(pb.x0)}–${Math.round(pb.x1)}`;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 3;
      ctx.strokeText(text, labelX, labelY);
      ctx.fillStyle = "#17171c";
      ctx.fillText(text, labelX, labelY);
    }
  }, [width, buckets, thresholds, maxCount, peak, hoverIdx]);

  // Latest draw closure, so the entrance loop never paints with a stale width.
  const drawRef = useRef(draw);
  drawRef.current = draw;

  // One entrance (≤400ms ease-out) once the container has real width, then
  // still. Reduced motion lands directly in the final state.
  const startedRef = useRef(false);
  useEffect(() => {
    if (width === 0 || startedRef.current) return;
    startedRef.current = true;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      progressRef.current = 1;
      drawRef.current();
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 400);
      progressRef.current = 1 - Math.pow(1 - t, 3); // ease-out cubic
      drawRef.current();
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [width]);

  // Redraws after the entrance (resize, toggle, hover) render the final state.
  useEffect(() => {
    if (progressRef.current === 1) draw();
  }, [draw]);

  const handleMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const innerW = width - MARGIN.left - MARGIN.right;
    const idx = Math.floor(((mx - MARGIN.left) / innerW) * buckets.length);
    setHoverIdx(idx >= 0 && idx < buckets.length ? idx : null);
  };

  const hovered = hoverIdx !== null ? buckets[hoverIdx] : null;

  return (
    <figure className={className}>
      <p className="max-w-prose text-caption text-slate">{annotation}</p>

      <div ref={ref} className="relative mt-2">
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={`Histogram of ${total.toLocaleString()} match scores from 0 to 100. ${annotation}`}
          onMouseMove={handleMove}
          onMouseLeave={() => setHoverIdx(null)}
          className="block w-full"
        />
        {hovered && hovered.count > 0 ? (
          <div className="pointer-events-none absolute top-0 right-0 rounded-[10px] border border-hairline bg-white px-3 py-2 shadow-float">
            <p className="text-micro text-slate-muted">
              Score {Math.round(hovered.x0)}–{Math.round(hovered.x1)}
            </p>
            <p className="text-caption tabular-nums text-cohere-ink">
              {hovered.count.toLocaleString()} pairs ·{" "}
              {((hovered.count / Math.max(1, total)) * 100).toFixed(1)}%
            </p>
          </div>
        ) : null}
      </div>

      {/* Screen-reader / no-canvas fallback: the same data as a table. */}
      <details className="mt-2">
        <summary className="cursor-pointer text-micro text-slate-muted">
          View as data table
        </summary>
        <div className="mt-2 max-h-64 overflow-y-auto">
          <table className="w-full text-caption">
            <thead>
              <tr className="border-b border-hairline text-left text-micro text-slate-muted">
                <th className="py-1 pr-3 font-medium">Score range</th>
                <th className="py-1 text-right font-medium">Pairs</th>
              </tr>
            </thead>
            <tbody>
              {buckets
                .filter((b) => b.count > 0)
                .map((b) => (
                  <tr key={b.x0} className="border-b border-hairline">
                    <td className="py-1 pr-3 tabular-nums text-slate">
                      {Math.round(b.x0)}–{Math.round(b.x1)}
                    </td>
                    <td className="py-1 text-right tabular-nums text-slate">
                      {b.count.toLocaleString()}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
