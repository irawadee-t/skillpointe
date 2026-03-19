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
  Zap,
  ExternalLink,
  ClipboardList,
  GraduationCap,
  Wrench,
  FileText,
  Star,
  Info,
} from "lucide-react";

import type {
  JobMatchSummary,
  RankedMatchesResponse,
} from "@/lib/api/applicant";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface Props {
  data: RankedMatchesResponse | null;
  fetchError: string | null;
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function MatchesClient({ data, fetchError }: Props) {
  if (fetchError) {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-4xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-800 flex items-start gap-2">
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
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <BackLink />
          <h1 className="text-2xl font-bold text-spf-navy mt-2">
            Your job matches
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Ranked by how well each role fits your trade, location, and
            background.
          </p>
        </div>

        {matches?.has_matches && (
          <div className="grid grid-cols-3 gap-3">
            <StatCard
              label="Total matches"
              value={totalMatches}
              icon={<Target className="w-4 h-4" />}
              color="text-spf-navy"
              bgColor="bg-spf-navy/5"
            />
            <StatCard
              label="Ready to apply"
              value={eligibleCount}
              icon={<Shield className="w-4 h-4" />}
              color="text-green-700"
              bgColor="bg-green-50"
            />
            <StatCard
              label="Close matches"
              value={nearFitCount}
              icon={<TrendingUp className="w-4 h-4" />}
              color="text-amber-700"
              bgColor="bg-amber-50"
            />
          </div>
        )}

        {!matches?.has_matches ? (
          <NoMatchesCard
            profileHasFamily={matches?.profile_has_family ?? false}
            profileHasLocation={matches?.profile_has_location ?? false}
          />
        ) : (
          <>
            {/* Eligible Section */}
            <section>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-6 rounded-full bg-green-500" />
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Ready to apply
                  </h2>
                  <p className="text-xs text-gray-500">
                    You meet the key requirements for these roles
                  </p>
                </div>
                <span className="ml-auto text-sm font-semibold text-green-700 bg-green-50 rounded-full px-3 py-0.5">
                  {eligibleCount}
                </span>
              </div>
              {matches.eligible_matches.length === 0 ? (
                <EmptySection message="No eligible matches yet. Complete your profile to improve results." />
              ) : (
                <div className="space-y-3">
                  {matches.eligible_matches.map((m) => (
                    <MatchCard key={m.match_id} match={m} />
                  ))}
                </div>
              )}
            </section>

            {/* Near-fit Section */}
            <section>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-6 rounded-full bg-amber-400" />
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Close matches
                  </h2>
                  <p className="text-xs text-gray-500">
                    Worth exploring — one or two gaps to address
                  </p>
                </div>
                <span className="ml-auto text-sm font-semibold text-amber-700 bg-amber-50 rounded-full px-3 py-0.5">
                  {nearFitCount}
                </span>
              </div>
              {matches.near_fit_matches.length === 0 ? (
                <EmptySection message="No near-fit matches right now." />
              ) : (
                <div className="space-y-3">
                  {matches.near_fit_matches.map((m) => (
                    <MatchCard key={m.match_id} match={m} />
                  ))}
                </div>
              )}
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

function MatchCard({ match }: { match: JobMatchSummary }) {
  const [expanded, setExpanded] = useState(false);

  const score = match.policy_adjusted_score
    ? Math.round(match.policy_adjusted_score)
    : null;
  const location = [match.job_city, match.job_state].filter(Boolean).join(", ");
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

  const fitInfo = getFitInfo(score, match.eligibility_status);

  return (
    <div className="bg-white border border-gray-200 rounded-xl hover:border-gray-300 hover:shadow-sm transition-all">
      <div className="p-5">
        {/* Row 1: Title + actions */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5">
              {score !== null && (
                <div
                  className={`shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold ${fitInfo.scoreBg} ${fitInfo.scoreText}`}
                >
                  {score}
                </div>
              )}
              <div className="min-w-0">
                <h3 className="font-semibold text-gray-900 text-base leading-snug">
                  {match.job_title}
                </h3>
                <p className="text-sm text-gray-500 mt-0.5 flex items-center gap-1">
                  <Building2 className="w-3.5 h-3.5 shrink-0" />
                  {match.employer_name}
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {match.source_url && (
              <a
                href={match.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-3 py-1.5 bg-spf-navy text-white text-xs font-medium rounded-lg hover:bg-spf-navy-light transition-colors"
              >
                Apply <ExternalLink className="w-3 h-3" />
              </a>
            )}
            {hasDetail && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1.5 rounded-lg border border-gray-200 text-gray-400 hover:text-gray-600 hover:border-gray-300 transition-colors"
                aria-label={expanded ? "Collapse" : "Expand"}
              >
                {expanded ? (
                  <ChevronUp className="w-4 h-4" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Location, pay, setting */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-gray-600">
          {(location || workLabel) && (
            <span className="flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              {location || ""}
              {workLabel && (
                <span className="text-gray-400">
                  {location ? " · " : ""}
                  {workLabel}
                </span>
              )}
            </span>
          )}
          {payDisplay && (
            <span className="flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              {payDisplay}
            </span>
          )}
        </div>

        {/* Row 3: Match insight — single clear line */}
        <div className={`mt-3 px-3 py-2 rounded-lg ${fitInfo.insightBg}`}>
          <div className="flex items-start gap-2">
            <fitInfo.InsightIcon
              className={`w-4 h-4 shrink-0 mt-0.5 ${fitInfo.insightIconColor}`}
            />
            <div className="text-sm">
              <span className={`font-medium ${fitInfo.insightTextColor}`}>
                {fitInfo.label}
              </span>
              {match.recommended_next_step && (
                <span className="text-gray-600">
                  {" "}
                  — {match.recommended_next_step}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Row 4: Tags — strengths, gaps, family */}
        {!expanded && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {match.top_strengths.slice(0, 2).map((s, i) => (
              <span
                key={`s-${i}`}
                className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-700 border border-green-100 rounded-md px-2 py-0.5"
              >
                <CheckCircle2 className="w-3 h-3 shrink-0" />
                {shortLabel(s)}
              </span>
            ))}
            {match.top_gaps.slice(0, 2).map((g, i) => (
              <span
                key={`g-${i}`}
                className="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-100 rounded-md px-2 py-0.5"
              >
                <AlertTriangle className="w-3 h-3 shrink-0" />
                {shortLabel(g)}
              </span>
            ))}
            {familyLabel && (
              <span className="text-xs bg-gray-50 text-gray-500 border border-gray-100 rounded-md px-2 py-0.5">
                {familyLabel}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Expanded section: job details + match breakdown */}
      {expanded && (
        <ExpandedMatchContent match={match} hasDetail={hasDetail} />
      )}
    </div>
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
    <div className="border-t border-gray-100">
      {/* Match analysis */}
      <div className="px-5 py-4 space-y-4">
        {/* Why you match */}
        {match.top_strengths.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Why you match
            </h4>
            <div className="space-y-1.5">
              {match.top_strengths.map((s, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-sm text-gray-700"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0 mt-0.5" />
                  <span>{humanize(s)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* What to work on */}
        {match.top_gaps.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              What to work on
            </h4>
            <div className="space-y-1.5">
              {match.top_gaps.map((g, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-sm text-gray-700"
                >
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                  <span>{humanize(g)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Scoring breakdown toggle */}
        <button
          onClick={() => setShowScoring(!showScoring)}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
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
        <div className="border-t border-gray-100 px-5 py-4 bg-gray-50/50 space-y-5">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
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
                className="inline-flex items-center gap-2 px-4 py-2 bg-spf-navy text-white text-sm font-medium rounded-lg hover:bg-spf-navy-light transition-colors"
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
    <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-700">Overall score</span>
        <span className="font-bold text-gray-900">{score ?? "—"}/100</span>
      </div>
      <div className="flex items-center justify-between">
        <span>Eligibility</span>
        <span
          className={
            match.eligibility_status === "eligible"
              ? "text-green-600"
              : "text-amber-600"
          }
        >
          {match.eligibility_status === "eligible"
            ? "Eligible"
            : "Near-fit"}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span>Confidence</span>
        <span>{match.confidence_level ?? "—"}</span>
      </div>
      <p className="text-gray-400 pt-1 border-t border-gray-200">
        Score reflects trade alignment, geography, credentials, timing, and
        job requirements. For a full breakdown, visit{" "}
        <Link
          href={`/applicant/matches/${match.match_id}`}
          className="text-spf-navy hover:underline"
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
  overview: <Briefcase className="w-4 h-4 text-gray-500" />,
  responsibilities: <ClipboardList className="w-4 h-4 text-gray-500" />,
  requirements: <Wrench className="w-4 h-4 text-gray-500" />,
  qualifications: <GraduationCap className="w-4 h-4 text-gray-500" />,
  preferred: <Star className="w-4 h-4 text-gray-500" />,
  benefits: <FileText className="w-4 h-4 text-gray-500" />,
  other: <FileText className="w-4 h-4 text-gray-500" />,
};

function DescriptionSection({ section }: { section: Section }) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5 mb-2">
        {SECTION_ICONS[section.icon]}
        {section.title}
      </h4>
      <div className="text-sm text-gray-600 leading-relaxed">
        {section.items.map((item, i) =>
          item.type === "bullet" ? (
            <div key={i} className="flex items-start gap-2 py-0.5">
              <span className="w-1.5 h-1.5 bg-gray-300 rounded-full mt-1.5 shrink-0" />
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

function StatCard({
  label,
  value,
  icon,
  color,
  bgColor,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
}) {
  return (
    <div className={`${bgColor} rounded-xl p-4 border border-transparent`}>
      <div
        className={`flex items-center gap-1.5 ${color} text-xs font-medium`}
      >
        {icon}
        {label}
      </div>
      <p className={`text-2xl font-bold ${color} mt-1 tabular-nums`}>
        {value}
      </p>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/applicant"
      className="text-sm text-gray-400 hover:text-gray-600 inline-flex items-center gap-1 transition-colors"
    >
      <ChevronLeft className="w-4 h-4" /> Dashboard
    </Link>
  );
}

function EmptySection({ message }: { message: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 text-sm text-gray-500 text-center">
      {message}
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
    <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
      <Briefcase className="w-8 h-8 text-gray-300 mx-auto" />
      <p className="text-gray-700 font-semibold text-lg mt-3">
        No matches yet
      </p>
      <p className="text-sm text-gray-500 mt-2">
        Matches are computed when the scoring pipeline runs.
      </p>
      {!profileHasFamily && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-amber-600 mt-4">
          <AlertCircle className="w-3.5 h-3.5" />
          Your trade program hasn&apos;t been normalized yet — this affects
          match quality.
        </p>
      )}
      {!profileHasLocation && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-amber-600 mt-2">
          <AlertCircle className="w-3.5 h-3.5" />
          Set your location for geography-based matching.
        </p>
      )}
    </div>
  );
}

function getFitInfo(
  score: number | null,
  eligibilityStatus: string
): {
  label: string;
  scoreBg: string;
  scoreText: string;
  insightBg: string;
  insightIconColor: string;
  insightTextColor: string;
  InsightIcon: typeof CheckCircle2;
} {
  if (eligibilityStatus === "eligible" && score !== null && score >= 80) {
    return {
      label: "Strong fit",
      scoreBg: "bg-green-50",
      scoreText: "text-green-700",
      insightBg: "bg-green-50/60",
      insightIconColor: "text-green-500",
      insightTextColor: "text-green-700",
      InsightIcon: CheckCircle2,
    };
  }
  if (eligibilityStatus === "eligible") {
    return {
      label: "Good fit",
      scoreBg: "bg-spf-navy/5",
      scoreText: "text-spf-navy",
      insightBg: "bg-blue-50/60",
      insightIconColor: "text-spf-navy",
      insightTextColor: "text-spf-navy",
      InsightIcon: CheckCircle2,
    };
  }
  if (score !== null && score >= 55) {
    return {
      label: "Close match",
      scoreBg: "bg-amber-50",
      scoreText: "text-amber-700",
      insightBg: "bg-amber-50/60",
      insightIconColor: "text-amber-500",
      insightTextColor: "text-amber-700",
      InsightIcon: Zap,
    };
  }
  return {
    label: "Worth exploring",
    scoreBg: "bg-gray-50",
    scoreText: "text-gray-500",
    insightBg: "bg-gray-50/60",
    insightIconColor: "text-gray-400",
    insightTextColor: "text-gray-600",
    InsightIcon: Zap,
  };
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
