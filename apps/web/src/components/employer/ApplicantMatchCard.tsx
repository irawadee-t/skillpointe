/**
 * ApplicantMatchCard — compact match card for the employer's ranked applicant list.
 *
 * Shows (safe fields only — no user_id, no email):
 *   - Applicant name + program/trade
 *   - Location + geography note
 *   - Availability
 *   - Eligibility badge + fit label
 *   - Match score
 *   - Top 2 strengths (green) + top 2 gaps (orange)
 *   - Recommended next step
 *   - Confidence / review flags
 */
import type { ApplicantMatchSummary } from "@/lib/api/employer";
import {
  formatApplicantName,
  formatAvailability,
  formatWorkSetting,
} from "@/lib/api/employer";
import { EligibilityBadge, MatchLabel } from "@/components/matches/MatchLabel";

interface ApplicantMatchCardProps {
  match: ApplicantMatchSummary;
}

export function ApplicantMatchCard({ match }: ApplicantMatchCardProps) {
  const {
    first_name,
    last_name,
    city,
    state,
    program_name_raw,
    canonical_job_family_code,
    available_from_date,
    expected_completion_date,
    willing_to_relocate,
    willing_to_travel,
    eligibility_status,
    match_label,
    policy_adjusted_score,
    top_strengths,
    top_gaps,
    recommended_next_step,
    confidence_level,
    requires_review,
    geography_note,
  } = match;

  const name = formatApplicantName(first_name, last_name);
  const locationStr = [city, state].filter(Boolean).join(", ");
  const availability = formatAvailability(available_from_date, expected_completion_date);
  const programDisplay = canonical_job_family_code
    ? `${program_name_raw ?? ""} (${canonical_job_family_code})`
    : (program_name_raw ?? null);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 hover:border-gray-300 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900 text-base leading-snug truncate">
            {name}
          </h3>
          {programDisplay && (
            <p className="text-sm text-gray-500 mt-0.5 truncate">{programDisplay}</p>
          )}
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

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
      </div>

      {/* Location + availability */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-gray-600">
        {locationStr && <span>📍 {locationStr}</span>}
        {availability !== "Not set" && <span>📅 Available {availability}</span>}
      </div>

      {/* Geography note */}
      {geography_note && (
        <p className="mt-1 text-xs text-blue-600">{geography_note}</p>
      )}

      {/* Mobility indicators */}
      {(willing_to_relocate || willing_to_travel) && (
        <div className="flex gap-2 mt-2">
          {willing_to_relocate && (
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-2 py-0.5">
              Open to relocate
            </span>
          )}
          {willing_to_travel && (
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-2 py-0.5">
              Open to travel
            </span>
          )}
        </div>
      )}

      {/* Strengths */}
      {top_strengths.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {top_strengths.slice(0, 2).map((s, i) => (
            <span
              key={i}
              className="text-xs bg-green-50 text-green-700 border border-green-200 rounded px-2 py-0.5"
            >
              ✓ {_short(s)}
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
              △ {_short(g)}
            </span>
          ))}
        </div>
      )}

      {/* Recommended next step */}
      {recommended_next_step && (
        <p className="mt-3 text-sm text-gray-700 leading-snug">
          <span className="font-medium">Suggested:</span> {recommended_next_step}
        </p>
      )}

      {/* Flags */}
      {(confidence_level === "low" || requires_review) && (
        <div className="mt-3 flex gap-3 text-xs text-amber-600">
          {confidence_level === "low" && <span>⚠ Low confidence data</span>}
          {requires_review && <span>⚠ Needs review</span>}
        </div>
      )}
    </div>
  );
}

function _short(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 40) return text.slice(0, colonIdx);
  return text.length > 50 ? text.slice(0, 50) + "…" : text;
}
