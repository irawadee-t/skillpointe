/**
 * Edit job — Phase 6.2
 *
 * Fetches existing job data via the single-job detail endpoint and pre-fills
 * every form field. Client-side form handles validation + toast.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { Reveal } from "@/components/ui";
import { ScreeningEditor } from "@/components/employer/ScreeningEditor";
import { EditJobFormClient } from "./EditJobFormClient";
import type { JobFormDefaults } from "../../new/JobFormFields";

interface PageProps {
  params: Promise<{ jobId: string }>;
}

export default async function EditJobPage({ params }: PageProps) {
  const { jobId } = await params;

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Fetch full job detail so every field pre-fills correctly.
  let defaults: JobFormDefaults = {};
  try {
    const res = await fetch(`${API_URL}/employer/me/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: "no-store",
    });
    if (res.ok) {
      const job = await res.json();
      defaults = {
        title_raw: job.title_raw ?? undefined,
        city: job.city ?? undefined,
        state: job.state ?? undefined,
        work_setting: job.work_setting ?? undefined,
        travel_requirement: job.travel_requirement ?? undefined,
        pay_min: job.pay_min ?? undefined,
        pay_max: job.pay_max ?? undefined,
        pay_type: job.pay_type ?? undefined,
        description_raw: job.description_raw ?? undefined,
        requirements_raw: job.requirements_raw ?? undefined,
        experience_level: job.experience_level ?? undefined,
        sector_code: job.sector_code ?? undefined,
        field_code: job.field_code ?? undefined,
        is_active: job.is_active,
        accepts_internal_applications: job.accepts_internal_applications,
        internal_apply_effective: job.internal_apply_effective,
        required_profile_fields: job.required_profile_fields ?? undefined,
      };
    }
  } catch {
    // Non-fatal — form will render with empty values
  }

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-3xl px-5 space-y-6">
        <Reveal>
          <a
            href="/employer"
            className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
          >
            ← Back to dashboard
          </a>
          <h1 className="font-display text-card sm:text-heading text-cohere-ink mt-3">Edit job</h1>
        </Reveal>

        <Reveal delay={0.1}>
          <EditJobFormClient
            token={session.access_token}
            jobId={jobId}
            defaults={defaults}
          />
        </Reveal>

        {/* Extra questions beyond the profile — shown to applicants inside the
            apply sheet. Employer-only editor (admin views are read-only). */}
        {role === "employer" && (
          <Reveal delay={0.15}>
            <ScreeningEditor token={session.access_token} jobId={jobId} />
          </Reveal>
        )}
      </div>
    </main>
  );
}
