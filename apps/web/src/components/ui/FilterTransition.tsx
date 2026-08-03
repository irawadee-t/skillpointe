"use client";

import { useRef } from "react";
import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

/**
 * Smooth content swap for filterable, URL-driven lists: when the query string
 * changes (a filter or search applied), the fresh results fade in over ~150ms
 * instead of flashing. Opacity only — zero layout shift, and the very first
 * render never animates (no arrival flicker). Collapses to an instant swap
 * under prefers-reduced-motion via the `motion-reduce` variant.
 *
 * Wrap the results region ONLY (list/table + count line) — not the filter bar,
 * which must never re-animate while the user is typing in it.
 */
export function FilterTransition({
  children,
  params,
  className,
}: {
  children: React.ReactNode;
  /** Query params that constitute "the filters" — defaults to all of them. */
  params?: string[];
  className?: string;
}) {
  const searchParams = useSearchParams();
  const key = params
    ? params.map((p) => `${p}=${searchParams.get(p) ?? ""}`).join("&")
    : searchParams.toString();

  const firstKey = useRef(key);
  const navigated = useRef(false);
  if (key !== firstKey.current) navigated.current = true;

  return (
    <div
      key={key}
      className={cn(
        navigated.current &&
          "animate-[fade-in_150ms_ease_both] motion-reduce:animate-none",
        className,
      )}
    >
      {children}
    </div>
  );
}
