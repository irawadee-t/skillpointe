/**
 * Employer Analytics Page
 *
 * Shows engagement and outcome metrics:
 *   - Outreach sent count
 *   - Candidates who marked interest / applied
 *   - Hire outcomes reported
 *   - Recent outreach history
 *
 * Server component.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { Mail, ThumbsUp, CheckCircle2, Users, Clock, DollarSign, Gauge, Sparkles } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, Card, MetricCard, MonoLabel, Reveal, Stagger, StaggerItem } from "@/components/ui";
import { AnalyticsChat } from "@/components/employer/AnalyticsChat";
import { InsightFreshness } from "@/components/employer/InsightFreshness";

async function fetchAnalytics(token: string) {
  const API_URL =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${API_URL}/employer/me/analytics`, {
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

async function fetchInsights(token: string): Promise<EmployerInsights | null> {
  const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${API_URL}/employer/me/analytics/insights`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as EmployerInsights;
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

  const insights = await fetchInsights(session.access_token);
  let data;
  try {
    data = await fetchAnalytics(session.access_token);
  } catch {
    return (
      <main className="py-8">
        <div className="page-shell">
          <BackLink />
          <div className="mt-6 rounded-md border border-error-red/30 bg-rose-50 p-5 text-body text-error-red">
            <strong className="font-medium">Could not reach the API.</strong> The backend may be starting up — please refresh.
          </div>
        </div>
      </main>
    );
  }

  const stats = [
    {
      label: "Outreach sent",
      value: data.outreach_sent,
      icon: Mail,
    },
    {
      label: "Candidates interested",
      value: data.candidates_interested,
      icon: ThumbsUp,
    },
    {
      label: "Candidates applied",
      value: data.candidates_applied,
      icon: Users,
    },
    {
      label: "Hired",
      value: data.hired_count,
      icon: CheckCircle2,
    },
  ];

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
              lead="Engagement and placement outcomes for your candidates"
            />
          </div>
        </div>

        {/* Stats grid — warm stone product-card style, no color fills */}
        <Stagger className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {stats.map(({ label, value, icon: Icon }) => (
            <StaggerItem key={label}>
              <MetricCard label={label} value={value} icon={Icon} tone="stone" />
            </StaggerItem>
          ))}
        </Stagger>

        {/* Hiring intelligence */}
        {insights && insights.hires > 0 && (
          <section className="space-y-4">
            <MonoLabel className="block">Hiring intelligence</MonoLabel>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MetricCard
                label="Median time to fill"
                value={insights.time_to_fill_days != null ? `${insights.time_to_fill_days}d` : "—"}
                icon={Clock}
                tone="white"
              />
              <MetricCard
                label="Median wage"
                value={insights.median_wage != null ? `$${insights.median_wage.toLocaleString()}` : "—"}
                icon={DollarSign}
                tone="white"
              />
              <MetricCard
                label="vs platform median"
                value={
                  insights.wage_vs_platform_pct != null
                    ? `${insights.wage_vs_platform_pct >= 0 ? "+" : ""}${insights.wage_vs_platform_pct}%`
                    : "—"
                }
                icon={Gauge}
                tone="white"
              />
              <MetricCard
                label="Avg candidate fit"
                value={insights.avg_match_fit != null ? `${Math.round(insights.avg_match_fit * 100)}%` : "—"}
                icon={ThumbsUp}
                tone="white"
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
                Wage benchmark is platform-internal — narrative{" "}
                {insights.narrative_source === "ai" ? "written by AI" : "auto-drafted (no AI key configured)"}.
              </p>
            </div>
          </section>
        )}

        {/* Recent outreach */}
        <section>
          <MonoLabel className="mb-5 block">Recent outreach</MonoLabel>
          {data.recent_outreach.length === 0 ? (
            <Card tone="stone" className="p-10 text-center">
              <p className="text-body-lg font-semibold text-cohere-ink">No outreach sent yet.</p>
              <p className="text-body text-slate mt-1">
                Use the &quot;Reach out&quot; button on matched candidate cards.
              </p>
            </Card>
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
                          {new Date(o.sent_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </Card>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </section>

        <AnalyticsChat token={session.access_token} />
      </div>
    </main>
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
