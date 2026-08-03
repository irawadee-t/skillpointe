"use client";

/**
 * Client-side edit-job form — mirrors NewJobFormClient for validation and toast.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import { JobFormFields, type JobFormDefaults } from "../../new/JobFormFields";
import { useToast } from "@/components/ui";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function EditJobFormClient({
  token,
  jobId,
  defaults,
}: {
  token: string;
  jobId: string;
  defaults: JobFormDefaults;
}) {
  const router = useRouter();
  const toast = useToast();
  const [valid, setValid] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!valid || submitting) return;
    const formData = new FormData(e.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
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
      // Internal-apply config — always sent explicitly (checkbox → hidden input).
      const acceptsInternalRaw = formData.get("accepts_internal_applications");
      if (acceptsInternalRaw !== null) {
        payload["accepts_internal_applications"] = acceptsInternalRaw === "true";
        payload["required_profile_fields"] = formData.getAll("required_profile_fields").map(String);
      }
      const res = await fetch(`${API_URL}/employer/me/jobs/${jobId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      toast.success("Job updated");
      router.push("/employer");
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save changes";
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-md border border-border-light bg-white p-8 space-y-6"
    >
      <JobFormFields defaults={defaults} onValidChange={setValid} />

      {/* Active toggle */}
      <div>
        <label className="mb-2 block text-micro font-medium tracking-wide text-slate">
          Status
        </label>
        <select
          name="is_active"
          defaultValue={defaults?.is_active === false ? "false" : "true"}
          className="input-cohere"
        >
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </div>

      {error && (
        <p className="text-body text-error-red" role="alert">
          {error}
        </p>
      )}

      <div className="flex items-center gap-4 pt-2">
        <button
          type="submit"
          disabled={!valid || submitting}
          className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? "Saving…" : "Save changes"}
        </button>
        <a href="/employer" className="btn-secondary">
          Cancel
        </a>
      </div>
    </form>
  );
}
