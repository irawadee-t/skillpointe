/**
 * Employer "Connect careers page" pipeline.
 * Backend: apps/api/app/routers/career_sources.py
 */
import { apiFetch } from "./client";

export interface CareerSource {
  id: string;
  employer_id: string;
  url: string;
  platform?: string | null;
  batch_id?: string | null;
  last_pulled_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  jobs_found: number;
  created_at: string;
  // Learned-profile + auto-sync state
  has_profile: boolean;
  auto_sync_enabled: boolean;
  auto_sync_interval_hours: number;
  next_auto_sync_at?: string | null;
  consecutive_failures: number;
  // Parked for a human: a sync's removal set was too large to apply blind.
  needs_attention: boolean;
  attention_reason?: string | null;
  attention_at?: string | null;
}

export interface AdminCareerSource extends CareerSource {
  employer_name: string;
  jobs_published: number;
  jobs_staged: number;
  jobs_held: number;
  last_links_broken: number;
  last_jobs_rejected: number;
  last_pull_details: PullDetails;
}

export interface AdminCareerSourceList {
  items: AdminCareerSource[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminPullHistory {
  items: CareerSourcePullHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface PullDetailEntry {
  title: string;
  url?: string | null;
}

export interface PullDetails {
  added?: PullDetailEntry[];
  updated?: PullDetailEntry[];
  removed?: PullDetailEntry[];
  held?: PullDetailEntry[];
  restored?: PullDetailEntry[];
  added_more?: number;
  updated_more?: number;
  removed_more?: number;
  unchanged?: number;
  relearned?: boolean;
  note?: string;
  // Removal decision (see career_sources.plan_removals)
  removal_detection?: RemovalDetection;
  listing_complete?: boolean;
  listing_pages?: number;
  removal_hold?: { would_remove: number; live: number };
  removal_note?: string;
}

export type RemovalDetection =
  | "applied"
  | "skipped_incomplete"
  | "held_for_review"
  | "not_applicable";

export interface CareerSourcePull {
  pull_id?: string | null;
  batch_id?: string | null;
  status: string; // ok | error | blocked | no_jobs
  platform?: string | null;
  error?: string | null;
  jobs_found: number;
  jobs_new: number;
  jobs_updated: number;
  jobs_removed: number;
  jobs_rejected: number;
  links_broken: number;
  sync_mode: "full" | "incremental" | "not_modified" | "relearned";
  duration_ms?: number | null;
  fetch_count?: number | null;
  details: PullDetails;
  // Did the pull see the whole listing, and what did it do about removals?
  listing_complete?: boolean | null;
  removal_detection?: RemovalDetection | null;
}

export interface CareerSourcePullHistoryItem extends CareerSourcePull {
  created_at: string;
  triggered_by?: string | null; // null = scheduled auto-sync
}

export const listCareerSources = (token: string) =>
  apiFetch<CareerSource[]>("/employer/me/career-source", token);

export const saveCareerSource = (token: string, url: string) =>
  apiFetch<CareerSource>("/employer/me/career-source", token, {
    method: "POST",
    body: JSON.stringify({ url }),
  });

export const deleteCareerSource = (token: string, sourceId: string) =>
  apiFetch<{ ok: boolean }>(`/employer/me/career-source/${sourceId}`, token, {
    method: "DELETE",
  });

export const updateCareerSourceSettings = (
  token: string,
  sourceId: string,
  settings: { auto_sync_enabled?: boolean; auto_sync_interval_hours?: number },
) =>
  apiFetch<CareerSource>(`/employer/me/career-source/${sourceId}`, token, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });

export const pullCareerSource = (
  token: string,
  sourceId?: string,
  maxJobs = 200,
  mode: "auto" | "full" = "auto",
) =>
  apiFetch<CareerSourcePull>("/employer/me/career-source/pull", token, {
    method: "POST",
    body: JSON.stringify({ source_id: sourceId, max_jobs: maxJobs, mode }),
  });

export const careerSourcePullHistory = (token: string, sourceId?: string) => {
  const q = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : "";
  return apiFetch<CareerSourcePullHistoryItem[]>(
    `/employer/me/career-source/pulls${q}`,
    token,
  );
};

// Admin console (paginated envelopes — real totals, no silent truncation)
export const adminListCareerSources = (token: string, limit = 100, offset = 0) =>
  apiFetch<AdminCareerSourceList>(
    `/admin/career-sources?limit=${limit}&offset=${offset}`, token,
  );

export const adminCareerSourcePulls = (token: string, sourceId: string, limit = 50, offset = 0) =>
  apiFetch<AdminPullHistory>(
    `/admin/career-sources/${sourceId}/pulls?limit=${limit}&offset=${offset}`,
    token,
  );

export const adminPullCareerSource = (token: string, sourceId: string) =>
  apiFetch<CareerSourcePull>(`/admin/career-sources/${sourceId}/pull`, token, {
    method: "POST",
  });
