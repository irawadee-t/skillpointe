/**
 * Client for the robustness-pack backend:
 *   - Resume upload + parse
 *   - Notification preferences
 *   - Training-pathway recs
 */
import { API_BASE, apiFetch } from "./client";

// ---------------------------------------------------------------------------
// Resume upload
// ---------------------------------------------------------------------------

export interface ParsedResume {
  upload_id: string;
  filename: string;
  fields: {
    first_name?: string;
    last_name?: string;
    phone?: string;
    email?: string;
    city?: string;
    state?: string;
    program_name_raw?: string;
    career_goals_raw?: string;
    experience_raw?: string;
    bio_raw?: string;
    years_experience?: number;
  };
  certifications: string[];
  skills: string[];
  raw_text_preview: string;
}

export async function parseResume(token: string, file: File): Promise<ParsedResume> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/applicant/me/resume/parse`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
    cache: "no-store",
  });
  if (!res.ok) throw new Error((await res.text()) || "Could not parse resume");
  return res.json();
}

export const applyResume = (token: string, uploadId: string, accept: Record<string, unknown>) =>
  apiFetch<{ ok: boolean; applied: string[] }>("/applicant/me/resume/apply", token, {
    method: "POST",
    body: JSON.stringify({ upload_id: uploadId, accept }),
  });

export interface ResumeUpload {
  id: string;
  filename: string;
  created_at: string;
  applied_at: string | null;
}

/** Prior resume uploads, newest first — backend: GET /applicant/me/resume/uploads. */
export const listResumeUploads = (token: string) =>
  apiFetch<ResumeUpload[]>("/applicant/me/resume/uploads", token);

// ---------------------------------------------------------------------------
// Preferences
// ---------------------------------------------------------------------------

export interface Preferences {
  email_opt_in: boolean;
  sms_opt_in: boolean;
  preferred_locale: "en" | "es";
}

export const getPreferences = (token: string) =>
  apiFetch<Preferences>("/me/preferences", token);

export const patchPreferences = (token: string, patch: Partial<Preferences>) =>
  apiFetch<Preferences>("/me/preferences", token, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

// ---------------------------------------------------------------------------
// Training
// ---------------------------------------------------------------------------

export interface TrainingProgram {
  id: string;
  name: string;
  credential_key: string;
  provider_name: string;
  provider_url?: string | null;
  duration_weeks?: number | null;
  cost_range?: string | null;
  format?: string | null;
  city?: string | null;
  state?: string | null;
  url?: string | null;
  description?: string | null;
}

export interface MatchTraining {
  match_id: string;
  missing_credentials: string[];
  recommendations: TrainingProgram[];
}

export const trainingForMatch = (token: string, matchId: string) =>
  apiFetch<MatchTraining>(`/applicant/me/matches/${matchId}/training`, token);

// ---------------------------------------------------------------------------
// Commute / drive-time
// ---------------------------------------------------------------------------

export interface Commute {
  minutes: number | null;
  provider: string;                    // google | mapbox | haversine | cached | unknown
  from_label?: string | null;
  to_label?: string | null;
  unavailable_reason?: string | null;
  /** Geodesic miles home → job city — same number the radius gate uses. */
  distance_miles?: number | null;
}

export const commuteForMatch = (token: string, matchId: string) =>
  apiFetch<Commute>(`/applicant/me/matches/${matchId}/commute`, token);

// ---------------------------------------------------------------------------
// Credential verification (NCCER / NSC / Credential Engine)
// ---------------------------------------------------------------------------

export interface VerifyPayload {
  card_number?: string;
  first_name?: string;
  last_name?: string;
  dob?: string;
  school_code?: string;
}

export interface VerifyResult {
  ok: boolean;
  provider: "nccer" | "nsc" | "credential_engine" | string;
  status: "verified" | "not_found" | "expired" | "revoked" | "error" | "stub";
  stubbed: boolean;
  external_ref?: string | null;
  credential?: string | null;
  verified_name?: string | null;
  message?: string | null;
}

export const verifyCredential = (token: string, credentialId: string, payload: VerifyPayload) =>
  apiFetch<VerifyResult>(`/applicant/me/credentials/${credentialId}/verify`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
