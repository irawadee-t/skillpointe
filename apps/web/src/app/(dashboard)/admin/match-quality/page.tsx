/**
 * Admin Match Quality — the SHAPE of the marketplace, not its activity.
 *
 * Four questions, in reading order:
 *   1. Do applicants have matches? (coverage headline + distribution)
 *   2. Why don't the rest? (named causes, live-computed)
 *   3. What expertise is walking in the door vs what each partner's catalog
 *      actually contains? (supply/demand composition)
 *   4. Which missing profile fields are holding matches back right now?
 *      (data-gap impact — counts of real matches, not hypotheticals)
 *
 * All data from GET /admin/analytics/marketplace (live aggregates).
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, Breadcrumb, MetricCard } from "@/components/ui";

const API_URL = () =>
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SectorRow { sector: string; applicants: number }
interface FieldRow { field: string; applicants: number }
interface PartnerRow {
  partner: string; active_jobs: number;
  pct_entry: number; pct_mid: number; pct_senior: number; pct_management: number;
  pct_will_train: number; pct_apprenticeship: number;
  pct_with_credentials: number; pct_with_pay: number; states: number;
}
interface Marketplace {
  generated_at: string;
  applicant_sectors: SectorRow[];
  applicant_fields: FieldRow[];
  partners: PartnerRow[];
  coverage: {
    applicants: number; with_any_match: number; with_eligible: number;
    with_one_step: number; near_fit_only: number; zero: number;
    b_1_4: number; b_5_19: number; b_20_plus: number;
    median_when_matched: number;
    pct_with_any: number; pct_with_eligible: number;
    pct_near_fit_only: number; pct_zero: number;
  };
  zero_causes: {
    total: number; no_location: number; no_jobs_in_state: number; no_jobs_in_field: number;
  };
  data_gaps: {
    field_coverage: {
      timing_pct: number; stated_career_pct: number; classified_pct: number;
      city_pct: number; radius_pct: number;
    };
    credentials_disclosed_applicants: number;
    one_cert_away_matches: number;
    one_cert_away_people: number;
    timing_blocked_matches: number;
    score_evidence_mean: number;
    score_evidence_median: number;
  };
}

async function fetchMarketplace(token: string): Promise<Marketplace | null> {
  try {
    const res = await fetch(`${API_URL()}/admin/analytics/marketplace`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

const nf = (n: number) => n.toLocaleString("en-US");

/** Horizontal proportion bar — one row of a composition chart. */
function Bar({ label, value, max, detail }: { label: string; value: number; max: number; detail?: string }) {
  const pct = max > 0 ? Math.max(1.5, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-56 shrink-0 truncate text-body text-ink" title={label}>{label}</span>
      <div className="h-4 flex-1 rounded-sm bg-stone">
        <div className="h-4 rounded-sm bg-cohere-blue/80" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-28 shrink-0 text-right text-body tabular-nums text-slate">
        {nf(value)}{detail ? ` ${detail}` : ""}
      </span>
    </div>
  );
}

function SectionCard({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[14px] border border-hairline bg-white p-6">
      <h2 className="text-[1.05rem] font-semibold text-cohere-ink">{title}</h2>
      {sub && <p className="mt-1 text-micro text-slate max-w-prose">{sub}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export default async function AdminMatchQualityPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const data = await fetchMarketplace(session.access_token);
  if (!data) {
    return (
      <main className="py-8">
        <div className="page-shell">
          <p className="text-body text-slate">
            Match-quality analytics are unavailable — the API did not respond. Check that the backend is running.
          </p>
        </div>
      </main>
    );
  }

  const c = data.coverage;
  const g = data.data_gaps;
  const maxSector = Math.max(...data.applicant_sectors.map((s) => s.applicants), 1);
  const maxField = Math.max(...data.applicant_fields.map((f) => f.applicants), 1);
  const unexplainedZero =
    data.zero_causes.total - data.zero_causes.no_location -
    data.zero_causes.no_jobs_in_state - data.zero_causes.no_jobs_in_field;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Match quality" }]} />
        <PageHeader
          title="Match quality"
          lead="The shape of the marketplace: who has matches, why the rest don't, what each partner's catalog contains, and which missing data is holding matches back."
        />

        {/* 1 — Coverage headline */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricCard
            label="Applicants with matches"
            value={`${c.pct_with_any}%`}
            sub={`${nf(c.with_any_match)} of ${nf(c.applicants)}`}
          />
          <MetricCard
            label="Ready now (eligible)"
            value={`${c.pct_with_eligible}%`}
            sub={`${nf(c.with_eligible)} applicants have an apply-today job`}
          />
          <MetricCard
            label="One step away"
            value={nf(c.with_one_step)}
            sub="applicants with a 1-gap match — the coachable pipeline"
          />
          <MetricCard
            label="No matches yet"
            value={`${c.pct_zero}%`}
            sub={`${nf(c.zero)} applicants — causes below`}
          />
        </div>

        {/* 2 — How many matches does a matched person have? */}
        <SectionCard
          title="Matches per applicant"
          sub={`Median ${c.median_when_matched} matches when matched at all. Buckets count visible (eligible + near-fit) matches.`}
        >
          <div className="space-y-2.5">
            <Bar label="No matches" value={c.zero} max={c.applicants} />
            <Bar label="1–4 matches" value={c.b_1_4} max={c.applicants} />
            <Bar label="5–19 matches" value={c.b_5_19} max={c.applicants} />
            <Bar label="20+ matches" value={c.b_20_plus} max={c.applicants} />
          </div>
        </SectionCard>

        {/* 3 — Why zero? Named causes, not a shrug */}
        <SectionCard
          title="Why the unmatched are unmatched"
          sub="Live-computed causes for the zero-match population. These are catalog and data problems, not scoring problems — each names its own fix."
        >
          <div className="space-y-2.5">
            <Bar label="No jobs in their career field anywhere" value={data.zero_causes.no_jobs_in_field} max={data.zero_causes.total} detail="→ sign that partner" />
            <Bar label="No active jobs in their state" value={data.zero_causes.no_jobs_in_state} max={data.zero_causes.total} detail="→ geographic gap" />
            <Bar label="No location on profile" value={data.zero_causes.no_location} max={data.zero_causes.total} detail="→ ask for city/state" />
            <Bar label="Other (field unclassified or gates)" value={Math.max(0, unexplainedZero)} max={data.zero_causes.total} />
          </div>
        </SectionCard>

        {/* 4 — Data gaps: the "one column away" panel */}
        <SectionCard
          title="Matches held back by missing profile data"
          sub="The PSA import left certifications, timing, and commute radius blank. Each number counts real matches whose named blocker is that missing field — filling the field flips them."
        >
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MetricCard
              label="One credential away"
              value={nf(g.one_cert_away_matches)}
              sub={`matches across ${nf(g.one_cert_away_people)} people — certs were left blank, many may already hold them`}
            />
            <MetricCard
              label="Certs disclosed"
              value={nf(g.credentials_disclosed_applicants)}
              sub={`of ${nf(c.applicants)} applicants have any credential on file`}
            />
            <MetricCard
              label="Timing known"
              value={`${g.field_coverage.timing_pct}%`}
              sub="completion dates absent — the timing dimension scores nothing today"
            />
            <MetricCard
              label="Score evidence"
              value={`${g.score_evidence_median}%`}
              sub={`median share of each score backed by real data (mean ${g.score_evidence_mean}%)`}
            />
          </div>
          <p className="mt-4 text-micro text-slate max-w-prose">
            Field coverage: city {g.field_coverage.city_pct}% · career field classified {g.field_coverage.classified_pct}% ·
            stated career text {g.field_coverage.stated_career_pct}% · commute radius {g.field_coverage.radius_pct}% ·
            completion date {g.field_coverage.timing_pct}%. The fastest quality win is collecting certifications and
            completion dates — either from the next PSA export or by asking applicants at sign-in.
          </p>
        </SectionCard>

        {/* 5 — Supply: applicant expertise */}
        <div className="grid gap-6 lg:grid-cols-2">
          <SectionCard title="Applicant expertise by sector" sub="What's walking in the door.">
            <div className="space-y-2.5">
              {data.applicant_sectors.map((s) => (
                <Bar key={s.sector} label={s.sector} value={s.applicants} max={maxSector} />
              ))}
            </div>
          </SectionCard>
          <SectionCard title="Top career fields" sub="Fifteen largest classified fields.">
            <div className="space-y-2.5">
              {data.applicant_fields.map((f) => (
                <Bar key={f.field} label={f.field} value={f.applicants} max={maxField} />
              ))}
            </div>
          </SectionCard>
        </div>

        {/* 6 — Demand: what each partner's catalog actually contains */}
        <SectionCard
          title="Partner catalog composition"
          sub="Share of each partner's active postings by seniority and signals — the honest answer to “what % of a partner's jobs are actually entry level”."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-body tabular-nums">
              <thead>
                <tr className="border-b border-ink/70 text-left text-micro uppercase tracking-wide text-slate">
                  <th className="py-2 pr-4 font-medium">Partner</th>
                  <th className="py-2 pr-4 text-right font-medium">Jobs</th>
                  <th className="py-2 pr-4 text-right font-medium">Entry</th>
                  <th className="py-2 pr-4 text-right font-medium">Mid</th>
                  <th className="py-2 pr-4 text-right font-medium">Senior</th>
                  <th className="py-2 pr-4 text-right font-medium">Mgmt</th>
                  <th className="py-2 pr-4 text-right font-medium">Will train</th>
                  <th className="py-2 pr-4 text-right font-medium">Apprentice</th>
                  <th className="py-2 pr-4 text-right font-medium">Creds listed</th>
                  <th className="py-2 pr-4 text-right font-medium">Pay listed</th>
                  <th className="py-2 text-right font-medium">States</th>
                </tr>
              </thead>
              <tbody>
                {data.partners.map((p) => (
                  <tr key={p.partner} className="border-b border-hairline">
                    <td className="py-2.5 pr-4 text-ink">{p.partner}</td>
                    <td className="py-2.5 pr-4 text-right">{nf(p.active_jobs)}</td>
                    <td className={`py-2.5 pr-4 text-right ${p.pct_entry >= 30 ? "font-semibold text-cohere-ink" : ""}`}>{p.pct_entry}%</td>
                    <td className="py-2.5 pr-4 text-right text-slate">{p.pct_mid}%</td>
                    <td className="py-2.5 pr-4 text-right text-slate">{p.pct_senior}%</td>
                    <td className="py-2.5 pr-4 text-right text-slate">{p.pct_management}%</td>
                    <td className={`py-2.5 pr-4 text-right ${p.pct_will_train >= 25 ? "font-semibold text-cohere-ink" : ""}`}>{p.pct_will_train}%</td>
                    <td className={`py-2.5 pr-4 text-right ${p.pct_apprenticeship >= 10 ? "font-semibold text-cohere-ink" : ""}`}>{p.pct_apprenticeship}%</td>
                    <td className="py-2.5 pr-4 text-right text-slate">{p.pct_with_credentials}%</td>
                    <td className="py-2.5 pr-4 text-right text-slate">{p.pct_with_pay}%</td>
                    <td className="py-2.5 text-right text-slate">{p.states}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-micro text-slate max-w-prose">
            For a trainee-heavy applicant base, the columns that matter are Entry, Will train, and Apprentice —
            a partner can post many jobs and still offer this audience nothing.
          </p>
        </SectionCard>
      </div>
    </main>
  );
}
