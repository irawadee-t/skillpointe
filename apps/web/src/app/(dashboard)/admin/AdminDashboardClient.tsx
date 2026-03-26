"use client";

import { useState } from "react";
import {
  Users,
  Briefcase,
  Building2,
  Target,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  MapPin,
  BarChart3,
  Database,
  Activity,
} from "lucide-react";
import type { AdminDashboard } from "@/lib/api/admin";

interface Props {
  data: AdminDashboard | null;
  error: string | null;
}

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-zinc-800">
          <Icon className="w-5 h-5 text-zinc-400" />
        </div>
        <div>
          <div className="text-2xl font-bold text-cyan-400">{value}</div>
          <div className="text-xs text-zinc-500 font-medium uppercase tracking-wide mt-0.5">{label}</div>
        </div>
      </div>
    </div>
  );
}

function BarChart({
  data,
  labelKey,
  valueKey,
  maxBars = 12,
}: {
  data: Record<string, unknown>[];
  labelKey: string;
  valueKey: string;
  maxBars?: number;
  colorFn?: (label: string) => string;
}) {
  const items = data.slice(0, maxBars);
  const max = Math.max(...items.map((d) => Number(d[valueKey]) || 0), 1);

  return (
    <div className="space-y-2">
      {items.map((d, i) => {
        const label = String(d[labelKey] || "Unknown");
        const val = Number(d[valueKey]) || 0;
        const pct = (val / max) * 100;
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-28 text-xs text-zinc-400 truncate text-right font-medium">{label}</div>
            <div className="flex-1 h-6 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cyan-500 to-blue-600 rounded-full transition-all duration-700"
                style={{ width: `${Math.max(pct, 2)}%` }}
              />
            </div>
            <div className="w-10 text-xs text-zinc-500 font-medium">{val}</div>
          </div>
        );
      })}
    </div>
  );
}

export function AdminDashboardClient({ data, error }: Props) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  if (error || !data) {
    return (
      <main className="p-8">
        <div className="max-w-6xl mx-auto">
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-6 text-rose-400">
            {error || "Failed to load dashboard data."}
          </div>
        </div>
      </main>
    );
  }

  const { overview: ov } = data;
  const actionable = ov.eligible_matches + ov.near_fit_matches;
  const matchRate = ov.total_matches > 0
    ? ((actionable / ov.total_matches) * 100).toFixed(1)
    : "0";
  const eligPct = ov.total_matches > 0
    ? ((ov.eligible_matches / ov.total_matches) * 100).toFixed(1)
    : "0";
  const nearPct = ov.total_matches > 0
    ? ((ov.near_fit_matches / ov.total_matches) * 100).toFixed(1)
    : "0";
  const ineligPct = ov.total_matches > 0
    ? ((ov.ineligible_matches / ov.total_matches) * 100).toFixed(1)
    : "0";
  const avgMatchesPerApplicant = ov.total_applicants > 0
    ? (actionable / ov.total_applicants).toFixed(1)
    : "0";

  const toggle = (s: string) => setExpandedSection(expandedSection === s ? null : s);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">Admin Dashboard</h1>
            <p className="text-sm text-zinc-400 mt-1">SkillPointe Match platform overview</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Activity className="w-3.5 h-3.5" />
            Live data
          </div>
        </div>

        {/* Top-level stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard label="Applicants" value={ov.total_applicants} icon={Users} />
          <StatCard label="Active jobs" value={ov.total_active_jobs} icon={Briefcase} />
          <StatCard label="Employers" value={ov.total_employers} icon={Building2} />
          <StatCard label="Actionable matches" value={actionable} icon={Target} />
          <StatCard label="Avg matches / applicant" value={avgMatchesPerApplicant} icon={BarChart3} />
        </div>

        {/* Match quality */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Eligible</span>
            </div>
            <div className="text-3xl font-bold text-emerald-400">{eligPct}%</div>
            <div className="text-xs text-zinc-500 mt-1">{ov.eligible_matches.toLocaleString()} matches &middot; {matchRate}% match rate</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Near fit</span>
            </div>
            <div className="text-3xl font-bold text-amber-400">{nearPct}%</div>
            <div className="text-xs text-zinc-500 mt-1">{ov.near_fit_matches.toLocaleString()} close matches worth surfacing</div>
          </div>
          <div className="bg-zinc-800/50 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-1">
              <XCircle className="w-4 h-4 text-zinc-500" />
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Ineligible</span>
            </div>
            <div className="text-3xl font-bold text-zinc-500">{ineligPct}%</div>
            <div className="text-xs text-zinc-600 mt-1">{ov.ineligible_matches.toLocaleString()} pairs filtered out</div>
          </div>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Jobs by trade family */}
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <button onClick={() => toggle("family")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-zinc-400" />
                <h2 className="font-semibold text-white">Jobs by Trade Family</h2>
              </div>
              {expandedSection === "family" ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
            </button>
            <div className={`mt-4 ${expandedSection === "family" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_family as unknown as Record<string, unknown>[]}
                labelKey="family_code"
                valueKey="count"
              />
            </div>
          </section>

          {/* Jobs by source */}
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <button onClick={() => toggle("source")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-zinc-400" />
                <h2 className="font-semibold text-white">Jobs by Source</h2>
              </div>
              {expandedSection === "source" ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
            </button>
            <div className={`mt-4 ${expandedSection === "source" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_source as unknown as Record<string, unknown>[]}
                labelKey="source_site"
                valueKey="count"
              />
            </div>
          </section>
        </div>

        {/* Job distribution map placeholder + stats */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="w-4 h-4 text-zinc-400" />
            <h2 className="font-semibold text-white">Job Distribution by State</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {data.jobs_by_state.slice(0, 16).map((s) => (
              <div key={s.state} className="bg-zinc-800 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-cyan-400">{s.count}</div>
                <div className="text-xs text-zinc-500 font-medium">{s.state}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-zinc-600 mt-3">
            Interactive map available in the Map tab
          </p>
        </section>

        {/* Experience levels */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-zinc-400" />
            <h2 className="font-semibold text-white">Experience Levels</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            {data.experience_levels.map((e) => (
              <div key={e.level} className="border border-zinc-700 rounded-lg px-4 py-2 bg-zinc-800">
                <div className="text-xl font-bold text-cyan-400">{e.count}</div>
                <div className="text-xs font-medium text-zinc-500 capitalize">{e.level.replace("_", " ")}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Data quality */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <h2 className="font-semibold text-white">Data Quality</h2>
          </div>
          <div className="space-y-3">
            {data.data_quality.map((dq) => (
              <div key={dq.metric} className="flex items-center gap-4">
                <div className="w-48 text-sm text-zinc-300">{dq.metric}</div>
                <div className="flex-1 h-3 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${dq.pct > 20 ? "bg-rose-500" : dq.pct > 5 ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${Math.max(dq.pct, 1)}%` }}
                  />
                </div>
                <div className="w-20 text-right text-sm text-zinc-500">
                  {dq.value}/{dq.total} ({dq.pct}%)
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
