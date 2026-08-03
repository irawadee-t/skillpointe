"use client";

/**
 * WhyThisRanking — collapsed-by-default disclosure on each candidate card
 * that lazily loads GET /viz/matches/{id}/explanation on first open and
 * mounts the viz2 MatchExplanation composite in job context ("where this
 * candidate sits among all candidates scored for the job").
 *
 * The endpoint authorizes employers via job ownership (and admin read-only),
 * so the same card works on both sessions. Fetches once; errors offer retry.
 */

import { useCallback, useState } from "react";
import { ChevronDown } from "lucide-react";

import { MatchExplanation } from "@/components/viz2";
import {
  fetchMatchExplanation,
  type MatchExplanationData,
} from "@/components/viz2/types";

export function WhyThisRanking({
  matchId,
  token,
}: {
  matchId: string;
  token: string;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<MatchExplanationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchMatchExplanation(matchId, token)
      .then(setData)
      .catch((err: unknown) => {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load the ranking explanation.",
        );
      })
      .finally(() => setLoading(false));
  }, [matchId, token]);

  const toggle = () => {
    setOpen((v) => {
      const next = !v;
      if (next && !data && !loading && !error) load();
      return next;
    });
  };

  return (
    <div className="mt-4 border-t border-hairline pt-3">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-caption text-slate-muted transition-colors duration-200 hover:text-cohere-ink"
      >
        Why this ranking
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {open && (
        <div className="mt-4">
          {data ? (
            <MatchExplanation data={data} contextMode="job" />
          ) : error ? (
            <div className="rounded-[10px] border border-hairline bg-white p-4">
              <p className="text-caption text-cohere-ink">{error}</p>
              <button
                type="button"
                onClick={load}
                className="mt-2 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-slate transition-colors duration-200 hover:text-cohere-ink"
              >
                Try again
              </button>
            </div>
          ) : (
            <ExplanationSkeleton />
          )}
        </div>
      )}
    </div>
  );
}

/** Loading skeleton matching the composite's shape: heading line, summary
 *  sentence, then driver rows (label + track bar) — no layout jump on data. */
function ExplanationSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading explanation">
      <div className="h-4 w-36 rounded-full bg-stone" />
      <div className="mt-2 h-3.5 w-3/4 rounded-full bg-stone" />
      <div className="mt-5 space-y-0">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className={`grid grid-cols-[minmax(150px,220px)_1fr] items-center gap-x-5 py-2.5 ${
              i > 0 ? "border-t border-hairline" : ""
            }`}
          >
            <div className="h-3.5 w-28 rounded-full bg-stone" />
            <div className="h-[12px] rounded-[3px] bg-stone" style={{ width: `${70 - i * 10}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}
