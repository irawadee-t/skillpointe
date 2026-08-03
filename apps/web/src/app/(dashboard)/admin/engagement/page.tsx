/**
 * Admin Engagement — north-star + AARRR-flavoured supporting metrics.
 *
 * Design principle: one hero KPI (verified hires in the last 30 days), then
 * a small grid of supporting lenses (acquisition, activation, engagement,
 * conversion), then the two activation funnels + cohort retention + hire
 * economics. Nothing vanity: no total-events count, no page-view padding.
 *
 * All data comes from a single aggregate endpoint,
 *   GET /admin/analytics/engagement/summary
 *
 * Sub-tables (per-applicant / per-employer engagement) are still available
 * via ?view=applicants / ?view=employers for drill-down.
 */
import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, Breadcrumb, MetricCard, UrlSearchField, UrlSelectField } from "@/components/ui";
import { MarketplaceFunnel, TrendLine } from "@/components/viz";
import { MatchQualityCard } from "@/components/admin/MatchQualityCard";
import { PagerJump } from "@/components/admin/PagerJump";
import { formatRelative } from "@/lib/time";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SparkPt { label: string; value: number }
interface NorthStar {
  value: number;
  prev_value: number;
  all_time: number;
  spark: SparkPt[];
}
interface Lens {
  lens: "acquisition" | "activation" | "engagement" | "retention" | "conversion";
  label: string;
  value: string;
  detail: string;
  trend: number | null;
}
interface FunnelStep { label: string; count: number; pct_of_top: number }
interface RetCohort { week_offset: number; pct_returning: number; n_users: number }
interface TimeToHire { p50_days: number | null; p90_days: number | null; sample_size: number }
interface ResponseSLA { median_hours: number | null; p90_hours: number | null; sample_size: number }

interface Summary {
  generated_at: string;
  north_star: NorthStar;
  lenses: Lens[];
  applicant_funnel: FunnelStep[];
  employer_funnel: FunnelStep[];
  retention: RetCohort[];
  time_to_hire: TimeToHire;
  employer_response: ResponseSLA;
}

/**
 * The stage pair losing the most people — each funnel's one "so what".
 * Uses absolute loss, not rate: at small scale a "0 of 1" transition would
 * always win on rate while the real story is the hundreds lost earlier.
 */
function funnelDropTakeaway(steps: FunnelStep[]): string | null {
  if (steps.length < 2 || steps[0].count === 0) return null;
  let worstIdx = -1;
  let worstLoss = -1;
  for (let i = 0; i < steps.length - 1; i++) {
    if (steps[i].count === 0) break;
    const loss = steps[i].count - steps[i + 1].count;
    if (loss > worstLoss) {
      worstLoss = loss;
      worstIdx = i;
    }
  }
  if (worstIdx < 0 || worstLoss <= 0) return null;
  const from = steps[worstIdx];
  const to = steps[worstIdx + 1];
  const rate = to.count / from.count;
  const pctLabel = rate > 0 && rate < 0.005 ? "<1%" : `${Math.round(rate * 100)}%`;
  return `Biggest drop-off: ${from.label.toLowerCase()} → ${to.label.toLowerCase()}: ${to.count.toLocaleString()} of ${from.count.toLocaleString()} continue (${pctLabel}).`;
}

interface ApplicantRow {
  applicant_id: string;
  name: string;
  program: string | null;
  state: string | null;
  interest_signals: number;
  apply_clicks: number;
  chat_messages: number;
  dms_sent: number;
  total_events: number;
}

interface EmployerRow {
  employer_id: string;
  name: string;
  outreach_sent: number;
  dms_sent: number;
  hires_reported: number;
  candidates_viewed: number;
  total_actions: number;
}

// ---------------------------------------------------------------------------
// API fetchers
// ---------------------------------------------------------------------------

const API_URL = () =>
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchSummary(token: string): Promise<Summary | null> {
  try {
    const res = await fetch(`${API_URL()}/admin/analytics/engagement/summary`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

async function fetchApplicants(
  token: string, q: string, sort: string, page: number,
): Promise<{ total: number; active_total: number; rows: ApplicantRow[] } | null> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: "50",
    sort,
    ...(q ? { q } : {}),
  });
  try {
    const res = await fetch(
      `${API_URL()}/admin/analytics/engagement/applicants?${params}`,
      { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
    );
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

async function fetchEmployers(
  token: string, q: string, sort: string, page: number,
): Promise<{ total: number; active_total: number; rows: EmployerRow[] } | null> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: "50",
    sort,
    ...(q ? { q } : {}),
  });
  try {
    const res = await fetch(
      `${API_URL()}/admin/analytics/engagement/employers?${params}`,
      { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
    );
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Lens config — descriptive title per AARRR lens
// ---------------------------------------------------------------------------

const LENS_META: Record<Lens["lens"], { title: string }> = {
  acquisition: { title: "Acquisition" },
  activation:  { title: "Activation"  },
  engagement:  { title: "Engagement"  },
  retention:   { title: "Retention"   },
  conversion:  { title: "Conversion"  },
};

type View = "overview" | "applicants" | "employers";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface PageProps {
  searchParams: Promise<{
    view?: string;
    q?: string;
    sort?: string;
    page?: string;
  }>;
}

export default async function AdminEngagementPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const view: View =
    sp.view === "applicants" || sp.view === "employers" ? sp.view : "overview";
  const q = sp.q ?? "";
  const page = Math.max(1, Number(sp.page) || 1);

  const defaultSort: Record<View, string> = {
    overview:   "",
    applicants: "total_events",
    employers:  "total_actions",
  };
  const sort = sp.sort ?? defaultSort[view];
  const token = session.access_token;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Engagement" }]} />
        <PageHeader
          eyebrow="Engagement analytics"
          title="Platform engagement"
          lead="One north star, five lenses, two funnels. Cut deeper only when you have a reason to."
          actions={
            <Link href="/admin" className="btn-secondary">
              ← Dashboard
            </Link>
          }
        />

        {/* Tabs */}
        <div className="flex flex-wrap gap-2" data-tour-id="engagement-tabs">
          {(
            [
              { key: "overview",   label: "Overview" },
              { key: "applicants", label: "Applicant drill-down" },
              { key: "employers",  label: "Employer drill-down" },
            ] as { key: View; label: string }[]
          ).map(({ key, label }) => (
            <Link
              key={key}
              href={`/admin/engagement?view=${key}`}
              className={
                view === key
                  ? "btn-md"
                  : "btn-ghost"
              }
            >
              {label}
            </Link>
          ))}
        </div>

        {/* Stream the data section under the (already painted) header + tabs.
            key={view} remounts the boundary on tab switch so the fallback
            shows immediately instead of freezing on the previous view. */}
        <Suspense key={view} fallback={<ViewFallback />}>
          <EngagementView view={view} token={token} q={q} sort={sort} page={page} />
        </Suspense>
      </div>
    </main>
  );
}

/** Awaits the per-view fetch — identical fetch logic, just streamed. */
async function EngagementView({
  view,
  token,
  q,
  sort,
  page,
}: {
  view: View;
  token: string;
  q: string;
  sort: string;
  page: number;
}) {
  const [summary, applicantsData, employersData] = await Promise.all([
    view === "overview"   ? fetchSummary(token) : null,
    view === "applicants" ? fetchApplicants(token, q, sort, page) : null,
    view === "employers"  ? fetchEmployers(token, q, sort, page)  : null,
  ]);

  if (view === "applicants") return <ApplicantsView data={applicantsData} q={q} sort={sort} page={page} />;
  if (view === "employers")  return <EmployersView  data={employersData}  q={q} sort={sort} page={page} />;
  return <OverviewView data={summary} token={token} />;
}

/** Quiet shape-matched placeholder for the section below the tabs. */
function ViewFallback() {
  return (
    <div className="space-y-4" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="animate-pulse rounded-2xl border border-hairline bg-white p-6 motion-reduce:animate-none">
        <div className="h-3 w-40 rounded-md bg-stone/70" />
        <div className="mt-3 h-8 w-24 rounded-md bg-stone/70" />
        <div className="mt-4 h-16 w-full rounded-md bg-stone/40" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="animate-pulse rounded-2xl border border-hairline bg-white p-5 motion-reduce:animate-none">
            <div className="h-3 w-20 rounded-md bg-stone/70" />
            <div className="mt-3 h-6 w-14 rounded-md bg-stone/70" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="animate-pulse rounded-2xl border border-hairline bg-white p-6 motion-reduce:animate-none">
            <div className="h-4 w-48 rounded-md bg-stone/70" />
            <div className="mt-4 h-32 w-full rounded-md bg-stone/40" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function OverviewView({ data, token }: { data: Summary | null; token: string }) {
  if (!data) {
    return (
      <div className="bg-error-red/[0.06] border border-error-red/30 rounded-2xl p-5 text-caption text-cohere-ink">
        <strong>Could not load engagement summary.</strong> Please refresh.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div data-tour-id="engagement-northstar">
        <NorthStarCard ns={data.north_star} generatedAt={data.generated_at} />
      </div>

      <LensGrid lenses={data.lenses} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-tour-id="engagement-funnels">
        <FunnelCard
          title="Applicant activation funnel"
          subtitle="Signup → activated → transacting"
          steps={data.applicant_funnel}
        />
        <FunnelCard
          title="Employer activation funnel"
          subtitle="Onboarded → first job → first hire"
          steps={data.employer_funnel}
        />
      </div>

      {/* Marketplace health — how match quality is distributed across every
          scored pair (viz2 histogram; annotation computed server-side). */}
      <MatchQualityCard token={token} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RetentionCard cohorts={data.retention} />
        <HireEconomicsCard tth={data.time_to_hire} sla={data.employer_response} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// North star — the one metric that matters
// ---------------------------------------------------------------------------

function NorthStarCard({ ns, generatedAt }: { ns: NorthStar; generatedAt: string }) {
  const delta = ns.prev_value === 0 ? null : ((ns.value - ns.prev_value) / ns.prev_value) * 100;

  return (
    <section className="rounded-[10px] border border-hairline bg-white p-6">
      <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div>
          <p className="text-caption text-slate-muted">North star · last 30 days</p>
          <h2 className="mt-3 font-display text-heading leading-none tabular-nums text-cohere-ink">
            {ns.value.toLocaleString()}
          </h2>
          <p className="mt-3 text-body text-cohere-ink">Verified hires reported</p>
          <p className="mt-1 text-caption text-slate">
            {delta === null
              ? "No prior 30-day baseline yet"
              : `${delta > 0 ? "Up" : delta < 0 ? "Down" : "Flat at"} ${Math.abs(delta).toFixed(0)}% vs the prior 30 days (${ns.prev_value.toLocaleString()} hires)`}
            {" · "}
            {ns.all_time.toLocaleString()} all-time
          </p>
          <p className="mt-4 text-micro text-slate-muted">
            Refreshed {formatRelative(generatedAt)}
          </p>
        </div>

        <div>
          {(() => {
            // A trend line with ≤1 non-zero week is a flat line pretending to
            // be a signal — say what happened in a sentence instead.
            const nonZero = ns.spark.filter((p) => p.value > 0);
            if (nonZero.length <= 1) {
              return (
                <p className="border-t border-hairline pt-3 text-caption text-slate-muted lg:border-t-0 lg:pt-0">
                  {nonZero.length === 0
                    ? `No hires in the last 12 weeks${ns.all_time > 0 ? `. All ${ns.all_time.toLocaleString()} reported hire${ns.all_time === 1 ? "" : "s"} predate this window` : ""}.`
                    : `One hire in the last 12 weeks (week of ${nonZero[0].label}). A weekly trend appears once hires recur.`}
                </p>
              );
            }
            return (
              <>
                <p className="mb-2 text-caption text-slate-muted">Hires per week, last 12 weeks</p>
                <TrendLine
                  points={ns.spark.map((p) => ({ label: p.label.slice(5), value: p.value }))}
                  height={112}
                  ariaLabel="Weekly verified hires, last 12 weeks"
                />
              </>
            );
          })()}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Lens grid — one card per AARRR lens
// ---------------------------------------------------------------------------

function LensGrid({ lenses }: { lenses: Lens[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
      {lenses.map((lens, i) => {
        const meta = LENS_META[lens.lens];
        const trendText =
          lens.trend === null
            ? null
            : lens.trend > 0
              ? `up ${Math.abs(lens.trend).toFixed(0)}%`
              : lens.trend < 0
                ? `down ${Math.abs(lens.trend).toFixed(0)}%`
                : "flat";
        return (
          <MetricCard
            key={i}
            label={lens.label}
            value={lens.value}
            sub={[meta.title, trendText, lens.detail].filter(Boolean).join(" · ")}
            className="h-full"
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Funnel card — horizontal bars
// ---------------------------------------------------------------------------

function FunnelCard({
  title, subtitle, steps,
}: {
  title: string; subtitle: string; steps: FunnelStep[];
}) {
  const takeaway = funnelDropTakeaway(steps);
  return (
    <section className="rounded-[10px] border border-hairline bg-white p-5">
      <h3 className="text-[1.0625rem] font-medium text-cohere-ink">{title}</h3>
      <p className="mb-4 text-caption text-slate-muted">{subtitle}</p>
      <MarketplaceFunnel
        stages={steps.map((s) => ({ key: s.label, label: s.label, count: s.count }))}
      />
      {takeaway && (
        <p className="mt-3 border-t border-hairline pt-3 text-caption text-slate">{takeaway}</p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Retention curve — cohort of last 12 weeks, weeks since signup
// ---------------------------------------------------------------------------

function RetentionCard({ cohorts }: { cohorts: RetCohort[] }) {
  const points = cohorts.filter((c) => c.n_users > 0);
  const cohortSize = points[0]?.n_users ?? 0;
  // Post-signup weeks only: W0 "returning" is just signup-week activity.
  const anyReturn = points.some((c) => c.week_offset > 0 && c.pct_returning > 0);

  return (
    <section className="rounded-[10px] border border-hairline bg-white p-5">
      <h3 className="text-[1.0625rem] font-medium text-cohere-ink">Applicant retention</h3>
      <p className="mb-4 text-caption text-slate-muted">
        Share of a signup cohort returning in each subsequent week (last 12 weeks of cohorts)
      </p>
      {points.length === 0 ? (
        <p className="border-t border-hairline pt-3 text-caption text-slate-muted">
          Not enough cohort data yet. The curve appears once applicants have been signed up
          for at least one week.
        </p>
      ) : !anyReturn ? (
        // An all-zero curve is not a curve — state the fact it would draw.
        <p className="border-t border-hairline pt-3 text-caption text-slate-muted">
          0 of {cohortSize.toLocaleString()} applicants who signed up in the last 12 weeks
          came back in a later week. The curve appears once anyone returns.
        </p>
      ) : (
        <TrendLine
          points={points.map((c) => ({
            label: `W${c.week_offset}`,
            value: c.pct_returning,
          }))}
          height={168}
          domainMax={1}
          format="percent"
          ariaLabel="Cohort retention curve"
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Hire economics — time-to-hire p50/p90 + employer response SLA
// ---------------------------------------------------------------------------

function HireEconomicsCard({ tth, sla }: { tth: TimeToHire; sla: ResponseSLA }) {
  const fmtDays = (v: number | null) => v === null ? "—" : v < 1 ? `${(v * 24).toFixed(0)}h` : `${v.toFixed(1)}d`;
  const fmtHrs  = (v: number | null) => v === null ? "—" : v < 24 ? `${v.toFixed(1)}h` : `${(v / 24).toFixed(1)}d`;
  return (
    <section className="rounded-[10px] border border-hairline bg-white p-5">
      <h3 className="text-[1.0625rem] font-medium text-cohere-ink">Hire economics</h3>
      <p className="mb-4 text-caption text-slate-muted">
        The two levers that most correlate with a healthy marketplace: speed to hire, speed of employer response.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <MetricCard
          label="median time to hire"
          value={fmtDays(tth.p50_days)}
          sub={
            tth.sample_size === 0
              ? "No hires recorded yet"
              : `Across ${tth.sample_size.toLocaleString()} hire${tth.sample_size === 1 ? "" : "s"}${tth.sample_size < 5 ? " (directional only)" : ""}`
          }
        />
        <MetricCard
          label="time to hire, p90"
          value={fmtDays(tth.p90_days)}
          sub={tth.sample_size < 10 ? "Needs ~10+ hires to mean much" : "Long tail · slowest 10%"}
        />
        <MetricCard
          label="median employer reply"
          value={fmtHrs(sla.median_hours)}
          sub={
            sla.sample_size === 0
              ? "No replied conversations yet"
              : `Across ${sla.sample_size.toLocaleString()} conversation${sla.sample_size === 1 ? "" : "s"}${sla.sample_size < 5 ? " (directional only)" : ""}`
          }
        />
        <MetricCard
          label="employer reply, p90"
          value={fmtHrs(sla.p90_hours)}
          sub={sla.sample_size < 10 ? "Needs ~10+ conversations to mean much" : "Slowest 10% of employers"}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Applicant drill-down
// ---------------------------------------------------------------------------

function ApplicantsView({
  data, q, sort, page,
}: {
  data: { total: number; active_total: number; rows: ApplicantRow[] } | null;
  q: string; sort: string; page: number;
}) {
  const cols: { key: string; label: string }[] = [
    { key: "name", label: "Applicant" },
    { key: "interest_signals", label: "Interest signals" },
    { key: "apply_clicks", label: "Apply clicks" },
    { key: "chat_messages", label: "Chat messages" },
    { key: "dms_sent", label: "DMs sent" },
    { key: "total_events", label: "Total events" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap items-center">
        <UrlSearchField
          param="q"
          placeholder="Search applicant name…"
          className="w-56"
          inputClassName="px-3 py-1.5 pl-9 text-caption"
        />
        <UrlSelectField
          param="sort"
          defaultValue="total_events"
          selectClassName="px-3 py-1.5 text-caption w-auto"
          options={cols.slice(1).map((c) => ({ value: c.key, label: `Sort: ${c.label}` }))}
        />
        {(q || sort !== "total_events") && (
          <Link href="/admin/engagement?view=applicants" className="btn-ghost">Reset</Link>
        )}
      </div>

      {!data ? <ErrorBox /> : data.rows.length === 0 ? (
        <EmptyBox>
          No applicants found. <Link href="/admin/applicants" className="underline hover:text-cohere-ink">View all applicants</Link>.
        </EmptyBox>
      ) : (
        <>
          <p className="text-caption text-slate">
            <span className="tabular-nums">{(data.active_total ?? 0).toLocaleString()}</span> of{" "}
            <span className="tabular-nums">{data.total.toLocaleString()}</span>{" "}
            applicant{data.total !== 1 ? "s" : ""} {(data.active_total ?? 0) === 1 ? "has" : "have"}{" "}
            any recorded activity; the rest have never engaged on the platform.
          </p>
          <div className="overflow-x-auto rounded-[10px] border border-hairline bg-white">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-hairline">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      aria-sort={c.key !== "name" ? (sort === c.key ? "descending" : "none") : undefined}
                      className={`px-4 py-2.5 text-micro font-medium text-slate ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=applicants&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`transition-colors hover:text-cohere-ink ${sort === c.key ? "text-cohere-ink" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {data.rows.map((r) => (
                  <tr key={r.applicant_id} className="transition-colors hover:bg-parchment/40">
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-cohere-ink">{r.name}</p>
                      <p className="text-caption text-slate-muted">
                        {[r.program, r.state].filter(Boolean).join(", ")}
                      </p>
                    </td>
                    <NumCell val={r.interest_signals} />
                    <NumCell val={r.apply_clicks} />
                    <NumCell val={r.chat_messages} />
                    <NumCell val={r.dms_sent} />
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums text-cohere-ink">
                      {r.total_events}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination view="applicants" q={q} sort={sort} page={page} total={data.total} pageSize={50} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Employer drill-down
// ---------------------------------------------------------------------------

function EmployersView({
  data, q, sort, page,
}: {
  data: { total: number; active_total: number; rows: EmployerRow[] } | null;
  q: string; sort: string; page: number;
}) {
  const cols: { key: string; label: string }[] = [
    { key: "name", label: "Employer" },
    { key: "outreach_sent", label: "Outreach" },
    { key: "dms_sent", label: "DMs sent" },
    { key: "hires_reported", label: "Hires" },
    { key: "candidates_viewed", label: "Candidates viewed" },
    { key: "total_actions", label: "Total actions" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap items-center">
        <UrlSearchField
          param="q"
          placeholder="Search employer name…"
          className="w-56"
          inputClassName="px-3 py-1.5 pl-9 text-caption"
        />
        <UrlSelectField
          param="sort"
          defaultValue="total_actions"
          selectClassName="px-3 py-1.5 text-caption w-auto"
          options={cols.slice(1).map((c) => ({ value: c.key, label: `Sort: ${c.label}` }))}
        />
        {(q || sort !== "total_actions") && (
          <Link href="/admin/engagement?view=employers" className="btn-ghost">Reset</Link>
        )}
      </div>

      {!data ? <ErrorBox /> : data.rows.length === 0 ? (
        <EmptyBox>
          No employers found. <Link href="/admin/employers" className="underline hover:text-cohere-ink">View all employers</Link>.
        </EmptyBox>
      ) : (
        <>
          <p className="text-caption text-slate">
            <span className="tabular-nums">{(data.active_total ?? 0).toLocaleString()}</span> of{" "}
            <span className="tabular-nums">{data.total.toLocaleString()}</span>{" "}
            employer{data.total !== 1 ? "s" : ""} {(data.active_total ?? 0) === 1 ? "has" : "have"}{" "}
            taken any action (outreach, DM, candidate view, or hire).
          </p>
          <div className="overflow-x-auto rounded-[10px] border border-hairline bg-white">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-hairline">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      aria-sort={c.key !== "name" ? (sort === c.key ? "descending" : "none") : undefined}
                      className={`px-4 py-2.5 text-micro font-medium text-slate ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=employers&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`transition-colors hover:text-cohere-ink ${sort === c.key ? "text-cohere-ink" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {data.rows.map((r) => (
                  <tr key={r.employer_id} className="transition-colors hover:bg-parchment/40">
                    <td className="px-4 py-2.5 font-medium text-cohere-ink">{r.name}</td>
                    <NumCell val={r.outreach_sent} />
                    <NumCell val={r.dms_sent} />
                    <NumCell val={r.hires_reported} />
                    <NumCell val={r.candidates_viewed} />
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums text-cohere-ink">
                      {r.total_actions}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination view="employers" q={q} sort={sort} page={page} total={data.total} pageSize={50} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function NumCell({ val }: { val: number }) {
  return (
    <td className={`px-4 py-2.5 text-right text-body tabular-nums ${
      val > 0 ? "text-cohere-ink" : "text-slate-muted/50"
    }`}>
      {val}
    </td>
  );
}

function Pagination({
  view, q, sort, page, total, pageSize,
}: {
  view: string; q: string; sort: string; page: number; total: number; pageSize: number;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  const base = `/admin/engagement?view=${view}${q ? `&q=${encodeURIComponent(q)}` : ""}&sort=${sort}`;

  return (
    <div className="flex flex-wrap items-center gap-3 justify-end text-caption">
      {page > 1 && (
        <Link href={`${base}&page=${page - 1}`} className="text-slate transition-colors hover:text-cohere-ink">
          ← Prev
        </Link>
      )}
      <PagerJump
        basePath="/admin/engagement"
        params={{ view, ...(q ? { q } : {}), sort }}
        page={page}
        totalPages={totalPages}
      />
      {page < totalPages && (
        <Link href={`${base}&page=${page + 1}`} className="text-slate transition-colors hover:text-cohere-ink">
          Next →
        </Link>
      )}
    </div>
  );
}

function ErrorBox() {
  return (
    <div className="bg-error-red/[0.06] border border-error-red/30 rounded-2xl p-5 text-caption text-cohere-ink">
      Could not load data. Please refresh.
    </div>
  );
}

function EmptyBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-hairline bg-white p-10 text-center text-caption text-slate-muted">
      {children}
    </div>
  );
}

