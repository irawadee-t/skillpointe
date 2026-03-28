/**
 * Admin Engagement Analytics — three tab views:
 *   general    Platform-wide metrics + event breakdown + recent feed
 *   applicants Per-applicant engagement table (interest, clicks, chat, DMs)
 *   employers  Per-employer engagement table (outreach, DMs, hires, views)
 *
 * Tabs are URL-driven (?view=general|applicants|employers) so each view
 * is bookmarkable and fully server-rendered.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  MessageSquare,
  Mail,
  ThumbsUp,
  CheckCircle2,
  MousePointerClick,
  Activity,
} from "lucide-react";

import { createClient } from "@/lib/supabase/server";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EngagementEventCount {
  event_type: string;
  count: number;
}

interface EngagementActivity {
  event_type: string;
  actor_name: string;
  detail: string | null;
  created_at: string;
}

interface GeneralData {
  total_events: number;
  total_dms_sent: number;
  total_outreach_sent: number;
  total_interest_signals: number;
  total_apply_clicks: number;
  total_hires_reported: number;
  total_active_conversations: number;
  events_by_type: EngagementEventCount[];
  recent_activity: EngagementActivity[];
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

async function fetchGeneral(token: string): Promise<GeneralData | null> {
  try {
    const res = await fetch(`${API_URL()}/admin/analytics/engagement`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

async function fetchApplicants(
  token: string,
  q: string,
  sort: string,
  page: number
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
  token: string,
  q: string,
  sort: string,
  page: number
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
// Constants
// ---------------------------------------------------------------------------

const EVENT_LABELS: Record<string, string> = {
  interest_set: "Interest signal",
  apply_click: "Apply click",
  match_view: "Match viewed",
  chat_started: "Chat started",
  chat_message_sent: "Chat message",
  outreach_sent: "Outreach email",
  candidate_viewed: "Candidate viewed",
  hire_reported: "Hire reported",
  dm_sent: "DM sent",
};

type View = "general" | "applicants" | "employers";

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
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const view: View =
    sp.view === "applicants" || sp.view === "employers" ? sp.view : "general";
  const q = sp.q ?? "";
  const page = Math.max(1, Number(sp.page) || 1);

  // Default sort per view
  const defaultSort: Record<View, string> = {
    general: "",
    applicants: "total_events",
    employers: "total_actions",
  };
  const sort = sp.sort ?? defaultSort[view];

  const token = session.access_token;

  // Fetch data for the active view
  const [general, applicantsData, employersData] = await Promise.all([
    fetchGeneral(token),
    view === "applicants" ? fetchApplicants(token, q, sort, page) : null,
    view === "employers" ? fetchEmployers(token, q, sort, page) : null,
  ]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <Link
            href="/admin"
            className="text-sm text-zinc-500 hover:text-zinc-900 inline-flex items-center gap-1 transition-colors"
          >
            ← Back to dashboard
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 mt-1">
            Platform Engagement
          </h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Applicant and employer activity across the platform
          </p>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-zinc-200 gap-1">
          {(
            [
              { key: "general", label: "Overview" },
              { key: "applicants", label: "Applicant view" },
              { key: "employers", label: "Employer view" },
            ] as { key: View; label: string }[]
          ).map(({ key, label }) => (
            <Link
              key={key}
              href={`/admin/engagement?view=${key}`}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                view === key
                  ? "border-zinc-200 text-zinc-900"
                  : "border-transparent text-zinc-400 hover:text-zinc-600"
              }`}
            >
              {label}
            </Link>
          ))}
        </div>

        {/* ── Overview tab ── */}
        {view === "general" && (
          <GeneralView data={general} />
        )}

        {/* ── Applicants tab ── */}
        {view === "applicants" && (
          <ApplicantsView
            data={applicantsData}
            q={q}
            sort={sort}
            page={page}
          />
        )}

        {/* ── Employers tab ── */}
        {view === "employers" && (
          <EmployersView
            data={employersData}
            q={q}
            sort={sort}
            page={page}
          />
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Overview view
// ---------------------------------------------------------------------------

function GeneralView({ data }: { data: GeneralData | null }) {
  if (!data) {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-lg p-5 text-sm text-rose-600">
        <strong>Could not load engagement data.</strong> Please refresh.
      </div>
    );
  }

  const topStats = [
    { label: "DMs sent", value: data.total_dms_sent, icon: MessageSquare },
    { label: "Outreach emails", value: data.total_outreach_sent, icon: Mail },
    { label: "Interest signals", value: data.total_interest_signals, icon: ThumbsUp },
    { label: "Apply clicks", value: data.total_apply_clicks, icon: MousePointerClick },
    { label: "Hires reported", value: data.total_hires_reported, icon: CheckCircle2 },
    { label: "Active convos (30d)", value: data.total_active_conversations, icon: Activity },
  ];

  return (
    <div className="space-y-6">
      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {topStats.map(({ label, value, icon: Icon }) => (
          <div key={label} className="bg-zinc-50 border border-zinc-200 rounded-lg p-4 text-center">
            <Icon className="w-6 h-6 mx-auto mb-2 text-zinc-400" />
            <div className="text-3xl font-bold leading-none text-spf-navy">
              {value.toLocaleString()}
            </div>
            <div className="text-xs text-zinc-400 mt-1">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Events by type */}
        <section>
          <h2 className="font-semibold text-zinc-900 mb-3">Events by type</h2>
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg overflow-hidden">
            {data.events_by_type.length === 0 ? (
              <p className="text-sm text-zinc-400 p-5">No events recorded yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 bg-zinc-100">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400">Event</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {data.events_by_type.map((e) => (
                    <tr key={e.event_type} className="border-b border-zinc-200/50 last:border-0">
                      <td className="px-4 py-2.5 text-zinc-600">
                        {EVENT_LABELS[e.event_type] ?? e.event_type}
                      </td>
                      <td className="px-4 py-2.5 text-right font-medium tabular-nums text-spf-navy">
                        {e.count.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* Recent activity */}
        <section>
          <h2 className="font-semibold text-zinc-900 mb-3">Recent activity</h2>
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg overflow-hidden">
            {data.recent_activity.length === 0 ? (
              <p className="text-sm text-zinc-400 p-5">No recent activity.</p>
            ) : (
              <div className="overflow-y-auto max-h-[320px] divide-y divide-zinc-200/50">
                {data.recent_activity.map((a, i) => (
                  <div key={i} className="px-4 py-2.5 flex items-start justify-between gap-3">
                    <p className="text-sm text-zinc-700 truncate">
                      <span className="font-medium">{a.actor_name}</span>
                      {" · "}
                      <span className="text-zinc-400">
                        {EVENT_LABELS[a.event_type] ?? a.event_type}
                      </span>
                    </p>
                    <span className="shrink-0 text-xs text-zinc-400">
                      {new Date(a.created_at).toLocaleDateString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Applicants view
// ---------------------------------------------------------------------------

function ApplicantsView({
  data,
  q,
  sort,
  page,
}: {
  data: { total: number; rows: ApplicantRow[] } | null;
  q: string;
  sort: string;
  page: number;
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
      {/* Search + sort bar */}
      <form method="GET" action="/admin/engagement" className="flex gap-3 flex-wrap">
        <input type="hidden" name="view" value="applicants" />
        <input
          name="q"
          defaultValue={q}
          placeholder="Search applicant name…"
          className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy w-56"
        />
        <select
          name="sort"
          defaultValue={sort}
          className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-spf-navy/20"
        >
          {cols.slice(1).map((c) => (
            <option key={c.key} value={c.key}>
              Sort: {c.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="px-4 py-1.5 bg-zinc-900 text-white text-sm rounded-full hover:bg-zinc-700 transition-colors"
        >
          Apply
        </button>
        {(q || sort !== "total_events") && (
          <Link
            href="/admin/engagement?view=applicants"
            className="px-4 py-1.5 border border-zinc-200 text-sm rounded-full text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 transition-colors"
          >
            Reset
          </Link>
        )}
      </form>

      {!data ? (
        <ErrorBox />
      ) : data.rows.length === 0 ? (
        <EmptyBox text="No applicants found." />
      ) : (
        <>
          <p className="text-xs text-zinc-400">
            {data.total.toLocaleString()} applicant{data.total !== 1 ? "s" : ""}
          </p>
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-100">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      className={`px-4 py-2.5 text-xs font-medium text-zinc-400 ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=applicants&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`hover:text-zinc-900 transition-colors ${sort === c.key ? "text-zinc-900 font-semibold" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : (
                        c.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr
                    key={r.applicant_id}
                    className="border-b border-zinc-200/50 last:border-0 hover:bg-zinc-100"
                  >
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-zinc-900">{r.name}</p>
                      <p className="text-xs text-zinc-400">
                        {[r.program, r.state].filter(Boolean).join(" · ")}
                      </p>
                    </td>
                    <NumCell val={r.interest_signals} highlight={r.interest_signals > 0} />
                    <NumCell val={r.apply_clicks} highlight={r.apply_clicks > 0} />
                    <NumCell val={r.chat_messages} highlight={r.chat_messages > 0} />
                    <NumCell val={r.dms_sent} highlight={r.dms_sent > 0} />
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-spf-navy">
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
// Employers view
// ---------------------------------------------------------------------------

function EmployersView({
  data,
  q,
  sort,
  page,
}: {
  data: { total: number; rows: EmployerRow[] } | null;
  q: string;
  sort: string;
  page: number;
}) {
  const cols: { key: string; label: string }[] = [
    { key: "name", label: "Employer" },
    { key: "outreach_sent", label: "Outreach emails" },
    { key: "dms_sent", label: "DMs sent" },
    { key: "hires_reported", label: "Hires reported" },
    { key: "candidates_viewed", label: "Candidates viewed" },
    { key: "total_actions", label: "Total actions" },
  ];

  return (
    <div className="space-y-4">
      {/* Search + sort bar */}
      <form method="GET" action="/admin/engagement" className="flex gap-3 flex-wrap">
        <input type="hidden" name="view" value="employers" />
        <input
          name="q"
          defaultValue={q}
          placeholder="Search employer name…"
          className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy w-56"
        />
        <select
          name="sort"
          defaultValue={sort}
          className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-spf-navy/20"
        >
          {cols.slice(1).map((c) => (
            <option key={c.key} value={c.key}>
              Sort: {c.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="px-4 py-1.5 bg-zinc-900 text-white text-sm rounded-full hover:bg-zinc-700 transition-colors"
        >
          Apply
        </button>
        {(q || sort !== "total_actions") && (
          <Link
            href="/admin/engagement?view=employers"
            className="px-4 py-1.5 border border-zinc-200 text-sm rounded-full text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 transition-colors"
          >
            Reset
          </Link>
        )}
      </form>

      {!data ? (
        <ErrorBox />
      ) : data.rows.length === 0 ? (
        <EmptyBox text="No employers found." />
      ) : (
        <>
          <p className="text-xs text-zinc-400">
            {data.total.toLocaleString()} employer{data.total !== 1 ? "s" : ""}
          </p>
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-100">
                  {cols.map((c) => (
                    <th
                      key={c.key}
                      className={`px-4 py-2.5 text-xs font-medium text-zinc-400 ${
                        c.key === "name" ? "text-left" : "text-right"
                      }`}
                    >
                      {c.key !== "name" ? (
                        <Link
                          href={`/admin/engagement?view=employers&sort=${c.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                          className={`hover:text-zinc-900 transition-colors ${sort === c.key ? "text-zinc-900 font-semibold" : ""}`}
                        >
                          {c.label} {sort === c.key ? "↓" : ""}
                        </Link>
                      ) : (
                        c.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr
                    key={r.employer_id}
                    className="border-b border-zinc-200/50 last:border-0 hover:bg-zinc-100"
                  >
                    <td className="px-4 py-2.5 font-medium text-zinc-900">{r.name}</td>
                    <NumCell val={r.outreach_sent} highlight={r.outreach_sent > 0} />
                    <NumCell val={r.dms_sent} highlight={r.dms_sent > 0} />
                    <NumCell val={r.hires_reported} highlight={r.hires_reported > 0} />
                    <NumCell val={r.candidates_viewed} highlight={r.candidates_viewed > 0} />
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-spf-navy">
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

function NumCell({
  val,
  highlight,
}: {
  val: number;
  highlight: boolean;
}) {
  return (
    <td
      className={`px-4 py-2.5 text-right tabular-nums ${
        highlight ? "text-spf-navy font-medium" : "text-zinc-400"
      }`}
    >
      {val}
    </td>
  );
}

function Pagination({
  view,
  q,
  sort,
  page,
  total,
  pageSize,
}: {
  view: string;
  q: string;
  sort: string;
  page: number;
  total: number;
  pageSize: number;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  const base = `/admin/engagement?view=${view}${q ? `&q=${encodeURIComponent(q)}` : ""}&sort=${sort}`;

  return (
    <div className="flex items-center gap-3 justify-end text-sm">
      {page > 1 && (
        <Link href={`${base}&page=${page - 1}`} className="text-zinc-500 hover:text-zinc-900 transition-colors">
          ← Prev
        </Link>
      )}
      <span className="text-zinc-400">
        Page {page} of {totalPages}
      </span>
      {page < totalPages && (
        <Link href={`${base}&page=${page + 1}`} className="text-zinc-500 hover:text-zinc-900 transition-colors">
          Next →
        </Link>
      )}
    </div>
  );
}

function ErrorBox() {
  return (
    <div className="bg-rose-50 border border-rose-200 rounded-lg p-5 text-sm text-rose-600">
      Could not load data. Please refresh.
    </div>
  );
}

function EmptyBox({ text }: { text: string }) {
  return (
    <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-10 text-center text-sm text-zinc-400">
      {text}
    </div>
  );
}
