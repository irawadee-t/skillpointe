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
} from "lucide-react";
import type { AdminDashboard } from "@/lib/api/admin";
import { PageHeader, MonoLabel, Reveal, Stagger, StaggerItem } from "@/components/ui";

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
    <div className="rounded-md bg-cohere-green p-5 text-white transition-transform duration-300 ease-cohere hover:-translate-y-1">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-sm bg-white/10">
          <Icon className="w-5 h-5 text-white/80" />
        </div>
        <div>
          <div className="font-display text-feature text-white tabular-nums leading-none">{value}</div>
          <MonoLabel className="mt-1.5 block text-white/55">{label}</MonoLabel>
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
            <div className="w-28 text-caption text-slate truncate text-right font-medium">{label}</div>
            <div className="flex-1 h-2 bg-stone rounded-sm overflow-hidden">
              <div
                className="h-full bg-studio-dark-cork rounded-sm transition-all duration-700"
                style={{ width: `${Math.max(pct, 2)}%` }}
              />
            </div>
            <div className="w-10 text-caption text-slate-muted font-medium tabular-nums">{val}</div>
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
        <div className="max-w-5xl mx-auto">
          <div className="bg-studio-maroon/10 border border-studio-maroon-soft rounded-md p-6 text-cohere-ink">
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
    <main className="py-8">
      <div className="page-shell space-y-6">
        {/* Header */}
        <PageHeader
          eyebrow="Platform overview"
          title="Admin Dashboard"
          lead="SKILLED Match platform analytics at a glance."
        />

        {/* Top-level stats */}
        <Stagger className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: "Applicants", value: ov.total_applicants, icon: Users },
            { label: "Active jobs", value: ov.total_active_jobs, icon: Briefcase },
            { label: "Employers", value: ov.total_employers, icon: Building2 },
            { label: "Actionable matches", value: actionable, icon: Target },
            { label: "Avg matches / applicant", value: avgMatchesPerApplicant, icon: BarChart3 },
          ].map((s) => (
            <StaggerItem key={s.label}>
              <StatCard label={s.label} value={s.value} icon={s.icon} />
            </StaggerItem>
          ))}
        </Stagger>

        {/* Match quality */}
        <Stagger className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StaggerItem className="border border-border-light rounded-md bg-white p-5">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="w-4 h-4 text-cohere-green" />
              <MonoLabel>Eligible</MonoLabel>
            </div>
            <div className="font-display text-card text-cohere-green tabular-nums leading-none">{eligPct}%</div>
            <div className="text-caption text-slate mt-2">{ov.eligible_matches.toLocaleString()} matches &middot; {matchRate}% match rate</div>
          </StaggerItem>
          <StaggerItem className="border border-border-light rounded-md bg-white p-5">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-studio-maroon" />
              <MonoLabel>Near fit</MonoLabel>
            </div>
            <div className="font-display text-card text-studio-maroon tabular-nums leading-none">{nearPct}%</div>
            <div className="text-caption text-slate mt-2">{ov.near_fit_matches.toLocaleString()} close matches worth surfacing</div>
          </StaggerItem>
          <StaggerItem className="border border-border-light rounded-md bg-stone p-5">
            <div className="flex items-center gap-2 mb-2">
              <XCircle className="w-4 h-4 text-slate-muted" />
              <MonoLabel>Ineligible</MonoLabel>
            </div>
            <div className="font-display text-card text-slate-muted tabular-nums leading-none">{ineligPct}%</div>
            <div className="text-caption text-slate mt-2">{ov.ineligible_matches.toLocaleString()} pairs filtered out</div>
          </StaggerItem>
        </Stagger>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Jobs by trade family */}
          <Reveal as="section" className="border border-border-light rounded-md bg-white p-5">
            <button onClick={() => toggle("family")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-slate" />
                <h2 className="text-feature font-display text-cohere-ink">Jobs by Trade Family</h2>
              </div>
              {expandedSection === "family" ? <ChevronUp className="w-4 h-4 text-slate-muted" /> : <ChevronDown className="w-4 h-4 text-slate-muted" />}
            </button>
            <div className={`mt-4 ${expandedSection === "family" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_family as unknown as Record<string, unknown>[]}
                labelKey="family_code"
                valueKey="count"
              />
            </div>
          </Reveal>

          {/* Jobs by source */}
          <Reveal as="section" delay={0.05} className="border border-border-light rounded-md bg-white p-5">
            <button onClick={() => toggle("source")} className="flex items-center justify-between w-full text-left">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-slate" />
                <h2 className="text-feature font-display text-cohere-ink">Jobs by Source</h2>
              </div>
              {expandedSection === "source" ? <ChevronUp className="w-4 h-4 text-slate-muted" /> : <ChevronDown className="w-4 h-4 text-slate-muted" />}
            </button>
            <div className={`mt-4 ${expandedSection === "source" ? "" : "max-h-64 overflow-hidden"}`}>
              <BarChart
                data={data.jobs_by_source as unknown as Record<string, unknown>[]}
                labelKey="source_site"
                valueKey="count"
              />
            </div>
          </Reveal>
        </div>

        {/* Job distribution map placeholder + stats */}
        <Reveal as="section" className="border border-border-light rounded-md bg-white p-5">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="w-4 h-4 text-slate" />
            <h2 className="text-feature font-display text-cohere-ink">Job Distribution by State</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {data.jobs_by_state.slice(0, 16).map((s) => (
              <div key={s.state} className="bg-stone rounded-sm p-2 text-center">
                <div className="text-body-lg font-display text-cohere-ink tabular-nums">{s.count}</div>
                <MonoLabel className="block">{s.state}</MonoLabel>
              </div>
            ))}
          </div>
          <p className="text-caption text-slate-muted mt-3">
            Interactive map available in the Map tab
          </p>
        </Reveal>

        {/* Experience levels */}
        <Reveal as="section" className="border border-border-light rounded-md bg-white p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-slate" />
            <h2 className="text-feature font-display text-cohere-ink">Experience Levels</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            {data.experience_levels.map((e) => (
              <div key={e.level} className="border border-border-light rounded-sm px-4 py-2 bg-stone">
                <div className="text-body-lg font-display text-cohere-ink tabular-nums">{e.count}</div>
                <div className="text-caption font-medium text-slate capitalize">{e.level.replace("_", " ")}</div>
              </div>
            ))}
          </div>
        </Reveal>

        {/* Data quality */}
        <Reveal as="section" className="border border-border-light rounded-md bg-white p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-studio-maroon" />
            <h2 className="text-feature font-display text-cohere-ink">Data Quality</h2>
          </div>
          <div className="space-y-3">
            {data.data_quality.map((dq) => (
              <div key={dq.metric} className="flex items-center gap-4">
                <div className="w-48 text-caption text-slate">{dq.metric}</div>
                <div className="flex-1 h-2 bg-stone rounded-sm overflow-hidden">
                  <div
                    className={`h-full rounded-sm transition-all duration-700 ${dq.pct > 20 ? "bg-cohere-coral" : dq.pct > 5 ? "bg-amber-500" : "bg-cohere-green"}`}
                    style={{ width: `${Math.max(dq.pct, 1)}%` }}
                  />
                </div>
                <div className="w-20 text-right text-caption text-slate-muted tabular-nums">
                  {dq.value}/{dq.total} ({dq.pct}%)
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </main>
  );
}
