"use client";

/**
 * Client-side new-job form.
 *
 * Uses inline validation (min title length, pay range) via JobFormFields
 * and shows a toast on success before redirecting.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import { JobFormFields } from "./JobFormFields";
import { useToast, Confetti } from "@/components/ui";
import { fireOnce } from "@/lib/milestones";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function NewJobFormClient({ token }: { token: string }) {
  const router = useRouter();
  const toast = useToast();
  const [valid, setValid] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!valid || submitting) return;
    const formData = new FormData(e.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
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
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      // Milestone: first job posted — Confetti + special toast, then still
      // route so the employer lands on their jobs list. Confetti fires while
      // the redirect happens, which is fine because the canvas is fixed-position.
      if (fireOnce("first_job_posted")) {
        setCelebrate(true);
        toast.success("🎉 Your first job is live to matched candidates.");
      } else {
        toast.success("Job posted — visible to matched candidates in a few minutes");
      }
      router.push("/employer");
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not post job";
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
      <Confetti active={celebrate} />
      <JobFormFields onValidChange={setValid} />
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
          {submitting ? "Posting…" : "Create job"}
        </button>
        <a href="/employer" className="btn-secondary">
          Cancel
        </a>
      </div>
    </form>
  );
}
