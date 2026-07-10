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
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  UserPlus,
  Zap,
  TrendingUp,
  Target,
  Activity,
} from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, Breadcrumb } from "@/components/ui";
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
): Promise<{ total: number; rows: ApplicantRow[] } | null> {
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
): Promise<{ total: number; rows: EmployerRow[] } | null> {
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
// Lens config — icon + descriptive title per AARRR lens
// ---------------------------------------------------------------------------

const LENS_META: Record<Lens["lens"], { icon: React.ElementType; title: string }> = {
  acquisition: { icon: UserPlus,   title: "Acquisition" },
  activation:  { icon: Zap,        title: "Activation"  },
  engagement:  { icon: Activity,   title: "Engagement"  },
  retention:   { icon: TrendingUp, title: "Retention"   },
  conversion:  { icon: Target,     title: "Conversion"  },
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

  const [summary, applicantsData, employersData] = await Promise.all([
    view === "overview"   ? fetchSummary(token) : null,
    view === "applicants" ? fetchApplicants(token, q, sort, page) : null,
    view === "employers"  ? fetchEmployers(token, q, sort, page)  : null,
  ]);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Engagement" }]} />
        <PageHeader
          eyebrow="Engagement analytics"
          title="Platform Engagement"
          lead="One north star, five lenses, two funnels. Cut deeper only when you have a reason to."
          actions={
            <Link href="/admin" className="btn-secondary">
              ← Dashboard
            </Link>
          }
        />

        {/* Tabs */}
        <div className="flex flex-wrap gap-2">
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

        {view === "overview"   && <OverviewView data={summary} />}
        {view === "applicants" && <ApplicantsView data={applicantsData} q={q} sort={sort} page={page} />}
        {view === "employers"  && <EmployersView  data={employersData}  q={q} sort={sort} page={page} />}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function OverviewView({ data }: { data: Summary | null }) {
  if (!data) {
    return (
      <div className="bg-cohere-coral/10 border border-cohere-coral-soft rounded-2xl p-5 text-caption text-cohere-ink">
        <strong>Could not load engagement summary.</strong> Please refresh.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <NorthStarCard ns={data.north_star} generatedAt={data.generated_at} />

      <LensGrid lenses={data.lenses} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
  const arrow = delta === null ? "" : delta > 0 ? "▲" : delta < 0 ? "▼" : "•";

  return (
    <section className="rounded-2xl border border-studio-dark-cork/15 bg-studio-cream p-6 shadow-subtle">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-6 items-center">
        <div>
          <p className="text-caption font-medium text-studio-sienna">
            NORTH STAR — LAST 30 DAYS
          </p>
          <h2 className="mt-3 font-display text-heading text-studio-maroon leading-none tabular-nums">
            {ns.value}
          </h2>
          <p className="mt-3 text-body text-studio-dark-cork">
            Verified hires reported
          </p>
          <p className="mt-1 text-caption text-studio-dark-cork/70">
            {delta === null ? (
              <>No prior 30-day baseline yet.</>
            ) : (
              <>
                <span className={delta > 0 ? "text-studio-forest font-semibold" : delta < 0 ? "text-studio-maroon font-semibold" : ""}>
                  {arrow} {Math.abs(delta).toFixed(0)}%
                </span>{" "}
                vs prior 30d ({ns.prev_value} hires)
              </>
            )}
            {", "}
            <span className="text-studio-dark-cork/60">
              {ns.all_time.toLocaleString()} all-time
            </span>
          </p>
          <p className="mt-4 text-micro text-studio-dark-cork/50">
            Refreshed {formatRelative(generatedAt)}
          </p>
        </div>

        <div>
          <p className="text-caption font-medium text-studio-dark-cork/70 mb-2">
            12-WEEK TREND
          </p>
          <Sparkline points={ns.spark} />
        </div>
      </div>
    </section>
  );
}

function Sparkline({ points }: { points: SparkPt[] }) {
  if (points.length === 0) {
    return <p className="text-caption text-studio-dark-cork/60">No data yet.</p>;
  }
  const w = 560;
  const h = 100;
  const pad = 8;
  const max = Math.max(1, ...points.map(p => p.value));
  const stepX = (w - pad * 2) / Math.max(1, points.length - 1);
  const y = (v: number) => h - pad - (v / max) * (h - pad * 2);

  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${(pad + i * stepX).toFixed(1)} ${y(p.value).toFixed(1)}`)
    .join(" ");

  const areaPath =
    `M ${pad} ${h - pad} ` +
    points.map((p, i) => `L ${(pad + i * stepX).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ") +
    ` L ${(pad + (points.length - 1) * stepX).toFixed(1)} ${h - pad} Z`;

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full h-24"
        role="img"
        aria-label="12-week hires trend"
      >
        <path d={areaPath} fill="#9E1B32" fillOpacity="0.08" />
        <path d={path} fill="none" stroke="#9E1B32" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={pad + i * stepX}
            cy={y(p.value)}
            r="2.5"
            fill="#9E1B32"
          />
        ))}
      </svg>
      <div className="flex justify-between mt-1 text-micro text-studio-dark-cork/50">
        <span>{points[0]?.label.slice(5) ?? ""}</span>
        <span>{points[points.length - 1]?.label.slice(5) ?? ""}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lens grid — one card per AARRR lens
// ---------------------------------------------------------------------------

function LensGrid({ lenses }: { lenses: Lens[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
      {lenses.map((lens, i) => {
        const meta = LENS_META[lens.lens];
        const Icon = meta.icon;
        const arrow = lens.trend === null ? "" : lens.trend > 0 ? "▲" : lens.trend < 0 ? "▼" : "•";
        const trendClass =
          lens.trend === null ? "text-studio-dark-cork/50"
          : lens.trend > 0 ? "text-studio-forest"
          : lens.trend < 0 ? "text-studio-maroon"
          : "text-studio-dark-cork/60";
        return (
          <div
            key={i}
            className="rounded-2xl border border-studio-dark-cork/15 bg-white p-4 shadow-subtle"
          >
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-studio-cream p-1.5">
                <Icon className="h-3.5 w-3.5 text-studio-dark-cork" strokeWidth={1.75} />
              </span>
              <span className="text-micro font-medium text-studio-dark-cork/70">
                {meta.title}
              </span>
            </div>
            <p className="mt-2 text-caption text-studio-dark-cork/80">
              {lens.label}
            </p>
            <p className="mt-2 font-display text-card text-studio-maroon leading-none tabular-nums">
              {lens.value}
            </p>
            <p className="mt-3 text-caption text-studio-dark-cork/60 leading-snug">
              {lens.trend !== null && (
                <>
                  <span className={`font-semibold ${trendClass}`}>
                    {arrow} {Math.abs(lens.trend).toFixed(0)}%
                  </span>
                  {", "}
                </>
              )}
              {lens.detail}
            </p>
          </div>
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
  return (
    <section className="rounded-2xl border border-studio-dark-cork/15 bg-white p-5 shadow-subtle">
      <h3 className="font-display text-subhead text-studio-maroon">{title}</h3>
      <p className="text-caption text-studio-dark-cork/60 mb-4">{subtitle}</p>
      <div className="space-y-3">
        {steps.map((s, i) => {
          const pct = Math.round(s.pct_of_top * 100);
          return (
            <div key={i}>
              <div className="flex justify-between items-baseline mb-1">
                <span className="text-caption text-studio-dark-cork">{s.label}</span>
                <span className="text-caption text-studio-dark-cork tabular-nums">
                  {s.count.toLocaleString()}
                  <span className="text-studio-dark-cork/50">, {pct}%</span>
                </span>
              </div>
              <div className="h-2 rounded-sm bg-studio-cream overflow-hidden">
                <div
                  className="h-full bg-studio-maroon"
                  style={{ width: `${Math.max(pct, 2)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Retention curve — cohort of last 12 weeks, weeks since signup
// ---------------------------------------------------------------------------

function RetentionCard({ cohorts }: { cohorts: RetCohort[] }) {
  const w = 480;
  const h = 180;
  const pad = { l: 32, r: 12, t: 12, b: 28 };
  const points = cohorts.filter(c => c.n_users > 0);
  const stepX = points.length > 1 ? (w - pad.l - pad.r) / (points.length - 1) : 0;
  const y = (pct: number) => pad.t + (1 - pct) * (h - pad.t - pad.b);

  const path = points
    .map((c, i) => `${i === 0 ? "M" : "L"} ${(pad.l + i * stepX).toFixed(1)} ${y(c.pct_returning).toFixed(1)}`)
    .join(" ");

  return (
    <section className="rounded-2xl border border-studio-dark-cork/15 bg-white p-5 shadow-subtle">
      <h3 className="font-display text-subhead text-studio-maroon">Applicant retention</h3>
      <p className="text-caption text-studio-dark-cork/60 mb-4">
        % of a signup cohort returning in each subsequent week (last 12 weeks of cohorts)
      </p>
      {points.length === 0 ? (
        <p className="text-caption text-studio-dark-cork/60 py-8 text-center">
          Not enough cohort data yet. Curve appears once applicants have been signed up for at least 1 week.
        </p>
      ) : (
        <div className="w-full overflow-x-auto">
          <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-44" role="img" aria-label="Cohort retention curve">
            {/* gridlines at 0/25/50/75/100% */}
            {[0, 0.25, 0.5, 0.75, 1].map((g) => (
              <g key={g}>
                <line
                  x1={pad.l} y1={y(g)}
                  x2={w - pad.r} y2={y(g)}
                  stroke="#000" strokeOpacity="0.06" strokeDasharray="2 3"
                />
                <text
                  x={pad.l - 6} y={y(g) + 3}
                  textAnchor="end"
                  className=""
                  fontSize="10"
                  fill="#5c4d3d"
                >
                  {Math.round(g * 100)}%
                </text>
              </g>
            ))}
            {/* x-axis labels */}
            {points.map((c, i) => (
              <text
                key={c.week_offset}
                x={pad.l + i * stepX}
                y={h - 8}
                textAnchor="middle"
                className=""
                fontSize="10"
                fill="#5c4d3d"
              >
                W{c.week_offset}
              </text>
            ))}
            {/* line */}
            <path d={path} fill="none" stroke="#9E1B32" strokeWidth="2" strokeLinejoin="round" />
            {points.map((c, i) => (
              <circle
                key={c.week_offset}
                cx={pad.l + i * stepX}
                cy={y(c.pct_returning)}
                r="3"
                fill="#9E1B32"
              />
            ))}
          </svg>
        </div>
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
    <section className="rounded-2xl border border-studio-dark-cork/15 bg-white p-5 shadow-subtle">
      <h3 className="font-display text-subhead text-studio-maroon">Hire economics</h3>
      <p className="text-caption text-studio-dark-cork/60 mb-4">
        The two levers that most correlate with a healthy marketplace: speed to hire, speed of employer response.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <StatBlock
          label="Time to hire (p50)"
          value={fmtDays(tth.p50_days)}
          detail={`n=${tth.sample_size}`}
        />
        <StatBlock
          label="Time to hire (p90)"
          value={fmtDays(tth.p90_days)}
          detail="Long-tail — worst 10%"
        />
        <StatBlock
          label="Employer reply (median)"
          value={fmtHrs(sla.median_hours)}
          detail={`n=${sla.sample_size} conversations`}
        />
        <StatBlock
          label="Employer reply (p90)"
          value={fmtHrs(sla.p90_hours)}
          detail="Worst 10% of employers"
        />
      </div>
    </section>
  );
}

function StatBlock({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl bg-studio-cream/60 p-3">
      <p className="text-micro font-medium text-studio-dark-cork/70">
        {label}
      </p>
      <p className="mt-1 font-display text-feature text-studio-maroon tabular-nums leading-none">
        {value}
      </p>
      <p className="mt-1 text-caption text-studio-dark-cork/60">
        {detail}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Applicant drill-down
// ---------------------------------------------------------------------------

function ApplicantsView({
  data, q, sort, page,
}: {
  data: { total: number; rows: ApplicantRow[] } | null;
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
      <form method="GET" action="/admin/engagement" className="flex gap-3 flex-wrap">
        <input type="hidden" name="view" value="applicants" />
        <input
          name="q"
          defaultValue={q}
          placeholder="Search applicant name…"
          className="input-cohere px-3 py-1.5 text-caption w-56"
        />
        <select
          name="sort"
          defaultValue={sort}
          className="input-cohere px-3 py-1.5 text-caption w-auto"
        >
          {cols.slice(1).map((c) => (
            <option key={c.key} value={c.key}>Sort: {c.label}</option>
          ))}
        </select>
        <button type="submit" className="btn-sm">Apply</button>
        {(q || sort !== "total_events") && (
          <Link href="/admin/engagement?view=applicants" className="btn-ghost">Reset</Link>
        )}
      </form>

      {!data ? <ErrorBox /> : data.rows.length === 0 ? (
        <EmptyBox>
          No applicants found. <Link href="/admin/applicants" className="underline hover:text-cohere-ink">View all applicants</Link>.
        </EmptyBox>
      ) : (
        <>
          <p className="text-caption font-medium text-studio-dark-cork/70">
            {data.total.toLocaleString()} applicant{data.total !== 1 ? "s" : ""}
          </p>
          <div className="border border-studio-dark-cork/15 rounded-2xl bg-white overflow-x-auto shadow-subtle">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-studio-dark-cork/10">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      className={`px-4 py-2.5 text-micro font-medium text-studio-dark-cork/70 ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=applicants&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`hover:text-studio-maroon transition-colors ${sort === c.key ? "text-studio-maroon" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-studio-dark-cork/10">
                {data.rows.map((r) => (
                  <tr key={r.applicant_id} className="transition-colors hover:bg-studio-cream/50">
                    <td className="px-4 py-2.5">
                      <p className="font-semibold text-studio-dark-cork">{r.name}</p>
                      <p className="text-caption text-studio-dark-cork/60">
                        {[r.program, r.state].filter(Boolean).join(", ")}
                      </p>
                    </td>
                    <NumCell val={r.interest_signals} />
                    <NumCell val={r.apply_clicks} />
                    <NumCell val={r.chat_messages} />
                    <NumCell val={r.dms_sent} />
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-studio-maroon">
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
  data: { total: number; rows: EmployerRow[] } | null;
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
      <form method="GET" action="/admin/engagement" className="flex gap-3 flex-wrap">
        <input type="hidden" name="view" value="employers" />
        <input
          name="q"
          defaultValue={q}
          placeholder="Search employer name…"
          className="input-cohere px-3 py-1.5 text-caption w-56"
        />
        <select
          name="sort"
          defaultValue={sort}
          className="input-cohere px-3 py-1.5 text-caption w-auto"
        >
          {cols.slice(1).map((c) => (
            <option key={c.key} value={c.key}>Sort: {c.label}</option>
          ))}
        </select>
        <button type="submit" className="btn-sm">Apply</button>
        {(q || sort !== "total_actions") && (
          <Link href="/admin/engagement?view=employers" className="btn-ghost">Reset</Link>
        )}
      </form>

      {!data ? <ErrorBox /> : data.rows.length === 0 ? (
        <EmptyBox>
          No employers found. <Link href="/admin/employers" className="underline hover:text-cohere-ink">View all employers</Link>.
        </EmptyBox>
      ) : (
        <>
          <p className="text-caption font-medium text-studio-dark-cork/70">
            {data.total.toLocaleString()} employer{data.total !== 1 ? "s" : ""}
          </p>
          <div className="border border-studio-dark-cork/15 rounded-2xl bg-white overflow-x-auto shadow-subtle">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-studio-dark-cork/10">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      className={`px-4 py-2.5 text-micro font-medium text-studio-dark-cork/70 ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=employers&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`hover:text-studio-maroon transition-colors ${sort === c.key ? "text-studio-maroon" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-studio-dark-cork/10">
                {data.rows.map((r) => (
                  <tr key={r.employer_id} className="transition-colors hover:bg-studio-cream/50">
                    <td className="px-4 py-2.5 font-medium text-studio-dark-cork">{r.name}</td>
                    <NumCell val={r.outreach_sent} />
                    <NumCell val={r.dms_sent} />
                    <NumCell val={r.hires_reported} />
                    <NumCell val={r.candidates_viewed} />
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-studio-maroon">
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
      val > 0 ? "text-studio-dark-cork font-semibold" : "text-studio-dark-cork/30"
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
        <Link href={`${base}&page=${page - 1}`} className="text-studio-dark-cork hover:text-studio-maroon transition-colors">
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
        <Link href={`${base}&page=${page + 1}`} className="text-studio-dark-cork hover:text-studio-maroon transition-colors">
          Next →
        </Link>
      )}
    </div>
  );
}

function ErrorBox() {
  return (
    <div className="bg-cohere-coral/10 border border-cohere-coral-soft rounded-2xl p-5 text-caption text-cohere-ink">
      Could not load data. Please refresh.
    </div>
  );
}

function EmptyBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="border border-studio-dark-cork/15 rounded-2xl bg-white p-10 text-center text-caption text-studio-dark-cork/60">
      {children}
    </div>
  );
}

