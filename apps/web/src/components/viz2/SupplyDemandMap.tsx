"use client";

/**
 * SupplyDemandMap — the two-sided geographic view: ONE map where every metro
 * cluster carries a paired encoding (size = combined volume, hue = which side
 * is starved), plus a companion SupplyDemandBars panel cross-filtered by
 * hover in both directions.
 *
 * Chart choice: supply and demand live in different places — the question is
 * WHERE the market is lopsided, so the imbalance is encoded on geography
 * itself instead of two maps the reader must mentally subtract.
 *
 * Encoding (colorblind-safe by construction): a two-hue diverging scale from
 * worker-heavy ink through a neutral mid to job-heavy brand maroon — never
 * red-green — with mark size as a redundant channel and the top-5 clusters
 * direct-labeled. The caption states the encoding in words (no swatch
 * legend to cross-match).
 *
 * Reuses the cleanly-exported UsMapFrame shell (zoom/pan/projection) from
 * components/viz — reference only, not modified.
 */

import { useMemo, useState } from "react";
import { scaleLinear, scaleSqrt } from "d3-scale";
import { UsMapFrame } from "@/components/viz";
import { SupplyDemandBars } from "./SupplyDemandBars";
import type { FamilySupplyDemand, GeoCluster } from "./marketData";

const INK = "#17171c"; // worker-heavy
const NEUTRAL_MID = "#b7b3ae"; // balanced
const MAROON = "#9d2235"; // job-heavy

interface Props {
  clusters: GeoCluster[];
  /** National families for the companion panel's resting state. */
  families: FamilySupplyDemand[];
  className?: string;
}

export function SupplyDemandMap({ clusters, families, className }: Props) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [hoveredFamily, setHoveredFamily] = useState<string | null>(null);

  const maxVolume = useMemo(
    () => Math.max(1, ...clusters.map((c) => c.workers + c.jobs)),
    [clusters],
  );
  // Area ∝ volume (sqrt radius) — proportional representation.
  const r = useMemo(
    () => scaleSqrt().domain([0, maxVolume]).range([0, 20]),
    [maxVolume],
  );
  // Diverging hue by job share: 0 → ink (all workers), 0.5 → neutral,
  // 1 → maroon (all jobs).
  const hue = useMemo(
    () =>
      scaleLinear<string>()
        .domain([0, 0.5, 1])
        .range([INK, NEUTRAL_MID, MAROON]),
    [],
  );

  const top5 = useMemo(() => new Set(clusters.slice(0, 5).map((c) => c.key)), [clusters]);
  const hoveredCluster = clusters.find((c) => c.key === hoveredKey) ?? null;

  // Companion panel: national mix at rest, the hovered cluster's mix on hover.
  const panelFamilies: FamilySupplyDemand[] = useMemo(() => {
    if (!hoveredCluster) return families;
    return hoveredCluster.families.map((f) => ({
      ...f,
      worker_cities: [],
      job_cities: [],
    }));
  }, [hoveredCluster, families]);

  // Bar-hover → map: emphasize clusters that contain the hovered family.
  const familyKeys = useMemo(() => {
    if (!hoveredFamily) return null;
    return new Set(
      clusters
        .filter((c) => c.families.some((f) => f.code === hoveredFamily))
        .map((c) => c.key),
    );
  }, [hoveredFamily, clusters]);

  return (
    <div className={className}>
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <figure
          className="relative"
          role="img"
          aria-label={`Map of ${clusters.length} metro clusters. Mark size is combined workers plus jobs; ink means worker-heavy, maroon means job-heavy. Largest: ${clusters
            .slice(0, 3)
            .map((c) => `${c.label} with ${c.workers} workers and ${c.jobs} jobs`)
            .join("; ")}.`}
        >
          <div className="h-[280px] w-full sm:h-[420px]">
            <UsMapFrame>
              {({ k, projection }) => (
                <g>
                  {[...clusters]
                    // Small marks paint last so big ones never swallow them.
                    .sort((a, b) => b.workers + b.jobs - (a.workers + a.jobs))
                    .map((c) => {
                      const pos = projection([c.lng, c.lat]);
                      if (!pos) return null;
                      const volume = c.workers + c.jobs;
                      const share = volume > 0 ? c.jobs / volume : 0.5;
                      const dimmed =
                        (hoveredKey !== null && hoveredKey !== c.key) ||
                        (familyKeys !== null && !familyKeys.has(c.key));
                      const labeled = top5.has(c.key);
                      return (
                        <g
                          key={c.key}
                          transform={`translate(${pos[0]}, ${pos[1]})`}
                          onMouseEnter={() => setHoveredKey(c.key)}
                          onMouseLeave={() => setHoveredKey(null)}
                          style={{ cursor: "default" }}
                        >
                          <circle
                            r={Math.max(2.5, r(volume)) / k}
                            fill={hue(share)}
                            fillOpacity={dimmed ? 0.18 : 0.78}
                            stroke="#ffffff"
                            strokeWidth={1 / k}
                            style={{ transition: "fill-opacity 200ms" }}
                          />
                          {labeled ? (
                            <text
                              y={-(Math.max(2.5, r(volume)) / k) - 4 / k}
                              textAnchor="middle"
                              fontSize={11 / k}
                              fontWeight={500}
                              fill="#33322f"
                              stroke="#fcfcfb"
                              strokeWidth={3 / k}
                              paintOrder="stroke"
                              opacity={dimmed ? 0.3 : 1}
                              style={{ pointerEvents: "none" }}
                            >
                              {c.label}
                            </text>
                          ) : null}
                        </g>
                      );
                    })}
                </g>
              )}
            </UsMapFrame>
          </div>

          {/* The encoding, stated in words — no swatch-matching legend. */}
          <figcaption className="mt-2 text-micro text-slate-muted">
            Mark size = workers + jobs in the metro.{" "}
            <span className="font-medium text-ink">Ink</span> = worker-heavy ·{" "}
            <span className="font-medium text-studio-maroon">Maroon</span> ={" "}
            job-heavy. Hover a metro to see its trade mix.
          </figcaption>

          {hoveredCluster ? (
            <div className="pointer-events-none absolute z-10 -mt-24 ml-4 rounded-[10px] border border-hairline bg-white px-3 py-2 shadow-float">
              <p className="text-caption font-medium text-cohere-ink">
                {hoveredCluster.label}
              </p>
              <p className="text-micro tabular-nums text-slate">
                {hoveredCluster.workers.toLocaleString()} workers ·{" "}
                {hoveredCluster.jobs.toLocaleString()} jobs
              </p>
            </div>
          ) : null}
        </figure>

        <div className="min-w-0">
          <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
            {hoveredCluster ? "Trade mix in view" : "National trade balance"}
          </h3>
          <SupplyDemandBars
            className="mt-3"
            families={panelFamilies}
            contextLabel={hoveredCluster?.label ?? null}
            maxRows={8}
            showCityTooltip={false}
            highlightCode={hoveredFamily}
            onHoverFamily={setHoveredFamily}
          />
        </div>
      </div>
    </div>
  );
}
