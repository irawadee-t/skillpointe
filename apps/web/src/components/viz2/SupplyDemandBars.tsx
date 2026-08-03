"use client";

/**
 * SupplyDemandBars — diverging horizontal bars: trained workers vs active
 * jobs per trade family, extending from a shared zero spine.
 *
 * Chart choice: the marketplace question is "where does supply outrun demand
 * (and vice versa)?" — a diverging pair per family puts the imbalance itself
 * on the page as visible asymmetry. Sorted by |imbalance| descending because
 * the imbalance IS the story.
 *
 * Contract compliance: two hues that are never red-green (ink for workers,
 * brand maroon for jobs), symmetric zero-based scale, direct labels at both
 * bar ends (no legend), hairline separation only, one ≤400ms entrance,
 * reduced-motion respected, desert rows flagged with the statusTones
 * attention affix.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { statusChipClass } from "@/components/ui/statusTones";
import type { FamilySupplyDemand } from "./marketData";

const WORKER_BAR = "#17171c"; // ink
const JOB_BAR = "#9d2235"; // brand maroon — ink vs maroon, never red-green

interface Props {
  families: FamilySupplyDemand[];
  /** Cross-filter in: dim every row except this family. */
  highlightCode?: string | null;
  /** Cross-filter out: fires with the hovered family code, null on leave. */
  onHoverFamily?: (code: string | null) => void;
  /** Small caption naming the slice, e.g. "Pittsburgh, PA" when filtered. */
  contextLabel?: string | null;
  /** Rows beyond this collapse behind a "Show all" affordance. */
  maxRows?: number;
  /** Hide the hover city tooltip (companion-panel mode). */
  showCityTooltip?: boolean;
  className?: string;
}

export function SupplyDemandBars({
  families,
  highlightCode = null,
  onHoverFamily,
  contextLabel = null,
  maxRows = 12,
  showCityTooltip = true,
  className,
}: Props) {
  const [mounted, setMounted] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const reducedMotion = useRef(false);

  useEffect(() => {
    reducedMotion.current = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    // One entrance, then still. With reduced motion, land in the final state.
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Sorted by absolute imbalance descending — server already sorts, but the
  // component must not depend on caller ordering to tell the truth.
  const rows = useMemo(
    () =>
      [...families].sort(
        (a, b) =>
          Math.abs(b.workers - b.jobs) - Math.abs(a.workers - a.jobs) ||
          b.workers + b.jobs - (a.workers + a.jobs),
      ),
    [families],
  );
  const visible = expanded ? rows : rows.slice(0, maxRows);

  // Symmetric scale: the same max on both sides so left/right lengths are
  // honestly comparable. Axis starts at zero in both directions by design.
  const max = Math.max(1, ...rows.flatMap((f) => [f.workers, f.jobs]));
  const x = scaleLinear().domain([0, max]).range([0, 100]);

  // The worst desert: most workers stranded with zero jobs (or the reverse).
  const worstDesert = useMemo(() => {
    const deserts = rows.filter((f) => f.jobs === 0 || f.workers === 0);
    if (deserts.length === 0) return null;
    return deserts.reduce((a, b) =>
      Math.max(b.workers, b.jobs) > Math.max(a.workers, a.jobs) ? b : a,
    );
  }, [rows]);

  if (rows.length === 0) {
    return (
      <div className={className}>
        <p className="border-t border-hairline pt-3 text-caption text-slate-muted">
          No supply or demand recorded yet.
        </p>
      </div>
    );
  }

  const barTransition = "transform 400ms cubic-bezier(0.16,1,0.3,1)";

  return (
    <figure
      className={className}
      role="img"
      aria-label={`Workers versus open jobs by trade family, sorted by imbalance. ${rows
        .slice(0, 5)
        .map((f) => `${f.name}: ${f.workers} workers, ${f.jobs} jobs`)
        .join(". ")}.`}
    >
      {contextLabel ? (
        <figcaption className="mb-2 text-caption text-slate">
          Showing <span className="font-medium text-cohere-ink">{contextLabel}</span>
        </figcaption>
      ) : null}

      {/* Column headers double as the only "legend" — direct, positional. */}
      <div className="grid grid-cols-2 gap-x-3 border-b border-hairline pb-1.5 sm:grid-cols-[minmax(96px,150px)_1fr_1fr]">
        <span aria-hidden className="hidden text-micro text-slate-muted sm:block">
          Trade
        </span>
        <span aria-hidden className="text-right text-micro text-slate-muted">
          Workers ←
        </span>
        <span aria-hidden className="text-micro text-slate-muted">
          → Open jobs
        </span>
      </div>

      <ul className="divide-y divide-hairline">
        {visible.map((f) => {
          const dimmed =
            (highlightCode != null && highlightCode !== f.code) ||
            (hovered != null && hovered !== f.code);
          const isDesert = f.jobs === 0 || f.workers === 0;
          return (
            <li
              key={f.code}
              className="relative transition-opacity duration-200"
              style={{ opacity: dimmed ? 0.35 : 1 }}
              onMouseEnter={() => {
                setHovered(f.code);
                onHoverFamily?.(f.code);
              }}
              onMouseLeave={() => {
                setHovered(null);
                onHoverFamily?.(null);
              }}
            >
              {/* Stacks on phones: name on its own line, the diverging pair
                  below at full width; from `sm` up, one three-column row. */}
              <div className="grid grid-cols-2 items-center gap-x-3 py-2 sm:grid-cols-[minmax(96px,150px)_1fr_1fr]">
                <span
                  className="col-span-2 truncate pb-1 text-label text-cohere-ink sm:col-span-1 sm:pb-0"
                  title={f.name}
                >
                  {f.name}
                </span>

                {/* Workers — extends LEFT from the shared spine */}
                <div className="flex items-center justify-end gap-1.5">
                  {f.workers === 0 ? (
                    <span className={statusChipClass("attention")}>0 workers</span>
                  ) : (
                    <span className="text-caption tabular-nums text-slate">
                      {f.workers.toLocaleString()}
                    </span>
                  )}
                  <div
                    aria-hidden
                    className="h-[10px] origin-right rounded-l-full"
                    style={{
                      width: `${f.workers > 0 ? Math.max(0.8, x(f.workers)) : 0}%`,
                      backgroundColor: WORKER_BAR,
                      transform:
                        mounted || reducedMotion.current ? "scaleX(1)" : "scaleX(0)",
                      transition: reducedMotion.current ? "none" : barTransition,
                    }}
                  />
                </div>

                {/* Jobs — extends RIGHT from the shared spine */}
                <div className="flex items-center gap-1.5 border-l border-slate-muted/50 pl-px">
                  <div
                    aria-hidden
                    className="h-[10px] origin-left rounded-r-full"
                    style={{
                      width: `${f.jobs > 0 ? Math.max(0.8, x(f.jobs)) : 0}%`,
                      backgroundColor: JOB_BAR,
                      transform:
                        mounted || reducedMotion.current ? "scaleX(1)" : "scaleX(0)",
                      transition: reducedMotion.current ? "none" : barTransition,
                    }}
                  />
                  {f.jobs === 0 ? (
                    <span className={statusChipClass("attention")}>0 jobs</span>
                  ) : (
                    <span className="text-caption tabular-nums text-slate">
                      {f.jobs.toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Annotation on the worst desert — computed, not canned. */}
              {worstDesert?.code === f.code && isDesert ? (
                <p className="pb-2 text-caption text-studio-maroon sm:pl-[calc(min(150px,25%)+12px)]">
                  {f.jobs === 0
                    ? `${f.workers} trained ${f.name.toLowerCase()} workers, zero active jobs. The largest untapped pool on the platform.`
                    : `${f.jobs} open ${f.name.toLowerCase()} jobs, zero trained workers. The platform's biggest unmet demand.`}
                </p>
              ) : null}

              {/* Hover detail — quiet white sheet with the top cities. */}
              {showCityTooltip &&
              hovered === f.code &&
              (f.worker_cities.length > 0 || f.job_cities.length > 0) ? (
                <div className="pointer-events-none absolute left-[25%] top-full z-10 mt-1 w-64 rounded-[10px] border border-hairline bg-white p-3 shadow-float">
                  <p className="text-caption font-medium text-cohere-ink">{f.name}</p>
                  <div className="mt-1.5 grid grid-cols-2 gap-x-3">
                    <div>
                      <p className="text-micro text-slate-muted">Workers</p>
                      {f.worker_cities.length === 0 ? (
                        <p className="text-micro text-slate-muted">—</p>
                      ) : (
                        f.worker_cities.map((c) => (
                          <p
                            key={`${c.city}-${c.state}`}
                            className="text-micro tabular-nums text-slate"
                          >
                            {c.city}, {c.state} · {c.count}
                          </p>
                        ))
                      )}
                    </div>
                    <div>
                      <p className="text-micro text-slate-muted">Jobs</p>
                      {f.job_cities.length === 0 ? (
                        <p className="text-micro text-slate-muted">—</p>
                      ) : (
                        f.job_cities.map((c) => (
                          <p
                            key={`${c.city}-${c.state}`}
                            className="text-micro tabular-nums text-slate"
                          >
                            {c.city}, {c.state} · {c.count}
                          </p>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {rows.length > maxRows ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-slate transition-colors duration-200 hover:text-cohere-ink"
        >
          {expanded ? "Show fewer" : `Show all ${rows.length} trades`}
        </button>
      ) : null}
    </figure>
  );
}
