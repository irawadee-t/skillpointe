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
  DollarSign,
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
import { InterestSignalPanel } from "@/components/matches/InterestSignalPanel";

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
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
          <strong>Could not reach the API.</strong> The backend may be starting up — please refresh in a moment.
        </div>
      </main>
    );
  }

  const interestSignal = await fetchInterestSignal(matchId, session.access_token);

  const locationStr = [match.job_city, match.job_state].filter(Boolean).join(", ");
  const payStr = formatPay(match.pay_min, match.pay_max, match.pay_type);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Breadcrumb */}
        <Link
          href="/applicant/matches"
          className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Back to matches
        </Link>

        {/* Job header */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-white leading-snug">
                {match.job_title}
              </h1>
              <p className="text-zinc-400 mt-0.5">
                {match.employer_name}
                {match.is_partner_employer && (
                  <span
                    className="ml-1.5 inline-flex items-center gap-0.5 text-amber-400"
                    title="SkillPointe partner employer"
                  >
                    <Star className="w-4 h-4 inline" /> Partner
                  </span>
                )}
              </p>
            </div>

            {/* Display score */}
            {match.policy_adjusted_score !== null && (
              <div className="shrink-0 text-right">
                <div className="text-4xl font-bold text-cyan-400 leading-none">
                  {Math.round(match.policy_adjusted_score)}
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">/ 100</div>
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
              <span className="inline-flex items-center gap-1 text-sm font-medium text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-3 py-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Low confidence
              </span>
            )}
            {match.requires_review && (
              <span className="inline-flex items-center gap-1 text-sm font-medium text-zinc-400 bg-zinc-800 border border-zinc-700 rounded-full px-3 py-1">
                <Info className="w-3.5 h-3.5" /> Pending review
              </span>
            )}
          </div>

          {/* Location + pay */}
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-4 text-sm text-zinc-400">
            {locationStr && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-zinc-500" />
                {locationStr}
                {match.work_setting &&
                  ` · ${formatWorkSetting(match.work_setting)}`}
              </span>
            )}
            {!locationStr && match.work_setting && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-zinc-500" />
                {formatWorkSetting(match.work_setting)}
              </span>
            )}
            {match.pay_min !== null && (
              <span className="flex items-center gap-1">
                <DollarSign className="w-3.5 h-3.5 text-zinc-500" />
                {payStr}
              </span>
            )}
          </div>

          {/* Geography note */}
          {match.geography_note && (
            <p className="mt-2 text-sm text-zinc-500">{match.geography_note}</p>
          )}
        </section>

        {/* Apply + Interest signal */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h2 className="font-semibold text-white mb-3">Your interest</h2>
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
                <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                  {s}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Recommended next step */}
        {match.recommended_next_step && (
          <Section title="Recommended next step">
            <p className="text-sm text-zinc-300">{match.recommended_next_step}</p>
          </Section>
        )}

        {/* Missing requirements */}
        {match.required_missing_items.length > 0 && (
          <Section title="What's missing">
            <MissingItems items={match.required_missing_items} />
          </Section>
        )}

        {/* Gaps */}
        {match.top_gaps.length > 0 && (
          <Section title="Areas to strengthen">
            <ul className="space-y-2">
              {match.top_gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                  <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
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
    <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
      <h2 className="font-semibold text-white mb-3">{title}</h2>
      {children}
    </section>
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
          <p className="text-xs font-semibold uppercase tracking-wide text-rose-400 mb-2">
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
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">
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
    <li className="flex items-start gap-2 text-sm text-zinc-300">
      {type === "mandatory"
        ? <XCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
        : <Circle className="w-4 h-4 text-zinc-500 mt-0.5 shrink-0" />}
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
            <span className="font-medium text-zinc-200 capitalize">
              {gate.gate_name.replace(/_/g, " ")}
            </span>
            <p className="text-zinc-500 mt-0.5">{gate.reason}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function GateIcon({ result }: { result: "pass" | "near_fit" | "fail" }) {
  if (result === "pass")
    return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />;
  if (result === "near_fit")
    return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />;
  return <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />;
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
    <div className="mt-5 pt-4 border-t border-zinc-800">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">
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
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd
        className={`text-lg font-bold mt-0.5 ${
          highlight ? "text-cyan-400" : "text-zinc-300"
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
        <div key={i} className="flex items-start justify-between gap-4 text-sm">
          <div>
            <span className="font-medium text-zinc-200 capitalize">
              {mod.policy.replace(/_/g, " ")}
            </span>
            <p className="text-zinc-500 mt-0.5">{mod.reason}</p>
          </div>
          <span
            className={`shrink-0 font-semibold ${
              mod.value > 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {mod.value > 0 ? `+${mod.value}` : mod.value}
          </span>
        </div>
      ))}
    </div>
  );
}
