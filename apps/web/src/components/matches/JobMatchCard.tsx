/**
 * JobMatchCard — compact match card for the ranked jobs list.
 *
 * Shows:
 *   - job title + employer (partner star if applicable)
 *   - location / work setting + geography note
 *   - pay range if available
 *   - eligibility badge + match label badge
 *   - policy_adjusted_score (the display score per SCORING_CONFIG.yaml §ui_visibility)
 *   - 1–2 top strengths (green)
 *   - 1–2 top gaps (orange)
 *   - recommended next step
 *   - "View details" link
 */
import Link from "next/link";

import type { JobMatchSummary } from "@/lib/api/applicant";
import {
  formatMatchLabel,
  formatPay,
  formatWorkSetting,
} from "@/lib/api/applicant";
import { EligibilityBadge, MatchLabel } from "./MatchLabel";

interface JobMatchCardProps {
  match: JobMatchSummary;
}

export function JobMatchCard({ match }: JobMatchCardProps) {
  const {
    match_id,
    job_title,
    employer_name,
    is_partner_employer,
    job_city,
    job_state,
    work_setting,
    geography_note,
    pay_min,
    pay_max,
    pay_type,
    eligibility_status,
    match_label,
    policy_adjusted_score,
    top_strengths,
    top_gaps,
    recommended_next_step,
    confidence_level,
    requires_review,
  } = match;

  const locationStr = [job_city, job_state].filter(Boolean).join(", ");
  const payStr = formatPay(pay_min, pay_max, pay_type);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 hover:border-gray-300 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900 text-base leading-snug truncate">
            {job_title}
          </h3>
          <p className="text-sm text-gray-500 mt-0.5">
            {employer_name}
            {is_partner_employer && (
              <span
                className="ml-1 text-amber-500"
                title="SkillPointe partner employer"
              >
                ★
              </span>
            )}
          </p>
        </div>

        {/* Score */}
        {policy_adjusted_score !== null && (
          <div className="shrink-0 text-right">
            <div className="text-2xl font-bold text-gray-900 leading-none">
              {Math.round(policy_adjusted_score)}
            </div>
            <div className="text-xs text-gray-400 mt-0.5">/ 100</div>
          </div>
        )}
      </div>

      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
      </div>

      {/* Location + pay */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-gray-600">
        {locationStr && (
          <span>
            📍 {locationStr}
            {work_setting && ` · ${formatWorkSetting(work_setting)}`}
          </span>
        )}
        {!locationStr && work_setting && (
          <span>📍 {formatWorkSetting(work_setting)}</span>
        )}
        {pay_min !== null && <span>💰 {payStr}</span>}
      </div>

      {/* Geography note */}
      {geography_note && (
        <p className="mt-1 text-xs text-blue-600">{geography_note}</p>
      )}

      {/* Strengths */}
      {top_strengths.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {top_strengths.slice(0, 2).map((s, i) => (
            <span
              key={i}
              className="text-xs bg-green-50 text-green-700 border border-green-200 rounded px-2 py-0.5"
            >
              ✓ {_shortRationale(s)}
            </span>
          ))}
        </div>
      )}

      {/* Gaps */}
      {top_gaps.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {top_gaps.slice(0, 2).map((g, i) => (
            <span
              key={i}
              className="text-xs bg-orange-50 text-orange-700 border border-orange-200 rounded px-2 py-0.5"
            >
              △ {_shortRationale(g)}
            </span>
          ))}
        </div>
      )}

      {/* Next step */}
      {recommended_next_step && (
        <p className="mt-3 text-sm text-gray-700 leading-snug">
          <span className="font-medium">Next:</span> {recommended_next_step}
        </p>
      )}

      {/* Footer row */}
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
        <div className="flex items-center gap-3 text-xs text-gray-400">
          {confidence_level === "low" && (
            <span className="text-amber-600">⚠ Low confidence data</span>
          )}
          {requires_review && (
            <span className="text-amber-600">⚠ Needs review</span>
          )}
        </div>
        <Link
          href={`/applicant/matches/${match_id}`}
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          View details →
        </Link>
      </div>
    </div>
  );
}

/** Trim rationale strings for card display — first clause only. */
function _shortRationale(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 40) return text.slice(0, colonIdx);
  return text.length > 50 ? text.slice(0, 50) + "…" : text;
}
