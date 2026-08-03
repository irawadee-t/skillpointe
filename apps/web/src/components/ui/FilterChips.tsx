"use client";

import { useEffect, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FilterChipDef } from "./filterDefs";

/**
 * The active-filter row shared by every granular list surface: each applied
 * filter appears as a quiet removable chip, plus one "Clear all" when any is
 * active. URL-synced — removing a chip rewrites the query string (and resets
 * pagination), which re-renders the server list.
 */
export function ActiveFilterChips({
  fields,
  className,
  resetParams = ["page"],
}: {
  fields: FilterChipDef[];
  className?: string;
  resetParams?: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  // Chips fading out: removal navigates inside a transition, so the old row
  // stays mounted long enough for the exit animation to play.
  const [removing, setRemoving] = useState<Set<string>>(new Set());

  const navigate = (params: URLSearchParams) => {
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  const chips: { key: string; text: string; remove: () => void }[] = [];
  for (const f of fields) {
    const raw = searchParams.get(f.param);
    if (!raw) continue;
    const pretty = (v: string) => f.options?.find((o) => o.value === v)?.label ?? v;
    if (f.multi) {
      const values = raw.split(",").filter(Boolean);
      for (const v of values) {
        chips.push({
          key: `${f.param}:${v}`,
          text: `${f.label}: ${pretty(v)}`,
          remove: () => {
            const next = values.filter((x) => x !== v);
            const params = new URLSearchParams(searchParams.toString());
            if (next.length) params.set(f.param, next.join(","));
            else params.delete(f.param);
            navigate(params);
          },
        });
      }
    } else {
      chips.push({
        key: f.param,
        text: `${f.label}: ${pretty(raw)}`,
        remove: () => {
          const params = new URLSearchParams(searchParams.toString());
          params.delete(f.param);
          navigate(params);
        },
      });
    }
  }

  // Once the URL catches up (removed chip is gone), forget it — so re-adding
  // the same filter later renders the chip fresh, not stuck invisible.
  const liveKeys = chips.map((c) => c.key).join("|");
  useEffect(() => {
    setRemoving((prev) => {
      if (prev.size === 0) return prev;
      const live = new Set(liveKeys.split("|"));
      const next = new Set([...prev].filter((k) => live.has(k)));
      return next.size === prev.size ? prev : next;
    });
  }, [liveKeys]);

  const clearAll = () => {
    setRemoving(new Set(chips.map((c) => c.key)));
    const params = new URLSearchParams(searchParams.toString());
    for (const f of fields) params.delete(f.param);
    navigate(params);
  };

  // The row is ALWAYS rendered with a reserved min-height so applying or
  // clearing the first filter never shifts the controls above it — the slot
  // exists from first render (DESIGN_CONTRACT: zero layout jump).
  return (
    <div className={cn("flex min-h-6 flex-wrap items-center gap-1.5", className)}>
      {chips.map((c) => (
        <span
          key={c.key}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-cohere-ink",
            "motion-safe:animate-chip-in transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none",
            removing.has(c.key) && "scale-95 opacity-0",
          )}
        >
          {c.text}
          <button
            type="button"
            onClick={() => {
              setRemoving((prev) => new Set(prev).add(c.key));
              c.remove();
            }}
            aria-label={`Remove filter ${c.text}`}
            className="rounded-full p-0.5 text-slate-muted transition-colors hover:text-cohere-ink"
          >
            <X className="h-3 w-3" strokeWidth={2} />
          </button>
        </span>
      ))}
      {chips.length > 0 && (
        <button
          type="button"
          onClick={clearAll}
          className="ml-1 text-caption text-slate transition-colors hover:text-cohere-ink"
        >
          Clear all
        </button>
      )}
    </div>
  );
}

