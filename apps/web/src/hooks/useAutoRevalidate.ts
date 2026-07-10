"use client";

import { useEffect, useRef } from "react";

type Options = {
  /** Interval in ms between polls. Set 0 to disable interval polling. */
  intervalMs?: number;
  /** Revalidate when the tab regains focus / becomes visible. */
  onFocus?: boolean;
  /** Skip polling while the tab is hidden. */
  pauseWhenHidden?: boolean;
  /** Turn the whole thing off (e.g. if user is in an edit modal). */
  enabled?: boolean;
};

/**
 * SWR-lite auto-revalidation.
 *
 * Runs the given `revalidate` callback on an interval and/or when the tab
 * regains focus. Cleans up on unmount. No caching, no dedup, no retry — just
 * a small hook to keep list pages fresh without pulling in a data-fetching lib.
 *
 * Usage:
 *   const { data, refetch } = useMyQuery();
 *   useAutoRevalidate(refetch, { intervalMs: 30_000 });
 */
export function useAutoRevalidate(
  revalidate: () => void | Promise<unknown>,
  {
    intervalMs = 30_000,
    onFocus = true,
    pauseWhenHidden = true,
    enabled = true,
  }: Options = {},
) {
  const cbRef = useRef(revalidate);
  cbRef.current = revalidate;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      if (pauseWhenHidden && typeof document !== "undefined" && document.hidden) return;
      cbRef.current();
    };

    let timer: ReturnType<typeof setInterval> | null = null;
    if (intervalMs > 0) timer = setInterval(tick, intervalMs);

    const onVisibility = () => {
      if (typeof document !== "undefined" && !document.hidden) cbRef.current();
    };
    if (onFocus && typeof window !== "undefined") {
      window.addEventListener("focus", onVisibility);
      document.addEventListener("visibilitychange", onVisibility);
    }

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      if (onFocus && typeof window !== "undefined") {
        window.removeEventListener("focus", onVisibility);
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, [intervalMs, onFocus, pauseWhenHidden, enabled]);
}
