/**
 * SKILLED ID Partner Console (admin).
 * Backend: apps/api/app/routers/skilled_id_admin.py
 */
import { apiFetch } from "./client";

export const TIERS = ["free", "standard", "premium", "bulk"] as const;
export const REQUESTER_CATEGORIES = [
  "employer",
  "staffing_agency",
  "job_board",
  "background_check",
  "government",
  "union",
  "other",
] as const;

export interface Partner {
  id: string;
  name: string;
  contact_email: string | null;
  requester_category: string;
  tier: string;
  key_prefix: string;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
  total_requests: number;
  requests_30d: number;
  rate_limit: number;
}

export interface KeyIssued {
  partner: Partner;
  api_key: string;
}

export interface PartnerCreate {
  name: string;
  contact_email?: string | null;
  requester_category?: string;
  tier?: string;
  live?: boolean;
}

export interface PartnerUpdate {
  name?: string;
  contact_email?: string | null;
  requester_category?: string;
  tier?: string;
  active?: boolean;
}

export interface UsagePoint { date: string; count: number; }
export interface EndpointCount { endpoint: string; count: number; }
export interface RecentRequest { endpoint: string; subject_count: number; status_code: number; created_at: string; }
export interface UsageReport {
  total_requests: number;
  total_subjects: number;
  requests_30d: number;
  last_used_at: string | null;
  daily: UsagePoint[];
  by_endpoint: EndpointCount[];
  recent: RecentRequest[];
}

export interface TestCredential {
  canonical_code: string | null;
  canonical_name: string | null;
  credential_type: string | null;
  issuer: string | null;
  verification_level: number;
  verification_badge: string;
  expires_date: string | null;
}
export interface TestResult {
  subject_id: string;
  found: boolean;
  consented: boolean;
  credentials: TestCredential[];
}

export const listPartners = (token: string) =>
  apiFetch<Partner[]>("/admin/skilled-id/clients", token);

export const createPartner = (token: string, body: PartnerCreate) =>
  apiFetch<KeyIssued>("/admin/skilled-id/clients", token, { method: "POST", body: JSON.stringify(body) });

export const rotateKey = (token: string, id: string) =>
  apiFetch<KeyIssued>(`/admin/skilled-id/clients/${id}/rotate`, token, { method: "POST" });

export const updatePartner = (token: string, id: string, body: PartnerUpdate) =>
  apiFetch<Partner>(`/admin/skilled-id/clients/${id}`, token, { method: "PATCH", body: JSON.stringify(body) });

export const getUsage = (token: string, id: string) =>
  apiFetch<UsageReport>(`/admin/skilled-id/clients/${id}/usage`, token);

export const testVerify = (token: string, api_client_id: string, subject_id: string) =>
  apiFetch<TestResult>("/admin/skilled-id/test", token, {
    method: "POST",
    body: JSON.stringify({ api_client_id, subject_id }),
  });

export const REQUESTER_LABELS: Record<string, string> = {
  employer: "Employer",
  staffing_agency: "Staffing agency",
  job_board: "Job board",
  background_check: "Background check",
  government: "Government",
  union: "Union",
  other: "Other",
};
