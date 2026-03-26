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
import { Mail, ThumbsUp, CheckCircle2, Users } from "lucide-react";

import { createClient } from "@/lib/supabase/server";

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

export default async function EmployerAnalyticsPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer") redirect("/login");

  let data;
  try {
    data = await fetchAnalytics(session.access_token);
  } catch {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
            <strong>Could not reach the API.</strong> The backend may be starting up — please refresh.
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
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <BackLink />
          <h1 className="text-2xl font-semibold tracking-tight text-white mt-1">Analytics</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Engagement and placement outcomes for your candidates
          </p>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {stats.map(({ label, value, icon: Icon }) => (
            <div
              key={label}
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 text-center"
            >
              <Icon className="w-6 h-6 mx-auto mb-2 text-zinc-500" />
              <div className="text-3xl font-bold leading-none text-cyan-400">{value}</div>
              <div className="text-xs text-zinc-500 mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* Recent outreach */}
        <section>
          <h2 className="font-semibold text-white mb-3">Recent outreach</h2>
          {data.recent_outreach.length === 0 ? (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
              <p className="text-zinc-500 text-sm">No outreach sent yet.</p>
              <p className="text-xs text-zinc-600 mt-1">
                Use the &quot;Reach out&quot; button on matched candidate cards.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {data.recent_outreach.map((o) => (
                <div
                  key={o.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-lg p-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-medium text-white truncate">
                        {o.applicant_name}
                      </p>
                      <p className="text-sm text-zinc-400">{o.job_title}</p>
                      {o.subject && (
                        <p className="text-xs text-zinc-500 mt-0.5 truncate">
                          {o.subject}
                        </p>
                      )}
                    </div>
                    {o.sent_at && (
                      <span className="shrink-0 text-xs text-zinc-500">
                        {new Date(o.sent_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link
      href="/employer"
      className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
    >
      ← Back to dashboard
    </Link>
  );
}
