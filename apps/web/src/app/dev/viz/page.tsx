"use client";

/**
 * /dev/viz — development-only harness for the viz2 match-explanation pieces.
 *
 * Renders MatchExplanation against real matches served live by
 * GET /viz/matches/{id}/explanation (sign in as admin in this browser first —
 * admin may inspect any match), plus a fixture-driven small-n dot-strip case
 * that real local data cannot produce (every job has 300+ candidates).
 *
 * Gated hard: production builds 404.
 */

import { useEffect, useRef, useState } from "react";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { MatchExplanation, ScoreInContext } from "@/components/viz2";
import {
  fetchMatchExplanation,
  type MatchExplanationData,
  type VizDistribution,
} from "@/components/viz2/types";

/** Real match ids from the local demo dataset (supabase/demo-data.sql +
 * recompute). Swap freely — the picker below accepts any match uuid. */
const SAMPLES: { label: string; id: string }[] = [
  { label: "Eligible · strict tier", id: "0a830664-1833-4d60-97d1-52821c8df733" },
  { label: "Near fit · null-handled dims", id: "a17cba31-c4dc-4667-8597-7a220dc1a33a" },
  { label: "Nearby tier", id: "988ee90a-e31c-4018-aff3-4f479c07b1d4" },
  { label: "Ineligible", id: "2f76dd1f-2013-4b28-806f-b361f07231e1" },
];

/** Fixture for the n < 20 dot strip (no real local population is this small). */
const SMALL_N_FIXTURE: VizDistribution = {
  n: 12,
  mode: "points",
  bucket_width: 5,
  buckets: [],
  points: [
    { score: 14.2, status: "ineligible" },
    { score: 18.9, status: "ineligible" },
    { score: 22.4, status: "ineligible" },
    { score: 29.1, status: "near_fit" },
    { score: 33.6, status: "near_fit" },
    { score: 34.8, status: "near_fit" },
    { score: 41.3, status: "near_fit" },
    { score: 52.7, status: "near_fit" },
    { score: 61.0, status: "eligible" },
    { score: 66.5, status: "eligible" },
    { score: 71.2, status: "eligible" },
    { score: 78.4, status: "eligible" },
  ],
  median: 38.0,
};

type Slot = {
  label: string;
  id: string;
  data?: MatchExplanationData;
  error?: string;
};

export default function DevVizPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <Harness />;
}

function Harness() {
  const [token, setToken] = useState<string | null>(null);
  const [slots, setSlots] = useState<Slot[]>(SAMPLES.map((s) => ({ ...s })));
  const [customId, setCustomId] = useState("");
  const [mode, setMode] = useState<"applicant" | "job">("applicant");
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data }) =>
        setToken(
          data.session?.access_token ??
            // Dev-only escape hatch: paste a JWT into localStorage when no
            // browser session exists (window.localStorage.setItem("viz2_dev_token", t)).
            window.localStorage.getItem("viz2_dev_token"),
        ),
      );
  }, []);

  const requested = useRef(new Set<string>());
  useEffect(() => {
    if (!token) return;
    slots.forEach((slot) => {
      if (slot.data || slot.error || requested.current.has(slot.id)) return;
      requested.current.add(slot.id);
      // No cancellation: promises outlive effect re-runs (slots is a dep) and
      // resolve via functional updates keyed by id.
      fetchMatchExplanation(slot.id, token)
        .then((data) => {
          setSlots((prev) =>
            prev.map((s) => (s.id === slot.id ? { ...s, data } : s)),
          );
        })
        .catch((err: unknown) => {
          const message = err instanceof Error ? err.message : String(err);
          setSlots((prev) =>
            prev.map((s) => (s.id === slot.id ? { ...s, error: message } : s)),
          );
        });
    });
  }, [token, slots]);

  const addCustom = () => {
    const id = customId.trim();
    if (!id) return;
    setSlots((prev) => [...prev, { label: "Custom", id }]);
    setCustomId("");
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-display text-feature text-cohere-ink">
        viz2 harness — match explanation
      </h1>
      <p className="mt-1 text-caption text-slate-muted">
        Dev-only. Sign in as admin in this browser, then reload. Live data from{" "}
        <code>/viz/matches/{"{id}"}/explanation</code>.
      </p>

      {token === null && (
        <p className="mt-4 rounded-[8px] border border-hairline bg-white px-4 py-3 text-caption text-slate">
          No Supabase session found — sign in at <code>/login</code> (admin
          recommended) and reload this page.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-caption text-slate">
          <input
            type="checkbox"
            checked={mode === "job"}
            onChange={(e) => setMode(e.target.checked ? "job" : "applicant")}
          />
          job context (employer view)
        </label>
        <label className="flex items-center gap-1.5 text-caption text-slate">
          <input
            type="checkbox"
            checked={narrow}
            onChange={(e) => setNarrow(e.target.checked)}
          />
          375px width
        </label>
        <span className="flex items-center gap-1.5">
          <input
            value={customId}
            onChange={(e) => setCustomId(e.target.value)}
            placeholder="match uuid…"
            className="w-72 rounded-[8px] border border-hairline bg-white px-2.5 py-1 text-caption"
          />
          <button
            type="button"
            onClick={addCustom}
            className="rounded-full border border-hairline bg-white px-3 py-1 text-caption text-slate hover:text-cohere-ink"
          >
            Add
          </button>
        </span>
      </div>

      <div className="mt-8 space-y-10">
        {slots.map((slot) => (
          <section
            key={slot.id}
            className="rounded-[14px] border border-hairline bg-white p-6"
            style={narrow ? { maxWidth: 375 } : undefined}
          >
            <p className="mb-3 text-[11px] font-medium text-slate-muted">
              {slot.label} · <span className="tabular-nums">{slot.id}</span>
            </p>
            {slot.data ? (
              <MatchExplanation data={slot.data} contextMode={mode} />
            ) : slot.error ? (
              <p className="text-caption text-error-red">{slot.error}</p>
            ) : (
              <p className="text-caption text-slate-muted">Loading…</p>
            )}
          </section>
        ))}

        <section
          className="rounded-[14px] border border-hairline bg-white p-6"
          style={narrow ? { maxWidth: 375 } : undefined}
        >
          <p className="mb-3 text-[11px] font-medium text-slate-muted">
            Small population (n = 12) — dot strip, FIXTURE data
          </p>
          <ScoreInContext
            distribution={SMALL_N_FIXTURE}
            score={61}
            thresholds={{ strong_fit_min: 80, good_fit_min: 60 }}
            mode="job"
            caption="Among 12 candidates scored for this job (fixture)"
          />
        </section>
      </div>
    </main>
  );
}
