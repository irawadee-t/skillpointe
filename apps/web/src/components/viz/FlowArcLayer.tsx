"use client";

/**
 * FlowArcLayer — great-arc connection lines for the Applications map view.
 *
 * Each arc runs applicant city -> job city. Width and opacity encode volume,
 * a single accent color per the design contract. Arcs draw in once with an
 * animated dash (origin -> destination, which doubles as a direction cue),
 * then hold still. Same-city flows render as a ring around the city instead
 * of a zero-length arc.
 *
 * Rendered inside UsMapFrame's ZoomableGroup: geometry is computed in
 * projected map space, and all screen-size values are divided by `k` so
 * arcs keep constant visual weight while zooming.
 */

import type { MouseEvent as ReactMouseEvent } from "react";
import type { ApplicationFlow } from "@/lib/api/admin";
import type { MapLayerContext } from "./UsMapFrame";

const ACCENT = "#9d2235";

interface Props extends MapLayerContext {
  flows: ApplicationFlow[];
  onHover: (flow: ApplicationFlow | null, event?: ReactMouseEvent) => void;
}

function strokeWidthFor(count: number) {
  return Math.min(4, 1 + 0.75 * Math.sqrt(count));
}

function opacityFor(count: number) {
  return Math.min(0.85, 0.45 + 0.08 * count);
}

export function FlowArcLayer({ flows, projection, k, onHover }: Props) {
  const arcs = flows
    .map((flow, i) => {
      const p1 = projection([flow.from.lng, flow.from.lat]);
      const p2 = projection([flow.to.lng, flow.to.lat]);
      if (!p1 || !p2) return null;
      return { flow, p1, p2, i };
    })
    .filter((a): a is NonNullable<typeof a> => a !== null);

  return (
    <g>
      {/* One-time draw-in. pathLength is normalized to 1 on every arc so a
          single keyframe animates all of them regardless of length. */}
      <style>{`
        @keyframes flow-arc-draw {
          from { stroke-dashoffset: 1; }
          to { stroke-dashoffset: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .flow-arc { animation: none !important; stroke-dashoffset: 0 !important; }
        }
      `}</style>

      {arcs.map(({ flow, p1, p2, i }) => {
        const [x1, y1] = p1;
        const [x2, y2] = p2;
        const dist = Math.hypot(x2 - x1, y2 - y1);
        const key = `${flow.from.city}-${flow.from.state}->${flow.to.city}-${flow.to.state}`;
        const sw = strokeWidthFor(flow.count) / k;
        const opacity = opacityFor(flow.count);

        // Same city (or effectively so): a quiet ring instead of an arc.
        if (dist < 2) {
          const r = 9 / k;
          return (
            <g key={key}>
              <circle
                className="flow-arc"
                cx={x1}
                cy={y1}
                r={r}
                fill="none"
                stroke={ACCENT}
                strokeWidth={sw}
                opacity={opacity}
                pathLength={1}
                strokeDasharray={1}
                style={{ animation: `flow-arc-draw 700ms ease-out ${i * 80}ms both` }}
              />
              <circle
                cx={x1}
                cy={y1}
                r={r + 4 / k}
                fill="transparent"
                style={{ cursor: "default" }}
                onMouseEnter={(e) => onHover(flow, e)}
                onMouseMove={(e) => onHover(flow, e)}
                onMouseLeave={() => onHover(null)}
              />
            </g>
          );
        }

        // Quadratic arc bowed perpendicular to the chord.
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const nx = -(y2 - y1) / dist;
        const ny = (x2 - x1) / dist;
        const bend = dist * 0.18;
        const d = `M ${x1} ${y1} Q ${mx + nx * bend} ${my + ny * bend} ${x2} ${y2}`;

        return (
          <g key={key}>
            <path
              className="flow-arc"
              d={d}
              fill="none"
              stroke={ACCENT}
              strokeWidth={sw}
              strokeLinecap="round"
              opacity={opacity}
              pathLength={1}
              strokeDasharray={1}
              style={{ animation: `flow-arc-draw 700ms ease-out ${i * 80}ms both` }}
            />
            {/* Endpoints: open ring = origin (workers), filled dot = destination (jobs). */}
            <circle cx={x1} cy={y1} r={3.5 / k} fill="#ffffff" stroke={ACCENT} strokeWidth={1.25 / k} opacity={opacity} />
            <circle cx={x2} cy={y2} r={3 / k} fill={ACCENT} opacity={opacity} />
            {/* Invisible wide hit area for hover. */}
            <path
              d={d}
              fill="none"
              stroke="transparent"
              strokeWidth={12 / k}
              style={{ cursor: "default" }}
              onMouseEnter={(e) => onHover(flow, e)}
              onMouseMove={(e) => onHover(flow, e)}
              onMouseLeave={() => onHover(null)}
            />
          </g>
        );
      })}
    </g>
  );
}
