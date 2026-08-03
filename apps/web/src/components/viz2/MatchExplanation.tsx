"use client";

/**
 * MatchExplanation — the composite "Why this score" piece:
 * driver-contribution bars + score-in-context strip + improvement levers,
 * under one heading, with a screen-reader summary and a data-table fallback.
 *
 * Mounting contract (for later integration passes):
 *   <MatchExplanation data={payload} contextMode="applicant" />
 *   - `data` is exactly GET /viz/matches/{id}/explanation
 *   - `contextMode` picks which population strip renders:
 *       "applicant" — where this job sits among all jobs scored for the
 *                     applicant (the applicant-facing surface)
 *       "job"       — where this candidate sits among all candidates scored
 *                     for the job (the employer-facing surface)
 */

import { useId } from "react";
import { MatchDrivers } from "./MatchDrivers";
import { ScoreInContext } from "./ScoreInContext";
import { ImprovementLevers } from "./ImprovementLevers";
import { dimensionLabel, fmt1, type MatchExplanationData } from "./types";

const LABEL_HUMAN: Record<string, string> = {
  strong_fit: "strong fit",
  good_fit: "good fit",
  moderate_fit: "moderate fit",
  low_fit: "low fit",
};
const ELIGIBILITY_HUMAN: Record<string, string> = {
  eligible: "eligible",
  near_fit: "near fit",
  ineligible: "not eligible",
};

export interface MatchExplanationProps {
  data: MatchExplanationData;
  contextMode?: "applicant" | "job";
  className?: string;
}

export function MatchExplanation({
  data,
  contextMode = "applicant",
  className,
}: MatchExplanationProps) {
  const headingId = useId();
  const descId = useId();
  const { match, dimensions, thresholds } = data;
  const distribution =
    contextMode === "applicant" ? data.context_applicant : data.context_job;
  const score = match.policy_adjusted_score;

  const labelText = match.match_label
    ? LABEL_HUMAN[match.match_label] ?? match.match_label.replaceAll("_", " ")
    : null;
  const eligibilityText =
    ELIGIBILITY_HUMAN[match.eligibility_status] ?? match.eligibility_status;

  return (
    <figure
      className={`m-0 ${className ?? ""}`}
      aria-labelledby={headingId}
      aria-describedby={descId}
    >
      <figcaption>
        <h2
          id={headingId}
          className="font-display text-feature text-cohere-ink"
        >
          Why this score
        </h2>
        <p id={descId} className="mt-1 text-body text-slate">
          {match.job_title} at {match.employer_name} scored{" "}
          <span className="font-medium tabular-nums text-cohere-ink">
            {/* Floor, not round — every marketplace surface floors displayed
                scores so the same match never shows two different numbers. */}
            {score != null ? Math.floor(score) : "—"}
          </span>{" "}
          of 100
          {labelText ? ` · ${labelText}` : ""}
          {`, ${eligibilityText}`}
          {match.distance_miles != null
            ? match.distance_miles < 1
              ? ", less than a mile away"
              : `, about ${Math.round(match.distance_miles)} miles away`
            : ""}
          {match.confidence_level
            ? `. Confidence in this estimate is ${match.confidence_level}.`
            : "."}
        </p>
      </figcaption>

      <section aria-label="Score drivers" className="mt-5">
        <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
          What drives it
        </h3>
        <MatchDrivers
          dimensions={dimensions}
          gates={match.gates}
          className="mt-2"
        />
      </section>

      {score != null && distribution.n > 0 && (
        <section aria-label="Score in context" className="mt-6">
          <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
            Where it sits
          </h3>
          <ScoreInContext
            distribution={distribution}
            score={score}
            thresholds={thresholds}
            mode={contextMode}
            className="mt-2"
          />
        </section>
      )}

      <section aria-label="What could improve it" className="mt-6">
        <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
          What could improve it
        </h3>
        <ImprovementLevers
          match={match}
          dimensions={dimensions}
          className="mt-2"
        />
      </section>

      <details className="mt-6 border-t border-hairline pt-3">
        <summary className="cursor-pointer text-caption text-slate hover:text-cohere-ink">
          View as data table
        </summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-left text-caption">
            <thead>
              <tr className="border-b border-hairline text-slate-muted">
                <th scope="col" className="py-1.5 pr-4 font-medium">
                  Dimension
                </th>
                <th scope="col" className="py-1.5 pr-4 text-right font-medium">
                  Weight
                </th>
                <th scope="col" className="py-1.5 pr-4 text-right font-medium">
                  Score
                </th>
                <th scope="col" className="py-1.5 pr-4 text-right font-medium">
                  Contribution
                </th>
                <th scope="col" className="py-1.5 font-medium">
                  Rationale
                </th>
              </tr>
            </thead>
            <tbody>
              {dimensions.map((d) => (
                <tr key={d.dimension} className="border-b border-hairline align-top">
                  <th scope="row" className="py-1.5 pr-4 font-normal text-cohere-ink">
                    {dimensionLabel(d.dimension)}
                    {d.null_handling_applied ? " (estimated)" : ""}
                  </th>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-slate">
                    {fmt1(d.weight)}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-slate">
                    {fmt1(d.raw_score)}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums text-slate">
                    {fmt1(d.weighted_score)}
                  </td>
                  <td className="py-1.5 text-slate-muted">{d.rationale ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
