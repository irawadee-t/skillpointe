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
export async function fetchClusterJobs(city: string, state: string, token: string): Promise<ClusterJob[]> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const url = `${base}/admin/analytics/cluster-jobs?city=${encodeURIComponent(city)}&state=${encodeURIComponent(state)}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch cluster jobs: ${res.status}`);
  return res.json();
}
