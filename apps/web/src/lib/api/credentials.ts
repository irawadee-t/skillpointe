/**
 * SKILLED Pro — applicant credentials API.
 * Backend: apps/api/app/routers/credentials.py
 */
import { API_BASE, ApiError, apiFetch, apiSend } from "./client";

export type VerificationLevel = 0 | 1 | 2;

/**
 * Structured credential categories — mirrors the backend taxonomy
 * (CredentialType in apps/api/app/skilled_pro/taxonomy.py), grounded in the
 * Credential Engine CTDL credential-type vocabulary.
 */
export type CredentialCategory =
  | "certification"
  | "license"
  | "degree"
  | "apprenticeship"
  | "safety"
  | "union"
  | "other";

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
  credential_ref?: string | null;
  credential_url?: string | null;
  // Partner verification (NCCER / NSC / Credential Engine)
  provider_source?: string | null;
  provider_verified_at?: string | null;
  provider_external_ref?: string | null;
  provider_stubbed?: boolean;
  verification_provider?: string | null;      // What can verify this credential
  ctdl_uri?: string | null;
  authority?: string | null;
  validity_note?: string | null;              // Typical validity/renewal cadence
  verify_url?: string | null;                 // Public issuer registry lookup
  /** TRUE while a document/badge verification waits in the admin review lane.
   *  Cleared when admin confirms (verified) or dismisses (back to
   *  self-reported, with a notification). */
  verification_review_pending?: boolean;
}

/**
 * Canonical registry suggestion for the add-credential type-ahead.
 * Backend: GET /credentials/taxonomy/suggest (deterministic, in-memory).
 */
export interface CredentialSuggestion {
  slug: string;
  name: string;
  category: CredentialCategory;
  issuer: string | null;
  validity_note: string | null;
  verify_url: string | null;
}

export function suggestCredentials(
  token: string,
  q: string,
  signal?: AbortSignal,
): Promise<CredentialSuggestion[]> {
  return apiFetch<CredentialSuggestion[]>(
    `/credentials/taxonomy/suggest?q=${encodeURIComponent(q)}`,
    token,
    { signal },
  );
}

// --- Admin: canonical-vs-raw normalization console --------------------------
// Backend: apps/api/app/routers/credential_taxonomy.py

export interface NormalizationRow {
  id: string;
  applicant_id: string;
  applicant_name: string | null;
  raw_name: string;
  canonical_code: string | null;
  canonical_name: string | null;
  credential_type: string | null;
  issuer: string | null;
  normalization_confidence: number;
  needs_review: boolean;
  source: string;
  verification_level: VerificationLevel;
  // How the mapper decided + why the row was flagged (server-computed).
  match_method: "exact" | "alias" | "token" | "fuzzy" | "none";
  match_reason: string;
  // Identical raw strings collapse into one fix-once row.
  group_key: string;
  group_count: number;
  group_ids: string[];
}

export interface NormalizationList {
  items: NormalizationRow[];
  total: number;             // total distinct raw strings ("Showing N of M")
  total_credentials: number; // total underlying credential rows
  limit: number;
  offset: number;
}

export function adminListNormalization(
  token: string,
  only: "review" | "unmatched" | "all" = "review",
  limit = 100,
  offset = 0,
): Promise<NormalizationList> {
  return apiFetch<NormalizationList>(
    `/admin/credentials/normalization?only=${only}&limit=${limit}&offset=${offset}`,
    token,
  );
}

export function adminFixCanonical(
  token: string,
  credentialId: string,
  slug: string | null,
  note?: string,
  applyToSameRaw = false,
): Promise<NormalizationRow> {
  return apiFetch<NormalizationRow>(
    `/admin/credentials/${credentialId}/canonical`,
    token,
    {
      method: "PATCH",
      body: JSON.stringify({
        slug, note: note ?? null, apply_to_same_raw: applyToSameRaw,
      }),
    },
  );
}

export interface CredentialInput {
  raw_name: string;
  category?: CredentialCategory | null;
  issuer?: string | null;
  issued_date?: string | null;
  expires_date?: string | null;
  document_url?: string | null;
  credential_ref?: string | null;
  credential_url?: string | null;
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

// --- Document upload (file + QR phone handoff) ------------------------------
// Backend: apps/api/app/routers/credential_uploads.py

export interface DocUploadResult {
  status: "accepted" | "needs_review";
  decision: string;
  score: number;
  reasons: string[];
  new_verification_level: VerificationLevel;
  new_badge: string;
  provider: string;
  detail: string;
}

/** Multipart upload — bypasses apiFetch because it must NOT set a JSON content type. */
export async function uploadCredentialDocument(
  token: string,
  id: string,
  file: File,
): Promise<DocUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/applicant/me/credentials/${id}/verify/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<DocUploadResult>;
}

export interface PhoneLink {
  url: string;
  expires_at: string;
}

export interface PhoneStatus {
  landed: boolean;
  verification_level: VerificationLevel;
  badge: string;
  needs_review: boolean;
}

export function createPhoneLink(token: string, id: string): Promise<PhoneLink> {
  return apiFetch<PhoneLink>(`/applicant/me/credentials/${id}/verify/phone-link`, token, {
    method: "POST",
  });
}

export function getPhoneStatus(token: string, id: string): Promise<PhoneStatus> {
  return apiFetch<PhoneStatus>(`/applicant/me/credentials/${id}/verify/phone-status`, token);
}

// --- Digital badge (Credly / Open Badges) ---------------------------------

export interface BadgeVerifyResult {
  verified: boolean;
  provider: string;
  issuer: string | null;
  badge_name: string | null;
  earner_name: string | null;
  name_matched: boolean;
  new_verification_level: VerificationLevel;
  new_badge: string;
  detail: string;
}

export function verifyBadge(
  token: string,
  id: string,
  badgeUrl: string,
): Promise<BadgeVerifyResult> {
  return apiFetch<BadgeVerifyResult>(`/applicant/me/credentials/${id}/verify-badge`, token, {
    method: "POST",
    body: JSON.stringify({ badge_url: badgeUrl }),
  });
}

// --- Checkr background / license verification ------------------------------

/**
 * Which optional verification methods this environment actually supports.
 * Backend: GET /applicant/me/credentials/verify-config — `checkr_enabled` is
 * true only when a real Checkr API key is configured, so the verify panel can
 * hide the background-check method instead of offering a dead end.
 */
export interface VerifyConfig {
  checkr_enabled: boolean;
}

export function getVerifyConfig(token: string): Promise<VerifyConfig> {
  return apiFetch<VerifyConfig>("/applicant/me/credentials/verify-config", token);
}

export interface CheckrInvite {
  status: string;
  /** Null when simulated — never open an external URL in that case. */
  invitation_url: string | null;
  package: string;
  simulated: boolean;
}

export function createCheckrInvite(token: string, id: string): Promise<CheckrInvite> {
  return apiFetch<CheckrInvite>(`/applicant/me/credentials/${id}/checkr/invite`, token, {
    method: "POST",
  });
}
