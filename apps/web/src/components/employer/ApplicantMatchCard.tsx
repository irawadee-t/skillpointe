/**
 * ApplicantMatchCard — compact match card for the employer's ranked applicant list.
 *
 * Shows (safe fields only — no user_id, no email):
 *   - Applicant name + program/trade
 *   - Location + geography note
 *   - Availability
 *   - Eligibility badge + fit label
 *   - Match score
 *   - Top 2 strengths + top 2 gaps
 *   - Recommended next step
 *   - Confidence / review flags
 */
import {
  MapPin,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  Info,
  ThumbsUp,
  ThumbsDown,
  ClipboardCheck,
} from "lucide-react";

import type { ApplicantMatchSummary } from "@/lib/api/employer";
import {
  formatApplicantName,
  formatAvailability,
  formatWorkSetting,
} from "@/lib/api/employer";
import { EligibilityBadge, MatchLabel } from "@/components/matches/MatchLabel";
import { CandidateActions } from "./CandidateActions";

interface ApplicantMatchCardProps {
  match: ApplicantMatchSummary;
  jobId: string;
  jobTitle: string;
  token: string;
  isAdmin?: boolean;
}

export function ApplicantMatchCard({ match, jobId, jobTitle, token, isAdmin = false }: ApplicantMatchCardProps) {
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
    applicant_interest,
  } = match;

  const name = formatApplicantName(first_name, last_name);
  const locationStr = [city, state].filter(Boolean).join(", ");
  const availability = formatAvailability(available_from_date, expected_completion_date);
  const programDisplay = canonical_job_family_code
    ? `${program_name_raw ?? ""} (${canonical_job_family_code})`
    : (program_name_raw ?? null);

  return (
    <div className="bg-white border border-zinc-200 rounded-lg p-5 hover:border-zinc-200 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-zinc-900 text-base leading-snug truncate">
            {name}
          </h3>
          {programDisplay && (
            <p className="text-sm text-zinc-500 mt-0.5 truncate">{programDisplay}</p>
          )}
        </div>

        {/* Score */}
        {policy_adjusted_score !== null && (
          <div className="shrink-0 text-right">
            <div className="text-2xl font-bold text-spf-navy leading-none">
              {Math.round(policy_adjusted_score)}
            </div>
            <div className="text-xs text-zinc-400 mt-0.5">/ 100</div>
          </div>
        )}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
        {applicant_interest && <ApplicantInterestBadge level={applicant_interest} />}
      </div>

      {/* Location + availability */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-zinc-500">
        {locationStr && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-zinc-400" /> {locationStr}
          </span>
        )}
        {availability !== "Not set" && (
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 text-zinc-400" /> Available {availability}
          </span>
        )}
      </div>

      {/* Geography note */}
      {geography_note && (
        <p className="mt-1 text-xs text-zinc-400">{geography_note}</p>
      )}

      {/* Mobility indicators */}
      {(willing_to_relocate || willing_to_travel) && (
        <div className="flex gap-2 mt-2">
          {willing_to_relocate && (
            <span className="text-xs bg-zinc-100 text-zinc-500 border border-zinc-200 rounded-full px-2 py-0.5">
              Open to relocate
            </span>
          )}
          {willing_to_travel && (
            <span className="text-xs bg-zinc-100 text-zinc-500 border border-zinc-200 rounded-full px-2 py-0.5">
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
              className="inline-flex items-center gap-1 text-xs bg-emerald-50 text-emerald-600 border border-emerald-200 rounded-md px-2 py-0.5"
            >
              <CheckCircle2 className="w-3 h-3" /> {_short(s)}
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
              className="inline-flex items-center gap-1 text-xs bg-rose-50 text-rose-600 border border-rose-200 rounded-md px-2 py-0.5"
            >
              <AlertTriangle className="w-3 h-3" /> {_short(g)}
            </span>
          ))}
        </div>
      )}

      {/* Recommended next step */}
      {recommended_next_step && (
        <p className="mt-3 text-sm text-zinc-600 leading-snug">
          <span className="font-medium text-zinc-700">Suggested:</span> {recommended_next_step}
        </p>
      )}

      {/* Flags */}
      {(confidence_level === "low" || requires_review) && (
        <div className="mt-3 flex gap-3 text-xs text-zinc-400">
          {confidence_level === "low" && (
            <span className="flex items-center gap-1 text-amber-600">
              <AlertTriangle className="w-3 h-3" /> Low confidence
            </span>
          )}
          {requires_review && (
            <span className="flex items-center gap-1 text-zinc-500">
              <Info className="w-3 h-3" /> Pending review
            </span>
          )}
        </div>
      )}

      {/* Actions: reach out + hire — hidden for admin (admin cannot act as employer) */}
      {!isAdmin && (
        <CandidateActions
          matchId={match.match_id}
          applicantId={match.applicant_id}
          jobId={jobId}
          applicantName={name}
          jobTitle={jobTitle}
          token={token}
        />
      )}
    </div>
  );
}

function ApplicantInterestBadge({ level }: { level: string }) {
  if (level === "applied") {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-emerald-50 text-emerald-600 border border-emerald-200 rounded-full px-2 py-0.5">
        <ClipboardCheck className="w-3 h-3" /> Candidate applied
      </span>
    );
  }
  if (level === "interested") {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-spf-navy/10 text-spf-navy border border-spf-navy/20 rounded-full px-2 py-0.5">
        <ThumbsUp className="w-3 h-3" /> Candidate interested
      </span>
    );
  }
  if (level === "not_interested") {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-zinc-100 text-zinc-400 border border-zinc-200 rounded-full px-2 py-0.5">
        <ThumbsDown className="w-3 h-3" /> Not interested
      </span>
    );
  }
  return null;
}

function _short(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 40) return text.slice(0, colonIdx);
  return text.length > 50 ? text.slice(0, 50) + "…" : text;
}
