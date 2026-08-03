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
  accepts_internal_applications_default: boolean;
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
  family_code: string | null;
  family_name: string | null;
  employment_type: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  pay_raw: string | null;
  source: string | null;
  source_site: string | null;
  is_stale: boolean;
  apply_link_status: string | null;
  /** Lifecycle: active | paused | filled | closed (is_active ⇔ 'active'). */
  status: JobLifecycleStatus;
  previous_status: JobLifecycleStatus | null;
  /** True when the job has applications/interest/outreach/hire history —
   *  Delete is refused (Close is the honest action). */
  has_activity: boolean;
  /** Career-source freshness (source-synced jobs only). */
  source_last_seen_at: string | null;
  source_vanished_at: string | null;
}

export type JobLifecycleStatus = "active" | "paused" | "filled" | "closed";

export interface JobStatusOut {
  job_id: string;
  status: JobLifecycleStatus;
  previous_status: JobLifecycleStatus | null;
  is_active: boolean;
}

export interface EmployerJobFacets {
  families: { value: string; label: string }[];
  states: string[];
  sources: string[];
  employment_types: string[];
}

export interface EmployerJobsListResponse {
  employer_id: string;
  company_name: string;
  jobs: EmployerJobSummary[];
  total_jobs: number;
  unfiltered_total: number | null;
  supports_internal_apply: boolean;
  facets: EmployerJobFacets;
}

export interface EmployerJobFilters {
  q?: string;
  families?: string;
  states?: string;
  city?: string;
  employment_types?: string;
  sources?: string;
  status?: string;          // active | inactive | stale
  apply_link?: string;      // ok | broken | unchecked
  has_pay?: boolean;
  pay_gte?: number;
  internal_apply?: boolean;
  posted_from?: string;
  posted_to?: string;
  candidates?: string;      // none | 1_9 | 10_49 | over_50
  sort?: string;            // newest | posted | title | pay
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
  applicant_interest: "interested" | "applied" | "not_interested" | null;
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
  /** Pagination over the FILTERED list. */
  filtered_total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface ApplicantFilters {
  eligibility?: "all" | "eligible" | "near_fit";
  minScore?: number;
  state?: string;
  willingToRelocate?: boolean;
  /** Partial, case-insensitive name search — narrows live as the user types. */
  q?: string;
  /** 1-based page over the filtered list. */
  page?: number;
  perPage?: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchMyCompany(
  token: string,
): Promise<EmployerCompanySummary> {
  return apiFetch<EmployerCompanySummary>("/employer/me/company", token);
}

/** Employer-editable company settings (partial update). */
export async function patchMyCompany(
  token: string,
  payload: { accepts_internal_applications_default: boolean },
): Promise<EmployerCompanySummary> {
  return apiFetch<EmployerCompanySummary>("/employer/me/company", token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchMyJobs(
  token: string,
  filters: EmployerJobFilters = {},
): Promise<EmployerJobsListResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  const q = qs.toString();
  return apiFetch<EmployerJobsListResponse>(`/employer/me/jobs${q ? `?${q}` : ""}`, token);
}

/** Move a job through its lifecycle. 409 = illegal transition or a
 *  concurrent change; the caller should refresh. */
export async function patchJobStatus(
  token: string,
  jobId: string,
  status: JobLifecycleStatus,
): Promise<JobStatusOut> {
  return apiFetch<JobStatusOut>(`/employer/me/jobs/${jobId}/status`, token, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

/** REAL undo for the last lifecycle transition (restores previous_status). */
export async function revertJobStatus(
  token: string,
  jobId: string,
): Promise<JobStatusOut> {
  return apiFetch<JobStatusOut>(`/employer/me/jobs/${jobId}/status/revert`, token, {
    method: "POST",
  });
}

/** Delete a zero-activity posting. 409 when it has history — close instead. */
export async function deleteJob(token: string, jobId: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/employer/me/jobs/${jobId}`, token, {
    method: "DELETE",
  });
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
  if (filters?.q) {
    params.set("q", filters.q);
  }
  if (filters?.page && filters.page > 1) {
    params.set("page", String(filters.page));
  }
  if (filters?.perPage) {
    params.set("per_page", String(filters.perPage));
  }
  const qs = params.toString();
  const path = `/employer/me/jobs/${jobId}/applicants${qs ? `?${qs}` : ""}`;
  return apiFetch<RankedApplicantsResponse>(path, token);
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
