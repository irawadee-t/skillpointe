/**
 * Employer Analytics Page
 *
 * Ordered by actionability, not by what we happen to count:
 *   1. "What to do next" — candidates waiting on this employer (no outreach,
 *      no DM) and unopened applications, each with a direct link to act.
 *   2. Pipeline phrase-stats (outreach → interested → applied → hired).
 *   3. Hiring intelligence (only once real hires exist).
 *   4. Recent outreach history + the analytics chat.
 *
 * Server component.
 */
import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Clock, DollarSign, Gauge, Sparkles, ThumbsUp } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, Card, MetricCard, MonoLabel, Stagger, StaggerItem } from "@/components/ui";
import { AnalyticsChat } from "@/components/employer/AnalyticsChat";
import { InsightFreshness } from "@/components/employer/InsightFreshness";
import { formatRelative } from "@/lib/time";

const API_URL = () =>
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchAnalytics(token: string) {
  const res = await fetch(`${API_URL()}/employer/me/analytics`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<{
    outreach_sent: number;
    candidates_interested: number;
    candidates_applied: number;
    hired_count: number;
    declined_count: number;
    // Application pipeline — same table + predicates as the applications inbox.
    applications_total: number;
    applications_new: number;
    applications_in_review: number;
    applications_interviewing: number;
    applications_hired: number;
    recent_outreach: Array<{
      id: string;
      subject: string;
      sent_at: string | null;
      applicant_name: string;
      job_title: string;
    }>;
  }>;
}

interface EmployerInsights {
  hires: number;
  time_to_fill_days: number | null;
  median_wage: number | null;
  platform_median_wage: number | null;
  wage_vs_platform_pct: number | null;
  avg_match_fit: number | null;
  strong_matches: number;
  surfaced: number;
  narrative: string;
  narrative_source: string;
}

interface NextActions {
  waiting_candidates_total: number;
  waiting_candidates: Array<{
    applicant_id: string;
    name: string;
    job_id: string;
    job_title: string;
    interest_level: string;
    since: string | null;
  }>;
  unviewed_applications: number;
  open_applications: number;
}

async function fetchInsights(token: string): Promise<EmployerInsights | null> {
  try {
    const res = await fetch(`${API_URL()}/employer/me/analytics/insights`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as EmployerInsights;
  } catch {
    return null;
  }
}

async function fetchNextActions(token: string): Promise<NextActions | null> {
  try {
    const res = await fetch(`${API_URL()}/employer/me/analytics/next-actions`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as NextActions;
  } catch {
    return null;
  }
}

export default async function EmployerAnalyticsPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer") redirect("/login");

  // The header paints immediately; the three analytics fetches stream in
  // below via Suspense. Fetch logic itself is unchanged.
  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        {/* Header */}
        <div>
          <BackLink />
          <div className="mt-3">
            <PageHeader
              eyebrow="Employer workspace"
              title="Analytics"
              lead="What's waiting on you, and how your hiring pipeline is doing"
            />
          </div>
        </div>

        <Suspense fallback={<AnalyticsFallback />}>
          <AnalyticsBody token={session.access_token} />
        </Suspense>
      </div>
    </main>
  );
}

/** Quiet shape-matched placeholder for the streamed sections. */
function AnalyticsFallback() {
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="animate-pulse rounded-[10px] border border-hairline bg-white p-5 motion-reduce:animate-none">
        <div className="h-4 w-64 max-w-full rounded-md bg-stone/70" />
        <div className="mt-3 h-3 w-40 rounded-md bg-stone/70" />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="animate-pulse rounded-[10px] border border-hairline bg-white p-4 motion-reduce:animate-none">
            <div className="h-3 w-20 rounded-md bg-stone/70" />
            <div className="mt-3 h-6 w-12 rounded-md bg-stone/70" />
          </div>
        ))}
      </div>
      <div className="animate-pulse rounded-[10px] border border-hairline bg-white p-6 motion-reduce:animate-none">
        <div className="h-4 w-40 rounded-md bg-stone/70" />
        <div className="mt-4 space-y-2.5">
          <div className="h-3 w-full rounded-md bg-stone/70" />
          <div className="h-3 w-5/6 rounded-md bg-stone/70" />
          <div className="h-3 w-2/3 rounded-md bg-stone/70" />
        </div>
      </div>
    </div>
  );
}

/** Awaits the analytics fetches — identical fetch logic, just streamed. */
async function AnalyticsBody({ token }: { token: string }) {
  // All three are independent — fetch concurrently instead of insights+actions
  // then analytics in sequence.
  const [insights, nextActions, analyticsResult] = await Promise.all([
    fetchInsights(token),
    fetchNextActions(token),
    fetchAnalytics(token).then(
      (d) => ({ ok: true as const, data: d }),
      () => ({ ok: false as const, data: null }),
    ),
  ]);
  const data = analyticsResult.data;
  if (!analyticsResult.ok || !data) {
    return (
      <div className="rounded-md border border-error-red/30 bg-rose-50 p-5 text-body text-error-red">
        <strong className="font-medium">Could not reach the API.</strong> The backend may be starting up. Please refresh.
      </div>
    );
  }

  // Pipeline tiles come from the APPLICATIONS table — the same rows, same
  // bucket predicates, as the /employer/applications inbox. One query family,
  // one truth: "applied" here means an application, exactly as in the inbox.
  const stats = [
    { label: "new applications", value: data.applications_new },
    { label: "in review", value: data.applications_in_review },
    { label: "interviewing", value: data.applications_interviewing },
    { label: "hired", value: data.applications_hired },
  ];

  // One honest reading of the pipeline, computed from the same numbers shown.
  const openWork = data.applications_new + data.applications_in_review + data.applications_interviewing;
  const pipelineTakeaway =
    data.applications_total > 0
      ? `${data.applications_total.toLocaleString()} application${data.applications_total === 1 ? "" : "s"} received in total. ${openWork.toLocaleString()} still in play${data.applications_hired > 0 ? `, ${data.applications_hired.toLocaleString()} hired` : ""}.`
      : data.outreach_sent > 0
        ? `No applications yet. You've reached out ${data.outreach_sent.toLocaleString()} time${data.outreach_sent === 1 ? "" : "s"}.`
        : "No applications yet. Start with the matched candidates on each job.";

  // Interest signals are a separate, self-reported family (saved_jobs) —
  // presented as a sentence, never mixed into the pipeline tiles.
  const interestSentence =
    data.candidates_interested + data.candidates_applied > 0
      ? `Interest signals from matches: ${data.candidates_interested.toLocaleString()} marked interested, ${data.candidates_applied.toLocaleString()} said they applied (self-reported) · ${data.outreach_sent.toLocaleString()} outreach logged.`
      : `Outreach logged: ${data.outreach_sent.toLocaleString()}.`;

  return (
    <>
        {/* 1 — What to do next: the action queue, before any counting.
            "Caught up" only when NOTHING is pending: no waiting candidates AND
            no open (undecided) applications — the same rows the inbox shows. */}
        {nextActions && (
          <section className="space-y-3" data-tour-id="analytics-next">
            <MonoLabel className="block">What to do next</MonoLabel>
            {nextActions.waiting_candidates_total === 0 && nextActions.open_applications === 0 ? (
              <div className="rounded-[10px] border border-hairline bg-white p-5">
                <p className="text-body text-cohere-ink">
                  You&apos;re caught up. No candidates or applications are waiting on you.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-[10px] border border-hairline bg-white">
                {nextActions.waiting_candidates_total > 0 && (
                  <div className="p-5">
                    <p className="text-body text-cohere-ink">
                      <span className="font-medium tabular-nums">{nextActions.waiting_candidates_total.toLocaleString()}</span>{" "}
                      candidate{nextActions.waiting_candidates_total === 1 ? " has" : "s have"} raised a hand on your
                      jobs and {nextActions.waiting_candidates_total === 1 ? "hasn't" : "haven't"} heard from you.
                    </p>
                    <ul className="mt-3 divide-y divide-hairline border-t border-hairline">
                      {nextActions.waiting_candidates.map((c) => (
                        <li key={`${c.applicant_id}-${c.job_id}`}>
                          <Link
                            href={`/employer/jobs/${c.job_id}/applicants`}
                            className="group flex items-center justify-between gap-4 py-3 transition-colors hover:bg-parchment/40"
                          >
                            <div className="min-w-0">
                              <p className="truncate text-body font-medium text-cohere-ink">{c.name}</p>
                              <p className="mt-0.5 truncate text-caption text-slate">
                                {c.interest_level === "applied" ? "Applied to" : "Interested in"} {c.job_title}
                                {c.since ? ` · ${formatRelative(c.since)}` : ""}
                              </p>
                            </div>
                            <span className="inline-flex shrink-0 items-center gap-1 text-caption text-slate transition-colors group-hover:text-cohere-ink">
                              Reach out <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                    {nextActions.waiting_candidates_total > nextActions.waiting_candidates.length && (
                      <p className="mt-2 text-caption text-slate-muted">
                        + {(nextActions.waiting_candidates_total - nextActions.waiting_candidates.length).toLocaleString()} more waiting
                      </p>
                    )}
                  </div>
                )}
                {nextActions.open_applications > 0 && (
                  <Link
                    href="/employer/applications"
                    className="group flex items-center justify-between gap-4 border-t border-hairline p-5 transition-colors hover:bg-parchment/40"
                  >
                    <p className="text-body text-cohere-ink">
                      <span className="font-medium tabular-nums">{nextActions.open_applications.toLocaleString()}</span>{" "}
                      application{nextActions.open_applications === 1 ? "" : "s"} awaiting your decision
                      {nextActions.unviewed_applications > 0 && (
                        <span className="text-slate">
                          {" "}({nextActions.unviewed_applications.toLocaleString()} never opened)
                        </span>
                      )}
                    </p>
                    <span className="inline-flex shrink-0 items-center gap-1 text-caption text-slate transition-colors group-hover:text-cohere-ink">
                      Review <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  </Link>
                )}
              </div>
            )}
          </section>
        )}

        {/* 2 — Application pipeline (same rows as the applications inbox) +
            one computed takeaway. Interest signals stay a separate sentence. */}
        <section className="space-y-3" data-tour-id="analytics-pipeline">
          <MonoLabel className="block">Your application pipeline</MonoLabel>
          <Stagger className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {stats.map(({ label, value }) => (
              <StaggerItem key={label}>
                <MetricCard label={label} value={value.toLocaleString()} className="h-full" />
              </StaggerItem>
            ))}
          </Stagger>
          <p className="text-caption text-slate">{pipelineTakeaway}</p>
          <p className="text-caption text-slate-muted">{interestSentence}</p>
        </section>

        {/* Hiring intelligence */}
        {insights && insights.hires > 0 && (
          <section className="space-y-4">
            <MonoLabel className="block">Hiring intelligence</MonoLabel>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MetricCard
                label="median time to fill"
                value={insights.time_to_fill_days != null ? `${insights.time_to_fill_days}d` : "—"}
                icon={Clock}
                sub={
                  insights.time_to_fill_days != null
                    ? `Across ${insights.hires.toLocaleString()} hire${insights.hires === 1 ? "" : "s"}${insights.hires < 5 ? " (directional only)" : ""}`
                    : "Add a hire date when reporting hires to see time to fill"
                }
              />
              <MetricCard
                label="median wage"
                value={insights.median_wage != null ? `$${insights.median_wage.toLocaleString()}` : "—"}
                icon={DollarSign}
                sub={insights.median_wage == null ? "Report a wage when marking hires to see wage benchmarks" : undefined}
              />
              <MetricCard
                label="vs platform median"
                value={
                  insights.wage_vs_platform_pct != null
                    ? `${insights.wage_vs_platform_pct >= 0 ? "+" : ""}${insights.wage_vs_platform_pct}%`
                    : "—"
                }
                icon={Gauge}
                sub={insights.wage_vs_platform_pct == null ? "Appears once your hires and the platform both have reported wages" : undefined}
              />
              <MetricCard
                label="avg candidate fit"
                value={insights.avg_match_fit != null ? `${Math.round(insights.avg_match_fit * 100)}%` : "—"}
                icon={ThumbsUp}
                sub={
                  insights.avg_match_fit != null
                    ? `${insights.strong_matches.toLocaleString()} of the ${insights.surfaced.toLocaleString()} candidates matched to your jobs score 70+`
                    : "Appears once candidates are matched to your jobs"
                }
              />
            </div>

            {/* AI insight — bordered white card with a soft accent rule, no green fill */}
            <div className="relative rounded-xl border border-hairline bg-white p-6 pl-7 shadow-[0_1px_2px_rgba(12,10,9,0.04)] before:absolute before:left-0 before:top-5 before:bottom-5 before:w-[3px] before:rounded-full before:bg-cohere-green">
              <div className="flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-cohere-green" strokeWidth={1.75} />
                <MonoLabel className="text-cohere-green">Reading of your data</MonoLabel>
              </div>
              <p className="mt-3 text-body-lg leading-relaxed text-cohere-ink">{insights.narrative}</p>
              <InsightFreshness />
              <p className="mt-3 text-micro text-slate-muted">
                Wage benchmark is platform-internal. Narrative{" "}
                {insights.narrative_source === "ai" ? "written by AI" : "computed directly from your numbers"}.
              </p>
            </div>
          </section>
        )}

        {/* Recent outreach */}
        <section>
          <MonoLabel className="mb-5 block">Recent outreach</MonoLabel>
          {data.recent_outreach.length === 0 ? (
            <div className="rounded-[10px] border border-hairline bg-white p-6">
              <p className="text-body text-cohere-ink">No outreach sent yet.</p>
              <p className="mt-1 text-body text-slate">
                Use the &quot;Reach out&quot; button on matched candidate cards
                {nextActions && nextActions.waiting_candidates_total > 0
                  ? ". Start with the waiting candidates above."
                  : "."}
              </p>
            </div>
          ) : (
            <Stagger className="space-y-3">
              {data.recent_outreach.map((o) => (
                <StaggerItem key={o.id}>
                  <Card className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-semibold text-cohere-ink truncate">
                          {o.applicant_name}
                        </p>
                        <p className="text-body text-slate">{o.job_title}</p>
                        {o.subject && (
                          <p className="text-body text-slate mt-0.5 truncate">
                            {o.subject}
                          </p>
                        )}
                      </div>
                      {o.sent_at && (
                        <span className="shrink-0 text-body text-slate tabular-nums">
                          {formatRelative(o.sent_at)}
                        </span>
                      )}
                    </div>
                  </Card>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </section>

        <div data-tour-id="analytics-ask">
          <AnalyticsChat token={token} />
        </div>
    </>
  );
}

function BackLink() {
  return (
    <Link
      href="/employer"
      className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
    >
      ← Back to dashboard
    </Link>
  );
}
