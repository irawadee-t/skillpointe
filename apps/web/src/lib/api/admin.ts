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
