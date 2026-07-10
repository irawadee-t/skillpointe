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
  credential?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export function searchVerifiedWorkers(token: string, params: SearchParams = {}): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  if (params.state) qs.set("state", params.state);
  if (params.trade) qs.set("trade", params.trade);
  if (params.credential) qs.set("credential", params.credential);
  if (params.q) qs.set("q", params.q);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const q = qs.toString();
  return apiFetch<SearchResponse>(`/employer/me/verified-workers${q ? `?${q}` : ""}`, token);
}

export function verifyWorker(token: string, applicantId: string): Promise<VerifyResponse> {
  return apiFetch<VerifyResponse>(`/employer/me/verified-workers/${applicantId}`, token);
}
