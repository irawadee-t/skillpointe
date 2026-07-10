/**
 * SKILLED Pro — applicant credentials API.
 * Backend: apps/api/app/routers/credentials.py
 */
import { apiFetch, apiSend } from "./client";

export type VerificationLevel = 0 | 1 | 2;

export interface Credential {
  id: string;
  raw_name: string;
  canonical_code: string | null;
  canonical_name: string | null;
  credential_type: string | null;
  issuer: string | null;
  normalization_confidence: number;
  needs_review: boolean;
  source: string;
  verification_level: VerificationLevel;
  verification_badge: string; // "Self-Reported" | "Institution-Verified" | "SKILLED Verified"
  issued_date: string | null;
  expires_date: string | null;
  document_url: string | null;
  // Partner verification (NCCER / NSC / Credential Engine)
  provider_source?: string | null;
  provider_verified_at?: string | null;
  provider_external_ref?: string | null;
  provider_stubbed?: boolean;
  verification_provider?: string | null;      // What can verify this credential
  ctdl_uri?: string | null;
  authority?: string | null;
}

export interface CredentialInput {
  raw_name: string;
  issuer?: string | null;
  issued_date?: string | null;
  expires_date?: string | null;
  document_url?: string | null;
}

export function listCredentials(token: string): Promise<Credential[]> {
  return apiFetch<Credential[]>("/applicant/me/credentials", token);
}

export function addCredential(token: string, body: CredentialInput): Promise<Credential> {
  return apiFetch<Credential>("/applicant/me/credentials", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteCredential(token: string, id: string): Promise<void> {
  return apiSend(`/applicant/me/credentials/${id}`, token, { method: "DELETE" });
}

export interface DocVerifyResult {
  decision: "verified" | "review" | "rejected";
  score: number;
  name_matched: boolean;
  issuer_matched: boolean;
  document_authentic: boolean;
  reasons: string[];
  new_verification_level: VerificationLevel;
  new_badge: string;
  provider: string;
}

export function verifyDocument(
  token: string,
  id: string,
  documentText: string,
): Promise<DocVerifyResult> {
  return apiFetch<DocVerifyResult>(`/applicant/me/credentials/${id}/verify-document`, token, {
    method: "POST",
    body: JSON.stringify({ document_text: documentText }),
  });
}
