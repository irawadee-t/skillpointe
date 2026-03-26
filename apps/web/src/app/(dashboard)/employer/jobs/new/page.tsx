/**
 * New job form — Phase 6.2
 *
 * Basic scaffold for creating a new job posting.
 * Server component with a server action that POSTs to /employer/me/jobs.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function NewJobPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  async function handleCreate(formData: FormData) {
    "use server";

    const supabase = await createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) redirect("/login");

    const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    const payload = {
      title_raw: formData.get("title_raw") as string,
      city: (formData.get("city") as string) || undefined,
      state: (formData.get("state") as string) || undefined,
      work_setting: (formData.get("work_setting") as string) || undefined,
      travel_requirement: (formData.get("travel_requirement") as string) || undefined,
      pay_min: formData.get("pay_min") ? Number(formData.get("pay_min")) : undefined,
      pay_max: formData.get("pay_max") ? Number(formData.get("pay_max")) : undefined,
      pay_type: (formData.get("pay_type") as string) || undefined,
      description_raw: (formData.get("description_raw") as string) || undefined,
      requirements_raw: (formData.get("requirements_raw") as string) || undefined,
      experience_level: (formData.get("experience_level") as string) || undefined,
    };

    const res = await fetch(`${API_URL}/employer/me/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    if (res.ok) {
      redirect("/employer");
    }
  }

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <a
            href="/employer"
            className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
          >
            ← Back to dashboard
          </a>
          <h1 className="text-2xl font-semibold tracking-tight text-white mt-1">Post a new job</h1>
        </div>

        <form action={handleCreate} className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
          <JobFormFields />
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="px-5 py-2 bg-cyan-500 text-black text-sm font-medium rounded-full hover:bg-cyan-400 transition-colors"
            >
              Create job
            </button>
            <a
              href="/employer"
              className="px-5 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Cancel
            </a>
          </div>
        </form>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Shared form fields component (used by new + edit pages)
// ---------------------------------------------------------------------------

export function JobFormFields({
  defaults,
}: {
  defaults?: {
    title_raw?: string;
    city?: string;
    state?: string;
    work_setting?: string;
    travel_requirement?: string;
    pay_min?: number;
    pay_max?: number;
    pay_type?: string;
    description_raw?: string;
    requirements_raw?: string;
    experience_level?: string;
    is_active?: boolean;
  };
}) {
  return (
    <>
      <Field label="Job title *" required>
        <input
          type="text"
          name="title_raw"
          required
          defaultValue={defaults?.title_raw}
          className={inputClass}
          placeholder="e.g. Welder – Entry Level"
        />
      </Field>

      <div className="grid grid-cols-2 gap-4">
        <Field label="City">
          <input
            type="text"
            name="city"
            defaultValue={defaults?.city}
            className={inputClass}
            placeholder="e.g. Austin"
          />
        </Field>
        <Field label="State">
          <input
            type="text"
            name="state"
            maxLength={2}
            defaultValue={defaults?.state}
            className={inputClass}
            placeholder="e.g. TX"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Work setting">
          <select name="work_setting" defaultValue={defaults?.work_setting ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="on_site">On-site</option>
            <option value="hybrid">Hybrid</option>
            <option value="remote">Remote</option>
            <option value="flexible">Flexible</option>
          </select>
        </Field>
        <Field label="Travel requirement">
          <select name="travel_requirement" defaultValue={defaults?.travel_requirement ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="none">None</option>
            <option value="light">Light</option>
            <option value="moderate">Moderate</option>
            <option value="frequent">Frequent</option>
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Field label="Pay min">
          <input
            type="number"
            name="pay_min"
            min="0"
            step="0.01"
            defaultValue={defaults?.pay_min}
            className={inputClass}
            placeholder="0"
          />
        </Field>
        <Field label="Pay max">
          <input
            type="number"
            name="pay_max"
            min="0"
            step="0.01"
            defaultValue={defaults?.pay_max}
            className={inputClass}
            placeholder="0"
          />
        </Field>
        <Field label="Pay type">
          <select name="pay_type" defaultValue={defaults?.pay_type ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="hourly">Hourly</option>
            <option value="annual">Annual</option>
            <option value="contract">Contract</option>
          </select>
        </Field>
      </div>

      <Field label="Experience level">
        <select name="experience_level" defaultValue={defaults?.experience_level ?? ""} className={inputClass}>
          <option value="">Not specified</option>
          <option value="entry">Entry level</option>
          <option value="mid">Mid level</option>
          <option value="senior">Senior</option>
        </select>
      </Field>

      <Field label="Job description">
        <textarea
          name="description_raw"
          rows={4}
          defaultValue={defaults?.description_raw}
          className={inputClass}
          placeholder="Describe the role, responsibilities, and work environment..."
        />
      </Field>

      <Field label="Requirements">
        <textarea
          name="requirements_raw"
          rows={3}
          defaultValue={defaults?.requirements_raw}
          className={inputClass}
          placeholder="List required qualifications, certifications, or experience..."
        />
      </Field>
    </>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-300 mb-1">
        {label}
        {required && <span className="text-rose-400 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputClass =
  "w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500";
