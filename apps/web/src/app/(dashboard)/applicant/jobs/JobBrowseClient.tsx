"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Search,
  MapPin,
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

import { motion, AnimatePresence } from "motion/react";

import type { JobBrowseItem, JobBrowseResponse } from "./page";
import { PageHeader, Stagger, StaggerItem } from "@/components/ui";
import { easeCohere } from "@/lib/motion";


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
  employers: string[];
}

export function JobBrowseClient({
  data,
  fetchError,
  currentPage,
  q,
  stateFilter,
  workSetting,
  employerFilter,
  employers,
}: Props) {
  const jobs = data?.jobs ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;
  const hasFilters = !!(q || stateFilter || workSetting || employerFilter);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Browse"
          title="Browse jobs"
          lead={`${total.toLocaleString()} skilled trade${total !== 1 ? "s" : ""} position${total !== 1 ? "s" : ""} available`}
        />

        <form
          method="GET"
          className="bg-white border border-border-light rounded-md p-4 space-y-3"
        >
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-muted z-10" />
              <input
                type="text"
                name="q"
                defaultValue={q}
                placeholder="Search by title or description..."
                className="input-cohere w-full pl-10"
              />
            </div>
            <button
              type="submit"
              className="btn-primary"
            >
              Search
            </button>
          </div>
          <div className="flex flex-wrap gap-3 pt-2 border-t border-border-light">
            <select name="employer" defaultValue={employerFilter} className="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40">
              <option value="">All employers</option>
              {employers.map((e) => (<option key={e} value={e}>{e}</option>))}
            </select>
            <select name="state" defaultValue={stateFilter} className="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40">
              <option value="">All states</option>
              {US_STATES.map((s) => (<option key={s} value={s}>{s}</option>))}
            </select>
            <select name="work_setting" defaultValue={workSetting} className="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40">
              <option value="">All work settings</option>
              <option value="on_site">On-site</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="flexible">Flexible</option>
            </select>
            {hasFilters && (
              <Link href="/applicant/jobs" className="flex items-center gap-1 text-micro text-slate-muted hover:text-ink self-center ml-auto transition-colors">
                Clear all
              </Link>
            )}
          </div>
        </form>

        {fetchError && (
          <div className="bg-studio-maroon/10 border border-studio-maroon-soft rounded-md p-5 text-body text-error-red">{fetchError}</div>
        )}

        {!fetchError && jobs.length === 0 && (
          <div className="bg-stone border border-transparent rounded-md p-10 text-center">
            <Briefcase className="w-8 h-8 text-slate mx-auto" />
            <p className="font-display text-feature text-cohere-ink mt-3">No jobs found</p>
            <p className="text-body text-slate mt-1">Try adjusting your search or filters.</p>
          </div>
        )}

        {jobs.length > 0 && (
          <Stagger className="space-y-3">
            {jobs.map((job) => (
              <StaggerItem key={job.job_id}>
                <ExpandableJobCard job={job} />
              </StaggerItem>
            ))}
          </Stagger>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between bg-white border border-border-light rounded-md px-4 py-3">
            <p className="text-body text-slate">
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
    <Link href={`/applicant/jobs?${qs.toString()}`} className="flex items-center gap-1 px-3 py-1.5 border border-hairline rounded-pill text-caption text-slate hover:border-cohere-ink hover:text-ink transition-colors">
      {icon === "left" && <ChevronLeft className="w-3.5 h-3.5" />}
      {label}
      {icon === "right" && <ChevronRight className="w-3.5 h-3.5" />}
    </Link>
  );
}

function ExpandableJobCard({ job }: { job: JobBrowseItem }) {
  const [expanded, setExpanded] = useState(false);

  // Scraped feeds sometimes send literal "Unspecified" — treat it as absent.
  const clean = (v: string | null | undefined) =>
    v && v.trim() && !/^unspecified$/i.test(v.trim()) ? v.trim() : null;
  const location = [clean(job.city), clean(job.state)].filter(Boolean).join(", ");
  const workLabel = job.work_setting ? (WORK_SETTING_LABELS[job.work_setting] ?? job.work_setting) : null;
  const payDisplay = formatPay(job);
  const hasDetail = !!(job.description || job.qualifications || job.requirements);
  const familyLabel = job.canonical_job_family_code
    ? job.canonical_job_family_code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  return (
    <div className="bg-white border border-border-light rounded-md hover:border-cohere-ink transition-colors">
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-feature text-cohere-ink leading-snug">{job.title}</h3>
            <p className="text-body text-slate mt-0.5 flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5 shrink-0" />
              {job.employer_name}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {job.source_url && (
              <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                className="btn-sm">
                Apply <ExternalLink className="w-3 h-3" />
              </a>
            )}
            {hasDetail && (
              <button onClick={() => setExpanded(!expanded)}
                className="p-1.5 rounded-sm border border-hairline text-slate hover:text-ink hover:border-cohere-ink transition-colors"
                aria-label={expanded ? "Collapse details" : "Expand details"}>
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-body text-slate">
          {(location || workLabel) && (
            <span className="flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 shrink-0 text-slate" />
              {[location, workLabel].filter(Boolean).join(", ")}
            </span>
          )}
          {/* payDisplay carries its own "$" — no icon, or it reads "$ $31". */}
          {payDisplay && <span>{payDisplay}</span>}
        </div>

        {!expanded && job.description_preview && (
          <p className="mt-2 text-caption text-slate line-clamp-2">
            {job.description_preview.trim()}
            {/[.!?…]$/.test(job.description_preview.trim()) ? "" : "…"}
          </p>
        )}

        {familyLabel && (
          <div className="mt-3">
            <span className="rounded-sm border border-hairline bg-parchment px-2 py-0.5 text-caption text-slate">
              {familyLabel}
            </span>
          </div>
        )}
      </div>

      <AnimatePresence initial={false}>
        {expanded && hasDetail && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easeCohere }}
            className="overflow-hidden"
          >
            <div className="border-t border-border-light px-5 py-4 bg-stone space-y-5">
              <StructuredDescription description={job.description} requirements={job.requirements} qualifications={job.qualifications} />
              {job.source_url && (
                <div className="pt-2">
                  <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                    className="btn-primary inline-flex items-center gap-2">
                    Apply for this position <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
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
  overview: <Briefcase className="w-4 h-4 text-slate" />,
  responsibilities: <ClipboardList className="w-4 h-4 text-slate" />,
  requirements: <Wrench className="w-4 h-4 text-slate" />,
  qualifications: <GraduationCap className="w-4 h-4 text-slate" />,
  preferred: <Star className="w-4 h-4 text-slate" />,
  benefits: <FileText className="w-4 h-4 text-slate" />,
  other: <FileText className="w-4 h-4 text-slate" />,
};

function DescriptionSection({ section }: { section: Section }) {
  return (
    <div>
      <h4 className="text-body font-semibold text-ink flex items-center gap-1.5 mb-2">
        {SECTION_ICONS[section.icon]}
        {section.title}
      </h4>
      <div className="text-body text-slate leading-relaxed">
        {section.items.map((item, i) =>
          item.type === "bullet" ? (
            <div key={i} className="flex items-start gap-2 py-0.5">
              <span className="w-1.5 h-1.5 bg-cohere-green rounded-full mt-2 shrink-0" />
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
