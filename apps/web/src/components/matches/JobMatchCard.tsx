import Link from "next/link";
import {
  MapPin,
  DollarSign,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Star,
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
      className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-300 hover:shadow-sm transition-all block group"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-gray-900 text-base leading-snug group-hover:text-spf-navy transition-colors">
            {job_title}
          </h3>
          <p className="text-sm text-gray-500 mt-0.5 flex items-center gap-1">
            {employer_name}
            {is_partner_employer && (
              <Star className="w-3.5 h-3.5 text-spf-orange fill-spf-orange" />
            )}
          </p>
        </div>

        {/* Score ring */}
        {score !== null && <ScoreIndicator score={score} />}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-gray-600">
        {locationStr && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-gray-400" />
            {locationStr}
            {work_setting && <span className="text-gray-400"> · {formatWorkSetting(work_setting)}</span>}
          </span>
        )}
        {!locationStr && work_setting && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-gray-400" />
            {formatWorkSetting(work_setting)}
          </span>
        )}
        {pay_min !== null && (
          <span className="flex items-center gap-1">
            <DollarSign className="w-3.5 h-3.5 text-gray-400" />
            {payStr}
          </span>
        )}
      </div>

      {geography_note && (
        <p className="mt-1.5 text-xs text-spf-navy/70 flex items-center gap-1">
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
              className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded-md px-2 py-0.5"
            >
              <CheckCircle2 className="w-3 h-3" />
              {shortRationale(s)}
            </span>
          ))}
          {top_gaps.slice(0, 2).map((g, i) => (
            <span
              key={`g-${i}`}
              className="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-md px-2 py-0.5"
            >
              <AlertTriangle className="w-3 h-3" />
              {shortRationale(g)}
            </span>
          ))}
        </div>
      )}

      {/* Next step */}
      {recommended_next_step && (
        <p className="mt-3 text-sm text-gray-600 leading-snug">
          <span className="font-medium text-gray-800">Next step:</span> {recommended_next_step}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
        <div className="flex items-center gap-3 text-xs text-gray-400">
          {confidence_level === "low" && (
            <span className="flex items-center gap-1 text-amber-500">
              <AlertTriangle className="w-3 h-3" /> Low confidence
            </span>
          )}
          {requires_review && (
            <span className="flex items-center gap-1 text-amber-500">
              <Info className="w-3 h-3" /> Pending review
            </span>
          )}
        </div>
        <span className="text-sm font-medium text-spf-navy group-hover:underline flex items-center gap-1">
          View details <ChevronRight className="w-4 h-4" />
        </span>
      </div>
    </Link>
  );
}

function ScoreIndicator({ score }: { score: number }) {
  const color = score >= 80 ? "text-green-600" : score >= 60 ? "text-spf-navy" : score >= 40 ? "text-amber-600" : "text-gray-400";
  const bgColor = score >= 80 ? "stroke-green-500" : score >= 60 ? "stroke-spf-navy" : score >= 40 ? "stroke-amber-500" : "stroke-gray-300";
  const circumference = 2 * Math.PI * 18;
  const filled = (score / 100) * circumference;

  return (
    <div className="relative w-14 h-14 shrink-0">
      <svg className="w-14 h-14 -rotate-90" viewBox="0 0 40 40">
        <circle cx="20" cy="20" r="18" fill="none" strokeWidth="3" className="stroke-gray-100" />
        <circle
          cx="20" cy="20" r="18" fill="none" strokeWidth="3"
          className={bgColor}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
        />
      </svg>
      <div className={`absolute inset-0 flex flex-col items-center justify-center ${color}`}>
        <span className="text-base font-bold leading-none tabular-nums">{score}</span>
      </div>
    </div>
  );
}

function shortRationale(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 40) return text.slice(0, colonIdx);
  return text.length > 45 ? text.slice(0, 45) + "..." : text;
}
