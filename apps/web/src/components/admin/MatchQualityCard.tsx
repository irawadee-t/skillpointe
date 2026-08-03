"use client";

/**
 * MatchQualityCard — "Match quality distribution" sheet for the admin
 * engagement page: the viz2 ScoreHistogram over ALL base-fit scores with the
 * active config's band thresholds and the server-computed annotation.
 *
 * The Canvas-heavy histogram is dynamically imported (ssr:false) behind a
 * same-height skeleton so it never weighs on the server bundle and the sheet
 * doesn't shift when it arrives.
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import {
  fetchScoreDistribution,
  type ScoreDistributionResponse,
} from "@/components/viz2/marketData";

const ScoreHistogram = dynamic(
  () =>
    import("@/components/viz2/ScoreHistogram").then((m) => m.ScoreHistogram),
  { ssr: false, loading: () => <HistogramSkeleton /> },
);

export function MatchQualityCard({ token }: { token: string }) {
  const [data, setData] = useState<ScoreDistributionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    fetchScoreDistribution(token)
      .then(setData)
      .catch(() =>
        setError("Could not load the score distribution. The API may be unreachable."),
      );
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="rounded-[10px] border border-hairline bg-white p-5">
      <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
        Match quality distribution
      </h3>
      <p className="mb-4 text-caption text-slate-muted">
        Every scored applicant–job pair by base fit, against the active config&apos;s bands
      </p>

      {error ? (
        <div>
          <p className="text-body text-cohere-ink">{error}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 rounded-full border border-hairline bg-white px-4 py-1.5 text-caption text-cohere-ink transition-colors hover:border-cohere-ink"
          >
            Try again
          </button>
        </div>
      ) : data === null ? (
        <HistogramSkeleton />
      ) : data.total === 0 ? (
        <p className="border-t border-hairline pt-3 text-caption text-slate-muted">
          No scored pairs yet. The distribution appears after the first match
          recompute.
        </p>
      ) : (
        <ScoreHistogram data={data} />
      )}
    </section>
  );
}

/** Same footprint as the loaded chart (annotation row + 240px canvas). */
function HistogramSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading score distribution">
      <div className="h-3.5 w-2/3 rounded-full bg-stone" />
      <div className="mt-2 flex h-[240px] items-end gap-1">
        {Array.from({ length: 24 }).map((_, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-[2px] bg-stone"
            style={{ height: `${12 + 80 * Math.exp(-((i - 7) ** 2) / 18)}%` }}
          />
        ))}
      </div>
    </div>
  );
}
