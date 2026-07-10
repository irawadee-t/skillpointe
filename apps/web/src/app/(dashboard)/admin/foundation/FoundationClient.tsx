"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Users, Briefcase, DollarSign, Award, Clock, Lock, FileText, Loader2, Sparkles,
} from "lucide-react";

import {
  Summary, Cohort, ImpactReport, GroupBy,
  getCohorts, getFeed, generateImpactReport, pct, money,
} from "@/lib/api/foundation";
import {
  PageHeader, MonoLabel, MetricCard, DataTable, Card, Breadcrumb, type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";

const DIMS: { key: GroupBy; label: string }[] = [
  { key: "program", label: "Program" },
  { key: "region", label: "Region" },
  { key: "cohort_year", label: "Cohort year" },
];

export function FoundationClient({
  summary, initialCohorts, token,
}: {
  summary: Summary;
  initialCohorts: Cohort[];
  token: string;
}) {
  const [groupBy, setGroupBy] = useState<GroupBy>("program");
  const [publishSafe, setPublishSafe] = useState(false);
  const [cohorts, setCohorts] = useState<Cohort[]>(initialCohorts);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [reporting, setReporting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const fetcher = publishSafe ? getFeed(token, groupBy, 10) : getCohorts(token, groupBy);
    fetcher.then((c) => active && setCohorts(c)).catch(() => {}).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token, groupBy, publishSafe]);

  async function onReport() {
    setReporting(true);
    try { setReport(await generateImpactReport(token)); } catch { /* noop */ } finally { setReporting(false); }
  }

  const columns: Column<Cohort>[] = [
    {
      key: "cohort",
      label: "Cohort",
      sortable: true,
      sortValue: (r) => r.cohort,
      filterValue: (r) => r.cohort,
      render: (r) => <span className="font-semibold text-cohere-ink">{r.cohort}</span>,
    },
    {
      key: "n",
      label: "Workers",
      align: "right",
      sortable: true,
      sortValue: (r) => r.n,
      render: (r) => <span className="text-slate">{r.n.toLocaleString()}</span>,
    },
    {
      key: "employment",
      label: "Employment",
      sortable: true,
      sortValue: (r) => r.suppressed ? null : (r.employment_rate ?? null),
      width: "220px",
      render: (r) => r.suppressed ? (
        <span className="flex items-center gap-1 text-micro text-slate-muted">
          <Lock className="h-3 w-3" /> suppressed (n&lt;10)
        </span>
      ) : (
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-stone">
            <div
              className="h-full rounded-full bg-cohere-green transition-[width] duration-500 ease-cohere"
              style={{ width: `${Math.round((r.employment_rate ?? 0) * 100)}%` }}
            />
          </div>
          <span className="tabular-nums text-caption text-cohere-ink">{pct(r.employment_rate)}</span>
        </div>
      ),
    },
    {
      key: "wage",
      label: "Median wage",
      align: "right",
      sortable: true,
      sortValue: (r) => r.suppressed ? null : (r.median_wage ?? null),
      render: (r) => r.suppressed ? <span className="text-slate-muted">—</span> : <span className="text-cohere-ink">{money(r.median_wage)}</span>,
    },
    {
      key: "attainment",
      label: "Attainment",
      align: "right",
      sortable: true,
      sortValue: (r) => r.suppressed ? null : (r.attainment_rate ?? null),
      render: (r) => r.suppressed ? <span className="text-slate-muted">—</span> : <span className="text-slate">{pct(r.attainment_rate)}</span>,
    },
    {
      key: "time_to_hire",
      label: "Time to hire",
      align: "right",
      sortable: true,
      sortValue: (r) => r.suppressed ? null : (r.median_time_to_hire_days ?? null),
      render: (r) => r.median_time_to_hire_days != null
        ? <span className="text-slate">{r.median_time_to_hire_days}d</span>
        : <span className="text-slate-muted">—</span>,
    },
  ];

  return (
    <main className="py-8">
      <div className="page-shell space-y-8">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Foundation" }]} />
        <PageHeader
          eyebrow="SKILLED Foundation"
          title="Impact & outcomes"
          lead="WIOA-style outcomes across all workers served — employment, earnings, credential attainment, and time to hire. Cohort breakdowns support a publish-safe view that suppresses any group smaller than 10 (k-anonymity)."
        />

        {/* Headline KPI row — rhythmic mix of tones so it doesn't read as a monotone slab. */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <MetricCard label="Workers served" value={summary.total_served.toLocaleString()} icon={Users} tone="green" />
          <MetricCard label="Employment rate" value={pct(summary.employment_rate)} icon={Briefcase} tone="stone" />
          <MetricCard label="Median wage" value={money(summary.median_wage)} icon={DollarSign} tone="white" />
          <MetricCard label="Credential attainment" value={pct(summary.attainment_rate)} icon={Award} tone="stone" />
          <MetricCard label="Median time to hire" value={`${summary.median_time_to_hire_days ?? "—"}d`} icon={Clock} tone="white" />
        </div>

        {/* Cohort table — sortable, filterable, zebra rows, muted for suppressed. */}
        <Card tone="white" className="p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <MonoLabel className="text-studio-maroon">Cohort breakdown</MonoLabel>
              <p className="mt-1 text-caption text-slate">Click a column header to sort. Filter by name.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="inline-flex rounded-md border border-hairline bg-white p-0.5">
                {DIMS.map((d) => (
                  <button
                    key={d.key}
                    onClick={() => setGroupBy(d.key)}
                    className={cn(
                      "rounded-sm px-3 py-1.5 text-caption transition-colors",
                      groupBy === d.key ? "bg-studio-dark-cork text-white" : "text-slate hover:text-cohere-ink",
                    )}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-caption text-slate">
                <input
                  type="checkbox"
                  checked={publishSafe}
                  onChange={(e) => setPublishSafe(e.target.checked)}
                  className="h-4 w-4 accent-cohere-green"
                />
                Publish-safe (k=10)
              </label>
            </div>
          </div>

          <div className={cn(loading && "opacity-50 transition-opacity")}>
            <DataTable
              columns={columns}
              rows={cohorts}
              rowKey={(r) => r.cohort}
              defaultSort={{ key: "n", dir: "desc" }}
              filterKeys={["cohort"]}
              filterPlaceholder={`Filter ${groupBy.replace("_", " ")}…`}
              isRowMuted={(r) => !!r.suppressed}
              maxRows={25}
            />
            {publishSafe && (
              <p className="mt-2 text-micro text-slate-muted">
                Cohorts with fewer than 10 learners are suppressed per k-anonymity policy.
              </p>
            )}
          </div>
        </Card>

        {/* Impact report — accent rule instead of a green-wash card. */}
        <Card tone="white" accent="green" className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <MonoLabel className="flex items-center gap-1.5 text-cohere-green">
                <FileText className="h-3.5 w-3.5" /> Impact report
              </MonoLabel>
              <p className="mt-1 max-w-prose text-caption text-slate">
                A board- and donor-ready narrative drafted from the exact figures above. Never invents numbers.
              </p>
            </div>
            <button onClick={onReport} disabled={reporting} className="btn-primary inline-flex items-center gap-1.5">
              {reporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {report ? "Regenerate" : "Generate report"}
            </button>
          </div>
          {report && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-5">
              <div className="rounded-md border border-hairline bg-parchment/40 p-4">
                <p className="whitespace-pre-line text-body leading-relaxed text-cohere-ink">{report.narrative}</p>
                <p className="mt-3 text-micro text-slate-muted">
                  Numbers computed deterministically — narrative {report.source === "ai" ? "AI-drafted" : "auto-drafted (no AI key)"}.
                </p>
              </div>
            </motion.div>
          )}
        </Card>
      </div>
    </main>
  );
}
