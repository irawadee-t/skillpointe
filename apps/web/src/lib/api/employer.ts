/**
 * Typed API functions for employer-side endpoints.
 * Mirrors the Pydantic schemas in apps/api/app/schemas/employer.py.
 *
 * Safety: ApplicantMatchSummary exposes only safe fields —
 * no user_id, no email, no admin-only data.
 */
import { apiFetch } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EmployerCompanySummary {
  employer_id: string;
  name: string;
  industry: string | null;
  city: string | null;
  state: string | null;
  is_partner: boolean;
  total_jobs: number;
  active_jobs: number;
}

export interface EmployerJobSummary {
  job_id: string;
  title: string;
  city: string | null;
  state: string | null;
  work_setting: string | null;
  is_active: boolean;
  posted_date: string | null;
  created_at: string;
  total_visible: number;
  eligible_count: number;
  near_fit_count: number;
}

export interface EmployerJobsListResponse {
  employer_id: string;
  company_name: string;
  jobs: EmployerJobSummary[];
  total_jobs: number;
}

export interface ApplicantMatchSummary {
  match_id: string;
  applicant_id: string;
  first_name: string | null;
  last_name: string | null;
  city: string | null;
  state: string | null;
  region: string | null;
  willing_to_relocate: boolean;
  willing_to_travel: boolean;
  program_name_raw: string | null;
  canonical_job_family_code: string | null;
  expected_completion_date: string | null;
  available_from_date: string | null;
  eligibility_status: "eligible" | "near_fit";
  match_label: "strong_fit" | "good_fit" | "moderate_fit" | "low_fit" | null;
  policy_adjusted_score: number | null;
  top_strengths: string[];
  top_gaps: string[];
  recommended_next_step: string | null;
  confidence_level: "high" | "medium" | "low" | null;
  requires_review: boolean;
  geography_note: string | null;
}

export interface RankedApplicantsResponse {
  job_id: string;
  job_title: string;
  employer_name: string;
  total_visible: number;
  eligible_count: number;
  near_fit_count: number;
  applicants: ApplicantMatchSummary[];
  filter_eligibility: string | null;
  filter_min_score: number | null;
  filter_state: string | null;
  filter_willing_to_relocate: boolean | null;
}

export interface JobCreateResponse {
  job_id: string;
  title_raw: string;
  is_active: boolean;
  created_at: string;
}

export interface ApplicantFilters {
  eligibility?: "all" | "eligible" | "near_fit";
  minScore?: number;
  state?: string;
  willingToRelocate?: boolean;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchMyCompany(
  token: string,
): Promise<EmployerCompanySummary> {
  return apiFetch<EmployerCompanySummary>("/employer/me/company", token);
}

export async function fetchMyJobs(
  token: string,
): Promise<EmployerJobsListResponse> {
  return apiFetch<EmployerJobsListResponse>("/employer/me/jobs", token);
}

export async function fetchJobApplicants(
  jobId: string,
  token: string,
  filters?: ApplicantFilters,
): Promise<RankedApplicantsResponse> {
  const params = new URLSearchParams();
  if (filters?.eligibility && filters.eligibility !== "all") {
    params.set("eligibility", filters.eligibility);
  }
  if (filters?.minScore && filters.minScore > 0) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters?.state) {
    params.set("state", filters.state);
  }
  if (filters?.willingToRelocate !== undefined) {
    params.set("willing_to_relocate", String(filters.willingToRelocate));
  }
  const qs = params.toString();
  const path = `/employer/me/jobs/${jobId}/applicants${qs ? `?${qs}` : ""}`;
  return apiFetch<RankedApplicantsResponse>(path, token);
}

export async function createJob(
  payload: {
    title_raw: string;
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
  },
  token: string,
): Promise<JobCreateResponse> {
  return apiFetch<JobCreateResponse>("/employer/me/jobs", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateJob(
  jobId: string,
  payload: Partial<{
    title_raw: string;
    city: string;
    state: string;
    work_setting: string;
    travel_requirement: string;
    pay_min: number;
    pay_max: number;
    pay_type: string;
    description_raw: string;
    requirements_raw: string;
    experience_level: string;
    is_active: boolean;
  }>,
  token: string,
): Promise<JobCreateResponse> {
  return apiFetch<JobCreateResponse>(`/employer/me/jobs/${jobId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export function formatWorkSetting(ws: string | null): string {
  switch (ws) {
    case "remote":   return "Remote";
    case "hybrid":   return "Hybrid";
    case "on_site":  return "On-site";
    case "flexible": return "Flexible";
    default:         return ws ?? "—";
  }
}

export function formatAvailability(
  availableFrom: string | null,
  expectedCompletion: string | null,
): string {
  const date = availableFrom ?? expectedCompletion;
  if (!date) return "Not set";
  try {
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
    });
  } catch {
    return date;
  }
}

export function formatApplicantName(
  first: string | null,
  last: string | null,
): string {
  return [first, last].filter(Boolean).join(" ") || "Anonymous";
}
