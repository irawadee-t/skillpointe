"use client";

/**
 * ImprovementLevers — "what could improve this score", derived ONLY from
 * stored data: unpassed hard gates, required_missing_items, null-handled
 * dimensions, and the engine's own top_gaps / recommended_next_step.
 *
 * Honesty rules: no invented predictions and no fabricated point estimates —
 * the backend computes no counterfactuals, so every lever stays qualitative
 * ("could unlock", "is currently estimated"), never "+12 points".
 */

import { useMemo } from "react";
import {
  dimensionLabel,
  sentenceCase,
  unpassedGates,
  GATE_TO_DIMENSION,
  type VizDimension,
  type VizMatchCore,
} from "./types";

/** Profile fields whose absence caused a neutral default, per dimension. */
const NULL_DIMENSION_HINTS: Record<string, string> = {
  compensation_alignment: "Add your desired pay",
  geography_alignment: "Set your location or commute radius",
  timing_readiness: "Add your availability date",
  work_style_signal_alignment: "Add your work-style preferences",
  experience_internship_alignment: "Add your experience history",
  credential_readiness: "Add your credentials",
  industry_alignment: "Add your industry interests",
  trade_program_alignment: "Add your training program details",
  employer_soft_pref_alignment: "Complete more of your profile",
};

interface Lever {
  key: string;
  text: string;
  detail: string | null;
  dimension: string | null;
}

export function deriveLevers(
  match: VizMatchCore,
  dimensions: VizDimension[],
): Lever[] {
  const levers: Lever[] = [];
  const seenText = new Set<string>();
  const push = (lever: Lever) => {
    const fingerprint = lever.text.toLowerCase();
    if (seenText.has(fingerprint)) return;
    seenText.add(fingerprint);
    levers.push(lever);
  };

  // 1 — required items the job asks for that are missing (strongest lever).
  // Items are usually credential names ("OSHA 10") but the engine sometimes
  // stores a full sentence — only template short name-like items.
  for (const item of match.required_missing_items) {
    // Sentence-style items now carry commas/semicolons instead of em dashes
    // (post de-dash engine copy); "—" is kept for legacy stored rows.
    const isNameLike = item.length <= 40 && !/[—,;]/.test(item);
    push({
      key: `missing:${item}`,
      text: isNameLike ? `Earn or upload ${item}` : sentenceCase(item),
      detail: "Required by this job. Earning it improves credential readiness.",
      dimension: "credential_readiness",
    });
  }

  // 2 — hard gates that did not cleanly pass, in the gate's own words.
  for (const gate of unpassedGates(match.gates)) {
    const dim = GATE_TO_DIMENSION[gate.gate_name] ?? null;
    if (!gate.reason) continue;
    push({
      key: `gate:${gate.gate_name}`,
      text: sentenceCase(gate.reason),
      detail: dim
        ? `Resolving this could improve ${dimensionLabel(dim).toLowerCase()}`
        : null,
      dimension: dim,
    });
  }

  // 3 — dimensions scored from a neutral default (missing profile data).
  for (const d of dimensions) {
    if (!d.null_handling_applied) continue;
    const hint = NULL_DIMENSION_HINTS[d.dimension] ?? "Complete more of your profile";
    push({
      key: `null:${d.dimension}`,
      text: hint,
      detail: `${dimensionLabel(d.dimension)} is currently estimated from a neutral default`,
      dimension: d.dimension,
    });
  }

  // 4 — the engine's own stated gaps (skip ones already covered above).
  for (const gap of match.top_gaps) {
    const lower = gap.toLowerCase();
    const covered =
      match.required_missing_items.some((item) =>
        lower.includes(item.toLowerCase()),
      ) || [...seenText].some((t) => t.includes(lower) || lower.includes(t));
    if (covered) continue;
    push({ key: `gap:${gap}`, text: sentenceCase(gap), detail: null, dimension: null });
  }

  return levers;
}

export interface ImprovementLeversProps {
  match: VizMatchCore;
  dimensions: VizDimension[];
  className?: string;
}

export function ImprovementLevers({ match, dimensions, className }: ImprovementLeversProps) {
  const levers = useMemo(() => deriveLevers(match, dimensions), [match, dimensions]);

  if (levers.length === 0) {
    return (
      <p className={`text-caption text-slate-muted ${className ?? ""}`}>
        No specific blockers are on file for this match.
      </p>
    );
  }

  return (
    <div className={className}>
      <ul className="m-0 list-none divide-y divide-hairline p-0" data-testid="levers">
        {levers.map((lever) => (
          <li
            key={lever.key}
            className="flex items-baseline justify-between gap-4 py-2.5"
          >
            <div className="min-w-0">
              <p className="text-[13px] leading-snug text-cohere-ink">{lever.text}</p>
              {lever.detail && (
                <p className="mt-0.5 text-[12px] leading-snug text-slate-muted">
                  {lever.detail}
                </p>
              )}
            </div>
            {lever.dimension && (
              <span className="shrink-0 rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">
                {dimensionLabel(lever.dimension)}
              </span>
            )}
          </li>
        ))}
      </ul>
      {match.recommended_next_step && (
        <p className="mt-2 border-t border-hairline pt-2 text-[12px] leading-snug text-slate">
          <span className="font-medium text-cohere-ink">Suggested next step: </span>
          {sentenceCase(match.recommended_next_step)}
        </p>
      )}
    </div>
  );
}
