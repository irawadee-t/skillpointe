/**
 * SKILLED Pro — employer Verified-Worker Directory + SKILLED Verify.
 * Backend: apps/api/app/routers/verified_workers.py
 */
import { apiFetch } from "./client";

export interface VerifiedCredentialBrief {
  canonical_code: string | null;
  canonical_name: string | null;
  verification_level: number;
  verification_badge: string;
}

export interface WorkerCard {
  applicant_id: string;
  name: string;
  city: string | null;
  state: string | null;
  trade: string | null;
  available_from: string | null;
  willing_to_relocate: boolean;
  verified_count: number;
  relevance: number;
  last_active_days: number | null;
  top_credentials: VerifiedCredentialBrief[];
}

export interface Facet {
  code: string;
  name: string;
}

export interface SearchFacets {
  trades: Facet[];
  credentials: Facet[];
}

export interface SearchResponse {
  total: number;
  page: number;
  page_size: number;
  workers: WorkerCard[];
  facets: SearchFacets;
}

export interface VerifiedCredentialFull {
  canonical_code: string | null;
  canonical_name: string | null;
  credential_type: string | null;
  issuer: string | null;
  verification_level: number;
  verification_badge: string;
  issued_date: string | null;
  expires_date: string | null;
}

export interface VerifyResponse {
  applicant_id: string;
  name: string;
  city: string | null;
  state: string | null;
  trade: string | null;
  verified_count: number;
  credentials: VerifiedCredentialFull[];
}

export interface SearchParams {
  state?: string;
  trade?: string;
  trades?: string;              // comma-separated multi-select
  credential?: string;
  credential_types?: string;    // comma-separated categories
  min_level?: number;           // 1 = institution, 2 = SKILLED
  available_by?: string;        // "now" | YYYY-MM-DD
  relocate?: boolean;
  near_city?: string;
  near_state?: string;
  active_within_days?: number;
  q?: string;
  page?: number;
  page_size?: number;
}

export function searchVerifiedWorkers(
  token: string,
  params: SearchParams = {},
  options?: { signal?: AbortSignal },
): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  const q = qs.toString();
  return apiFetch<SearchResponse>(
    `/employer/me/verified-workers${q ? `?${q}` : ""}`,
    token,
    options?.signal ? { signal: options.signal } : undefined,
  );
}

export function verifyWorker(token: string, applicantId: string): Promise<VerifyResponse> {
  return apiFetch<VerifyResponse>(`/employer/me/verified-workers/${applicantId}`, token);
}
