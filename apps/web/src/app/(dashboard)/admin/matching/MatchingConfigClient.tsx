"use client";

/**
 * /admin/matching — view, dry-run, and activate the matching configuration.
 *
 * The engine reads its config from the active policy_configs row; this page
 * edits a draft, previews consequences server-side (old vs new, honest tier
 * labels), and activates a NEW versioned row (history preserved, audited,
 * global recompute fired). Relaxation tiers change visibility only — never
 * a score — and the preview shows that explicitly.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { ConfirmDialog, useToast } from "@/components/ui";
import { TourLaunchButton } from "@/components/tour/TourLaunchButton";
import { fetchRecomputeStatus } from "@/lib/api/admin";
import { DIMENSION_LABELS as WEIGHT_LABELS, GATE_LABELS } from "@/components/viz2/types";
import { NumberField, SliderRow, ThresholdBandTrack, WeightMixer } from "./controls";

/* ------------------------------------------------------------------ */
/*  Types (mirror apps/api/app/routers/matching_admin.py)              */
/* ------------------------------------------------------------------ */

type Weights = Record<string, number>;

export interface MatchingConfig {
  version: string;
  structured_score: { weights: Weights };
  base_fit: { weights: { structured: number; semantic: number } };
  match_labels: { strong_fit_min: number; good_fit_min: number; moderate_fit_min: number };
  relaxation: {
    enabled: boolean;
    min_results: number;
    nearby_max_miles: number;
    tiers: { adjacent: boolean; nearby_other_trade: boolean };
  };
  gates: Record<string, boolean>;
  geography_relaxation: { relax_unknown_prefs: boolean };
  eligibility: { labels: Record<string, { hard_gate_cap: number }> };
  [key: string]: unknown;
}

export interface MatchingConfigResponse {
  config: MatchingConfig;
  active: { version: string; description: string | null; activated_at: string | null } | null;
  history: Array<{
    version: string; description: string | null; is_active: boolean;
    created_at: string; activated_at: string | null; deactivated_at: string | null;
  }>;
  last_recompute: {
    kind: string; status: string; started_at: string | null;
    completed_at: string | null; error: string | null;
  } | null;
  distribution: {
    total: number; eligible: number; near_fit: number;
    nearby_tier: number; applicants_with_any_tier: number;
  } | null;
}

interface PreviewTopItem {
  job_id: string; job_title: string | null; city: string | null; state: string | null;
  score: number; eligibility_status: string; match_label: string | null;
  match_tier: string | null; tier_reason: string | null; distance_miles: number | null;
}

interface PreviewSide { counts: Record<string, number>; top: PreviewTopItem[] }

interface PreviewResponse {
  sample_applicants: number;
  total_applicants: number;
  jobs: number;
  old_totals: Record<string, number>;
  new_totals: Record<string, number>;
  spotlight: Array<{ applicant_id: string; name: string; family: string | null; old: PreviewSide; new: PreviewSide }>;
  note: string;
}

/* ------------------------------------------------------------------ */

const TIER_LABELS: Record<string, string> = {
  strict: "Meets all requirements",
  adjacent: "Related trade",
  stretch: "Stretch",
  nearby: "Near you, different trade",
};

export function MatchingConfigClient({
  initial, fetchError, token,
}: {
  initial: MatchingConfigResponse | null;
  fetchError: string | null;
  token: string;
}) {
  const toast = useToast();
  const [cfg, setCfg] = useState<MatchingConfig | null>(initial?.config ?? null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewElapsed, setPreviewElapsed] = useState(0);
  const [previewCleared, setPreviewCleared] = useState(false);
  const [activating, setActivating] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [ackNoPreview, setAckNoPreview] = useState(false);
  const [note, setNote] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activatedVersion, setActivatedVersion] = useState<string | null>(null);
  // Post-activation recompute progress (polled).
  const [recompute, setRecompute] = useState<{
    status: string; elapsed: number | null; error: string | null;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const weightSum = useMemo(() => {
    if (!cfg) return 0;
    return Object.values(cfg.structured_score.weights).reduce((a, b) => a + Number(b || 0), 0);
  }, [cfg]);
  const weightsOk = Math.abs(weightSum - 100) < 0.01;

  // Elapsed-time ticker while the dry run is in flight.
  useEffect(() => {
    if (!previewing) { setPreviewElapsed(0); return; }
    const started = Date.now();
    const iv = setInterval(() => setPreviewElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(iv);
  }, [previewing]);

  // Poll recompute progress after activation until it completes or fails.
  useEffect(() => {
    if (!activatedVersion) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await fetchRecomputeStatus(token);
        if (cancelled) return;
        setRecompute(s.run ? {
          status: s.run.status, elapsed: s.run.elapsed_seconds, error: s.run.error,
        } : null);
        if (s.run && (s.run.status === "complete" || s.run.status === "failed")) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
      } catch { /* keep polling */ }
    };
    void poll();
    pollRef.current = setInterval(poll, 4000);
    return () => {
      cancelled = true;
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [activatedVersion, token]);

  if (fetchError || !cfg) {
    return (
      <main className="p-6 md:p-8">
        <div className="mx-auto max-w-5xl">
          <div className="flex items-start gap-2 rounded-md border border-studio-maroon/30 bg-studio-maroon/[0.06] p-5 text-caption text-cohere-ink">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {fetchError ?? "No configuration loaded."}
          </div>
        </div>
      </main>
    );
  }

  const dist = initial?.distribution;
  const lastRun = initial?.last_recompute;

  const set = (updater: (c: MatchingConfig) => MatchingConfig) => {
    setCfg((c) => (c ? updater(structuredClone(c)) : c));
    // Edits invalidate the previous dry run — say so, don't just vanish it.
    setPreview((p) => {
      if (p) setPreviewCleared(true);
      return null;
    });
  };

  const runPreview = async () => {
    setPreviewing(true);
    setErrorMsg(null);
    try {
      const res = await apiFetch<PreviewResponse>("/admin/matching/preview", token, {
        method: "POST",
        body: JSON.stringify({ config: cfg, sample_size: 20 }),
      });
      setPreview(res);
      setPreviewCleared(false);
      setAckNoPreview(false);
    } catch (e) {
      setErrorMsg(extractDetail(e, "Preview failed."));
    } finally {
      setPreviewing(false);
    }
  };

  const requestActivate = () => {
    if (note.trim().length < 3) {
      setErrorMsg("Add a short note describing the change. It goes in the audit log.");
      return;
    }
    if (!weightsOk) {
      setErrorMsg(
        `Dimension weights sum to ${Math.round(weightSum * 100) / 100}, not 100. `
        + "Use “Normalize to 100” (or fix them by hand) before activating.",
      );
      return;
    }
    setErrorMsg(null);
    setConfirmOpen(true);
  };

  const activate = async () => {
    setActivating(true);
    setErrorMsg(null);
    try {
      const res = await apiFetch<{ version: string; detail: string }>(
        "/admin/matching/activate", token,
        { method: "POST", body: JSON.stringify({ config: cfg, note: note.trim() }) },
      );
      setConfirmOpen(false);
      setActivatedVersion(res.version);
      setRecompute({ status: "pending", elapsed: 0, error: null });
      toast.success(`Config ${res.version} activated. Recompute started.`);
    } catch (e) {
      setConfirmOpen(false);
      setErrorMsg(extractDetail(e, "Activation failed."));
    } finally {
      setActivating(false);
    }
  };

  // The confirm restates the preview's aggregate consequence before commit.
  const totalPairs = (initial?.distribution?.total ?? 0);
  const confirmBody = (
    <div className="space-y-3">
      {preview ? (
        <>
          <p>Across the sampled dry run, this config changes:</p>
          <ul className="list-inside list-disc space-y-1">
            <li>
              Ready to apply: <Delta oldVal={preview.old_totals.eligible} newVal={preview.new_totals.eligible} />
            </li>
            <li>
              Near fit: <Delta oldVal={preview.old_totals.near_fit} newVal={preview.new_totals.near_fit} />
            </li>
            <li>
              Nearby tier: <Delta oldVal={preview.old_totals.nearby} newVal={preview.new_totals.nearby} />
            </li>
          </ul>
          <p>
            Activation rescores <strong>every pair</strong>
            {totalPairs > 0 && <> ({totalPairs.toLocaleString()} scored pairs today)</>}.
            Scores and tiers update over the next few minutes. Versioned and audited.
          </p>
        </>
      ) : (
        <>
          <p className="text-studio-maroon">
            You have not previewed this config. Activating rescores the whole
            marketplace{totalPairs > 0 && <> ({totalPairs.toLocaleString()} pairs)</>} sight-unseen.
          </p>
          <label className="flex items-start gap-2 text-body text-cohere-ink">
            <input
              type="checkbox"
              checked={ackNoPreview}
              onChange={(e) => setAckNoPreview(e.target.checked)}
              className="mt-1 h-4 w-4 accent-studio-maroon"
            />
            Activate without a preview. I understand the consequences are unreviewed.
          </label>
        </>
      )}
    </div>
  );

  return (
    <main className="p-6 md:p-8">
      <div className="mx-auto max-w-5xl space-y-10">
        <div>
          <div className="flex items-start justify-between gap-4">
            <h1 className="font-display text-feature text-cohere-ink">Matching</h1>
            <TourLaunchButton />
          </div>
          <p className="mt-1.5 text-body text-slate">
            The rules that decide which jobs surface for which workers. Edit, preview the
            consequences, then activate. Every activation is versioned, audited, and rescores
            the whole marketplace.
          </p>
          {dist && (
            <p className="mt-3 text-body text-slate">
              Right now: <span className="font-medium tabular-nums text-cohere-ink">{dist.total.toLocaleString()}</span> scored pairs
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium tabular-nums text-cohere-ink">{dist.eligible.toLocaleString()}</span> ready to apply
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium tabular-nums text-cohere-ink">{dist.near_fit.toLocaleString()}</span> near fit
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium tabular-nums text-cohere-ink">{dist.nearby_tier.toLocaleString()}</span> nearby tier
            </p>
          )}
          {initial?.active && (
            <p className="mt-1 text-caption text-slate-muted">
              Active config {initial.active.version}
              {lastRun && ` · last recompute ${lastRun.status}${lastRun.completed_at ? ` at ${formatTs(lastRun.completed_at)}` : ""}`}
            </p>
          )}
          {lastRun?.error && (
            <p className="mt-2 flex items-start gap-2 rounded-md border border-error-red/30 bg-error-red/[0.06] p-3 text-caption text-cohere-ink" role="alert">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              Last recompute failed: {lastRun.error}
            </p>
          )}
        </div>

        {/* Dimension weights */}
        <section data-tour-id="matching-weights">
          <h2 className="text-base font-semibold text-cohere-ink">Dimension weights</h2>
          <p className="mb-3 mt-1 text-caption text-slate">
            How much each dimension contributes to the structured score. Must sum to 100.
          </p>
          <WeightMixer
            weights={cfg.structured_score.weights}
            labels={WEIGHT_LABELS}
            onChange={(next) => set((c) => { c.structured_score.weights = next; return c; })}
          />
        </section>

        {/* Hard gates */}
        <section data-tour-id="matching-gates">
          <h2 className="text-base font-semibold text-cohere-ink">Hard gates</h2>
          <p className="mt-1 text-caption text-slate">
            A failed gate caps the score. It can never be hidden inside a blended number.
            Disabling a gate skips it entirely.
          </p>
          <div className="mt-3 rounded-[10px] border border-hairline bg-white">
            {Object.entries(cfg.gates).map(([key, on], i) => (
              <label
                key={key}
                className={`flex cursor-pointer items-center justify-between px-5 py-3.5 ${i > 0 ? "border-t border-hairline" : ""}`}
              >
                <span className="text-body text-cohere-ink">{GATE_LABELS[key] ?? key}</span>
                <input
                  type="checkbox" checked={on}
                  onChange={(e) => set((c) => { c.gates[key] = e.target.checked; return c; })}
                  className="h-4 w-4 accent-studio-maroon"
                />
              </label>
            ))}
            <label className="flex cursor-pointer items-center justify-between border-t border-hairline px-5 py-3.5">
              <span className="text-body text-cohere-ink">
                Treat unknown relocation preferences as near fit
                <span className="block text-caption text-slate">
                  Imported workers who never set a radius or relocation preference aren&apos;t
                  hard-failed on distance. Missing data isn&apos;t a refusal to move.
                </span>
              </span>
              <input
                type="checkbox"
                checked={cfg.geography_relaxation.relax_unknown_prefs}
                onChange={(e) => set((c) => {
                  c.geography_relaxation.relax_unknown_prefs = e.target.checked;
                  return c;
                })}
                className="h-4 w-4 accent-studio-maroon"
              />
            </label>
          </div>
        </section>

        {/* Relaxation tiers */}
        <section>
          <h2 className="text-base font-semibold text-cohere-ink">Progressive relaxation</h2>
          <p className="mt-1 text-caption text-slate">
            When strict matching leaves a worker with too few results, the matches page expands
            through labeled tiers instead of showing nothing. Tiers change what&apos;s visible,
            never any score.
          </p>
          <div className="mt-3 rounded-[10px] border border-hairline bg-white">
            <label className="flex cursor-pointer items-center justify-between px-5 py-3.5">
              <span className="text-body text-cohere-ink">Relaxation enabled</span>
              <input
                type="checkbox" checked={cfg.relaxation.enabled}
                onChange={(e) => set((c) => { c.relaxation.enabled = e.target.checked; return c; })}
                className="h-4 w-4 accent-studio-maroon"
              />
            </label>
            <SliderRow
              label="Result floor"
              description="The nearby tier turns on when a worker has fewer results than this."
              value={cfg.relaxation.min_results}
              min={0} max={50}
              unit="results"
              onChange={(v) => set((c) => { c.relaxation.min_results = v; return c; })}
            />
            <label className="flex cursor-pointer items-center justify-between border-t border-hairline px-5 py-3.5">
              <span className="text-body text-cohere-ink">Related-trade tier</span>
              <input
                type="checkbox" checked={cfg.relaxation.tiers.adjacent}
                onChange={(e) => set((c) => { c.relaxation.tiers.adjacent = e.target.checked; return c; })}
                className="h-4 w-4 accent-studio-maroon"
              />
            </label>
            <label className="flex cursor-pointer items-center justify-between border-t border-hairline px-5 py-3.5">
              <span className="text-body text-cohere-ink">
                Nearby tier (&quot;Near you, different trade&quot;)
              </span>
              <input
                type="checkbox" checked={cfg.relaxation.tiers.nearby_other_trade}
                onChange={(e) => set((c) => { c.relaxation.tiers.nearby_other_trade = e.target.checked; return c; })}
                className="h-4 w-4 accent-studio-maroon"
              />
            </label>
            <SliderRow
              label="Nearby tier max distance"
              description={'Only jobs with a verified distance inside this cap (or the worker’s own radius, if larger) can appear as “near you”.'}
              value={cfg.relaxation.nearby_max_miles}
              min={1} max={300}
              unit="mi"
              onChange={(v) => set((c) => { c.relaxation.nearby_max_miles = v; return c; })}
            />
          </div>
        </section>

        {/* Labels + blend */}
        <section>
          <h2 className="text-base font-semibold text-cohere-ink">Labels and blend</h2>
          <p className="mt-1 text-caption text-slate">
            Score thresholds for the fit labels workers see, and how the structured and
            semantic scores combine.
          </p>
          <div className="mt-3 rounded-[10px] border border-hairline bg-white">
            <ThresholdBandTrack
              values={cfg.match_labels}
              onChange={(key, v) => set((c) => { c.match_labels[key] = v; return c; })}
            />
            {([
              ["strong_fit_min", "Strong fit at or above", cfg.match_labels.good_fit_min, 100],
              ["good_fit_min", "Good fit at or above", cfg.match_labels.moderate_fit_min, cfg.match_labels.strong_fit_min],
              ["moderate_fit_min", "Moderate fit at or above", 0, cfg.match_labels.good_fit_min],
            ] as const).map(([key, label, min, max]) => (
              <div key={key} className="flex items-center justify-between border-t border-hairline px-5 py-3.5">
                <span className="text-body text-cohere-ink">{label}</span>
                <NumberField
                  value={cfg.match_labels[key]}
                  min={min} max={max}
                  onCommit={(v) => set((c) => { c.match_labels[key] = v; return c; })}
                  ariaLabel={label}
                />
              </div>
            ))}
            <SliderRow
              label="Structured share of base fit"
              description={`Semantic share is the remainder (${Math.round((1 - cfg.base_fit.weights.structured) * 100)}%).`}
              value={Math.round(cfg.base_fit.weights.structured * 100)}
              min={0} max={100} step={5}
              unit="%"
              onChange={(v) => set((c) => {
                c.base_fit.weights.structured = v / 100;
                c.base_fit.weights.semantic = Math.round(100 - v) / 100;
                return c;
              })}
            />
          </div>
        </section>

        {/* Preview + activate */}
        <section data-tour-id="matching-preview">
          <h2 className="text-base font-semibold text-cohere-ink">Preview, then activate</h2>
          <p className="mt-1 text-caption text-slate">
            The dry run scores a 20-worker sample against every active job with your draft
            config. Nothing is saved until you activate.
          </p>

          {errorMsg && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-caption text-cohere-ink">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          {previewCleared && !preview && (
            <p className="mt-3 rounded-md border border-hairline bg-stone/40 p-3 text-caption text-slate" role="status">
              Config changed. The previous preview no longer reflects this draft and was
              cleared. Run the dry run again before activating.
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={runPreview}
              disabled={previewing}
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-white px-5 py-2 text-body font-medium text-cohere-ink transition-colors hover:bg-stone disabled:opacity-50"
              data-testid="preview-button"
            >
              {previewing && <Loader2 className="h-4 w-4 animate-spin" />}
              {previewing
                ? `Running dry run… ${previewElapsed}s`
                : "Preview changes"}
            </button>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why this change? (goes in the audit log)"
              className="min-w-64 flex-1 rounded-[8px] border border-hairline bg-white px-3 py-2 text-body text-cohere-ink placeholder:text-slate-muted focus:outline-2 focus:outline-studio-maroon"
              aria-label="Activation note"
            />
            <button
              onClick={requestActivate}
              disabled={activating}
              className="rounded-full bg-studio-maroon px-5 py-2 text-body font-medium text-white transition-colors hover:bg-[#8a1e2f] disabled:opacity-50"
              data-testid="activate-button"
            >
              {activating ? "Activating…" : "Activate and rescore"}
            </button>
          </div>

          <ConfirmDialog
            open={confirmOpen}
            onClose={() => setConfirmOpen(false)}
            onConfirm={() => { void activate(); }}
            busy={activating}
            danger
            disabled={!preview && !ackNoPreview}
            title="Activate this matching config?"
            confirmLabel="Activate and rescore"
            body={confirmBody}
          />

          {activatedVersion && (
            <div className="mt-3 space-y-1 text-body text-cohere-ink" role="status">
              <p>
                Config {activatedVersion} is live.
                {recompute?.status === "complete"
                  ? " Recompute finished. Scores and tiers are up to date."
                  : recompute?.status === "failed"
                    ? " Recompute failed. See the error below."
                    : ` Full recompute ${recompute?.status === "in_progress" ? "running" : "starting"}…${recompute?.elapsed != null ? ` ${recompute.elapsed}s elapsed.` : ""}`}
              </p>
              {recompute?.status && recompute.status !== "complete" && recompute.status !== "failed" && (
                <p className="flex items-center gap-2 text-caption text-slate">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Scores and tiers update as it completes.
                </p>
              )}
              {recompute?.error && (
                <p className="flex items-start gap-2 rounded-md border border-error-red/30 bg-error-red/[0.06] p-3 text-caption text-cohere-ink" role="alert">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  {recompute.error}
                </p>
              )}
            </div>
          )}

          {preview && (
            <div className="mt-6 space-y-6">
              <p className="text-body text-slate">
                Across {preview.sample_applicants} sampled workers (of {preview.total_applicants}) ×{" "}
                {preview.jobs} jobs: ready to apply{" "}
                <Delta oldVal={preview.old_totals.eligible} newVal={preview.new_totals.eligible} />, near fit{" "}
                <Delta oldVal={preview.old_totals.near_fit} newVal={preview.new_totals.near_fit} />, nearby tier{" "}
                <Delta oldVal={preview.old_totals.nearby} newVal={preview.new_totals.nearby} />. Workers with at
                least one result:{" "}
                <Delta oldVal={preview.old_totals.applicants_with_results} newVal={preview.new_totals.applicants_with_results} />.
              </p>

              {preview.spotlight.map((s) => {
                const oldTop = s.old.top.slice(0, 5);
                const newTop = s.new.top.slice(0, 5);
                const oldIds = oldTop.map((t) => t.job_id);
                const newIds = newTop.map((t) => t.job_id);
                const unchanged =
                  oldIds.length === newIds.length &&
                  oldIds.every((id, i) => id === newIds[i]) &&
                  ["eligible", "near_fit", "nearby"].every(
                    (k) => (s.old.counts[k] ?? 0) === (s.new.counts[k] ?? 0),
                  );
                return (
                  <div key={s.applicant_id} className="rounded-[10px] border border-hairline bg-white">
                    <div className="border-b border-hairline px-5 py-3.5">
                      <span className="text-[1.0625rem] font-medium text-cohere-ink">{s.name}</span>
                      {s.family && <span className="ml-2 text-caption text-slate-muted">{s.family}</span>}
                    </div>
                    {unchanged ? (
                      // Unchanged spotlights collapse — the eye goes to real diffs.
                      <p className="px-5 py-3.5 text-body text-slate">
                        No change for this worker: same top {newTop.length || "results"} and counts.
                      </p>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2">
                        <SpotlightColumn title="Current" side={s.old} otherIds={newIds} mode="old" />
                        <SpotlightColumn title="With this config" side={s.new} otherIds={oldIds} mode="new" bordered />
                      </div>
                    )}
                  </div>
                );
              })}

              <p className="text-caption text-slate-muted">{preview.note}</p>
            </div>
          )}
        </section>

        {/* History */}
        {initial?.history && initial.history.length > 0 && (
          <section>
            <h2 className="text-base font-semibold text-cohere-ink">Version history</h2>
            <div className="mt-3 rounded-[10px] border border-hairline bg-white">
              {initial.history.map((h, i) => (
                <div key={h.version} className={`flex items-baseline justify-between px-5 py-3.5 ${i > 0 ? "border-t border-hairline" : ""}`}>
                  <span className="text-body text-cohere-ink">
                    {h.version}
                    {h.is_active && <span className="ml-2 text-caption font-medium text-cohere-green">Active</span>}
                    {h.description && <span className="ml-2 text-caption text-slate">{h.description}</span>}
                  </span>
                  <span className="text-caption tabular-nums text-slate-muted">
                    {formatTs(h.activated_at ?? h.created_at)}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */

function Delta({ oldVal, newVal }: { oldVal?: number; newVal?: number }) {
  const o = oldVal ?? 0;
  const n = newVal ?? 0;
  const diff = n - o;
  return (
    <span className="tabular-nums">
      <span className="text-slate-muted">{o.toLocaleString()}</span>
      {" → "}
      <span className="font-medium text-cohere-ink">{n.toLocaleString()}</span>
      {diff !== 0 && (
        <span className={diff > 0 ? "ml-1 text-cohere-green" : "ml-1 text-studio-maroon"}>
          ({diff > 0 ? "+" : ""}{diff.toLocaleString()})
        </span>
      )}
    </span>
  );
}

/**
 * One side of a spotlight diff. Rows are highlighted only when they CHANGED
 * relative to the other side's top-5: entered (new side, wasn't in old),
 * left (old side, dropped from new), or moved position. Unchanged rows stay
 * quiet so real movement pops.
 */
function SpotlightColumn({
  title, side, bordered, otherIds = [], mode = "old",
}: {
  title: string; side: PreviewSide; bordered?: boolean;
  otherIds?: string[]; mode?: "old" | "new";
}) {
  const top = side.top.slice(0, 5);
  const change = (jobId: string, idx: number): "entered" | "left" | "moved" | null => {
    const otherIdx = otherIds.indexOf(jobId);
    if (otherIdx === -1) return mode === "new" ? "entered" : "left";
    if (otherIdx !== idx) return "moved";
    return null;
  };
  return (
    <div className={`px-5 py-4 ${bordered ? "border-t border-hairline md:border-l md:border-t-0" : ""}`}>
      <p className="text-caption font-medium text-slate-muted">{title}</p>
      {top.length === 0 ? (
        <p className="mt-2 text-body text-slate">No results surfaced.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {top.map((t, idx) => {
            const c = change(t.job_id, idx);
            return (
            <li
              key={t.job_id}
              className={`text-body text-cohere-ink ${
                c === "entered" ? "-mx-2 rounded-md bg-wash-green px-2 py-1"
                : c === "left" ? "-mx-2 rounded-md bg-studio-maroon/[0.06] px-2 py-1"
                : ""
              }`}
            >
              {c && (
                <span className={`mr-1.5 text-micro font-medium ${
                  c === "entered" ? "text-cohere-green" : c === "left" ? "text-studio-maroon" : "text-slate-muted"
                }`}>
                  {c === "entered" ? "New in top 5" : c === "left" ? "Drops out" : `Moves ${otherIds.indexOf(t.job_id) + 1} → ${idx + 1}`}
                </span>
              )}
              <span className="font-medium">{t.job_title ?? "Untitled"}</span>
              <span className="ml-1.5 text-slate">
                {[t.city, t.state].filter(Boolean).join(", ")}
              </span>
              <span className="block text-caption text-slate">
                {t.match_tier === "nearby"
                  ? `${TIER_LABELS.nearby}${t.distance_miles !== null ? ` · ${Math.round(t.distance_miles)} mi` : ""}`
                  : `${TIER_LABELS[t.match_tier ?? ""] ?? t.eligibility_status} · score ${Math.round(t.score)}`}
              </span>
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function extractDetail(e: unknown, fallback: string): string {
  if (e instanceof Error && "body" in e) {
    try {
      const body = JSON.parse((e as { body: string }).body);
      if (typeof body?.detail === "string") return body.detail;
    } catch { /* not json */ }
  }
  return fallback;
}
