/**
 * Match detail view.
 *
 * Two content modules (plus the hero + apply panel):
 *   - "The job"  — cleaned job sections
 *   - "Your fit" — why this matched, what's missing (gaps merged in),
 *                  recommended next step, eligibility checks, and the
 *                  dimension bars ("Why this score")
 *
 * Engine internals (score components, policy adjustments, dimension weights)
 * live behind ONE quiet "How the math works" disclosure at the bottom of
 * "Your fit" — never in the default view.
 *
 * Server component.
 */
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import {
  MapPin,
  Star,
  ChevronLeft,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Circle,
} from "lucide-react";

import { fetchMatchDetail } from "@/lib/api/applicant";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import {
  formatWorkSetting,
  formatPay,
  formatDimensionName,
  stripZeroDistance,
} from "@/lib/api/applicant";
import type { DimensionScoreItem, GateResultItem, PolicyModifierItem } from "@/lib/api/applicant";
import { JobSections } from "@/components/jobs/JobSections";
import { EligibilityBadge, MatchLabel } from "@/components/matches/MatchLabel";
import { DimensionBreakdown } from "@/components/matches/DimensionBreakdown";
import { MatchExplanation } from "@/components/viz2";
import {
  fetchMatchExplanation,
  type MatchExplanationData,
} from "@/components/viz2/types";
import { TrainingRecs } from "@/components/applicant/TrainingRecs";
import { CommuteChip } from "@/components/applicant/CommuteChip";
import { ApplyFlow } from "@/components/applicant/ApplyFlow";
import { InterestSignalPanel } from "@/components/matches/InterestSignalPanel";
import { ATTENTION_TEXT_CLASS } from "@/components/ui/statusTones";
import { Reveal } from "@/components/ui";

export default async function MatchDetailPage({
  params,
}: {
  params: Promise<{ matchId: string }>;
}) {
  const { matchId } = await params;

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  // Fetch interest signal
  async function fetchInterestSignal(mId: string, tok: string) {
    try {
      const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API_URL}/applicant/me/matches/${mId}/interest`, {
        headers: { Authorization: `Bearer ${tok}` },
        cache: "no-store",
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.interest_level ?? null;
    } catch {
      return null;
    }
  }

  let match;
  try {
    match = await fetchMatchDetail(matchId, session.access_token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return (
      <main className="py-8">
        <div className="mx-auto w-full max-w-4xl px-5 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
          <strong>Could not reach the API.</strong> The backend may be starting up. Please refresh in a moment.
        </div>
      </main>
    );
  }

  const interestSignal = await fetchInterestSignal(matchId, session.access_token);

  // Rich "Why this score" payload (viz2). Best-effort: on ANY failure the page
  // falls back to the previous dimension-bars rendering — never blocks.
  let explanation: MatchExplanationData | null = null;
  try {
    explanation = await fetchMatchExplanation(matchId, session.access_token);
  } catch {
    explanation = null;
  }

  const locationStr = [match.job_city, match.job_state].filter((v) => v && !/^unspecified$/i.test(v.trim())).join(", ");
  const payStr = formatPay(match.pay_min, match.pay_max, match.pay_type);

  // "What's missing" merges the old "Areas to strengthen" (top_gaps) into the
  // required_missing_items list — one section, one name. Dedupe on the exact
  // string so an item flagged by both sources renders once.
  const missingItems = match.required_missing_items.map(stripZeroDistance);
  const missingSet = new Set(missingItems.map((s) => s.trim().toLowerCase()));
  const extraGaps = match.top_gaps
    .map(stripZeroDistance)
    .filter((g) => !missingSet.has(g.trim().toLowerCase()));
  const hasMissing = missingItems.length > 0 || extraGaps.length > 0;

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-4xl px-5 space-y-6">
        {/* Breadcrumb */}
        <Link
          href="/applicant/matches"
          className="text-body text-slate hover:text-cohere-ink inline-flex items-center gap-1 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Back to matches
        </Link>

        {/* Job header — white sheet hero panel */}
        <Reveal as="section" className="bg-white border border-hairline rounded-[14px] p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-card text-cohere-ink leading-tight">
                {match.job_title}
              </h1>
              <p className="text-body text-slate mt-1">
                {match.employer_name}
                {match.is_partner_employer && (
                  <span
                    className="ml-1.5 inline-flex items-center gap-0.5 text-cohere-ink"
                    title="SKILLED Nation partner employer"
                  >
                    <Star className="w-4 h-4 inline" /> Partner
                  </span>
                )}
              </p>
            </div>

            {/* Display score */}
            {match.policy_adjusted_score !== null && (
              <div
                className="shrink-0 text-right cursor-help"
                title={`Match score ${Math.floor(match.policy_adjusted_score)} out of 100. See "Why this score" below.`}
              >
                <div className="text-heading font-display text-cohere-ink leading-none">
                  {Math.floor(match.policy_adjusted_score)}
                </div>
                <div className="text-caption text-slate-muted mt-0.5">/ 100</div>
              </div>
            )}
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-2 mt-4">
            <EligibilityBadge status={match.eligibility_status} size="md" />
            {match.match_label && (
              <MatchLabel label={match.match_label} size="md" />
            )}
            {match.confidence_level === "low" && (
              <span className="inline-flex items-center gap-1 text-caption font-medium text-slate bg-stone border border-hairline rounded-sm px-3 py-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Low confidence
              </span>
            )}
            {/* `requires_review` is internal admin workflow state — showing
                "Pending review" next to "Eligible / Strong fit" read as a
                contradiction to applicants, so it is deliberately not shown. */}
          </div>

          {/* Location + pay */}
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-4 text-body text-slate">
            {locationStr && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-slate-muted" />
                {locationStr}
                {match.work_setting &&
                  `, ${formatWorkSetting(match.work_setting)}`}
              </span>
            )}
            {!locationStr && match.work_setting && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-slate-muted" />
                {formatWorkSetting(match.work_setting)}
              </span>
            )}
            {/* payStr carries its own "$". */}
            {match.pay_min !== null && <span>{payStr}</span>}
            <CommuteChip token={session.access_token} matchId={matchId} tone="on-light" />
          </div>

          {/* Geography note */}
          {match.geography_note && (
            <p className="mt-2 text-caption text-slate-muted">{match.geography_note}</p>
          )}

          {/* Credentials the posting names, extracted from its own text.
              Solid chip = stated as required; outlined = preferred/mentioned. */}
          {(match.required_credentials?.length ?? 0) > 0 && (
            <div className="mt-4">
              <span className="text-caption font-medium text-slate">Credentials for this job</span>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {match.required_credentials.map((c: { name: string; requirement: string }) => (
                  <span
                    key={c.name}
                    className={
                      c.requirement === "required"
                        ? "inline-flex items-center rounded-sm bg-cohere-ink px-3 py-1 text-caption font-medium text-white"
                        : "inline-flex items-center rounded-sm border border-hairline bg-white px-3 py-1 text-caption text-slate"
                    }
                  >
                    {c.name}
                    {c.requirement === "preferred" && <span className="ml-1 text-slate-muted">· preferred</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Reveal>

        {/* Apply on SKILLED Nation — the in-platform application flow */}
        <ApplyFlow
          token={session.access_token}
          jobId={match.job_id}
          jobTitle={match.job_title}
          sourceUrl={match.source_url}
        />

        {/* Interest signal — kept for lightweight "I'm interested" tracking + external apply escape hatch */}
        <section className="bg-white border border-border-light rounded-md p-5">
          <h2 className="text-[1.0625rem] font-medium text-cohere-ink mb-3">Not ready to apply?</h2>
          <InterestSignalPanel
            matchId={matchId}
            sourceUrl={match.source_url}
            initialSignal={interestSignal}
            token={session.access_token}
          />
        </section>

        {/* Module 1 — The job. Rendered through the same cleaned-sections
            layer as the browse and matches views (never raw scrape text). */}
        <Section title="The job">
          <JobSections jobId={match.job_id} token={session.access_token} />
        </Section>

        {/* Module 2 — Your fit. Everything about this pairing, in one sheet. */}
        <Section title="Your fit">
          <div className="space-y-5">
            {/* Why this matched */}
            {match.top_strengths.length > 0 && (
              <SubSection heading="Why this matched" first>
                <ul className="space-y-2">
                  {match.top_strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-body text-ink">
                      <CheckCircle2 className="w-4 h-4 text-cohere-green mt-0.5 shrink-0" />
                      {stripZeroDistance(s)}
                    </li>
                  ))}
                </ul>
              </SubSection>
            )}

            {/* What's missing — required items + areas to strengthen, merged.
                When the viz2 explanation loaded, its "What could improve it"
                levers carry these exact items (plus the next step), so the two
                sections below render only on the fallback path. */}
            {hasMissing && !explanation && (
              <SubSection heading="What's missing" first={match.top_strengths.length === 0}>
                <MissingItems
                  items={missingItems}
                  extraGaps={extraGaps}
                />
              </SubSection>
            )}

            {/* Recommended next step (fallback path — see note above) */}
            {match.recommended_next_step && !explanation && (
              <SubSection heading="Recommended next step">
                <p className="text-body text-ink">{match.recommended_next_step}</p>
              </SubSection>
            )}

            {/* Eligibility checks */}
            {match.hard_gate_rationale.length > 0 && (
              <SubSection heading="Eligibility checks">
                <GateResultsTable gates={match.hard_gate_rationale} />
              </SubSection>
            )}

            {/* Why this score — the viz2 composite (driver bars + score in
                context + improvement levers). Falls back to the previous
                dimension bars if the explanation endpoint errored. */}
            {explanation ? (
              <div className="border-t border-hairline pt-5">
                <MatchExplanation data={explanation} contextMode="applicant" />
              </div>
            ) : (
              match.dimension_scores.length > 0 && (
                <SubSection heading="Why this score">
                  <DimensionBreakdown dimensions={match.dimension_scores} />
                </SubSection>
              )
            )}

            {/* ONE quiet disclosure for the engine internals — score
                components, policy adjustments, and per-dimension weights. */}
            <HowTheMathWorks match={match} />
          </div>
        </Section>

        {/* Training pathways — only renders if backend finds programs for missing credentials */}
        <TrainingRecs token={session.access_token} matchId={matchId} />
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Reveal as="section" className="bg-white border border-border-light rounded-md p-5">
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink mb-3">{title}</h2>
      {children}
    </Reveal>
  );
}

/** A titled block inside a module sheet — hairline-divided rows, sans heading. */
function SubSection({
  heading,
  children,
  first = false,
}: {
  heading: string;
  children: React.ReactNode;
  first?: boolean;
}) {
  return (
    <div className={first ? "" : "border-t border-hairline pt-5"}>
      <h3 className="text-caption font-semibold text-cohere-ink mb-2">{heading}</h3>
      {children}
    </div>
  );
}

/**
 * "What's missing" — required_missing_items split into mandatory (keywords
 * like "required", "must", "license") vs. improvable, with the former
 * "Areas to strengthen" gaps merged into the improvable list under this one
 * section name.
 */
function MissingItems({ items, extraGaps }: { items: string[]; extraGaps: string[] }) {
  const mandatoryKeywords = [
    "required",
    "must",
    "license",
    "certificate",
    "certification",
    "degree",
    "credential",
    "mandatory",
  ];
  const isMandatory = (s: string) =>
    mandatoryKeywords.some((kw) => s.toLowerCase().includes(kw));

  const mandatory = items.filter(isMandatory);
  const improvable = [...items.filter((s) => !isMandatory(s)), ...extraGaps];

  if (mandatory.length === 0) {
    return (
      <ul className="space-y-2">
        {improvable.map((item, i) => (
          <MissingItem key={i} text={item} type="improvable" />
        ))}
      </ul>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className={`text-micro font-semibold tracking-wide ${ATTENTION_TEXT_CLASS} mb-2`}>
          Required: must address
        </p>
        <ul className="space-y-2">
          {mandatory.map((item, i) => (
            <MissingItem key={i} text={item} type="mandatory" />
          ))}
        </ul>
      </div>
      {improvable.length > 0 && (
        <div>
          <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
            Improvable: would strengthen fit
          </p>
          <ul className="space-y-2">
            {improvable.map((item, i) => (
              <MissingItem key={i} text={item} type="improvable" />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MissingItem({
  text,
  type,
}: {
  text: string;
  type: "mandatory" | "improvable";
}) {
  return (
    <li className="flex items-start gap-2 text-body text-ink">
      {type === "mandatory"
        ? <XCircle className={`w-4 h-4 ${ATTENTION_TEXT_CLASS} mt-0.5 shrink-0`} />
        : <Circle className="w-4 h-4 text-slate-muted mt-0.5 shrink-0" />}
      {text}
    </li>
  );
}

function GateResultsTable({ gates }: { gates: GateResultItem[] }) {
  return (
    <div className="space-y-2">
      {gates.map((gate, i) => (
        <div
          key={i}
          className="flex items-start gap-3 text-sm"
        >
          <GateIcon result={gate.result} />
          <div className="min-w-0">
            <span className="font-semibold text-ink capitalize">
              {gate.gate_name.replace(/_/g, " ")}
            </span>
            <p className="text-body text-slate mt-0.5">{stripZeroDistance(gate.reason)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function GateIcon({ result }: { result: "pass" | "near_fit" | "fail" }) {
  if (result === "pass")
    return <CheckCircle2 className="w-4 h-4 text-cohere-green shrink-0 mt-0.5" />;
  if (result === "near_fit")
    return <AlertTriangle className={`w-4 h-4 ${ATTENTION_TEXT_CLASS} shrink-0 mt-0.5`} />;
  return <XCircle className={`w-4 h-4 ${ATTENTION_TEXT_CLASS} shrink-0 mt-0.5`} />;
}

/**
 * The one disclosure holding engine internals: score components (structured /
 * semantic / base / display), policy adjustments, and per-dimension weights.
 * Plain <details> — works in a server component, closed by default.
 */
function HowTheMathWorks({
  match,
}: {
  match: {
    base_fit_score: number | null;
    weighted_structured_score: number | null;
    semantic_score: number | null;
    policy_adjusted_score: number | null;
    policy_modifiers: PolicyModifierItem[];
    dimension_scores: DimensionScoreItem[];
  };
}) {
  const hasAnything =
    match.base_fit_score !== null ||
    match.policy_modifiers.length > 0 ||
    match.dimension_scores.length > 0;
  if (!hasAnything) return null;

  return (
    <details className="group border-t border-hairline pt-4">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-caption text-slate-muted transition-colors hover:text-cohere-ink [&::-webkit-details-marker]:hidden">
        How the math works
        <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>

      <div className="mt-4 space-y-5">
        {/* Score components */}
        {match.base_fit_score !== null && (
          <div>
            <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
              Score components
            </p>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <ScoreKV label="Structured" value={match.weighted_structured_score} />
              <ScoreKV label="Semantic" value={match.semantic_score} />
              <ScoreKV label="Base fit" value={match.base_fit_score} />
              <ScoreKV label="Display score" value={match.policy_adjusted_score} highlight />
            </dl>
          </div>
        )}

        {/* Policy adjustments */}
        {match.policy_modifiers.length > 0 && (
          <div>
            <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
              Policy adjustments
            </p>
            <PolicyModifierList modifiers={match.policy_modifiers} />
          </div>
        )}

        {/* Dimension weights */}
        {match.dimension_scores.length > 0 && (
          <div>
            <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
              Dimension weights
            </p>
            <dl className="space-y-1">
              {match.dimension_scores.map((d) => (
                <div key={d.dimension} className="flex items-center justify-between text-caption">
                  <dt className="text-slate">{formatDimensionName(d.dimension)}</dt>
                  <dd className="tabular-nums text-slate-muted">weight {d.weight}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <p className="text-micro text-slate-muted">
          The display score is the structured dimensions (75%) blended with
          semantic fit (25%), capped by any hard-gate failure, then adjusted
          by SKILLED policy (partner priority, geography).
        </p>
      </div>
    </details>
  );
}

function ScoreKV({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number | null;
  highlight?: boolean;
}) {
  return (
    <div>
      <dt className="text-caption text-slate">{label}</dt>
      <dd
        className={`text-body-lg font-bold mt-0.5 ${
          highlight ? "text-cohere-green" : "text-ink"
        }`}
      >
        {value !== null ? Math.round(value) : "—"}
      </dd>
    </div>
  );
}

function PolicyModifierList({ modifiers }: { modifiers: PolicyModifierItem[] }) {
  return (
    <div className="space-y-2">
      {modifiers.map((mod, i) => (
        <div key={i} className="flex items-start justify-between gap-4 text-body">
          <div>
            <span className="font-semibold text-ink capitalize">
              {mod.policy.replace(/_/g, " ")}
            </span>
            <p className="text-slate mt-0.5">{mod.reason}</p>
          </div>
          <span
            className={`shrink-0 font-semibold ${
              mod.value > 0 ? "text-cohere-green" : ATTENTION_TEXT_CLASS
            }`}
          >
            {mod.value > 0 ? `+${mod.value}` : mod.value}
          </span>
        </div>
      ))}
    </div>
  );
}
