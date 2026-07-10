/**
 * Match detail view — Phase 6.1
 *
 * Shows for a single applicant-job match:
 *   - Job header (title, employer, location, pay, badges)
 *   - Why this matched (top strengths)
 *   - What's missing (required_missing_items split into mandatory vs. improvable)
 *   - Hard gate results (pass / near_fit / fail per gate)
 *   - Recommended next step
 *   - Scoring breakdown (dimension bars via DimensionBreakdown)
 *   - Score transparency (base, structured, semantic, policy adjustments)
 *   - Policy modifiers
 *
 * Server component.
 */
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import {
  MapPin,
  Star,
  ChevronLeft,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Circle,
  Info,
} from "lucide-react";

import { fetchMatchDetail } from "@/lib/api/applicant";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import {
  formatWorkSetting,
  formatPay,
  formatMatchLabel,
} from "@/lib/api/applicant";
import type { GateResultItem, PolicyModifierItem } from "@/lib/api/applicant";
import { EligibilityBadge, MatchLabel } from "@/components/matches/MatchLabel";
import { DimensionBreakdown } from "@/components/matches/DimensionBreakdown";
import { TrainingRecs } from "@/components/applicant/TrainingRecs";
import { CommuteChip } from "@/components/applicant/CommuteChip";
import { ApplyFlow } from "@/components/applicant/ApplyFlow";
import { InterestSignalPanel } from "@/components/matches/InterestSignalPanel";
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
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

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
        <div className="mx-auto w-full max-w-4xl px-5 bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-5 text-body text-error-red">
          <strong>Could not reach the API.</strong> The backend may be starting up — please refresh in a moment.
        </div>
      </main>
    );
  }

  const interestSignal = await fetchInterestSignal(matchId, session.access_token);

  const locationStr = [match.job_city, match.job_state].filter((v) => v && !/^unspecified$/i.test(v.trim())).join(", ");
  const payStr = formatPay(match.pay_min, match.pay_max, match.pay_type);

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

        {/* Job header — deep-green hero panel */}
        <Reveal as="section" className="card-green p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-card text-white leading-tight">
                {match.job_title}
              </h1>
              <p className="text-body text-white/70 mt-1">
                {match.employer_name}
                {match.is_partner_employer && (
                  <span
                    className="ml-1.5 inline-flex items-center gap-0.5 text-cohere-coral"
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
                title={`Match score ${Math.round(match.policy_adjusted_score)}/100 — combines structured dimensions (${Math.round(match.weighted_structured_score ?? 0)}) and semantic fit (${Math.round(match.semantic_score ?? 0)}), capped by any hard-gate failures. See Eligibility checks below.`}
              >
                <div className="text-heading font-display text-white leading-none">
                  {Math.round(match.policy_adjusted_score)}
                </div>
                <div className="text-caption text-white/60 mt-0.5">/ 100</div>
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
              <span className="inline-flex items-center gap-1 text-caption font-medium text-white bg-white/10 border border-white/20 rounded-sm px-3 py-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Low confidence
              </span>
            )}
            {match.requires_review && (
              <span className="inline-flex items-center gap-1 text-caption font-medium text-white bg-white/10 border border-white/15 rounded-sm px-3 py-1">
                <Info className="w-3.5 h-3.5" /> Pending review
              </span>
            )}
          </div>

          {/* Location + pay */}
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-4 text-body text-white/80">
            {locationStr && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-white/60" />
                {locationStr}
                {match.work_setting &&
                  `, ${formatWorkSetting(match.work_setting)}`}
              </span>
            )}
            {!locationStr && match.work_setting && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-white/60" />
                {formatWorkSetting(match.work_setting)}
              </span>
            )}
            {/* payStr carries its own "$". */}
            {match.pay_min !== null && <span>{payStr}</span>}
            <CommuteChip token={session.access_token} matchId={matchId} tone="on-dark" />
          </div>

          {/* Geography note */}
          {match.geography_note && (
            <p className="mt-2 text-caption text-white/70">{match.geography_note}</p>
          )}
        </Reveal>

        {/* Apply on SkillPointe — the in-platform application flow */}
        <ApplyFlow
          token={session.access_token}
          jobId={match.job_id}
          matchId={matchId}
          jobTitle={match.job_title}
        />

        {/* Interest signal — kept for lightweight "I'm interested" tracking + external apply escape hatch */}
        <section className="bg-white border border-border-light rounded-md p-5">
          <h2 className="font-display text-feature text-cohere-ink mb-3">Not ready to apply?</h2>
          <InterestSignalPanel
            matchId={matchId}
            sourceUrl={match.source_url}
            initialSignal={interestSignal}
            token={session.access_token}
          />
        </section>

        {/* Strengths */}
        {match.top_strengths.length > 0 && (
          <Section title="Why this matched">
            <ul className="space-y-2">
              {match.top_strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-body text-ink">
                  <CheckCircle2 className="w-4 h-4 text-cohere-green mt-0.5 shrink-0" />
                  {s}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Recommended next step */}
        {match.recommended_next_step && (
          <Section title="Recommended next step">
            <p className="text-body text-ink">{match.recommended_next_step}</p>
          </Section>
        )}

        {/* Missing requirements */}
        {match.required_missing_items.length > 0 && (
          <Section title="What's missing">
            <MissingItems items={match.required_missing_items} />
          </Section>
        )}

        {/* Training pathways — only renders if backend finds programs for missing credentials */}
        <TrainingRecs token={session.access_token} matchId={matchId} />

        {/* Gaps */}
        {match.top_gaps.length > 0 && (
          <Section title="Areas to strengthen">
            <ul className="space-y-2">
              {match.top_gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2 text-body text-ink">
                  <AlertTriangle className="w-4 h-4 text-cohere-coral mt-0.5 shrink-0" />
                  {g}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Hard gate results */}
        {match.hard_gate_rationale.length > 0 && (
          <Section title="Eligibility checks">
            <GateResultsTable gates={match.hard_gate_rationale} />
          </Section>
        )}

        {/* Scoring breakdown */}
        {match.dimension_scores.length > 0 && (
          <Section title="Scoring breakdown">
            <DimensionBreakdown dimensions={match.dimension_scores} />
            <ScoreTransparency
              base={match.base_fit_score}
              structured={match.weighted_structured_score}
              semantic={match.semantic_score}
              adjusted={match.policy_adjusted_score}
            />
          </Section>
        )}

        {/* Policy modifiers */}
        {match.policy_modifiers.length > 0 && (
          <Section title="Policy adjustments">
            <PolicyModifierList modifiers={match.policy_modifiers} />
          </Section>
        )}
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
      <h2 className="font-display text-feature text-cohere-ink mb-3">{title}</h2>
      {children}
    </Reveal>
  );
}

/**
 * Split missing items into mandatory (contain keywords like "required", "must",
 * "license", "certificate", "degree") vs. improvable, then display separately.
 * Falls back to showing all in a single list if no keywords match.
 */
function MissingItems({ items }: { items: string[] }) {
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
  const improvable = items.filter((s) => !isMandatory(s));

  if (mandatory.length === 0) {
    return (
      <ul className="space-y-2">
        {items.map((item, i) => (
          <MissingItem key={i} text={item} type="improvable" />
        ))}
      </ul>
    );
  }

  return (
    <div className="space-y-4">
      {mandatory.length > 0 && (
        <div>
          <p className="text-micro font-semibold tracking-wide text-error-red mb-2">
            Required — must address
          </p>
          <ul className="space-y-2">
            {mandatory.map((item, i) => (
              <MissingItem key={i} text={item} type="mandatory" />
            ))}
          </ul>
        </div>
      )}
      {improvable.length > 0 && (
        <div>
          <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
            Improvable — would strengthen fit
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
        ? <XCircle className="w-4 h-4 text-error-red mt-0.5 shrink-0" />
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
            <p className="text-body text-slate mt-0.5">{gate.reason}</p>
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
    return <AlertTriangle className="w-4 h-4 text-cohere-coral shrink-0 mt-0.5" />;
  return <XCircle className="w-4 h-4 text-error-red shrink-0 mt-0.5" />;
}

function ScoreTransparency({
  base,
  structured,
  semantic,
  adjusted,
}: {
  base: number | null;
  structured: number | null;
  semantic: number | null;
  adjusted: number | null;
}) {
  if (base === null) return null;
  return (
    <div className="mt-5 pt-4 border-t border-border-light">
      <p className="text-micro font-semibold tracking-wide text-slate-muted mb-2">
        Score components
      </p>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <ScoreKV label="Structured" value={structured} />
        <ScoreKV label="Semantic" value={semantic} />
        <ScoreKV label="Base fit" value={base} />
        <ScoreKV label="Display score" value={adjusted} highlight />
      </dl>
    </div>
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
              mod.value > 0 ? "text-cohere-green" : "text-error-red"
            }`}
          >
            {mod.value > 0 ? `+${mod.value}` : mod.value}
          </span>
        </div>
      ))}
    </div>
  );
}
