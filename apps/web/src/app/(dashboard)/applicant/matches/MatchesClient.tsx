"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Briefcase,
  ExternalLink,
  Check,
  Info,
  Loader2,
} from "lucide-react";

import { motion, AnimatePresence } from "motion/react";

import type {
  JobMatchSummary,
  RankedMatchesResponse,
} from "@/lib/api/applicant";
import { fetchMyMatches, stripZeroDistance } from "@/lib/api/applicant";
import { JobSections } from "@/components/jobs/JobSections";
import { ApplySheet } from "@/components/applicant/ApplySheet";
import { listMyApplications } from "@/lib/api/transactions";
import {
  InterestSignalPanel,
  setMatchInterest,
  type InterestLevel,
} from "@/components/matches/InterestSignalPanel";
import { LABEL_TEXT as FIT_LABEL_TEXT } from "@/components/matches/MatchLabel";
import { useToast } from "@/components/ui";
import { TourLaunchButton } from "@/components/tour/TourLaunchButton";
import { ATTENTION_TEXT_CLASS } from "@/components/ui/statusTones";
import { easeCohere } from "@/lib/motion";

// Acronym-aware trade label: "hvac" → "HVAC", "cdl_driving" → "CDL Driving",
// not the naive "Hvac" title-casing that shipped before.
const TRADE_ACRONYMS = new Set(["hvac", "cdl", "cnc", "it", "ems", "lpn", "cna"]);
function sentenceCase(s: string): string {
  const lower = s.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function formatTradeLabel(code: string): string {
  return code
    .split("_")
    .map((w) => (TRADE_ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

/** Per-job applied state, loaded once and updated optimistically on apply. */
interface AppliedInfo {
  id: string;
  status: string;
  when: string; // display string, e.g. "Jul 12" or "Just now"
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface Props {
  data: RankedMatchesResponse | null;
  fetchError: string | null;
  token: string;
}

type TierKey = "eligible" | "near_fit" | "nearby";

/** Page size for incremental "Show more" loads. */
const SHOW_MORE_PAGE = 25;

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function MatchesClient({ data, fetchError, token }: Props) {
  const toast = useToast();

  // Interest signals lifted here so marking "Not interested" can hide the card
  // and Undo can genuinely restore both the card and the pill state.
  const [signals, setSignals] = useState<Record<string, InterestLevel | null>>({});
  const [hiddenIds, setHiddenIds] = useState<ReadonlySet<string>>(new Set());

  // Incrementally-loaded pages appended to the server-rendered first page.
  const [extra, setExtra] = useState<Record<TierKey, JobMatchSummary[]>>({
    eligible: [],
    near_fit: [],
    nearby: [],
  });
  const [loadingTier, setLoadingTier] = useState<TierKey | null>(null);

  // Applied overlay — which of these jobs the applicant already applied to.
  // Withdrawn applications don't show as "Applied" (one re-apply is allowed).
  const [applied, setApplied] = useState<Record<string, AppliedInfo>>({});
  useEffect(() => {
    listMyApplications(token)
      .then((apps) => {
        const map: Record<string, AppliedInfo> = {};
        for (const a of apps) {
          if (a.status === "withdrawn") continue;
          map[a.job_id] = {
            id: a.id,
            status: a.status,
            when: new Date(a.submitted_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
          };
        }
        setApplied(map);
      })
      .catch(() => { /* non-fatal — rows just show the apply buttons */ });
  }, [token]);

  // One sheet instance for the whole list; the job persists through the close
  // animation so the exit transition isn't cut short.
  const [sheetJob, setSheetJob] = useState<JobMatchSummary | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const signalFor = (m: JobMatchSummary): InterestLevel | null =>
    m.match_id in signals ? signals[m.match_id] : (m.applicant_interest ?? null);

  function handleSignalChange(
    m: JobMatchSummary,
    next: InterestLevel | null,
    prev: InterestLevel | null,
  ) {
    setSignals((s) => ({ ...s, [m.match_id]: next }));
    if (next !== "not_interested") return;

    // Hide the card, with an undo that restores card AND saved state.
    setHiddenIds((h) => new Set(h).add(m.match_id));
    toast.undo(`Marked not interested. ${m.job_title} hidden.`, async () => {
      // Bring the card back first so the undo feels instant…
      setHiddenIds((h) => {
        const nextSet = new Set(h);
        nextSet.delete(m.match_id);
        return nextSet;
      });
      // …then revert the saved signal to what it was before.
      try {
        await setMatchInterest(token, m.match_id, prev);
        setSignals((s) => ({ ...s, [m.match_id]: prev }));
      } catch {
        toast.error("The job is back in your list, but we couldn't clear the signal. Tap the pill to change it.");
      }
    });
  }

  if (fetchError) {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-caption text-cohere-ink flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {fetchError}
          </div>
        </div>
      </main>
    );
  }

  const matches = data;

  // Full served lists = server-rendered first page + incrementally loaded pages.
  const servedEligible = [...(matches?.eligible_matches ?? []), ...extra.eligible];
  const servedNearFit = [...(matches?.near_fit_matches ?? []), ...extra.near_fit];
  const servedNearby = [...(matches?.nearby_matches ?? []), ...extra.nearby];

  const visibleEligible = servedEligible.filter((m) => !hiddenIds.has(m.match_id));
  const visibleNearFit = servedNearFit.filter((m) => !hiddenIds.has(m.match_id));
  // Three-tier split (research-backed: plain-language tiers measurably steer
  // seekers toward winnable applications — ZipRecruiter saw -47% mismatched
  // applies after shipping theirs). Ours is derived from the auditable gate
  // count, not an opaque score: 1 gap = one named thing to close; 2+ = a
  // stretch worth knowing about but presented with more distance. The server
  // orders near-fit by n_gaps ASC, so this split is pagination-stable.
  const visibleOneStep = visibleNearFit.filter((m) => (m.n_gaps ?? 2) <= 1);
  const visibleStretch = visibleNearFit.filter((m) => (m.n_gaps ?? 2) >= 2);
  const visibleNearby = servedNearby.filter((m) => !hiddenIds.has(m.match_id));

  // Header counts come from the API's TRUE totals, not the served list — the
  // server caps each list, so len() would undercount a 274-near-fit applicant
  // as "100". Locally hidden (not-interested) cards are subtracted: hiding
  // only happens on served items, so total − hidden stays coherent.
  const hiddenIn = (list: JobMatchSummary[]) =>
    list.filter((m) => hiddenIds.has(m.match_id)).length;
  const eligibleCount = Math.max(0, (matches?.total_eligible ?? 0) - hiddenIn(servedEligible));
  const nearFitCount = Math.max(0, (matches?.total_near_fit ?? 0) - hiddenIn(servedNearFit));
  const nearbyCount = Math.max(0, (matches?.total_nearby ?? 0) - hiddenIn(servedNearby));
  const totalMatches = eligibleCount + nearFitCount + nearbyCount;

  async function loadMore(tier: TierKey) {
    if (loadingTier) return;
    setLoadingTier(tier);
    try {
      const served =
        tier === "eligible" ? servedEligible.length
        : tier === "near_fit" ? servedNearFit.length
        : servedNearby.length;
      const page = await fetchMyMatches(token, {
        eligibleOffset: tier === "eligible" ? served : 0,
        nearFitOffset: tier === "near_fit" ? served : 0,
        nearbyOffset: tier === "nearby" ? served : 0,
        limit: SHOW_MORE_PAGE,
      });
      const next =
        tier === "eligible" ? page.eligible_matches
        : tier === "near_fit" ? page.near_fit_matches
        : page.nearby_matches;
      // Guard against duplicates if the ranking shifted between requests.
      const seen = new Set(
        (tier === "eligible" ? servedEligible : tier === "near_fit" ? servedNearFit : servedNearby)
          .map((m) => m.match_id),
      );
      setExtra((e) => ({
        ...e,
        [tier]: [...e[tier], ...(next ?? []).filter((m) => !seen.has(m.match_id))],
      }));
    } catch {
      toast.error("Couldn't load more matches. Try again.");
    } finally {
      setLoadingTier(null);
    }
  }

  const renderRow = (m: JobMatchSummary) => (
    <div key={m.match_id}>
      <MatchRow
        match={m}
        token={token}
        signal={signalFor(m)}
        onSignalChange={(next, prev) => handleSignalChange(m, next, prev)}
        applied={applied[m.job_id]}
        onApply={() => { setSheetJob(m); setSheetOpen(true); }}
      />
    </div>
  );

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <BackLink />

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-cohere-ink">
              Your job matches
            </h1>
            <p className="mt-1.5 text-sm text-slate">
              Ranked by how well each role fits your trade, location, and background.
            </p>
          </div>
          <TourLaunchButton className="mt-1" />
        </div>

        {matches?.has_matches && (
          /* Numbers live in a sentence, not a stat strip. */
          <p className="text-body text-slate" data-tour-id="matches-summary">
            <span className="font-medium tabular-nums text-cohere-ink">{eligibleCount.toLocaleString()}</span> ready to apply
            <span className="mx-1.5 text-slate-muted">·</span>
            <span className="font-medium tabular-nums text-cohere-ink">{nearFitCount.toLocaleString()}</span> close
            {nearbyCount > 0 && (
              <>
                <span className="mx-1.5 text-slate-muted">·</span>
                <span className="font-medium tabular-nums text-cohere-ink">{nearbyCount.toLocaleString()}</span> near you
              </>
            )}
            <span className="mx-1.5 text-slate-muted">·</span>
            <span className="tabular-nums">{totalMatches.toLocaleString()}</span> total
          </p>
        )}

        {!matches?.has_matches ? (
          <NoMatchesCard
            profileHasFamily={matches?.profile_has_family ?? false}
            profileHasLocation={matches?.profile_has_location ?? false}
          />
        ) : (
          <>
            {/* Eligible Section */}
            <section data-tour-id="matches-ready">
              <h2 className="text-base font-semibold text-cohere-ink">
                Ready to apply <span className="ml-1 font-normal text-slate-muted">{eligibleCount.toLocaleString()}</span>
              </h2>
              <div className="mt-3">
                {visibleEligible.length === 0 ? (
                  <EmptySection message="Nothing here yet. Finish the rest of your profile to see jobs you're ready to apply to." />
                ) : (
                  <div className="space-y-4">
                    {visibleEligible.map(renderRow)}
                  </div>
                )}
                <ShowMore
                  shown={servedEligible.length}
                  total={matches?.total_eligible ?? 0}
                  loading={loadingTier === "eligible"}
                  disabled={loadingTier !== null}
                  onClick={() => loadMore("eligible")}
                />
              </div>
            </section>

            {/* One step away — near-fit with exactly one named gate to close */}
            <section data-tour-id="matches-close">
              <h2 className="text-base font-semibold text-cohere-ink">
                One step away <span className="ml-1 font-normal text-slate-muted">{visibleOneStep.length.toLocaleString()}</span>
              </h2>
              <p className="mt-0.5 text-micro text-slate-muted">
                One thing stands between you and eligible — each card names it.
              </p>
              <div className="mt-3">
                {visibleOneStep.length === 0 ? (
                  <EmptySection message="No one-step matches right now." />
                ) : (
                  <div className="space-y-4">
                    {visibleOneStep.map(renderRow)}
                  </div>
                )}
              </div>
            </section>

            {/* Worth exploring — near-fit with 2+ gaps, honestly framed */}
            {(visibleStretch.length > 0 || servedNearFit.length < (matches?.total_near_fit ?? 0)) && (
              <section>
                <h2 className="text-base font-semibold text-cohere-ink">
                  Worth exploring <span className="ml-1 font-normal text-slate-muted">{visibleStretch.length.toLocaleString()}</span>
                </h2>
                <p className="mt-0.5 text-micro text-slate-muted">
                  A few things to close before these are realistic — shown so you can see what's out there.
                </p>
                <div className="mt-3">
                  {visibleStretch.length > 0 && (
                    <div className="space-y-4">
                      {visibleStretch.map(renderRow)}
                    </div>
                  )}
                  <ShowMore
                    shown={servedNearFit.length}
                    total={matches?.total_near_fit ?? 0}
                    loading={loadingTier === "near_fit"}
                    disabled={loadingTier !== null}
                    onClick={() => loadMore("near_fit")}
                  />
                </div>
              </section>
            )}

            {/* Nearby tier — geography-only relaxation. Shown only when the
                stricter sections are thin; grouped separately and labeled so
                a different-trade job is never dressed up as a trade match. */}
            {visibleNearby.length > 0 && (
              <section>
                <h2 className="text-base font-semibold text-cohere-ink">
                  Near you, different trade{" "}
                  <span className="ml-1 font-normal text-slate-muted">{nearbyCount.toLocaleString()}</span>
                </h2>
                <p className="mt-1 text-body text-slate">
                  Employers hiring close to you in other trades. Shown because few
                  jobs match your trade right now.
                </p>
                <div className="mt-3 space-y-4">
                  {visibleNearby.map(renderRow)}
                </div>
                <ShowMore
                  shown={servedNearby.length}
                  total={matches?.total_nearby ?? 0}
                  loading={loadingTier === "nearby"}
                  disabled={loadingTier !== null}
                  onClick={() => loadMore("nearby")}
                />
              </section>
            )}
          </>
        )}

        {sheetJob && (
          <ApplySheet
            token={token}
            jobId={sheetJob.job_id}
            jobTitle={sheetJob.job_title}
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            onApplied={(app) =>
              setApplied((prev) => ({
                ...prev,
                [sheetJob.job_id]: { id: app.id, status: app.status, when: "Just now" },
              }))
            }
          />
        )}
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  Show more — per-tier incremental loading                           */
/* ------------------------------------------------------------------ */

function ShowMore({
  shown,
  total,
  loading,
  disabled,
  onClick,
}: {
  shown: number;
  total: number;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const remaining = total - shown;
  if (remaining <= 0) return null;
  return (
    <div className="mt-4">
      <button
        onClick={onClick}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-white px-4 py-1.5 text-caption font-medium text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink disabled:opacity-60"
      >
        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        Show more
        <span className="font-normal text-slate-muted tabular-nums">
          {remaining.toLocaleString()} left
        </span>
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Match Row — THE one card implementation for this list              */
/* ------------------------------------------------------------------ */

const WORK_SETTING_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  on_site: "On-site",
  flexible: "Flexible",
};

/**
 * A single match rendered as a white hairline card. The title links to the
 * match detail page; the commit Apply opens the in-platform ApplySheet
 * directly from the list (same pattern as JobBrowseClient).
 */
function MatchRow({
  match,
  token,
  signal,
  onSignalChange,
  applied,
  onApply,
}: {
  match: JobMatchSummary;
  token: string;
  signal: InterestLevel | null;
  onSignalChange: (next: InterestLevel | null, prev: InterestLevel | null) => void;
  applied?: AppliedInfo;
  onApply: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Explicit null check — a legitimate score of 0 must still render.
  // Information gate: a score computed mostly from null-handling defaults
  // (evidence below 40% of scoring weight) is not shown as a confident
  // numeral — the card says "Early estimate" until the profile carries
  // enough real data. Nothing is hidden; the label is the honest display.
  const lowEvidence =
    match.score_evidence_pct != null && match.score_evidence_pct < 40;
  const score = match.policy_adjusted_score != null && !lowEvidence
    ? Math.min(99, Math.floor(match.policy_adjusted_score))
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
    ? formatTradeLabel(match.canonical_job_family_code)
    : null;

  const eligible = match.eligibility_status === "eligible";
  // Nearby tier ("Near you, different trade"): the trade doesn't match, so
  // the card must never dress itself up as a fit — no fit chip, no score
  // numeral. The honest fact is the distance.
  const isNearby = match.match_tier === "nearby";
  // Fit chip = the stored, config-calibrated match_label (status-capped by
  // the engine). Never re-derived client-side from the raw score — a local
  // threshold would let this chip disagree with the detail page and the
  // employer's view of the same pair.
  const fitLabel = isNearby
    ? null
    : match.match_label
      ? (FIT_LABEL_TEXT[match.match_label] ?? null)
      : score !== null ? (eligible ? "Good fit" : "Near fit") : null;
  const tierChip = isNearby ? (match.tier_reason ?? "Near you, different trade") : null;
  const distanceLabel =
    isNearby && match.distance_miles !== null
      ? `${Math.round(match.distance_miles)} mi`
      : null;
  // Fit-label hues match the shared MatchLabel pill exactly — green (strong),
  // blue (good), slate (moderate), slate-muted (low); the statusTones
  // attention hue is reserved for the near-fit state. One hue per meaning.
  const fitToneClass = match.match_label
    ? ({
        strong_fit: "text-cohere-green",
        good_fit: "text-cohere-blue",
        moderate_fit: "text-slate",
        low_fit: "text-slate-muted",
      }[match.match_label] ?? "text-slate-muted")
    : match.eligibility_status === "eligible"
      ? "text-cohere-blue"
      : ATTENTION_TEXT_CLASS;

  const metaBits = [
    match.employer_name,
    location || null,
    workLabel,
    payDisplay,
  ].filter(Boolean) as string[];

  // ONE insight line — the actionable fact. A gap (what to fix) beats
  // restating strengths; strengths show only when there is nothing to close.
  const insight = match.top_gaps.length > 0
    ? { label: "To close", tone: ATTENTION_TEXT_CLASS, text: match.top_gaps.slice(0, 2).map(shortLabel).join(" · ") }
    : match.top_strengths.length > 0
      ? { label: "Working for you", tone: "text-cohere-ink", text: match.top_strengths.slice(0, 2).map(shortLabel).join(" · ") }
      : null;

  return (
    <article className="group rounded-[14px] border border-hairline bg-white p-6 transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float">
      {/* Header — editorial title vs one quiet numeral */}
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[11px] leading-none">
            {tierChip && (
              <span className="font-medium text-slate">{tierChip}</span>
            )}
            {fitLabel && (
              <span className={`font-medium ${fitToneClass}`}>{sentenceCase(fitLabel)}</span>
            )}
            {(fitLabel || tierChip) && familyLabel && <span aria-hidden className="text-slate-muted">·</span>}
            {familyLabel && <span className="text-slate-muted">{familyLabel}</span>}
          </div>
          <h3 className="mt-2 text-[1.25rem] font-semibold leading-snug text-cohere-ink">
            <Link
              href={`/applicant/matches/${match.match_id}`}
              className="transition-colors hover:underline decoration-hairline underline-offset-4 hover:decoration-cohere-ink"
            >
              {match.job_title}
            </Link>
          </h3>
          {metaBits.length > 0 && (
            <p className="mt-1.5 text-body text-slate">
              {metaBits.join("  ·  ")}
            </p>
          )}
        </div>
        {isNearby ? (
          distanceLabel && (
            <span
              className="shrink-0 pt-1 font-display text-[1.25rem] leading-none tabular-nums text-slate"
              title={`About ${distanceLabel} from home`}
            >
              {distanceLabel}
            </span>
          )
        ) : (
          score !== null ? (
            <span
              className="shrink-0 pt-1 font-display text-[1.75rem] leading-none tabular-nums text-cohere-ink"
              title={`Match score ${score} out of 100`}
            >
              {score}
            </span>
          ) : lowEvidence ? (
            <span
              className="shrink-0 pt-2 text-[11px] font-medium leading-tight text-slate-muted text-right max-w-[5.5rem]"
              title="We don't have enough profile information yet to score this precisely"
            >
              Early estimate
            </span>
          ) : null
        )}
      </div>

      {/* One insight line — never a checklist */}
      {insight && (
        <p className="mt-4 text-body text-slate">
          <span className={`font-medium ${insight.tone}`}>{insight.label}</span>{" "}
          {insight.text}
        </p>
      )}

      {/* Primary actions — internal apply commits from the list (same pattern
          as JobBrowseClient); external apply is the secondary ghost path. */}
      <div className="mt-5 flex flex-wrap items-center gap-4">
        {applied ? (
          <Link
            href={`/applicant/applications/${applied.id}`}
            className="inline-flex items-center gap-1 rounded-full border border-cohere-green bg-cohere-green px-3 py-1 text-caption font-medium text-white"
          >
            <Check className="w-3.5 h-3.5 text-white" /> Applied · {applied.when}
          </Link>
        ) : match.internal_apply ? (
          <button
            onClick={onApply}
            className={`${eligible ? "btn-commit" : "btn-ghost"} !px-4 !py-1.5 text-caption transition-transform duration-100 active:scale-[0.97]`}
          >
            Apply
          </button>
        ) : null}
        {!applied && match.source_url && (
          <a
            href={match.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className={`${match.internal_apply ? "text-body text-slate underline decoration-hairline underline-offset-4 transition-colors hover:text-cohere-ink hover:decoration-cohere-ink inline-flex items-center gap-1" : "btn-ghost !px-4 !py-1.5 text-caption inline-flex items-center gap-1.5"}`}
          >
            Apply on employer site <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        {hasDetail && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-body text-slate underline decoration-hairline underline-offset-4 transition-colors hover:text-cohere-ink hover:decoration-cohere-ink"
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
              <ExpandedMatchContent
                match={match}
                hasDetail={hasDetail}
                token={token}
                applied={applied}
                onApply={onApply}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Interest signal — quiet footer */}
      <div className="mt-6 border-t border-hairline pt-4">
        <InterestSignalPanel
          matchId={match.match_id}
          sourceUrl={match.source_url}
          initialSignal={match.applicant_interest ?? null}
          token={token}
          signal={signal}
          onSignalChange={onSignalChange}
        />
      </div>
    </article>
  );
}

/* ------------------------------------------------------------------ */
/*  Expanded match content                                             */
/* ------------------------------------------------------------------ */

function ExpandedMatchContent({
  match,
  hasDetail,
  token,
  applied,
  onApply,
}: {
  match: JobMatchSummary;
  hasDetail: boolean;
  token: string;
  applied?: AppliedInfo;
  onApply: () => void;
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
                  <span><Humanized text={stripZeroDistance(s)} /></span>
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
                  <AlertTriangle className={`w-3.5 h-3.5 ${ATTENTION_TEXT_CLASS} shrink-0 mt-0.5`} />
                  <span><Humanized text={stripZeroDistance(g)} /></span>
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
          <JobSections jobId={match.job_id} token={token} />
          {!applied && (match.internal_apply || match.source_url) && (
            <div className="flex flex-wrap items-center gap-2 pt-2">
              {match.internal_apply && (
                <button
                  onClick={onApply}
                  className="btn-commit inline-flex items-center gap-2 transition-transform duration-100 active:scale-[0.97]"
                >
                  Apply on SKILLED Nation
                </button>
              )}
              {match.source_url && (
                <a
                  href={match.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${match.internal_apply ? "btn-ghost" : "btn-primary"} inline-flex items-center gap-2`}
                >
                  Apply on employer site <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
          )}
          {applied && (
            <p className="pt-2 text-caption text-cohere-ink">
              <Check className="mr-1 inline w-3.5 h-3.5 text-cohere-green" />
              You applied to this job · {applied.when}
            </p>
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
  // Explicit null check — a legitimate score of 0 must still render.
  const lowEvidence =
    match.score_evidence_pct != null && match.score_evidence_pct < 40;
  const score = match.policy_adjusted_score != null
    ? Math.min(99, Math.floor(match.policy_adjusted_score))
    : null;

  return (
    <div className="bg-stone rounded-sm p-3 text-micro text-slate space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-medium text-ink">Overall score</span>
        <span className="font-bold text-cohere-blue">
          {lowEvidence ? "Early estimate" : `${score ?? "—"}/100`}
        </span>
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
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

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
      <p className="text-[1.0625rem] font-medium text-cohere-ink mt-3">
        No matches yet
      </p>
      <p className="text-caption text-slate mt-2">
        Finish your profile to see jobs you&apos;re ready to apply to.
      </p>
      {!profileHasFamily && (
        <p className="flex items-center justify-center gap-1.5 text-micro text-slate mt-4">
          <AlertCircle className={`w-3.5 h-3.5 ${ATTENTION_TEXT_CLASS}`} />
          Your trade program hasn&apos;t been normalized yet. This affects
          match quality.
        </p>
      )}
      {!profileHasLocation && (
        <p className="flex items-center justify-center gap-1.5 text-micro text-slate mt-2">
          <AlertCircle className={`w-3.5 h-3.5 ${ATTENTION_TEXT_CLASS}`} />
          Set your location for geography-based matching.
        </p>
      )}
    </div>
  );
}

function shortLabel(text: string): string {
  const cleaned = stripZeroDistance(text);
  const colonIdx = cleaned.indexOf(":");
  if (colonIdx > 0 && colonIdx < 35) {
    return cleaned.slice(0, colonIdx);
  }
  // Distance strengths ("~31 mi from Valencia, inside your 50 mi radius"):
  // keep the verified fact, drop the clause, never a mid-word ellipsis.
  // (Engine strings use ", " where they used " — " before the de-dash pass.)
  const sepIdx = cleaned.indexOf(", ");
  if (sepIdx > 0 && sepIdx <= 35) {
    return cleaned.slice(0, sepIdx);
  }
  return cleaned.length > 35 ? cleaned.slice(0, 35) + "..." : cleaned;
}

/**
 * "Credential readiness: has OSHA 10" → bold "Credential readiness" + em-dash.
 * The emphasis actually renders (a <strong>), unlike the old string-only
 * version whose markdown was stripped before display.
 */
function Humanized({ text }: { text: string }) {
  const m = text.match(/^([A-Z][a-z_]+(?: [A-Z][a-z_]+)*): ([\s\S]*)$/);
  if (!m) return <>{text}</>;
  return (
    <>
      <strong className="font-medium text-cohere-ink">{m[1]}</strong>: {m[2]}
    </>
  );
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
