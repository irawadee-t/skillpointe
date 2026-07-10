"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  Target,
  TrendingUp,
  Building2,
  MapPin,
  DollarSign,
  CheckCircle2,
  AlertTriangle,
  Briefcase,
  Shield,
  ExternalLink,
  ClipboardList,
  GraduationCap,
  Wrench,
  FileText,
  Star,
  Info,
} from "lucide-react";

import { motion, AnimatePresence } from "motion/react";

import type {
  JobMatchSummary,
  RankedMatchesResponse,
} from "@/lib/api/applicant";
import { InterestSignalPanel } from "@/components/matches/InterestSignalPanel";
import { PageHeader, Stagger, StaggerItem, MonoLabel } from "@/components/ui";
import { easeCohere } from "@/lib/motion";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface Props {
  data: RankedMatchesResponse | null;
  fetchError: string | null;
  token: string;
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function MatchesClient({ data, fetchError, token }: Props) {
  if (fetchError) {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-studio-maroon/10 border border-studio-maroon-soft rounded-md p-5 text-caption text-error-red flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {fetchError}
          </div>
        </div>
      </main>
    );
  }

  const matches = data;
  const eligibleCount = matches?.total_eligible ?? 0;
  const nearFitCount = matches?.total_near_fit ?? 0;
  const totalMatches = eligibleCount + nearFitCount;

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <BackLink />

        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-cohere-ink">
            Your job matches
          </h1>
          <p className="mt-1.5 text-sm text-slate">
            Ranked by how well each role fits your trade, location, and background.
          </p>
        </div>

        {matches?.has_matches && (
          <div className="flex divide-x divide-hairline rounded-lg border border-hairline bg-white">
            <SummaryStat label="Total matches" value={totalMatches} />
            <SummaryStat label="Ready to apply" value={eligibleCount} highlight={eligibleCount > 0} />
            <SummaryStat label="Close matches" value={nearFitCount} />
          </div>
        )}

        {!matches?.has_matches ? (
          <NoMatchesCard
            profileHasFamily={matches?.profile_has_family ?? false}
            profileHasLocation={matches?.profile_has_location ?? false}
          />
        ) : (
          <>
            {/* Eligible Section — editorial list, hairline-divided rows, no per-item borders */}
            <section>
              <h2 className="text-base font-semibold text-cohere-ink">
                Ready to apply <span className="ml-1 font-normal text-slate-muted">{eligibleCount}</span>
              </h2>
              <div className="mt-3">
                {matches.eligible_matches.length === 0 ? (
                  <EmptySection message="Nothing here yet. Finish the rest of your profile to see jobs you're ready to apply to." />
                ) : (
                  <div className="divide-y divide-hairline rounded-lg border border-hairline bg-white shadow-subtle">
                    {matches.eligible_matches.map((m) => (
                      <div key={m.match_id} className="px-6">
                        <MatchRow match={m} token={token} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* Near-fit Section */}
            <section>
              <h2 className="text-base font-semibold text-cohere-ink">
                Close matches <span className="ml-1 font-normal text-slate-muted">{nearFitCount}</span>
              </h2>
              <div className="mt-3">
                {matches.near_fit_matches.length === 0 ? (
                  <EmptySection message="No near-fit matches right now." />
                ) : (
                  <div className="divide-y divide-hairline rounded-lg border border-hairline bg-white shadow-subtle">
                    {matches.near_fit_matches.map((m) => (
                      <div key={m.match_id} className="px-6">
                        <MatchRow match={m} token={token} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  Match Card                                                         */
/* ------------------------------------------------------------------ */

const WORK_SETTING_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  on_site: "On-site",
  flexible: "Flexible",
};

function MatchCard({ match, token }: { match: JobMatchSummary; token: string }) {
  const [expanded, setExpanded] = useState(false);

  const score = match.policy_adjusted_score
    ? Math.round(match.policy_adjusted_score)
    : null;
  const location = [match.job_city, match.job_state].filter((v) => v && !/^unspecified$/i.test(v.trim())).join(", ");
  const workLabel = match.work_setting
    ? (WORK_SETTING_LABELS[match.work_setting] ?? match.work_setting)
    : null;
  const payDisplay = formatPay(match);
  const hasDetail = !!(
    match.description_raw ||
    match.requirements_raw ||
    match.preferred_qualifications_raw
  );
  const familyLabel = match.canonical_job_family_code
    ? match.canonical_job_family_code
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  const eligible = match.eligibility_status === "eligible";
  // Left rule keyed to eligibility — green (eligible), coral (near), stone (ineligible).
  // A left border reads more editorial than a top rule and doesn't compete with the title.
  const railClass =
    match.eligibility_status === "eligible"
      ? "border-l-cohere-green"
      : match.eligibility_status === "near_fit"
        ? "border-l-cohere-coral"
        : "border-l-hairline";

  const metaBits = [
    location || null,
    workLabel,
    payDisplay,
    familyLabel,
  ].filter(Boolean) as string[];

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-hairline border-l-[3px] bg-white transition-shadow duration-300 hover:shadow-[0_10px_28px_-14px_rgba(12,10,9,0.15)] ${railClass}`}
    >
      <div className="p-7">
        {/* Header — title left, score right. No mono labels, no chip. */}
        <div className="flex items-start justify-between gap-8">
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-heading leading-[1.1] text-cohere-ink">
              {match.job_title}
            </h3>
            <p className="mt-2 text-body-lg text-cohere-ink">
              {match.employer_name}
            </p>
            {metaBits.length > 0 && (
              <p className="mt-1 text-body text-slate">
                {metaBits.join(", ")}
              </p>
            )}
          </div>

          {score !== null && (
            <div className="shrink-0 text-right">
              <div className="font-display text-[3rem] leading-none tabular-nums text-cohere-ink">
                {score}
              </div>
              <div className="mt-1 text-caption text-slate">
                {score >= 85 ? "Strong fit" : eligible ? "Good fit" : "Near fit"}
              </div>
            </div>
          )}
        </div>

        {/* Strengths and gaps — body-sized, one per line for scannability. */}
        {!expanded && (match.top_strengths.length > 0 || match.top_gaps.length > 0) && (
          <ul className="mt-5 space-y-1.5 text-body">
            {match.top_strengths.slice(0, 2).map((s, i) => (
              <li key={`s-${i}`} className="flex items-start gap-2 text-cohere-ink">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-cohere-green" strokeWidth={2} />
                <span>{shortLabel(s)}</span>
              </li>
            ))}
            {match.top_gaps.slice(0, 2).map((g, i) => (
              <li key={`g-${i}`} className="flex items-start gap-2 text-cohere-ink">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-studio-maroon" strokeWidth={2} />
                <span>{shortLabel(g)}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Actions — right-aligned, secondary details next to primary */}
        <div className="mt-6 flex items-center justify-end gap-4">
          {hasDetail && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-body text-slate underline decoration-hairline underline-offset-4 hover:text-cohere-ink hover:decoration-cohere-ink"
            >
              {expanded ? "Show less" : "See details"}
            </button>
          )}
          {match.source_url && (
            <a
              href={match.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary inline-flex items-center gap-1.5"
            >
              Apply <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>

        {/* Row 5: Interest signal — always visible */}
        <div className="mt-3 pt-3 border-t border-border-light">
          <InterestSignalPanel
            matchId={match.match_id}
            sourceUrl={match.source_url}
            initialSignal={match.applicant_interest ?? null}
            token={token}
          />
        </div>
      </div>

      {/* Expanded section: job details + match breakdown */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easeCohere }}
            className="overflow-hidden"
          >
            <ExpandedMatchContent match={match} hasDetail={hasDetail} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Match Row — Cohere Research–style editorial list row               */
/* ------------------------------------------------------------------ */

/**
 * A single match rendered as a hairline-divided list row, no card border.
 * Category chip → big display title → body meta line → strengths → apply.
 * Modelled directly on cohere.com/research row treatment.
 */
function MatchRow({ match, token }: { match: JobMatchSummary; token: string }) {
  const [expanded, setExpanded] = useState(false);

  const score = match.policy_adjusted_score
    ? Math.round(match.policy_adjusted_score)
    : null;
  const location = [match.job_city, match.job_state].filter((v) => v && !/^unspecified$/i.test(v.trim())).join(", ");
  const workLabel = match.work_setting
    ? (WORK_SETTING_LABELS[match.work_setting] ?? match.work_setting)
    : null;
  const payDisplay = formatPay(match);
  const hasDetail = !!(
    match.description_raw ||
    match.requirements_raw ||
    match.preferred_qualifications_raw
  );
  const familyLabel = match.canonical_job_family_code
    ? match.canonical_job_family_code
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  const eligible = match.eligibility_status === "eligible";
  const isStrong = score !== null && score >= 85;
  const fitLabel = score !== null ? (isStrong ? "Strong fit" : eligible ? "Good fit" : "Near fit") : null;
  // Color rhetoric on the dark palette:
  //   maroon  — strong fit (≥85), prestige / brand-tie moment
  //   forest  — eligible / good fit, positive default
  //   sienna  — near fit, attention accent
  //   grey    — ineligible / muted
  const fitToneClass = isStrong
    ? "text-studio-maroon"
    : match.eligibility_status === "eligible"
      ? "text-studio-forest"
      : match.eligibility_status === "near_fit"
        ? "text-studio-maroon"
        : "text-studio-grey-brown";

  const metaBits = [
    match.employer_name,
    location || null,
    workLabel,
    payDisplay,
  ].filter(Boolean) as string[];

  return (
    <article className="group grid grid-cols-[1fr_auto] gap-6 py-5">
      <div className="min-w-0">
        {/* Category tag row — small caps, dashboard-scale */}
        <div className="flex flex-wrap items-center gap-2 text-[11px] leading-none">
          {fitLabel && (
            <span className={`font-semibold uppercase tracking-[0.06em] ${fitToneClass}`}>
              {fitLabel}
            </span>
          )}
          {fitLabel && familyLabel && <span aria-hidden className="text-slate-muted">—</span>}
          {familyLabel && (
            <span className="text-slate-muted">{familyLabel}</span>
          )}
        </div>

        {/* Item title */}
        <h3 className="mt-1.5 text-body-lg font-medium leading-snug text-cohere-ink">
          {match.job_title}
        </h3>

        {/* Meta line */}
        {metaBits.length > 0 && (
          <p className="mt-0.5 text-caption text-slate-muted">
            {metaBits.join(", ")}
          </p>
        )}

        {/* Strengths / gaps — 13px, one per line */}
        {(match.top_strengths.length > 0 || match.top_gaps.length > 0) && (
          <ul className="mt-2.5 space-y-1 text-[13px]">
            {match.top_strengths.slice(0, 2).map((s, i) => (
              <li key={`s-${i}`} className="flex items-start gap-1.5 text-cohere-ink">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cohere-green" strokeWidth={2} />
                <span>{shortLabel(s)}</span>
              </li>
            ))}
            {match.top_gaps.slice(0, 2).map((g, i) => (
              <li key={`g-${i}`} className="flex items-start gap-1.5 text-cohere-ink">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-studio-maroon" strokeWidth={2} />
                <span>{shortLabel(g)}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Actions row */}
        <div className="mt-3 flex items-center gap-4">
          {match.source_url && (
            <a
              href={match.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary-sm inline-flex items-center gap-1.5"
            >
              Apply <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
          {hasDetail && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[13px] text-slate underline decoration-hairline underline-offset-2 transition-colors hover:text-cohere-ink hover:decoration-cohere-ink"
            >
              {expanded ? "Show less" : "See details"}
            </button>
          )}
        </div>

        {/* Expanded detail */}
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: easeCohere }}
              className="overflow-hidden"
            >
              <div className="mt-4 rounded-lg border border-hairline bg-white">
                <ExpandedMatchContent match={match} hasDetail={hasDetail} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Interest signal — kept but denser */}
        <div className="mt-4 border-t border-hairline pt-3">
          <InterestSignalPanel
            matchId={match.match_id}
            sourceUrl={match.source_url}
            initialSignal={match.applicant_interest ?? null}
            token={token}
          />
        </div>
      </div>

      {/* Score column — right side, dashboard-scale number */}
      {score !== null && (
        <div className="shrink-0 pt-0.5 text-right">
          <div className="text-2xl font-semibold leading-none tabular-nums text-cohere-ink">
            {score}
          </div>
          <div className="mt-1 text-[11px] text-slate-muted">of 100</div>
        </div>
      )}
    </article>
  );
}

/* ------------------------------------------------------------------ */
/*  Expanded match content                                             */
/* ------------------------------------------------------------------ */

function ExpandedMatchContent({
  match,
  hasDetail,
}: {
  match: JobMatchSummary;
  hasDetail: boolean;
}) {
  const [showScoring, setShowScoring] = useState(false);

  return (
    <div className="border-t border-border-light">
      {/* Match analysis */}
      <div className="px-5 py-4 space-y-4">
        {/* Why you match */}
        {match.top_strengths.length > 0 && (
          <div>
            <h4 className="text-micro font-semibold text-slate-muted tracking-wide mb-2">
              Why you match
            </h4>
            <div className="space-y-1.5">
              {match.top_strengths.map((s, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-caption text-slate"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-cohere-green shrink-0 mt-0.5" />
                  <span>{humanize(s)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* What to work on */}
        {match.top_gaps.length > 0 && (
          <div>
            <h4 className="text-micro font-semibold text-slate-muted tracking-wide mb-2">
              What to work on
            </h4>
            <div className="space-y-1.5">
              {match.top_gaps.map((g, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-caption text-slate"
                >
                  <AlertTriangle className="w-3.5 h-3.5 text-studio-maroon shrink-0 mt-0.5" />
                  <span>{humanize(g)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Scoring breakdown toggle */}
        <button
          onClick={() => setShowScoring(!showScoring)}
          className="flex items-center gap-1.5 text-micro text-slate-muted hover:text-ink transition-colors"
        >
          <Info className="w-3.5 h-3.5" />
          {showScoring ? "Hide" : "View"} scoring details
          {showScoring ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </button>

        {showScoring && <ScoringBreakdown match={match} />}
      </div>

      {/* Job description */}
      {hasDetail && (
        <div className="border-t border-border-light px-5 py-4 bg-stone space-y-5">
          <h4 className="text-micro font-semibold text-slate-muted tracking-wide">
            About this role
          </h4>
          <StructuredDescription
            description={match.description_raw}
            requirements={match.requirements_raw}
            qualifications={match.preferred_qualifications_raw}
          />
          {match.source_url && (
            <div className="pt-2">
              <a
                href={match.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary inline-flex items-center gap-2"
              >
                Apply for this position{" "}
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Scoring breakdown (for explainability)                             */
/* ------------------------------------------------------------------ */

function ScoringBreakdown({ match }: { match: JobMatchSummary }) {
  const score = match.policy_adjusted_score
    ? Math.round(match.policy_adjusted_score)
    : null;

  return (
    <div className="bg-stone rounded-sm p-3 text-micro text-slate space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-medium text-ink">Overall score</span>
        <span className="font-bold text-cohere-blue">{score ?? "—"}/100</span>
      </div>
      <div className="flex items-center justify-between">
        <span>Eligibility</span>
        <span className="text-ink">
          {match.eligibility_status === "eligible"
            ? "Eligible"
            : "Near-fit"}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span>Confidence</span>
        <span>{match.confidence_level ?? "—"}</span>
      </div>
      <p className="text-slate-muted pt-1 border-t border-hairline">
        Score reflects trade alignment, geography, credentials, timing, and
        job requirements. For a full breakdown, visit{" "}
        <Link
          href={`/applicant/matches/${match.match_id}`}
          className="text-cohere-blue hover:text-cohere-ink"
        >
          match details
        </Link>
        .
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Structured Description (shared with jobs page)                     */
/* ------------------------------------------------------------------ */

function StructuredDescription({
  description,
  requirements,
  qualifications,
}: {
  description: string | null;
  requirements: string | null;
  qualifications: string | null;
}) {
  const sections = parseDescriptionIntoSections(description || "");
  const hasExplicitReqs = !!requirements;
  const hasExplicitQuals = !!qualifications;

  return (
    <div className="space-y-5">
      {sections.map((section, i) => (
        <DescriptionSection key={i} section={section} />
      ))}
      {hasExplicitReqs && (
        <DescriptionSection
          section={{
            title: "Requirements",
            icon: "requirements",
            items: classifyLines(
              requirements!
                .split("\n")
                .map((l) => l.trim())
                .filter(Boolean)
            ),
          }}
        />
      )}
      {hasExplicitQuals && (
        <DescriptionSection
          section={{
            title: "Qualifications",
            icon: "qualifications",
            items: classifyLines(
              qualifications!
                .split("\n")
                .map((l) => l.trim())
                .filter(Boolean)
            ),
          }}
        />
      )}
    </div>
  );
}

interface Section {
  title: string;
  icon:
    | "overview"
    | "responsibilities"
    | "requirements"
    | "qualifications"
    | "preferred"
    | "benefits"
    | "other";
  items: SectionItem[];
}

type SectionItem =
  | { type: "paragraph"; text: string }
  | { type: "bullet"; text: string };

const SECTION_ICONS: Record<string, React.ReactNode> = {
  overview: <Briefcase className="w-4 h-4 text-slate" />,
  responsibilities: <ClipboardList className="w-4 h-4 text-slate" />,
  requirements: <Wrench className="w-4 h-4 text-slate" />,
  qualifications: <GraduationCap className="w-4 h-4 text-slate" />,
  preferred: <Star className="w-4 h-4 text-slate" />,
  benefits: <FileText className="w-4 h-4 text-slate" />,
  other: <FileText className="w-4 h-4 text-slate" />,
};

function DescriptionSection({ section }: { section: Section }) {
  return (
    <div>
      <h4 className="text-caption font-semibold text-ink flex items-center gap-1.5 mb-2">
        {SECTION_ICONS[section.icon]}
        {section.title}
      </h4>
      <div className="text-caption text-slate leading-relaxed">
        {section.items.map((item, i) =>
          item.type === "bullet" ? (
            <div key={i} className="flex items-start gap-2 py-0.5">
              <span className="w-1.5 h-1.5 bg-cohere-coral rounded-full mt-1.5 shrink-0" />
              <span>{item.text}</span>
            </div>
          ) : (
            <p key={i} className={i > 0 ? "mt-2" : ""}>
              {item.text}
            </p>
          )
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Description parser (mirrors JobBrowseClient)                       */
/* ------------------------------------------------------------------ */

const SECTION_HEADERS: {
  pattern: RegExp;
  title: string;
  icon: Section["icon"];
}[] = [
  {
    pattern:
      /^(?:about\s+(?:the\s+)?(?:role|position|job|opportunity)|job\s+description|overview|summary|position\s+summary)[\s:]*$/i,
    title: "About the role",
    icon: "overview",
  },
  {
    pattern:
      /^(?:what\s+you(?:'ll|.will)\s+do|(?:key\s+)?responsibilities|duties|your\s+(?:impactful\s+)?responsibilities|a\s+typical\s+day|day[- ]to[- ]day)[\s:]*$/i,
    title: "Responsibilities",
    icon: "responsibilities",
  },
  {
    pattern:
      /^(?:you(?:'ll|.will)\s+have\.{0,3}|what\s+(?:we(?:'re)?\s+(?:looking|need)|you\s+(?:need|bring))|requirements?|minimum\s+qualifications?|basic\s+qualifications?|who\s+you\s+are|this\s+may\s+be\s+the\s+next)[\s:]*$/i,
    title: "Requirements",
    icon: "requirements",
  },
  {
    pattern:
      /^(?:even\s+better,?\s+you\s+may\s+have\.{0,3}|preferred\s+qualifications?|nice\s+to\s+have|bonus\s+(?:skills|qualifications)|additional\s+qualifications?)[\s:]*$/i,
    title: "Preferred",
    icon: "preferred",
  },
  {
    pattern:
      /^(?:what\s+we\s+(?:offer|have|provide)|benefits?|compensation\s+(?:and|&)\s+benefits|perks|why\s+(?:join|work)|what(?:'s|\s+is)\s+in\s+it\s+for\s+you)[\s:]*$/i,
    title: "Benefits",
    icon: "benefits",
  },
  {
    pattern: /^(?:on\s+some\s+days)[\s:]*$/i,
    title: "Additional duties",
    icon: "responsibilities",
  },
  {
    pattern: /^(?:how\s+you(?:'ll)?\s+help|your\s+role)[\s:]*$/i,
    title: "About the role",
    icon: "overview",
  },
];

function parseDescriptionIntoSections(raw: string): Section[] {
  if (!raw || !raw.trim()) return [];
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const rawSections: {
    title: string;
    icon: Section["icon"];
    lines: string[];
  }[] = [];
  let currentTitle = "About the role";
  let currentIcon: Section["icon"] = "overview";
  let currentLines: string[] = [];

  for (const line of lines) {
    let matchedHeader = false;
    for (const sh of SECTION_HEADERS) {
      if (sh.pattern.test(line)) {
        if (currentLines.length > 0) {
          rawSections.push({
            title: currentTitle,
            icon: currentIcon,
            lines: [...currentLines],
          });
        }
        currentTitle = sh.title;
        currentIcon = sh.icon;
        currentLines = [];
        matchedHeader = true;
        break;
      }
    }
    if (!matchedHeader) {
      currentLines.push(line);
    }
  }
  if (currentLines.length > 0) {
    rawSections.push({
      title: currentTitle,
      icon: currentIcon,
      lines: currentLines,
    });
  }
  if (rawSections.length === 0) return [];
  return rawSections.map((rs) => ({
    title: rs.title,
    icon: rs.icon,
    items: classifyLines(rs.lines),
  }));
}

function classifyLines(lines: string[]): SectionItem[] {
  if (lines.length === 0) return [];
  const items: SectionItem[] = [];
  let paragraphBuffer: string[] = [];

  const flushParagraph = () => {
    if (paragraphBuffer.length > 0) {
      items.push({ type: "paragraph", text: paragraphBuffer.join(" ") });
      paragraphBuffer = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (
      /^\s*[-•·▪►◆★✓✔]\s+/.test(line) ||
      /^\s*\d+[.)]\s+/.test(line) ||
      /^\s*[a-z][.)]\s+/.test(line)
    ) {
      flushParagraph();
      items.push({
        type: "bullet",
        text: line
          .replace(/^\s*[-•·▪►◆★✓✔]\s+/, "")
          .replace(/^\s*\d+[.)]\s+/, "")
          .replace(/^\s*[a-z][.)]\s+/, "")
          .trim(),
      });
      continue;
    }
    const isShortActionLine =
      line.length < 250 &&
      /^[A-Z]/.test(line) &&
      !line.endsWith(",") &&
      (line.endsWith(".") || line.endsWith(":") || !line.includes(". "));
    const prevIsBullet =
      items.length > 0 && items[items.length - 1].type === "bullet";
    const nextIsShort = i + 1 < lines.length && lines[i + 1].length < 250;
    if (
      isShortActionLine &&
      (prevIsBullet ||
        (i > 0 && paragraphBuffer.length === 0 && nextIsShort))
    ) {
      flushParagraph();
      items.push({ type: "bullet", text: line });
      continue;
    }
    if (line.length > 200 && line.includes(". ")) {
      paragraphBuffer.push(line);
    } else if (paragraphBuffer.length > 0 && line.length > 150) {
      paragraphBuffer.push(line);
    } else if (paragraphBuffer.length === 0 && i === 0 && line.length > 80) {
      paragraphBuffer.push(line);
    } else if (
      items.length === 0 &&
      paragraphBuffer.length === 0 &&
      line.length > 60
    ) {
      paragraphBuffer.push(line);
    } else {
      flushParagraph();
      items.push({ type: "bullet", text: line });
    }
  }
  flushParagraph();

  const bulletCount = items.filter((it) => it.type === "bullet").length;
  const paraCount = items.filter((it) => it.type === "paragraph").length;
  if (paraCount > 3 && bulletCount === 0) {
    return items.map((it) =>
      it.type === "paragraph" && it.text.length < 300
        ? ({ type: "bullet", text: it.text } as const)
        : it
    );
  }
  return items;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function SummaryStat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className="flex-1 px-4 py-3">
      <div className={`text-xl font-semibold tabular-nums ${highlight ? "text-cohere-green" : "text-cohere-ink"}`}>
        {value.toLocaleString()}
      </div>
      <div className="mt-0.5 text-[12px] text-slate">{label}</div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/applicant"
      className="text-caption text-slate hover:text-cohere-ink inline-flex items-center gap-1 transition-colors"
    >
      <ChevronLeft className="w-4 h-4" /> Dashboard
    </Link>
  );
}

function EmptySection({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-4 py-6">
      <p className="mx-auto max-w-prose text-center text-[13px] text-slate">{message}</p>
    </div>
  );
}

function NoMatchesCard({
  profileHasFamily,
  profileHasLocation,
}: {
  profileHasFamily: boolean;
  profileHasLocation: boolean;
}) {
  return (
    <div className="bg-stone border border-transparent rounded-md p-10 text-center">
      <Briefcase className="w-8 h-8 text-slate-muted mx-auto" />
      <p className="font-display text-feature text-cohere-ink mt-3">
        No matches yet
      </p>
      <p className="text-caption text-slate mt-2">
        Finish your profile to see jobs you&apos;re ready to apply to.
      </p>
      {!profileHasFamily && (
        <p className="flex items-center justify-center gap-1.5 text-micro text-slate mt-4">
          <AlertCircle className="w-3.5 h-3.5 text-studio-maroon" />
          Your trade program hasn&apos;t been normalized yet — this affects
          match quality.
        </p>
      )}
      {!profileHasLocation && (
        <p className="flex items-center justify-center gap-1.5 text-micro text-slate mt-2">
          <AlertCircle className="w-3.5 h-3.5 text-studio-maroon" />
          Set your location for geography-based matching.
        </p>
      )}
    </div>
  );
}

function shortLabel(text: string): string {
  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 35) {
    return text.slice(0, colonIdx);
  }
  return text.length > 35 ? text.slice(0, 35) + "..." : text;
}

function humanize(text: string): string {
  return text
    .replace(/^([A-Z][a-z_]+( [A-Z][a-z_]+)*): /, (_, label) => {
      return `**${label}** — `;
    })
    .replace(/\*\*/g, "");
}

function formatPay(match: JobMatchSummary): string | null {
  if (match.pay_min === null && match.pay_max === null) return null;
  const payMin = match.pay_min ?? 0;
  const payMax = match.pay_max;
  const suffix =
    match.pay_type === "hourly"
      ? "/hr"
      : match.pay_type === "annual"
        ? "/yr"
        : "";
  const fmt = (n: number) =>
    match.pay_type === "annual"
      ? `$${(n / 1000).toFixed(0)}k`
      : `$${n.toFixed(0)}`;
  if (payMax && payMax !== payMin)
    return `${fmt(payMin)}-${fmt(payMax)}${suffix}`;
  return `${fmt(payMin)}${suffix}`;
}
