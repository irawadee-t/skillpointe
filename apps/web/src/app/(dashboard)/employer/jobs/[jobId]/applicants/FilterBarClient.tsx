"use client";

/**
 * Filter bar — live type-ahead filters synced to the URL. Every control
 * narrows the server-rendered list as you interact (typing filters live,
 * debounced ~250ms; no Apply button needed).
 */
import { useEffect, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { UrlSearchField, UrlSelectField } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

export function FilterBarClient({
  eligibility,
  minScore,
}: {
  jobId: string;
  eligibility: string;
  minScore: number;
  state: string | undefined;
  relocate: boolean | undefined;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  // Min score — slider and numeric input share state; URL updates debounced.
  const [score, setScore] = useState<number>(minScore || 0);
  const debouncedScore = useDebouncedValue(score, 250);
  const lastPushedScore = useRef(minScore || 0);

  useEffect(() => {
    if (debouncedScore === lastPushedScore.current) return;
    lastPushedScore.current = debouncedScore;
    const params = new URLSearchParams(searchParams.toString());
    if (debouncedScore > 0) params.set("min_score", String(debouncedScore));
    else params.delete("min_score");
    params.delete("page");
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedScore]);

  return (
    <div className="rounded-md border border-border-light bg-white p-5">
      <p className="mono-label mb-4">Filters</p>
      <div className="flex flex-wrap gap-4 items-end">
        {/* Candidate name — live search */}
        <UrlSearchField
          param="q"
          label="Search name"
          placeholder="Jane Doe…"
          className="min-w-[180px] flex-1 sm:flex-none"
        />

        {/* Eligibility */}
        <UrlSelectField
          param="eligibility"
          label="Eligibility"
          defaultValue={eligibility || "all"}
          className="min-w-[140px]"
          options={[
            { value: "all", label: "All (eligible + near fit)" },
            { value: "eligible", label: "Eligible only" },
            { value: "near_fit", label: "Near fit only" },
          ]}
        />

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
        <UrlSearchField
          param="state"
          label="State"
          placeholder="e.g. TX"
          maxLength={2}
          uppercase
          className="min-w-[110px]"
        />

        {/* Willing to relocate */}
        <UrlSelectField
          param="relocate"
          label="Willing to relocate"
          className="min-w-[140px]"
          options={[
            { value: "", label: "Any" },
            { value: "true", label: "Open to relocate" },
            { value: "false", label: "Local only" },
          ]}
        />
      </div>
    </div>
  );
}
