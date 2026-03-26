import Link from "next/link";
import {
  MapPin,
  DollarSign,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Info,
} from "lucide-react";

import type { JobMatchSummary } from "@/lib/api/applicant";
import {
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
  const score = policy_adjusted_score !== null ? Math.round(policy_adjusted_score) : null;

  return (
    <Link
      href={`/applicant/matches/${match_id}`}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition-all block group"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-white text-base leading-snug">
            {job_title}
          </h3>
          <p className="text-sm text-zinc-400 mt-0.5 flex items-center gap-1">
            {employer_name}
          </p>
        </div>

        {/* Score */}
        {score !== null && (
          <div className="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold bg-zinc-800 text-cyan-400">
            {score}
          </div>
        )}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-zinc-400">
        {locationStr && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-zinc-500" />
            {locationStr}
            {work_setting && <span className="text-zinc-500"> · {formatWorkSetting(work_setting)}</span>}
          </span>
        )}
        {!locationStr && work_setting && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-zinc-500" />
            {formatWorkSetting(work_setting)}
          </span>
        )}
        {pay_min !== null && (
          <span className="flex items-center gap-1">
            <DollarSign className="w-3.5 h-3.5 text-zinc-500" />
            {payStr}
          </span>
        )}
      </div>

      {geography_note && (
        <p className="mt-1.5 text-xs text-zinc-500 flex items-center gap-1">
          <Info className="w-3 h-3" />
          {geography_note}
        </p>
      )}

      {/* Strengths + Gaps */}
      {(top_strengths.length > 0 || top_gaps.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {top_strengths.slice(0, 2).map((s, i) => (
            <span
              key={`s-${i}`}
              className="inline-flex items-center gap-1 text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-md px-2 py-0.5"
            >
              <CheckCircle2 className="w-3 h-3" />
              {shortRationale(s)}
            </span>
          ))}
          {top_gaps.slice(0, 2).map((g, i) => (
            <span
              key={`g-${i}`}
              className="inline-flex items-center gap-1 text-xs bg-rose-500/10 text-rose-400 border border-rose-500/30 rounded-md px-2 py-0.5"
            >
              <AlertTriangle className="w-3 h-3" />
              {shortRationale(g)}
            </span>
          ))}
        </div>
      )}

      {/* Next step */}
      {recommended_next_step && (
        <p className="mt-3 text-sm text-zinc-300 leading-snug">
          <span className="font-medium text-zinc-200">Next step:</span> {recommended_next_step}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-zinc-800">
        <div className="flex items-center gap-3 text-xs text-zinc-500">
          {confidence_level === "low" && (
            <span className="flex items-center gap-1 text-amber-400">
              <AlertTriangle className="w-3 h-3" /> Low confidence
            </span>
          )}
          {requires_review && (
            <span className="flex items-center gap-1 text-zinc-400">
              <Info className="w-3 h-3" /> Pending review
            </span>
          )}
        </div>
        <span className="text-sm font-medium text-zinc-500 group-hover:text-cyan-400 flex items-center gap-1 transition-colors">
          View details <ChevronRight className="w-4 h-4" />
        </span>
      </div>
    </Link>
  );
}

function shortRationale(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 40) return text.slice(0, colonIdx);
  return text.length > 45 ? text.slice(0, 45) + "..." : text;
}
