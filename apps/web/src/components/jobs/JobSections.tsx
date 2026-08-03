"use client";

/**
 * JobSections — fetches `/jobs/{id}/sections` and renders every job in the
 * same canonical schema:
 *
 *   At a glance → About the role → What you'll do → What you'll need →
 *   Nice to have → Pay & benefits → Schedule →
 *   About the company (collapsed) → Equal opportunity & other notices (collapsed)
 *
 * Empty sections are omitted. Marketing prose and legal boilerplate exist for
 * completeness but stay behind quiet disclosure rows so the working sections
 * read clean.
 */

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { apiFetch } from "@/lib/api/client";
import { Skeleton } from "@/components/ui";

interface JobSectionsData {
  job_id: string;
  source: string;
  quality: string;
  glance: {
    location: string | null;
    work_setting: string | null;
    shift: string | null;
    pay: string | null;
  };
  about: string[];
  duties: string[];
  needs: string[];
  nice_to_have: string[];
  benefits: string[];
  schedule?: string[];
  company?: string[];
  notices?: string[];
}

const WORK_SETTING_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  on_site: "On-site",
  flexible: "Flexible",
};

export function JobSections({ jobId, token }: { jobId: string; token: string }) {
  const [data, setData] = useState<JobSectionsData | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setData(null);
    setFailed(false);
    apiFetch<JobSectionsData>(`/jobs/${jobId}/sections`, token)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [jobId, token, attempt]);

  if (failed) {
    return (
      <div className="space-y-3">
        <p className="text-body text-slate-muted">
          Job details couldn&apos;t be loaded right now.
        </p>
        <button
          type="button"
          onClick={() => setAttempt((a) => a + 1)}
          className="btn-pill-outline text-micro"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-2" aria-hidden>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    );
  }

  const schedule = data.schedule ?? [];
  const company = data.company ?? [];
  const notices = data.notices ?? [];

  const glanceItems: { label: string; value: string }[] = [];
  if (data.glance.location) glanceItems.push({ label: "Location", value: data.glance.location });
  if (data.glance.work_setting)
    glanceItems.push({
      label: "Work setting",
      value: WORK_SETTING_LABELS[data.glance.work_setting] ?? data.glance.work_setting,
    });
  if (data.glance.shift) glanceItems.push({ label: "Shift", value: data.glance.shift });
  if (data.glance.pay) glanceItems.push({ label: "Pay", value: data.glance.pay });

  const hasContent =
    glanceItems.length > 0 ||
    data.about.length > 0 ||
    data.duties.length > 0 ||
    data.needs.length > 0 ||
    data.nice_to_have.length > 0 ||
    data.benefits.length > 0 ||
    schedule.length > 0 ||
    company.length > 0 ||
    notices.length > 0;

  if (!hasContent) {
    return <p className="text-body text-slate-muted">No details available for this job.</p>;
  }

  return (
    <div className="space-y-5">
      {glanceItems.length > 0 && (
        <section>
          <h4 className="text-body font-medium text-cohere-ink mb-2">At a glance</h4>
          <dl className="space-y-1">
            {glanceItems.map((item) => (
              <div key={item.label} className="flex gap-2 text-body">
                <dt className="text-slate-muted shrink-0">{item.label}</dt>
                <dd className="text-slate">{item.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {data.about.length > 0 && (
        <section>
          <h4 className="text-body font-medium text-cohere-ink mb-2">About the role</h4>
          <div className="space-y-2">
            {data.about.map((p, i) => (
              <p key={i} className="text-body text-slate leading-relaxed">
                {p}
              </p>
            ))}
          </div>
        </section>
      )}

      <BulletSection title="What you'll do" items={data.duties} />
      <BulletSection title="What you'll need" items={data.needs} />
      <BulletSection title="Nice to have" items={data.nice_to_have} />
      <BulletSection title="Pay & benefits" items={data.benefits} />
      <BulletSection title="Schedule" items={schedule} />

      <DisclosureSection title="About the company" items={company} />
      <DisclosureSection title="Equal opportunity & other notices" items={notices} small />
    </div>
  );
}

function BulletSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h4 className="text-body font-medium text-cohere-ink mb-2">{title}</h4>
      <ul className="list-disc pl-5 text-body text-slate space-y-1">
        {items.map((item, i) => (
          <li key={i} className="leading-relaxed">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Quiet disclosure row — collapsed by default. Used for company marketing and
 * legal notices: present for completeness, out of the way by design.
 */
function DisclosureSection({
  title,
  items,
  small = false,
}: {
  title: string;
  items: string[];
  small?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <section className="border-t border-hairline pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left text-caption font-medium text-slate-muted hover:text-cohere-ink transition-colors"
      >
        {title}
        <ChevronDown
          className={`w-3.5 h-3.5 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {items.map((p, i) => (
            <p
              key={i}
              className={`${small ? "text-caption" : "text-body"} text-slate-muted leading-relaxed`}
            >
              {p}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
