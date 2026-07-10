"use client";

/**
 * Filter bar — GETs the applicants page with query params in the URL.
 * The min-score slider and the numeric input share the same state so the
 * employer can drag OR type a value.
 */
import { useState } from "react";

export function FilterBarClient({
  jobId,
  eligibility,
  minScore,
  state,
  relocate,
}: {
  jobId: string;
  eligibility: string;
  minScore: number;
  state: string | undefined;
  relocate: boolean | undefined;
}) {
  const [score, setScore] = useState<number>(minScore || 0);

  return (
    <form
      method="GET"
      action={`/employer/jobs/${jobId}/applicants`}
      className="rounded-md border border-border-light bg-white p-5"
    >
      <p className="mono-label mb-4">Filters</p>
      <div className="flex flex-wrap gap-4 items-end">
        {/* Eligibility */}
        <div className="min-w-[140px]">
          <label className="block text-micro tracking-wide text-slate mb-1.5">Eligibility</label>
          <select
            name="eligibility"
            defaultValue={eligibility}
            className="input-cohere"
          >
            <option value="all">All (eligible + near fit)</option>
            <option value="eligible">Eligible only</option>
            <option value="near_fit">Near fit only</option>
          </select>
        </div>

        {/* Min score — slider + numeric input sharing state */}
        <div className="min-w-[220px] flex-1 sm:flex-none">
          <label className="block text-micro tracking-wide text-slate mb-1.5">
            Min score
          </label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={score}
              onChange={(e) => setScore(Number(e.target.value))}
              className="flex-1 accent-cohere-green"
              aria-label="Minimum score slider"
            />
            <input
              type="number"
              name="min_score"
              min={0}
              max={100}
              step={1}
              value={score || ""}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (Number.isNaN(v)) return;
                setScore(Math.max(0, Math.min(100, v)));
              }}
              placeholder="0"
              className="input-cohere w-20"
              aria-label="Minimum score value"
            />
          </div>
        </div>

        {/* State */}
        <div className="min-w-[100px]">
          <label className="block text-micro tracking-wide text-slate mb-1.5">State</label>
          <input
            type="text"
            name="state"
            maxLength={2}
            defaultValue={state || ""}
            placeholder="e.g. TX"
            className="input-cohere"
          />
        </div>

        {/* Willing to relocate */}
        <div className="min-w-[140px]">
          <label className="block text-micro tracking-wide text-slate mb-1.5">Relocate willingness</label>
          <select
            name="relocate"
            defaultValue={
              relocate === true ? "true" : relocate === false ? "false" : ""
            }
            className="input-cohere"
          >
            <option value="">Any</option>
            <option value="true">Open to relocate</option>
            <option value="false">Local only</option>
          </select>
        </div>

        <button type="submit" className="btn-primary">Apply</button>
      </div>
    </form>
  );
}
