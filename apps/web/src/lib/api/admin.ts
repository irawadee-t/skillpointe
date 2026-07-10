/**
 * Typed API functions for admin analytics endpoints.
 */
import { apiFetch } from "./client";

export interface OverviewStats {
  total_applicants: number;
  total_active_jobs: number;
  total_employers: number;
  total_matches: number;
  eligible_matches: number;
  near_fit_matches: number;
  ineligible_matches: number;
}

export interface JobFamilyCount {
  family_code: string;
  family_name: string;
  count: number;
}

export interface SourceCount {
  source_site: string;
  count: number;
}

export interface StateCount {
  state: string;
  count: number;
}

export interface CityJobCluster {
  city: string;
  state: string;
  lat: number;
  lon: number;
  count: number;
  families: string[];
}

export interface MatchQualityBucket {
  label: string;
  count: number;
}

export interface ExperienceLevelCount {
  level: string;
  count: number;
}

export interface DataQualityMetric {
  metric: string;
  value: number;
  total: number;
  pct: number;
}

export interface AdminDashboard {
  overview: OverviewStats;
  jobs_by_family: JobFamilyCount[];
  jobs_by_source: SourceCount[];
  jobs_by_state: StateCount[];
  job_clusters: CityJobCluster[];
  match_quality: MatchQualityBucket[];
  experience_levels: ExperienceLevelCount[];
  data_quality: DataQualityMetric[];
}

export interface ClusterJob {
  id: string;
  title: string;
  employer: string;
  family_code: string | null;
  experience_level: string | null;
  source_url: string | null;
}

export interface PlatformOverview {
  platform: { users: number; applicants: number; employers: number; institutions: number; partners: number };
  acquisition: {
    new_applicants_7d: number; new_applicants_30d: number;
    new_jobs_7d: number; new_jobs_30d: number;
    new_credentials_7d: number; new_credentials_30d: number;
  };
  verification: {
    credentials_total: number; self_reported: number; institution_verified: number;
    skilled_verified: number; verified_rate: number; needs_review: number;
  };
  consent: { sharing_with_employers: number; total_with_settings: number };
  matching: {
    total: number; eligible: number; near_fit: number; ineligible: number;
    avg_fit: number; strong: number; applicants_matched: number;
  };
  marketplace: { active_jobs: number; discoverable_workers: number; top_trades: { name: string; count: number }[] };
  engagement: { total: number; total_7d: number; by_type: { type: string; count: number; last_7d: number }[] };
  outcomes: { placements: number; median_wage: number | null };
  skilled_id: { partners: number; active: number; queries_total: number; queries_7d: number };
  sync: { outbox_total: number; outbox_unpublished: number; inbox_applied: number };
  funnel: { key: string; label: string; count: number }[];
  alerts: {
    review_queue: number; unmatched_learners: number; jobs_no_candidates: number;
    verified_not_sharing: number; sync_pending: number;
  };
}

export async function fetchAdminOverview(token: string): Promise<PlatformOverview> {
  return apiFetch<PlatformOverview>("/admin/analytics/overview", token);
}

export async function fetchAdminDashboard(token: string): Promise<AdminDashboard> {
  return apiFetch<AdminDashboard>("/admin/analytics/dashboard", token);
}

export async function fetchJobMapData(token: string): Promise<CityJobCluster[]> {
  return apiFetch<CityJobCluster[]>("/admin/analytics/job-map", token);
}

/**
 * Client-safe fetch for cluster job drill-down (called from "use client" components).
 * Uses NEXT_PUBLIC_API_URL so it works in the browser.
 */
export interface AdminApplicantRow {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  city: string | null;
  state: string | null;
  program_name_raw: string | null;
  job_family_code: string | null;
  job_family_name: string | null;
  available_from: string | null;
  profile_completeness: number;
  willing_to_relocate: boolean;
  eligible_count: number;
  near_fit_count: number;
}

export interface AdminApplicantList {
  total: number;
  applicants: AdminApplicantRow[];
}

export interface AdminEmployerRow {
  id: string;
  name: string;
  industry: string | null;
  city: string | null;
  state: string | null;
  is_partner: boolean;
  total_jobs: number;
  active_jobs: number;
  contact_email: string | null;
  contact_name: string | null;
}

export interface AdminEmployerList {
  total: number;
  employers: AdminEmployerRow[];
}

export interface AdminEmployerJobRow {
  id: string;
  title: string;
  city: string | null;
  state: string | null;
  work_setting: string | null;
  experience_level: string | null;
  is_active: boolean;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  source_url: string | null;
  eligible_count: number;
  near_fit_count: number;
  total_visible: number;
}

export interface AdminEmployerDetail {
  id: string;
  name: string;
  industry: string | null;
  description: string | null;
  website: string | null;
  city: string | null;
  state: string | null;
  is_partner: boolean;
  partner_since: string | null;
  contact_email: string | null;
  total_jobs: number;
  active_jobs: number;
  jobs: AdminEmployerJobRow[];
}

export async function fetchAdminEmployerDetail(
  employerId: string,
  token: string,
): Promise<AdminEmployerDetail> {
  return apiFetch<AdminEmployerDetail>(`/admin/employers/${employerId}`, token);
}

export async function fetchAdminApplicants(
  token: string,
  params: { q?: string; state?: string; job_family?: string; page?: number } = {},
): Promise<AdminApplicantList> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.state) qs.set("state", params.state);
  if (params.job_family) qs.set("job_family", params.job_family);
  if (params.page) qs.set("page", String(params.page));
  return apiFetch<AdminApplicantList>(`/admin/applicants?${qs}`, token);
}

export async function fetchAdminEmployers(
  token: string,
  params: { q?: string; state?: string; is_partner?: boolean; page?: number } = {},
): Promise<AdminEmployerList> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.state) qs.set("state", params.state);
  if (params.is_partner !== undefined) qs.set("is_partner", String(params.is_partner));
  if (params.page) qs.set("page", String(params.page));
  return apiFetch<AdminEmployerList>(`/admin/employers?${qs}`, token);
}

export async function fetchClusterJobs(city: string, state: string, token: string): Promise<ClusterJob[]> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const url = `${base}/admin/analytics/cluster-jobs?city=${encodeURIComponent(city)}&state=${encodeURIComponent(state)}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch cluster jobs: ${res.status}`);
  return res.json();
}


// ---------------------------------------------------------------------------
// Test mode: applicant switcher
// ---------------------------------------------------------------------------

export interface TestApplicantListItem {
  id: string;
  first_name: string | null;
  last_name: string | null;
  state: string | null;
  program: string | null;
  family_code: string | null;
  eligible_count: number;
  near_fit_count: number;
}

export interface TestApplicantProfile {
  applicant_id: string;
  first_name: string | null;
  last_name: string | null;
  program: string | null;
  family_code: string | null;
  city: string | null;
  state: string | null;
  region: string | null;
  expected_completion_date: string | null;
  travel_preference: string | null;
  relocation_preference: string | null;
}

export interface TestMatchSummary {
  match_id: string;
  job_id: string;
  job_title: string;
  employer_name: string;
  job_city: string | null;
  job_state: string | null;
  work_setting: string | null;
  eligibility_status: string;
  match_label: string | null;
  policy_adjusted_score: number | null;
  top_strengths: string[];
  top_gaps: string[];
  recommended_next_step: string | null;
  source_url: string | null;
  family_code: string | null;
  description_raw: string | null;
  requirements_raw: string | null;
  experience_level: string | null;
  confidence_level: string | null;
}

export interface TestApplicantMatches {
  profile: TestApplicantProfile;
  eligible_matches: TestMatchSummary[];
  near_fit_matches: TestMatchSummary[];
  total_eligible: number;
  total_near_fit: number;
}

export async function fetchTestApplicants(token: string): Promise<TestApplicantListItem[]> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/admin/test/applicants`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch test applicants: ${res.status}`);
  return res.json();
}

export async function fetchTestApplicantMatches(
  applicantId: string,
  token: string,
): Promise<TestApplicantMatches> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/admin/test/applicants/${applicantId}/matches`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch test matches: ${res.status}`);
  return res.json();
}
