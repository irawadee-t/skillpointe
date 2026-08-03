/**
 * Unified "Add jobs" entry — clarifies the two ways to get jobs onto the platform.
 * Replaces the confusing split between /jobs/new (single post) and /jobs/imports
 * (bulk import).
 */
import { redirect } from "next/navigation";
import Link from "next/link";
import { Plus, Upload, ArrowRight, LinkIcon, FileSpreadsheet, ClipboardList } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { PageHeader, MonoLabel } from "@/components/ui";

export default async function AddJobsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Employer"
          title="Post jobs"
          lead="Two ways to get roles onto SKILLED. Pick the one that matches how you already work."
        />

        <div className="grid gap-4 md:grid-cols-2">
          {/* Single job */}
          <Card
            tourId="post-single"
            eyebrow="One at a time"
            title="Write one job"
            body="Best if you have a specific role to post and want to write it yourself. Takes a few minutes."
            icon={Plus}
            href="/employer/jobs/new"
            cta="Post a job"
          />

          {/* Bulk import */}
          <Card
            tourId="post-import"
            eyebrow="Bring a batch"
            title="Import your existing jobs"
            body="Best if your roles already live somewhere: a careers page, a spreadsheet, or a doc. We'll pull them in and you review each one before it goes live."
            icon={Upload}
            href="/employer/jobs/imports"
            cta="Import jobs"
            secondary
          >
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-caption text-slate">
              <span className="inline-flex items-center gap-1"><LinkIcon className="h-3.5 w-3.5" /> Careers URL</span>
              <span className="inline-flex items-center gap-1"><FileSpreadsheet className="h-3.5 w-3.5" /> CSV upload</span>
              <span className="inline-flex items-center gap-1"><ClipboardList className="h-3.5 w-3.5" /> Manual list</span>
            </div>
          </Card>
        </div>

        <section className="rounded-xl border border-hairline bg-white p-6" data-tour-id="post-how">
          <MonoLabel className="mb-2 block">How the two work together</MonoLabel>
          <p className="text-body text-slate max-w-prose">
            Both routes end up in the same place: your published jobs list and the applicant matching engine. Imports go through a quick admin review; single posts publish straight away since you wrote them.
          </p>
          <div className="mt-4">
            <Link href="/employer/jobs/imports/list" className="inline-flex items-center gap-1 text-caption text-cohere-blue underline decoration-cohere-blue/40 underline-offset-2 hover:decoration-cohere-blue">
              See your import history <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}

function Card({
  eyebrow, title, body, icon: Icon, href, cta, secondary, children, tourId,
}: {
  eyebrow: string;
  title: string;
  body: string;
  icon: typeof Plus;
  href: string;
  cta: string;
  secondary?: boolean;
  children?: React.ReactNode;
  tourId?: string;
}) {
  return (
    <Link
      href={href}
      data-tour-id={tourId}
      className="group flex flex-col rounded-xl border border-hairline bg-white p-6 transition-shadow hover:shadow-[0_8px_28px_-12px_rgba(12,10,9,0.12)]"
    >
      <Icon className={`h-5 w-5 ${secondary ? "text-cohere-blue" : "text-cohere-green"}`} strokeWidth={1.75} />
      <MonoLabel className={`mt-3 ${secondary ? "text-cohere-blue" : "text-cohere-green"}`}>{eyebrow}</MonoLabel>
      <h3 className="mt-2 text-card font-medium tracking-tight text-cohere-ink">{title}</h3>
      <p className="mt-2 flex-1 text-body text-slate">{body}</p>
      {children}
      <span className="mt-5 inline-flex items-center gap-1 text-caption font-medium text-cohere-ink">
        {cta} <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}
