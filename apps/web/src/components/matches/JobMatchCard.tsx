import Link from "next/link";
import {
  MapPin,
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
import { cn } from "@/lib/utils";

interface JobMatchCardProps {
  match: JobMatchSummary;
}

// A 3-px top rule colored by eligibility gives the list an instantly-scannable
// left-margin — green for eligible, coral for near-fit, muted for ineligible.
const ACCENT_BY_STATUS: Record<string, string> = {
  eligible:   "before:bg-cohere-green",
  near_fit:   "before:bg-studio-maroon",
  ineligible: "before:bg-slate-muted",
};

export function JobMatchCard({ match }: JobMatchCardProps) {
  const {
    match_id,
    job_title,
    employer_name,
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

  const locationStr = [job_city, job_state].filter((v) => v && !/^unspecified$/i.test(v.trim())).join(", ");
  const payStr = formatPay(pay_min, pay_max, pay_type);
  const score = policy_adjusted_score !== null ? Math.round(policy_adjusted_score) : null;
  const accentClass = ACCENT_BY_STATUS[eligibility_status] ?? "before:bg-hairline";

  return (
    <Link
      href={`/applicant/matches/${match_id}`}
      className={cn(
        "group relative block overflow-hidden rounded-xl border border-hairline bg-white p-5 shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-all duration-300 ease-cohere",
        // Eligibility accent — 3px top rule via ::before
        "before:absolute before:left-0 before:top-0 before:h-[3px] before:w-full before:content-['']",
        accentClass,
        // Warm-tinted hover + lift
        "hover:-translate-y-0.5 hover:border-cohere-ink/20 hover:shadow-[0_10px_28px_-14px_rgba(12,10,9,0.15)]",
      )}
    >
      {/* Header — title + editorial score */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-feature leading-snug text-cohere-ink">
            {job_title}
          </h3>
          <p className="mt-1 text-caption text-slate">
            {employer_name}
          </p>
        </div>

        {score !== null && (
          <div className="shrink-0 text-right">
            <div className="mono-label text-slate-muted">Fit</div>
            <div className="mt-0.5 font-display text-[2rem] leading-none tabular-nums text-cohere-ink">
              {score}
            </div>
          </div>
        )}
      </div>

      {/* Status pills */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <EligibilityBadge status={eligibility_status} />
        {match_label && <MatchLabel label={match_label} />}
      </div>

      {/* Meta row */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-caption text-slate">
        {locationStr && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3.5 w-3.5 text-slate-muted" />
            {locationStr}
            {work_setting && <span className="text-slate-muted">, {formatWorkSetting(work_setting)}</span>}
          </span>
        )}
        {!locationStr && work_setting && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3.5 w-3.5 text-slate-muted" />
            {formatWorkSetting(work_setting)}
          </span>
        )}
        {/* payStr carries its own "$" — an icon would read "$ $31". */}
        {pay_min !== null && <span>{payStr}</span>}
      </div>

      {geography_note && (
        <p className="mt-1.5 flex items-center gap-1 text-micro text-slate-muted">
          <Info className="h-3 w-3" />
          {geography_note}
        </p>
      )}

      {/* Match-why one-liner — the top-1 (or top-2 joined) reason this ranked
          well. Italic + forest green so it reads as an editorial aside, not
          a chip. Renders only when at least one strength is present. */}
      {top_strengths.length > 0 && (
        <p className="mt-2 flex items-center gap-1 text-caption italic text-studio-forest">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          Strong on: {formatWhyLine(top_strengths)}
        </p>
      )}

      {/* Strengths + Gaps — checkmark / caution + inline text, no filled pills */}
      {(top_strengths.length > 0 || top_gaps.length > 0) && (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-caption">
          {top_strengths.slice(0, 2).map((s, i) => (
            <li key={`s-${i}`} className="inline-flex items-center gap-1.5 text-cohere-ink">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-cohere-green" strokeWidth={2} />
              {shortRationale(s)}
            </li>
          ))}
          {top_gaps.slice(0, 2).map((g, i) => (
            <li key={`g-${i}`} className="inline-flex items-center gap-1.5 text-cohere-ink">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-studio-maroon" strokeWidth={2} />
              {shortRationale(g)}
            </li>
          ))}
        </ul>
      )}

      {/* Next step */}
      {recommended_next_step && (
        <p className="mt-3 text-caption leading-snug text-slate">
          <span className="font-medium text-ink">Next step:</span> {recommended_next_step}
        </p>
      )}

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between border-t border-hairline pt-3">
        <div className="flex items-center gap-3 text-micro text-slate-muted">
          {confidence_level === "low" && (
            <span className="flex items-center gap-1 text-studio-maroon">
              <AlertTriangle className="h-3 w-3" /> Low confidence
            </span>
          )}
          {requires_review && (
            <span className="flex items-center gap-1 text-slate">
              <Info className="h-3 w-3" /> Pending review
            </span>
          )}
        </div>
        <span className="flex items-center gap-1 text-caption font-medium text-slate-muted transition-colors group-hover:text-cohere-ink">
          View details <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
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

/**
 * Build the "Strong on: X + Y" tail from the top strengths. Strips the
 * post-colon detail so it reads as short keywords rather than a full
 * rationale. Joins the top 2 with " + " for a "trade + location" feel.
 */
function formatWhyLine(strengths: string[]): string {
  const parts = strengths
    .slice(0, 2)
    .map((s) => {
      const colonIdx = s.indexOf(":");
      const head = colonIdx > 0 && colonIdx < 40 ? s.slice(0, colonIdx) : s;
      return head.trim().toLowerCase();
    })
    .filter(Boolean);
  if (parts.length === 0) return "your profile";
  return parts.join(" + ");
}
