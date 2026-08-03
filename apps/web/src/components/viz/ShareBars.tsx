"use client";

import { useEffect, useState } from "react";
import { scaleLinear } from "d3";

export interface ShareBarItem {
  label: string;
  value: number;
}

/**
 * ShareBars — a compact, direct-labeled horizontal breakdown.
 *
 * Each row is a label, a thin accent bar scaled to the max value, and the
 * count. Single accent family, hairline row dividers, one scale-in entrance.
 */
export function ShareBars({
  items,
  emptyLabel = "No activity yet.",
  className,
}: {
  items: ShareBarItem[];
  emptyLabel?: string;
  className?: string;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!items || items.length === 0) {
    return (
      <div className={className}>
        <div className="border-t border-hairline pt-3 text-caption text-slate-muted">
          {emptyLabel}
        </div>
      </div>
    );
  }

  const x = scaleLinear()
    .domain([0, Math.max(1, ...items.map((i) => i.value))])
    .range([0, 100]);

  return (
    <ul className={`divide-y divide-hairline ${className ?? ""}`}>
      {items.map((it) => (
        <li key={it.label} className="grid grid-cols-[1fr_auto] items-center gap-4 py-2.5">
          <div className="min-w-0">
            <div className="truncate text-body text-cohere-ink">{it.label}</div>
            <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-stone/70">
              <div
                className="h-full origin-left rounded-full bg-studio-maroon/70 transition-transform duration-[400ms] ease-out"
                style={{
                  width: `${it.value > 0 ? Math.max(1, x(it.value)) : 0}%`,
                  transform: mounted ? "scaleX(1)" : "scaleX(0)",
                }}
              />
            </div>
          </div>
          <span className="text-caption tabular-nums text-slate">
            {it.value.toLocaleString()}
          </span>
        </li>
      ))}
    </ul>
  );
}
