"use client";

import { useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { SlidersHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Progressive-disclosure filter bar shared by the heavy list surfaces
 * (verified workers, admin jobs console, admin employers directory).
 *
 * `primary` renders the 3–4 highest-value controls, always visible.
 * `children` are the long-tail controls, hidden behind a "More filters"
 * ghost pill. The pill shows an active-count badge ("More filters · 3")
 * whenever hidden filters are applied, and hidden-filter state ALWAYS stays
 * visible via the removable-chip row the caller renders below — state is
 * never invisible. All fields stay URL-synced exactly as before; this
 * component only owns show/hide and the panel-scoped "Clear all".
 */
export function FilterBar({
  primary,
  moreParams,
  children,
  footer,
  className,
}: {
  /** Always-visible controls (the 3–4 highest-value filters + sort). */
  primary: React.ReactNode;
  /** Query params owned by the hidden panel — drives the badge + Clear all. */
  moreParams: string[];
  /** Hidden controls, revealed by the "More filters" pill. */
  children?: React.ReactNode;
  /** Always-visible row under everything — the active-filter chips. */
  footer?: React.ReactNode;
  className?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  const [open, setOpen] = useState(false);

  // Count applied hidden filters — comma-separated multi params count each value.
  const activeCount = useMemo(() => {
    let n = 0;
    for (const p of moreParams) {
      const raw = searchParams.get(p);
      if (raw) n += raw.split(",").filter(Boolean).length;
    }
    return n;
  }, [searchParams, moreParams]);

  const clearMore = () => {
    const params = new URLSearchParams(searchParams.toString());
    for (const p of moreParams) params.delete(p);
    params.delete("page");
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  return (
    <div className={cn("rounded-[10px] border border-hairline bg-white p-4", className)}>
      <div className="flex flex-wrap items-end gap-3">
        {primary}
        {children && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className={cn(
              "btn-pill-outline inline-flex shrink-0 items-center gap-1.5",
              (open || activeCount > 0) && "border-ink text-cohere-ink",
            )}
          >
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
            More filters
            {/* Count slot is always rendered (invisible at 0) so the pill's
                width never changes when a hidden filter is applied — the
                primary row must not shift. */}
            <span
              className={cn(
                "tabular-nums transition-opacity duration-150 motion-reduce:transition-none",
                activeCount === 0 && "opacity-0",
              )}
              aria-hidden={activeCount === 0}
            >
              · {activeCount || 0}
            </span>
          </button>
        )}
      </div>

      {/* The hidden panel stays mounted and animates height+opacity (~200ms
          ease-out); `inert` keeps its controls out of the tab order while
          collapsed. Reduced motion collapses instantly. */}
      {children && (
        <div
          className={cn(
            "grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none",
            open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
          )}
          aria-hidden={!open}
          inert={!open}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="mt-3 border-t border-hairline pt-4">
              <div className="space-y-4">{children}</div>
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={clearMore}
                  disabled={activeCount === 0}
                  className="text-caption text-slate transition-colors hover:text-cohere-ink disabled:cursor-default disabled:opacity-40"
                >
                  Clear all
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {footer}
    </div>
  );
}

/**
 * A labeled group inside the FilterBar's hidden panel — small sentence-case
 * label above a wrapping row of controls.
 */
export function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="mb-1.5 block text-caption font-medium text-cohere-ink">{label}</span>
      <div className="flex flex-wrap items-end gap-3">{children}</div>
    </div>
  );
}
