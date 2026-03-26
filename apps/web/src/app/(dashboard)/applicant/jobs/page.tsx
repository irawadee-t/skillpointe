import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api/client";
import { JobBrowseClient } from "./JobBrowseClient";

export interface JobBrowseItem {
  job_id: string;
  title: string;
  employer_name: string;
  city: string | null;
  state: string | null;
  work_setting: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  pay_raw: string | null;
  source: string | null;
  source_url: string | null;
  source_site: string | null;
  posted_date: string | null;
  canonical_job_family_code: string | null;
  description_preview: string | null;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  experience_level: string | null;
  employment_type: string | null;
}

export interface JobBrowseResponse {
  jobs: JobBrowseItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function JobBrowsePage({ searchParams }: PageProps) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : "";
  const stateFilter = typeof params.state === "string" ? params.state : "";
  const workSetting =
    typeof params.work_setting === "string" ? params.work_setting : "";
  const employerFilter =
    typeof params.employer === "string" ? params.employer : "";
  const currentPage =
    typeof params.page === "string" ? parseInt(params.page, 10) || 1 : 1;

  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (stateFilter) qs.set("state", stateFilter);
  if (workSetting) qs.set("work_setting", workSetting);
  if (employerFilter) qs.set("employer", employerFilter);
  qs.set("page", String(currentPage));
  qs.set("per_page", "24");

  let data: JobBrowseResponse | null = null;
  let fetchError: string | null = null;
  let employers: string[] = [];

  try {
    data = await apiFetch<JobBrowseResponse>(
      `/jobs/browse?${qs.toString()}`,
      session.access_token,
    );
  } catch (e) {
    fetchError = e instanceof Error ? e.message : "Failed to load jobs";
  }

  try {
    const emp = await apiFetch<{ employers: string[] }>("/jobs/employers", session.access_token);
    employers = emp.employers ?? [];
  } catch {
    // Non-critical — jobs still show, dropdown falls back to empty
  }

  return (
    <JobBrowseClient
      data={data}
      fetchError={fetchError}
      currentPage={currentPage}
      q={q}
      stateFilter={stateFilter}
      workSetting={workSetting}
      employerFilter={employerFilter}
      employers={employers}
    />
  );
}
