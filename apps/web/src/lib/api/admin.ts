/**
 * Typed API functions for admin analytics endpoints.
 */
import { apiFetch } from "./client";

export interface CityJobCluster {
  city: string;
  state: string;
  lat: number;
  lon: number;
  count: number;
  families: string[];
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
  engagement: {
    total: number; total_7d: number;
    active_applicants_7d: number; active_employers_7d: number;
    active_applicants_total: number; active_employers_total: number;
    by_type: { type: string; count: number; last_7d: number }[];
  };
  outcomes: { placements: number; median_wage: number | null };
  skilled_id: { partners: number; active: number; queries_total: number; queries_7d: number };
  sync: { outbox_total: number; outbox_unpublished: number; inbox_applied: number };
  funnel: { key: string; label: string; count: number }[];
  alerts: {
    review_queue: number; unmatched_learners: number; jobs_no_candidates: number;
    import_batches_pending: number; import_jobs_pending: number;
    sla_breaches: number;
    verified_not_sharing: number; sync_pending: number;
    review_items_pending: number;
    review_items_by_type: Record<string, number>;
  };
}

/* ── Sidebar pending-work badges — same shared definitions as the pages ── */
export interface PendingCounts {
  imports_awaiting_batches: number;
  imports_awaiting_rows: number;
  credentials_needs_review: number;
  review_items_pending: number;
}

export async function fetchPendingCounts(token: string): Promise<PendingCounts> {
  return apiFetch<PendingCounts>("/admin/ops/pending-counts", token);
}

/* ── /admin/review feed ── */
export interface ReviewItem {
  id: string;
  item_type: string;
  entity_type: string;
  entity_id: string;
  description: string | null;
  flags: unknown;
  confidence_level: string | null;
  priority: number;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolution_action: string | null;
  resolution_notes: string | null;
  link_href: string | null;
}

export interface ReviewFeed {
  items: ReviewItem[];
  total: number;
  limit: number;
  offset: number;
  pending_by_type: Record<string, number>;
  pending_total: number;
}

export async function fetchReviewFeed(
  token: string,
  opts?: { status?: string; itemType?: string; limit?: number; offset?: number },
): Promise<ReviewFeed> {
  const p = new URLSearchParams();
  if (opts?.status) p.set("status_filter", opts.status);
  if (opts?.itemType) p.set("item_type", opts.itemType);
  if (opts?.limit) p.set("limit", String(opts.limit));
  if (opts?.offset) p.set("offset", String(opts.offset));
  const q = p.toString();
  return apiFetch<ReviewFeed>(`/admin/review${q ? `?${q}` : ""}`, token);
}

export async function resolveReviewItem(
  token: string, id: string, action: "reviewed" | "overridden" | "dismissed", note?: string,
): Promise<ReviewItem> {
  return apiFetch<ReviewItem>(`/admin/review/${id}/resolve`, token, {
    method: "POST", body: JSON.stringify({ action, note }),
  });
}

/* ── /admin/audit-logs reader ── */
export interface AuditLogItem {
  id: string;
  actor_id: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  note: string | null;
  metadata: unknown;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLogItem[];
  total: number;
  limit: number;
  offset: number;
  actions: string[];
  entity_types: string[];
}

export async function fetchAuditLogs(
  token: string,
  opts?: {
    action?: string; entityType?: string; actorRole?: string;
    dateFrom?: string; dateTo?: string; limit?: number; offset?: number;
  },
): Promise<AuditLogList> {
  const p = new URLSearchParams();
  if (opts?.action) p.set("action", opts.action);
  if (opts?.entityType) p.set("entity_type", opts.entityType);
  if (opts?.actorRole) p.set("actor_role", opts.actorRole);
  if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
  if (opts?.dateTo) p.set("date_to", opts.dateTo);
  if (opts?.limit) p.set("limit", String(opts.limit));
  if (opts?.offset !== undefined) p.set("offset", String(opts.offset));
  const q = p.toString();
  return apiFetch<AuditLogList>(`/admin/audit-logs${q ? `?${q}` : ""}`, token);
}

/* ── Recompute progress poller (matching activation + dashboard button) ── */
export interface RecomputeStatus {
  run: {
    id: string; kind: string; status: string; error: string | null;
    started_at: string | null; completed_at: string | null;
    elapsed_seconds: number | null;
  } | null;
  matches_total: number;
}

export async function fetchRecomputeStatus(token: string): Promise<RecomputeStatus> {
  return apiFetch<RecomputeStatus>("/admin/matching/recompute-status", token);
}

export async function fetchAdminOverview(token: string): Promise<PlatformOverview> {
  return apiFetch<PlatformOverview>("/admin/analytics/overview", token);
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
  created_at: string | null;
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
  created_at: string | null;
  has_career_source: boolean;
  hired_count: number;
  outreach_count: number;
  last_activity_at: string | null;
}

export interface AdminEmployerFacets {
  industries: string[];
  states: string[];
}

export interface AdminEmployerList {
  total: number;
  employers: AdminEmployerRow[];
  facets: AdminEmployerFacets;
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

// ---------------------------------------------------------------------------
// Admin "view as applicant" debug mode (read-only impersonation)
// ---------------------------------------------------------------------------

export interface ViewAsStartResponse {
  applicant_id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  has_linked_account: boolean;
}

/** Start an audited view-as session — writes ONE audit_logs row per start. */
export async function startViewAsApplicant(
  token: string,
  applicantId: string,
): Promise<ViewAsStartResponse> {
  return apiFetch<ViewAsStartResponse>(`/admin/view-as/${applicantId}/start`, token, {
    method: "POST",
  });
}

export interface AdminEmployerFilters {
  q?: string;
  state?: string;
  states?: string;          // comma-separated multi-select
  industry?: string;        // comma-separated multi-select
  is_partner?: boolean;
  has_active_jobs?: boolean;
  jobs_band?: string;       // none | 1_10 | 11_100 | over_100
  has_hired?: boolean;
  has_outreach?: boolean;
  has_career_source?: boolean;
  created_from?: string;
  created_to?: string;
  sort?: string;            // name | jobs | recent
  page?: number;
}

export async function fetchAdminEmployers(
  token: string,
  params: AdminEmployerFilters = {},
): Promise<AdminEmployerList> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  return apiFetch<AdminEmployerList>(`/admin/employers?${qs}`, token);
}

// ---------------------------------------------------------------------------
// Admin structured-jobs console — GET /admin/jobs
// ---------------------------------------------------------------------------

export interface AdminJobRow {
  id: string;
  title: string;
  employer_id: string | null;
  employer_name: string | null;
  city: string | null;
  state: string | null;
  family_code: string | null;
  family_name: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  pay_raw: string | null;
  employment_type: string | null;
  source: string | null;
  source_site: string | null;
  is_active: boolean;
  is_stale: boolean;
  apply_link_status: string | null;
  accepts_internal_applications: boolean | null;
  posted_date: string | null;
  created_at: string | null;
  candidate_count: number;
}

export interface AdminJobFacets {
  families: { value: string; label: string }[];
  industries: string[];
  states: string[];
  sources: string[];
  source_sites: string[];
  employment_types: string[];
}

export interface AdminJobList {
  total: number;
  page: number;
  page_size: number;
  supports_internal_apply: boolean;
  jobs: AdminJobRow[];
  facets: AdminJobFacets;
}

export interface AdminJobFilters {
  q?: string;
  families?: string;
  industries?: string;
  states?: string;
  city?: string;
  employment_types?: string;
  sources?: string;
  source_sites?: string;
  status?: string;          // active | inactive | stale
  apply_link?: string;      // ok | broken | unchecked
  has_pay?: boolean;
  pay_gte?: number;
  internal_apply?: boolean;
  posted_from?: string;
  posted_to?: string;
  created_from?: string;
  created_to?: string;
  candidates?: string;      // none | 1_9 | 10_49 | over_50
  sort?: string;            // newest | posted | title | pay
  page?: number;
  page_size?: number;
}

export async function fetchAdminJobs(
  token: string,
  params: AdminJobFilters = {},
): Promise<AdminJobList> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  return apiFetch<AdminJobList>(`/admin/jobs?${qs}`, token);
}

export interface CityApplicantCluster {
  city: string;
  state: string;
  lat: number;
  lng: number;
  applicant_count: number;
}

export interface FlowEndpoint {
  lat: number;
  lng: number;
  city: string;
  state: string;
}

export interface ApplicationFlow {
  from: FlowEndpoint;
  to: FlowEndpoint;
  count: number;
}

/**
 * Client-safe fetches for the map view toggle (called lazily from "use client"
 * components when a view is first opened). Use NEXT_PUBLIC_API_URL so they
 * work in the browser.
 */
export async function fetchApplicantMap(token: string): Promise<CityApplicantCluster[]> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/admin/analytics/applicant-map`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch applicant map: ${res.status}`);
  return res.json();
}

export async function fetchApplicationFlows(token: string): Promise<ApplicationFlow[]> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/admin/analytics/application-flows`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch application flows: ${res.status}`);
  return res.json();
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
