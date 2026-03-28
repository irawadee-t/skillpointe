/**
 * Edit job — Phase 6.2
 *
 * Fetches existing job data and pre-fills the form.
 * Server component with a server action that PATCHes /employer/me/jobs/{id}.
 */
import { notFound, redirect } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { JobFormFields } from "../../new/page";

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

  const API_URL = process.env.API_URL ?? "http://localhost:8000";

  // Fetch existing job via the jobs list endpoint and find the matching job
  let defaults: Record<string, unknown> | undefined;
  try {
    const res = await fetch(`${API_URL}/employer/me/jobs`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json();
      const job = (data.jobs ?? []).find(
        (j: { job_id: string }) => j.job_id === jobId
      );
      if (job) {
        defaults = {
          title_raw: job.title,
          city: job.city,
          state: job.state,
          work_setting: job.work_setting,
          is_active: job.is_active,
        };
      }
    }
  } catch {
    // Non-fatal — form will render without pre-filled values
  }

  async function handleUpdate(formData: FormData) {
    "use server";

    const supabase = await createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) redirect("/login");

    const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    const payload: Record<string, unknown> = {};

    const fields: [string, "string" | "number" | "bool"][] = [
      ["title_raw", "string"],
      ["city", "string"],
      ["state", "string"],
      ["work_setting", "string"],
      ["travel_requirement", "string"],
      ["pay_min", "number"],
      ["pay_max", "number"],
      ["pay_type", "string"],
      ["description_raw", "string"],
      ["requirements_raw", "string"],
      ["experience_level", "string"],
    ];

    for (const [field, type] of fields) {
      const raw = formData.get(field);
      if (raw !== null && raw !== "") {
        payload[field] = type === "number" ? Number(raw) : raw;
      }
    }

    const isActiveRaw = formData.get("is_active");
    if (isActiveRaw !== null) {
      payload["is_active"] = isActiveRaw === "true";
    }

    await fetch(`${API_URL}/employer/me/jobs/${jobId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    redirect("/employer");
  }

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <a
            href="/employer"
            className="text-sm text-zinc-500 hover:text-zinc-900 inline-flex items-center gap-1 transition-colors"
          >
            ← Back to dashboard
          </a>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 mt-1">Edit job</h1>
        </div>

        <form action={handleUpdate} className="bg-zinc-50 border border-zinc-200 rounded-lg p-6 space-y-5">
          <JobFormFields defaults={defaults as Parameters<typeof JobFormFields>[0]["defaults"]} />

          {/* Active toggle */}
          <div>
            <label className="block text-sm font-medium text-zinc-600 mb-1">
              Status
            </label>
            <select
              name="is_active"
              defaultValue={defaults?.is_active === false ? "false" : "true"}
              className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
            >
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="px-5 py-2 bg-zinc-900 text-white text-sm font-medium rounded-full hover:bg-zinc-700 transition-colors"
            >
              Save changes
            </button>
            <a
              href="/employer"
              className="px-5 py-2 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
            >
              Cancel
            </a>
          </div>
        </form>
      </div>
    </main>
  );
}
