/**
 * Edit job — Phase 6.2
 *
 * Fetches existing job data and pre-fills the form.
 * Server component with a server action that PATCHes /employer/me/jobs/{id}.
 */
import { notFound, redirect } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { JobFormFields } from "../new/page";

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

    const API_URL = process.env.API_URL ?? "http://localhost:8000";

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
    <main className="min-h-screen bg-gray-50 p-6 md:p-8">
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <a
            href="/employer"
            className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1"
          >
            ← Back to dashboard
          </a>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">Edit job</h1>
        </div>

        <form action={handleUpdate} className="bg-white border border-gray-200 rounded-lg p-6 space-y-5">
          <JobFormFields defaults={defaults as Parameters<typeof JobFormFields>[0]["defaults"]} />

          {/* Active toggle */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Status
            </label>
            <select
              name="is_active"
              defaultValue={defaults?.is_active === false ? "false" : "true"}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
            >
              Save changes
            </button>
            <a
              href="/employer"
              className="px-5 py-2 text-sm text-gray-600 hover:text-gray-800"
            >
              Cancel
            </a>
          </div>
        </form>
      </div>
    </main>
  );
}
