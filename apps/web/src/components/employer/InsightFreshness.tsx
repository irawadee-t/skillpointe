"use client";

import { useEffect, useState } from "react";

/**
 * Small client-side "As of HH:MM:SS AM/PM" line that updates on mount to
 * reflect when the AI insight was rendered. Kept trivial to avoid extra
 * fetches — the parent server component just re-renders on refresh.
 */
export function InsightFreshness() {
  const [asOf, setAsOf] = useState<string>("");

  useEffect(() => {
    // Minute precision — second-level "freshness" over-promises for numbers
    // that only change on refresh.
    setAsOf(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
  }, []);

  if (!asOf) return null;
  return (
    <p className="mt-1 text-micro text-slate-muted">As of {asOf}</p>
  );
}
