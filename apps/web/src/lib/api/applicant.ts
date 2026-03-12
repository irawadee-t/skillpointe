/**
 * Typed API functions for applicant-side endpoints.
 * Mirrors the Pydantic schemas in apps/api/app/schemas/applicant.py.
 */
import { apiFetch } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApplicantProfileSummary {
  applicant_id: string;
  first_name: string | null;
  last_name: string | null;
  program_name_raw: string | null;
  canonical_job_family_code: string | null;
  city: string | null;
  state: string | null;
  region: string | null;
  willing_to_relocate: boolean;
  willing_to_travel: boolean;
  expected_completion_date: string | null;
  available_from_date: string | null;
  profile_completeness: number;
}

export interface JobMatchSummary {
  match_id: string;
  job_id: string;
  job_title: string;
  employer_name: string;
  is_partner_employer: boolean;
  job_city: string | null;
  job_state: string | null;
  job_region: string | null;
  work_setting: string | null;
  travel_requirement: string | null;
  geography_note: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  eligibility_status: "eligible" | "near_fit";
  match_label: "strong_fit" | "good_fit" | "moderate_fit" | "low_fit" | null;
  policy_adjusted_score: number | null;
  top_strengths: string[];
  top_gaps: string[];
  recommended_next_step: string | null;
  confidence_level: "high" | "medium" | "low" | null;
  requires_review: boolean;
}

export interface DimensionScoreItem {
  dimension: string;
  weight: number;
  raw_score: number;
  weighted_score: number;
  rationale: string | null;
  null_handling_applied: boolean;
  null_handling_default: number | null;
}

export interface GateResultItem {
  gate_name: string;
  result: "pass" | "near_fit" | "fail";
  reason: string;
  severity: string | null;
}

export interface PolicyModifierItem {
  policy: string;
  value: number;
  reason: string;
}

export interface JobMatchDetail extends JobMatchSummary {
  base_fit_score: number | null;
  weighted_structured_score: number | null;
  semantic_score: number | null;
  required_missing_items: string[];
  hard_gate_rationale: GateResultItem[];
  policy_modifiers: PolicyModifierItem[];
  dimension_scores: DimensionScoreItem[];
}

export interface RankedMatchesResponse {
  applicant_id: string;
  eligible_matches: JobMatchSummary[];
  total_eligible: number;
  near_fit_matches: JobMatchSummary[];
  total_near_fit: number;
  has_matches: boolean;
  profile_has_family: boolean;
  profile_has_location: boolean;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchMyProfile(
  token: string,
): Promise<ApplicantProfileSummary> {
  return apiFetch<ApplicantProfileSummary>("/applicant/me/profile", token);
}

export async function fetchMyMatches(
  token: string,
): Promise<RankedMatchesResponse> {
  return apiFetch<RankedMatchesResponse>("/applicant/me/matches", token);
}

export async function fetchMatchDetail(
  matchId: string,
  token: string,
): Promise<JobMatchDetail> {
  return apiFetch<JobMatchDetail>(`/applicant/me/matches/${matchId}`, token);
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export function formatMatchLabel(label: string | null): string {
  switch (label) {
    case "strong_fit":    return "Strong fit";
    case "good_fit":      return "Good fit";
    case "moderate_fit":  return "Moderate fit";
    case "low_fit":       return "Low fit";
    default:              return "Not scored";
  }
}

export function formatWorkSetting(ws: string | null): string {
  switch (ws) {
    case "remote":    return "Remote";
    case "hybrid":    return "Hybrid";
    case "on_site":   return "On-site";
    case "flexible":  return "Flexible";
    default:          return ws ?? "—";
  }
}

export function formatPay(
  min: number | null,
  max: number | null,
  type: string | null,
): string {
  if (min === null) return "Pay not listed";
  const suffix = type === "hourly" ? "/hr" : type === "annual" ? "/yr" : "";
  const fmt = (n: number) =>
    type === "annual"
      ? `$${(n / 1000).toFixed(0)}k`
      : `$${n.toFixed(0)}`;
  if (max && max !== min) return `${fmt(min)}–${fmt(max)}${suffix}`;
  return `${fmt(min)}${suffix}`;
}

export function formatDimensionName(dim: string): string {
  return dim
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
