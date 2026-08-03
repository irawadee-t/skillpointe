"use client";

/**
 * Interactive controls for /admin/matching.
 *
 * WeightMixer — the Ableton/Lightroom mixer pattern for the nine dimension
 * weights that must sum to 100: per-dimension slider + synced number field,
 * per-dimension lock pins, proportional delta redistribution across unlocked
 * dimensions while dragging (sum invariant — math in @/lib/matchingWeights),
 * an always-visible sum indicator, and a live stacked-bar distribution
 * preview. Sliders track the pointer 1:1 with no width transitions, so drags
 * stay jank-free and reduced-motion needs no special casing.
 *
 * ThresholdBandTrack — a multi-thumb band track for the three fit-label
 * thresholds that live on one 0–100 scale. The bands (low/moderate/good/
 * strong) render in the shared match-tier hues; each thumb is a keyboard
 * slider clamped by its neighbors.
 *
 * SliderRow / NumberField — the slider-plus-number idiom for single scalar
 * settings (relaxation floor, nearby miles, structured share).
 */

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Lock, LockOpen } from "lucide-react";
import { normalizeTo100, redistribute, sumWeights } from "@/lib/matchingWeights";

const fmt = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(1));

/* ------------------------------------------------------------------ */
/*  NumberField — synced numeric entry that commits on blur/Enter      */
/* ------------------------------------------------------------------ */

export function NumberField({
  value, min, max, step = 1, onCommit, ariaLabel, disabled = false, className = "",
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onCommit: (v: number) => void;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);

  const commit = () => {
    if (draft === null) return;
    const n = Number(draft);
    setDraft(null);
    if (draft.trim() === "" || Number.isNaN(n)) return; // keep prior value
    onCommit(Math.min(max, Math.max(min, n)));
  };

  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={draft ?? fmt(value)}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") { commit(); (e.target as HTMLInputElement).blur(); }
        if (e.key === "Escape") setDraft(null);
      }}
      className={`w-20 rounded-[8px] border border-hairline bg-white px-2.5 py-1.5 text-right text-body tabular-nums text-cohere-ink focus:outline-2 focus:outline-studio-maroon disabled:opacity-40 ${className}`}
      aria-label={ariaLabel}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  SliderRow — slider + number for a single scalar setting            */
/* ------------------------------------------------------------------ */

export function SliderRow({
  label, description, value, min, max, step = 1, unit, onChange, bordered = true,
}: {
  label: string;
  description?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (v: number) => void;
  bordered?: boolean;
}) {
  return (
    <div className={`flex flex-col gap-3 px-5 py-3.5 sm:flex-row sm:items-center sm:gap-6 ${bordered ? "border-t border-hairline" : ""}`}>
      <span className="text-body text-cohere-ink sm:w-72 sm:shrink-0">
        {label}
        {description && <span className="block text-caption text-slate">{description}</span>}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-w-0 flex-1 accent-cohere-ink"
        aria-label={`${label} slider`}
        aria-valuetext={`${fmt(value)}${unit ? ` ${unit}` : ""}`}
      />
      <span className="flex shrink-0 items-center gap-1.5">
        <NumberField value={value} min={min} max={max} step={step} onCommit={onChange} ariaLabel={label} />
        {unit && <span className="w-8 text-caption text-slate">{unit}</span>}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  WeightMixer                                                        */
/* ------------------------------------------------------------------ */

export function WeightMixer({
  weights, labels, onChange,
}: {
  weights: Record<string, number>;
  labels: Record<string, string>;
  onChange: (next: Record<string, number>) => void;
}) {
  const [locked, setLocked] = useState<ReadonlySet<string>>(new Set());
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const sum = sumWeights(weights);
  const sumOk = Math.abs(sum - 100) < 0.01;
  const keys = Object.keys(weights);
  const allLocked = keys.every((k) => locked.has(k));

  const toggleLock = (key: string) => {
    setLocked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const move = useCallback((key: string, raw: number) => {
    onChange(redistribute(weights, key, raw, locked));
  }, [weights, locked, onChange]);

  const barTotal = Math.max(sum, 0.1);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span
          role="status"
          aria-live="polite"
          className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium tabular-nums ${
            sumOk
              ? "border-hairline bg-white text-slate"
              : "border-studio-maroon bg-studio-maroon text-white"
          }`}
        >
          {sumOk ? "Sum 100" : `Sum ${fmt(sum)}, must be 100`}
        </span>
        <button
          type="button"
          onClick={() => onChange(normalizeTo100(weights, locked))}
          disabled={allLocked || sumOk}
          className="text-body text-slate transition-colors hover:text-cohere-ink disabled:opacity-40"
        >
          Normalize to 100
        </button>
      </div>

      <div className="mt-3 rounded-[10px] border border-hairline bg-white">
        {/* Live distribution preview — the dragged dimension reads in the accent. */}
        <div className="px-5 pb-3 pt-4">
          <div
            className="flex h-2 w-full overflow-hidden rounded-full bg-stone"
            role="img"
            aria-label={`Weight distribution: ${keys.map((k) => `${labels[k] ?? k} ${fmt(weights[k] ?? 0)}`).join(", ")}`}
          >
            {keys.map((k) => (
              <div
                key={k}
                title={`${labels[k] ?? k}: ${fmt(weights[k] ?? 0)}`}
                style={{ width: `${((Number(weights[k]) || 0) / barTotal) * 100}%` }}
                className={`transition-colors ${k === activeKey ? "bg-studio-maroon" : "bg-cohere-ink"} border-r border-white last:border-r-0`}
              />
            ))}
          </div>
        </div>

        {keys.map((key) => {
          const val = Number(weights[key]) || 0;
          const isLocked = locked.has(key);
          const label = labels[key] ?? key;
          return (
            <div
              key={key}
              className="flex items-center gap-3 border-t border-hairline px-5 py-3 sm:gap-4"
            >
              <button
                type="button"
                onClick={() => toggleLock(key)}
                aria-pressed={isLocked}
                aria-label={isLocked ? `Unlock ${label} (pinned at ${fmt(val)})` : `Lock ${label} at ${fmt(val)}`}
                title={isLocked ? "Unlock: let this weight move again" : "Lock: pin this weight while others move"}
                className={`shrink-0 rounded-[8px] p-1.5 transition-colors ${
                  isLocked ? "text-cohere-ink" : "text-slate-muted hover:text-cohere-ink"
                } focus:outline-2 focus:outline-studio-maroon`}
              >
                {isLocked ? <Lock className="h-4 w-4" aria-hidden /> : <LockOpen className="h-4 w-4" aria-hidden />}
              </button>
              <span className={`w-40 shrink-0 text-body sm:w-60 ${isLocked ? "text-slate-muted" : "text-cohere-ink"}`}>
                {label}
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={val}
                disabled={isLocked}
                onChange={(e) => move(key, Number(e.target.value))}
                onPointerDown={() => setActiveKey(key)}
                onPointerUp={() => setActiveKey(null)}
                onFocus={() => setActiveKey(key)}
                onBlur={() => setActiveKey(null)}
                className="min-w-0 flex-1 accent-cohere-ink disabled:opacity-40"
                aria-label={`Weight for ${label}`}
                aria-valuetext={`${fmt(val)} of 100 points`}
              />
              <NumberField
                value={val}
                min={0}
                max={100}
                step={1}
                disabled={isLocked}
                onCommit={(v) => move(key, v)}
                ariaLabel={`Weight for ${label}, exact value`}
              />
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-caption text-slate-muted">
        Moving one weight redistributes the difference across the unlocked dimensions, so the
        sum holds at {fmt(sum)}. Lock a dimension to pin its value.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ThresholdBandTrack — three thumbs on one 0–100 scale               */
/* ------------------------------------------------------------------ */

interface ThresholdValues {
  moderate_fit_min: number;
  good_fit_min: number;
  strong_fit_min: number;
}

const THUMBS: Array<{ key: keyof ThresholdValues; label: string }> = [
  { key: "moderate_fit_min", label: "Moderate fit at or above" },
  { key: "good_fit_min", label: "Good fit at or above" },
  { key: "strong_fit_min", label: "Strong fit at or above" },
];

// Shared match-tier hues (see DESIGN_CONTRACT: strong=green, good=blue,
// moderate=slate, low=muted) applied as quiet band fills.
const BAND_CLASSES = ["bg-stone", "bg-slate-muted/50", "bg-cohere-blue/70", "bg-cohere-green/80"];
const BAND_NAMES = ["Low", "Moderate", "Good", "Strong"];

export function ThresholdBandTrack({
  values, onChange,
}: {
  values: ThresholdValues;
  onChange: (key: keyof ThresholdValues, v: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragKey = useRef<keyof ThresholdValues | null>(null);
  const sawPointer = useRef(false);
  const baseId = useId();

  const bounds = (key: keyof ThresholdValues): [number, number] => {
    switch (key) {
      case "moderate_fit_min": return [0, values.good_fit_min];
      case "good_fit_min": return [values.moderate_fit_min, values.strong_fit_min];
      case "strong_fit_min": return [values.good_fit_min, 100];
    }
  };

  const clampTo = (key: keyof ThresholdValues, v: number) => {
    const [lo, hi] = bounds(key);
    return Math.round(Math.min(hi, Math.max(lo, v)));
  };

  const valueFromPointer = (clientX: number): number => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    return ((clientX - rect.left) / rect.width) * 100;
  };

  const onThumbPointerDown = (key: keyof ThresholdValues) => (e: ReactPointerEvent<HTMLButtonElement>) => {
    sawPointer.current = true;
    dragKey.current = key;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onThumbPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const key = dragKey.current;
    if (!key) return;
    onChange(key, clampTo(key, valueFromPointer(e.clientX)));
  };
  const onThumbPointerUp = () => { dragKey.current = null; };

  // Mouse fallback for environments that deliver mouse events without the
  // corresponding pointer events (some automation/AT stacks). Real pointer
  // input sets sawPointer and this path stays inert, so drags never double-fire.
  const onThumbMouseDown = (key: keyof ThresholdValues) => (e: ReactMouseEvent<HTMLButtonElement>) => {
    if (sawPointer.current || e.button !== 0) return;
    e.preventDefault();
    const move = (ev: MouseEvent) => onChange(key, clampTo(key, valueFromPointer(ev.clientX)));
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  };

  const onThumbKeyDown = (key: keyof ThresholdValues) => (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    const v = values[key];
    const [lo, hi] = bounds(key);
    let next: number | null = null;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") next = v - 1;
    else if (e.key === "ArrowRight" || e.key === "ArrowUp") next = v + 1;
    else if (e.key === "PageDown") next = v - 5;
    else if (e.key === "PageUp") next = v + 5;
    else if (e.key === "Home") next = lo;
    else if (e.key === "End") next = hi;
    if (next !== null) {
      e.preventDefault();
      onChange(key, clampTo(key, next));
    }
  };

  // Guard against configs arriving out of order (moderate > good, …): the
  // track still renders; each thumb is simply clamped from there on.
  const stops = [0, values.moderate_fit_min, values.good_fit_min, values.strong_fit_min, 100];
  const widths = stops.slice(1).map((s, i) => Math.max(0, s - stops[i]));

  return (
    <div className="px-5 py-4">
      <div className="relative pb-1 pt-2" style={{ touchAction: "none" }}>
        <div ref={trackRef} className="flex h-2 w-full overflow-hidden rounded-full bg-stone">
          {widths.map((w, i) => (
            <div key={BAND_NAMES[i]} style={{ width: `${w}%` }} className={BAND_CLASSES[i]} />
          ))}
        </div>
        {THUMBS.map(({ key, label }) => {
          const [lo, hi] = bounds(key);
          return (
            <button
              key={key}
              type="button"
              role="slider"
              id={`${baseId}-${key}`}
              aria-label={label}
              aria-valuemin={lo}
              aria-valuemax={hi}
              aria-valuenow={values[key]}
              aria-valuetext={`${label.replace(" at or above", "")} starts at score ${values[key]}`}
              onPointerDown={onThumbPointerDown(key)}
              onPointerMove={onThumbPointerMove}
              onPointerUp={onThumbPointerUp}
              onMouseDown={onThumbMouseDown(key)}
              onKeyDown={onThumbKeyDown(key)}
              style={{ left: `${values[key]}%` }}
              className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize rounded-full border-2 border-cohere-ink bg-white focus:outline-2 focus:outline-offset-2 focus:outline-studio-maroon"
            />
          );
        })}
      </div>
      <p className="mt-2 text-caption text-slate" aria-hidden>
        <span className="tabular-nums">
          Low &lt; {values.moderate_fit_min} · Moderate ≥ {values.moderate_fit_min} · Good ≥ {values.good_fit_min} · Strong ≥ {values.strong_fit_min}
        </span>
      </p>
    </div>
  );
}
