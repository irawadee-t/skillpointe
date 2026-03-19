"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Search,
  MapPin,
  DollarSign,
  Building2,
  ExternalLink,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Wrench,
  GraduationCap,
  ClipboardList,
  FileText,
  Star,
} from "lucide-react";

import type { JobBrowseItem, JobBrowseResponse } from "./page";

const EMPLOYERS = [
  "Ball Corporation",
  "Delta Air Lines",
  "Ford Motor Company",
  "GE Vernova",
  "Schneider Electric",
  "Southwire",
];

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

const WORK_SETTING_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  on_site: "On-site",
  flexible: "Flexible",
};

interface Props {
  data: JobBrowseResponse | null;
  fetchError: string | null;
  currentPage: number;
  q: string;
  stateFilter: string;
  workSetting: string;
  employerFilter: string;
}

export function JobBrowseClient({
  data,
  fetchError,
  currentPage,
  q,
  stateFilter,
  workSetting,
  employerFilter,
}: Props) {
  const jobs = data?.jobs ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;
  const hasFilters = !!(q || stateFilter || workSetting || employerFilter);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-spf-navy">Browse jobs</h1>
          <p className="text-sm text-gray-500 mt-1">
            {total.toLocaleString()} skilled trade{total !== 1 ? "s" : ""}{" "}
            position{total !== 1 ? "s" : ""} available
          </p>
        </div>

        <form
          method="GET"
          className="bg-white border border-gray-200 rounded-xl p-4 space-y-3"
        >
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                name="q"
                defaultValue={q}
                placeholder="Search by title or description..."
                className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/30"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 bg-spf-navy text-white text-sm rounded-lg hover:bg-spf-navy-light transition-colors"
            >
              Search
            </button>
          </div>
          <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-100">
            <select name="employer" defaultValue={employerFilter} className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/30">
              <option value="">All employers</option>
              {EMPLOYERS.map((e) => (<option key={e} value={e}>{e}</option>))}
            </select>
            <select name="state" defaultValue={stateFilter} className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/30">
              <option value="">All states</option>
              {US_STATES.map((s) => (<option key={s} value={s}>{s}</option>))}
            </select>
            <select name="work_setting" defaultValue={workSetting} className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/30">
              <option value="">All work settings</option>
              <option value="on_site">On-site</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="flexible">Flexible</option>
            </select>
            {hasFilters && (
              <Link href="/applicant/jobs" className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 self-center ml-auto">
                Clear all
              </Link>
            )}
          </div>
        </form>

        {fetchError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-700">{fetchError}</div>
        )}

        {!fetchError && jobs.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
            <Briefcase className="w-8 h-8 text-gray-300 mx-auto" />
            <p className="text-gray-600 font-medium mt-3">No jobs found</p>
            <p className="text-sm text-gray-500 mt-1">Try adjusting your search or filters.</p>
          </div>
        )}

        {jobs.length > 0 && (
          <div className="space-y-3">
            {jobs.map((job) => (<ExpandableJobCard key={job.job_id} job={job} />))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-4 py-3">
            <p className="text-sm text-gray-500">
              Page {currentPage} of {totalPages} ({total.toLocaleString()} total)
            </p>
            <div className="flex gap-2">
              {currentPage > 1 && (
                <PaginationLink page={currentPage - 1} q={q} state={stateFilter} workSetting={workSetting} employer={employerFilter} label="Previous" icon="left" />
              )}
              {currentPage < totalPages && (
                <PaginationLink page={currentPage + 1} q={q} state={stateFilter} workSetting={workSetting} employer={employerFilter} label="Next" icon="right" />
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function PaginationLink({ page, q, state, workSetting, employer, label, icon }: {
  page: number; q: string; state: string; workSetting: string; employer: string; label: string; icon: "left" | "right";
}) {
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (state) qs.set("state", state);
  if (workSetting) qs.set("work_setting", workSetting);
  if (employer) qs.set("employer", employer);
  qs.set("page", String(page));
  return (
    <Link href={`/applicant/jobs?${qs.toString()}`} className="flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm hover:border-gray-300 transition-colors">
      {icon === "left" && <ChevronLeft className="w-3.5 h-3.5" />}
      {label}
      {icon === "right" && <ChevronRight className="w-3.5 h-3.5" />}
    </Link>
  );
}

function ExpandableJobCard({ job }: { job: JobBrowseItem }) {
  const [expanded, setExpanded] = useState(false);

  const location = [job.city, job.state].filter(Boolean).join(", ");
  const workLabel = job.work_setting ? (WORK_SETTING_LABELS[job.work_setting] ?? job.work_setting) : null;
  const payDisplay = formatPay(job);
  const hasDetail = !!(job.description || job.qualifications || job.requirements);
  const familyLabel = job.canonical_job_family_code
    ? job.canonical_job_family_code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  return (
    <div className="bg-white border border-gray-200 rounded-xl hover:border-gray-300 hover:shadow-sm transition-all">
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-gray-900 text-base leading-snug">{job.title}</h3>
            <p className="text-sm text-gray-500 mt-0.5 flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5 shrink-0" />
              {job.employer_name}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {job.source_url && (
              <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 px-3 py-1.5 bg-spf-navy text-white text-xs font-medium rounded-lg hover:bg-spf-navy-light transition-colors">
                Apply <ExternalLink className="w-3 h-3" />
              </a>
            )}
            {hasDetail && (
              <button onClick={() => setExpanded(!expanded)}
                className="p-1.5 rounded-lg border border-gray-200 text-gray-400 hover:text-gray-600 hover:border-gray-300 transition-colors"
                aria-label={expanded ? "Collapse details" : "Expand details"}>
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-gray-600">
          {(location || workLabel) && (
            <span className="flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              {location || ""}
              {workLabel && <span className="text-gray-400">{location ? " · " : ""}{workLabel}</span>}
            </span>
          )}
          {payDisplay && (
            <span className="flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              {payDisplay}
            </span>
          )}
        </div>

        {!expanded && job.description_preview && (
          <p className="mt-2 text-xs text-gray-500 line-clamp-2">{job.description_preview}</p>
        )}

        {familyLabel && (
          <div className="mt-3">
            <span className="text-xs bg-spf-navy/5 text-spf-navy border border-spf-navy/10 rounded-md px-2 py-0.5">
              {familyLabel}
            </span>
          </div>
        )}
      </div>

      {expanded && hasDetail && (
        <div className="border-t border-gray-100 px-5 py-4 bg-gray-50/50 space-y-5">
          <StructuredDescription description={job.description} requirements={job.requirements} qualifications={job.qualifications} />
          {job.source_url && (
            <div className="pt-2">
              <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-spf-navy text-white text-sm font-medium rounded-lg hover:bg-spf-navy-light transition-colors">
                Apply for this position <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Structured Description Renderer                                     */
/* ------------------------------------------------------------------ */

function StructuredDescription({ description, requirements, qualifications }: {
  description: string | null; requirements: string | null; qualifications: string | null;
}) {
  const sections = parseDescriptionIntoSections(description || "");
  const hasExplicitReqs = !!requirements;
  const hasExplicitQuals = !!qualifications;

  return (
    <div className="space-y-5">
      {sections.map((section, i) => (
        <DescriptionSection key={i} section={section} />
      ))}

      {hasExplicitReqs && (
        <DescriptionSection section={{
          title: "Requirements",
          icon: "requirements",
          items: splitIntoItems(requirements!),
        }} />
      )}

      {hasExplicitQuals && (
        <DescriptionSection section={{
          title: "Qualifications",
          icon: "qualifications",
          items: splitIntoItems(qualifications!),
        }} />
      )}
    </div>
  );
}

interface Section {
  title: string;
  icon: "overview" | "responsibilities" | "requirements" | "qualifications" | "preferred" | "benefits" | "other";
  items: SectionItem[];
}

type SectionItem =
  | { type: "paragraph"; text: string }
  | { type: "bullet"; text: string };

const SECTION_ICONS: Record<string, React.ReactNode> = {
  overview: <Briefcase className="w-4 h-4 text-gray-500" />,
  responsibilities: <ClipboardList className="w-4 h-4 text-gray-500" />,
  requirements: <Wrench className="w-4 h-4 text-gray-500" />,
  qualifications: <GraduationCap className="w-4 h-4 text-gray-500" />,
  preferred: <Star className="w-4 h-4 text-gray-500" />,
  benefits: <FileText className="w-4 h-4 text-gray-500" />,
  other: <FileText className="w-4 h-4 text-gray-500" />,
};

function DescriptionSection({ section }: { section: Section }) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5 mb-2">
        {SECTION_ICONS[section.icon]}
        {section.title}
      </h4>
      <div className="text-sm text-gray-600 leading-relaxed">
        {section.items.map((item, i) =>
          item.type === "bullet" ? (
            <div key={i} className="flex items-start gap-2 py-0.5">
              <span className="w-1.5 h-1.5 bg-gray-300 rounded-full mt-1.5 shrink-0" />
              <span>{item.text}</span>
            </div>
          ) : (
            <p key={i} className={i > 0 ? "mt-2" : ""}>{item.text}</p>
          )
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Smart description parser                                            */
/* ------------------------------------------------------------------ */

const SECTION_HEADERS: { pattern: RegExp; title: string; icon: Section["icon"] }[] = [
  { pattern: /^(?:about\s+(?:the\s+)?(?:role|position|job|opportunity)|job\s+description|overview|summary|position\s+summary)[\s:]*$/i, title: "About the role", icon: "overview" },
  { pattern: /^(?:what\s+you(?:'ll|.will)\s+do|(?:key\s+)?responsibilities|duties|your\s+(?:impactful\s+)?responsibilities|a\s+typical\s+day|day[- ]to[- ]day)[\s:]*$/i, title: "Responsibilities", icon: "responsibilities" },
  { pattern: /^(?:you(?:'ll|.will)\s+have\.{0,3}|what\s+(?:we(?:'re)?\s+(?:looking|need)|you\s+(?:need|bring))|requirements?|minimum\s+qualifications?|basic\s+qualifications?|who\s+you\s+are|this\s+may\s+be\s+the\s+next)[\s:]*$/i, title: "Requirements", icon: "requirements" },
  { pattern: /^(?:even\s+better,?\s+you\s+may\s+have\.{0,3}|preferred\s+qualifications?|nice\s+to\s+have|bonus\s+(?:skills|qualifications)|additional\s+qualifications?)[\s:]*$/i, title: "Preferred", icon: "preferred" },
  { pattern: /^(?:what\s+we\s+(?:offer|have|provide)|benefits?|compensation\s+(?:and|&)\s+benefits|perks|why\s+(?:join|work)|what(?:'s|\s+is)\s+in\s+it\s+for\s+you)[\s:]*$/i, title: "Benefits", icon: "benefits" },
  { pattern: /^(?:on\s+some\s+days)[\s:]*$/i, title: "Additional duties", icon: "responsibilities" },
  { pattern: /^(?:how\s+you(?:'ll)?\s+help|your\s+role)[\s:]*$/i, title: "About the role", icon: "overview" },
];

function parseDescriptionIntoSections(raw: string): Section[] {
  if (!raw || !raw.trim()) return [];

  const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];

  const rawSections: { title: string; icon: Section["icon"]; lines: string[] }[] = [];
  let currentTitle = "About the role";
  let currentIcon: Section["icon"] = "overview";
  let currentLines: string[] = [];

  for (const line of lines) {
    let matchedHeader = false;

    for (const sh of SECTION_HEADERS) {
      if (sh.pattern.test(line)) {
        if (currentLines.length > 0) {
          rawSections.push({ title: currentTitle, icon: currentIcon, lines: [...currentLines] });
        }
        currentTitle = sh.title;
        currentIcon = sh.icon;
        currentLines = [];
        matchedHeader = true;
        break;
      }
    }

    if (!matchedHeader) {
      currentLines.push(line);
    }
  }

  if (currentLines.length > 0) {
    rawSections.push({ title: currentTitle, icon: currentIcon, lines: currentLines });
  }

  if (rawSections.length === 0) return [];

  return rawSections.map(rs => ({
    title: rs.title,
    icon: rs.icon,
    items: classifyLines(rs.lines),
  }));
}

function classifyLines(lines: string[]): SectionItem[] {
  if (lines.length === 0) return [];

  const items: SectionItem[] = [];
  let paragraphBuffer: string[] = [];

  const flushParagraph = () => {
    if (paragraphBuffer.length > 0) {
      items.push({ type: "paragraph", text: paragraphBuffer.join(" ") });
      paragraphBuffer = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (/^\s*[-•·▪►◆★✓✔]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line) || /^\s*[a-z][.)]\s+/.test(line)) {
      flushParagraph();
      items.push({ type: "bullet", text: line.replace(/^\s*[-•·▪►◆★✓✔]\s+/, "").replace(/^\s*\d+[.)]\s+/, "").replace(/^\s*[a-z][.)]\s+/, "").trim() });
      continue;
    }

    const isShortActionLine = line.length < 250 &&
      /^[A-Z]/.test(line) &&
      !line.endsWith(",") &&
      (line.endsWith(".") || line.endsWith(":") || !line.includes(". "));

    const prevIsBullet = items.length > 0 && items[items.length - 1].type === "bullet";
    const nextIsShort = i + 1 < lines.length && lines[i + 1].length < 250;

    if (isShortActionLine && (prevIsBullet || (i > 0 && paragraphBuffer.length === 0 && nextIsShort))) {
      flushParagraph();
      items.push({ type: "bullet", text: line });
      continue;
    }

    if (line.length > 200 && line.includes(". ")) {
      paragraphBuffer.push(line);
    } else if (paragraphBuffer.length > 0 && line.length > 150) {
      paragraphBuffer.push(line);
    } else if (paragraphBuffer.length === 0 && i === 0 && line.length > 80) {
      paragraphBuffer.push(line);
    } else if (items.length === 0 && paragraphBuffer.length === 0 && line.length > 60) {
      paragraphBuffer.push(line);
    } else {
      flushParagraph();
      items.push({ type: "bullet", text: line });
    }
  }

  flushParagraph();

  const bulletCount = items.filter(it => it.type === "bullet").length;
  const paraCount = items.filter(it => it.type === "paragraph").length;
  if (paraCount > 3 && bulletCount === 0) {
    return items.map(it => it.type === "paragraph" && it.text.length < 300
      ? { type: "bullet" as const, text: it.text }
      : it
    );
  }

  return items;
}

function splitIntoItems(text: string): SectionItem[] {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  return classifyLines(lines);
}

function formatPay(job: JobBrowseItem): string | null {
  if (job.pay_raw) return job.pay_raw;
  if (job.pay_min === null) return null;
  const suffix = job.pay_type === "hourly" ? "/hr" : job.pay_type === "annual" ? "/yr" : "";
  const fmt = (n: number) => job.pay_type === "annual" ? `$${(n / 1000).toFixed(0)}k` : `$${n.toFixed(0)}`;
  if (job.pay_max && job.pay_max !== job.pay_min) return `${fmt(job.pay_min)}-${fmt(job.pay_max)}${suffix}`;
  return `${fmt(job.pay_min)}${suffix}`;
}
