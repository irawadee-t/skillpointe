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
  color = "text-spf-navy",
  bgColor = "bg-white",
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color?: string;
  bgColor?: string;
}) {
  return (
    <div className={`${bgColor} border border-gray-200 rounded-xl p-5`}>
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-gray-50">
          <Icon className={`w-5 h-5 ${color}`} />
        </div>
        <div>
          <div className={`text-2xl font-bold ${color}`}>{value}</div>
          <div className="text-xs text-gray-500 font-medium uppercase tracking-wide mt-0.5">{label}</div>
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
  colorFn,
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
        const color = colorFn ? colorFn(label) : "bg-spf-navy";
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-28 text-xs text-gray-600 truncate text-right font-medium">{label}</div>
            <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full ${color} rounded-full transition-all`}
                style={{ width: `${Math.max(pct, 2)}%` }}
              />
            </div>
            <div className="w-10 text-xs text-gray-500 font-medium">{val}</div>
          </div>
        );
      })}
    </div>
  );
}

const FAMILY_COLORS: Record<string, string> = {
  electrical: "bg-amber-500",
  welding: "bg-red-500",
  hvac: "bg-blue-500",
  manufacturing: "bg-emerald-500",
  automotive: "bg-purple-500",
  construction: "bg-orange-500",
  logistics: "bg-cyan-500",
  aviation: "bg-indigo-500",
};

function familyColor(code: string): string {
  return FAMILY_COLORS[code] || "bg-gray-400";
}

function sourceColor(src: string): string {
  const map: Record<string, string> = {
    ball: "bg-red-500",
    delta: "bg-blue-600",
    ford: "bg-blue-400",
    ge_vernova: "bg-green-600",
    schneider_electric: "bg-emerald-500",
    southwire: "bg-orange-500",
    seed: "bg-gray-400",
    manual: "bg-gray-300",
  };
  return map[src] || "bg-gray-400";
}

export function AdminDashboardClient({ data, error }: Props) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  if (error || !data) {
    return (
      <main className="p-8">
        <div className="max-w-6xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-800">
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
    <main className="p-6 md:p-8 bg-gray-50 min-h-screen">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-spf-navy">Admin Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">SkillPointe Match platform overview</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Activity className="w-3.5 h-3.5" />
            Live data
          </div>
        </div>

        {/* Top-level stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard label="Applicants" value={ov.total_applicants} icon={Users} />
          <StatCard label="Active jobs" value={ov.total_active_jobs} icon={Briefcase} color="text-green-700" />
          <StatCard label="Employers" value={ov.total_employers} icon={Building2} color="text-blue-600" />
          <StatCard label="Actionable matches" value={actionable} icon={Target} color="text-purple-600" />
          <StatCard label="Avg matches / applicant" value={avgMatchesPerApplicant} icon={BarChart3} color="text-indigo-600" />
        </div>

        {/* Match quality */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-green-50 border border-green-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle2 className="w-4 h-4 text-green-600" />
              <span className="text-xs font-medium text-green-700 uppercase tracking-wide">Eligible</span>
            </div>
            <div className="text-3xl font-bold text-green-700">{eligPct}%</div>
            <div className="text-xs text-green-600 mt-1">{ov.eligible_matches.toLocaleString()} matches &middot; {matchRate}% match rate</div>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span className="text-xs font-medium text-amber-700 uppercase tracking-wide">Near fit</span>
            </div>
            <div className="text-3xl font-bold text-amber-700">{nearPct}%</div>
            <div className="text-xs text-amber-600 mt-1">{ov.near_fit_matches.toLocaleString()} close matches worth surfacing</div>
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <XCircle className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Ineligible</span>
            </div>
            <div className="text-3xl font-bold text-gray-500">{ineligPct}%</div>
            <div className="text-xs text-gray-400 mt-1">{ov.ineligible_matches.toLocaleString()} pairs filtered out</div>
          </div>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Jobs by trade family */}
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <button onClick={() => toggle("family")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-spf-navy" />
                <h2 className="font-semibold text-gray-900">Jobs by Trade Family</h2>
              </div>
              {expandedSection === "family" ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </button>
            <div className={`mt-4 ${expandedSection === "family" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_family as unknown as Record<string, unknown>[]}
                labelKey="family_code"
                valueKey="count"
                colorFn={familyColor}
              />
            </div>
          </section>

          {/* Jobs by source */}
          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <button onClick={() => toggle("source")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-spf-navy" />
                <h2 className="font-semibold text-gray-900">Jobs by Source</h2>
              </div>
              {expandedSection === "source" ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </button>
            <div className={`mt-4 ${expandedSection === "source" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_source as unknown as Record<string, unknown>[]}
                labelKey="source_site"
                valueKey="count"
                colorFn={sourceColor}
              />
            </div>
          </section>
        </div>

        {/* Job distribution map placeholder + stats */}
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="w-4 h-4 text-spf-navy" />
            <h2 className="font-semibold text-gray-900">Job Distribution by State</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {data.jobs_by_state.slice(0, 16).map((s) => (
              <div key={s.state} className="bg-gray-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-spf-navy">{s.count}</div>
                <div className="text-xs text-gray-500 font-medium">{s.state}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Interactive map available in the Map tab
          </p>
        </section>

        {/* Experience levels */}
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-spf-navy" />
            <h2 className="font-semibold text-gray-900">Experience Levels</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            {data.experience_levels.map((e) => {
              const colors: Record<string, string> = {
                entry: "bg-green-100 text-green-700 border-green-200",
                mid: "bg-blue-100 text-blue-700 border-blue-200",
                senior: "bg-purple-100 text-purple-700 border-purple-200",
                unspecified: "bg-gray-100 text-gray-500 border-gray-200",
              };
              return (
                <div key={e.level} className={`border rounded-lg px-4 py-2 ${colors[e.level] || colors.unspecified}`}>
                  <div className="text-xl font-bold">{e.count}</div>
                  <div className="text-xs font-medium capitalize">{e.level.replace("_", " ")}</div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Data quality */}
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <h2 className="font-semibold text-gray-900">Data Quality</h2>
          </div>
          <div className="space-y-3">
            {data.data_quality.map((dq) => (
              <div key={dq.metric} className="flex items-center gap-4">
                <div className="w-48 text-sm text-gray-700">{dq.metric}</div>
                <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${dq.pct > 20 ? "bg-red-400" : dq.pct > 5 ? "bg-amber-400" : "bg-green-400"}`}
                    style={{ width: `${Math.max(dq.pct, 1)}%` }}
                  />
                </div>
                <div className="w-20 text-right text-sm text-gray-500">
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
