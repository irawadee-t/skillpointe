/**
 * viz2/types.ts — payload contract for GET /viz/matches/{id}/explanation
 * (apps/api/app/routers/viz_analytics.py) plus the shared label vocabulary
 * for the match-explanation pieces.
 *
 * Everything rendered by viz2 components is stored data passed through this
 * contract — the components never invent numbers.
 */
import { apiFetch } from "@/lib/api/client";

/* ── API payload ─────────────────────────────────────────────────────── */

export interface VizGate {
  gate_name: string;
  result: string;
  reason: string;
  severity: string | null;
}

export interface VizDimension {
  dimension: string;
  weight: number;
  raw_score: number;
  weighted_score: number;
  rationale: string | null;
  null_handling_applied: boolean;
}

export interface VizBucket {
  x0: number;
  x1: number;
  eligible: number;
  near_fit: number;
  ineligible: number;
}

export interface VizPoint {
  score: number;
  status: string;
}

export interface VizDistribution {
  n: number;
  mode: "buckets" | "points";
  bucket_width: number;
  buckets: VizBucket[];
  points: VizPoint[];
  median: number | null;
}

export interface VizThresholds {
  strong_fit_min: number;
  good_fit_min: number;
}

export interface VizMatchCore {
  match_id: string;
  job_id: string;
  job_title: string;
  employer_name: string;
  eligibility_status: string;
  match_label: string | null;
  match_tier: string | null;
  tier_reason: string | null;
  policy_adjusted_score: number | null;
  base_fit_score: number | null;
  distance_miles: number | null;
  confidence_level: string | null;
  top_strengths: string[];
  top_gaps: string[];
  required_missing_items: string[];
  recommended_next_step: string | null;
  gates: VizGate[];
}

export interface MatchExplanationData {
  match: VizMatchCore;
  dimensions: VizDimension[];
  thresholds: VizThresholds;
  context_applicant: VizDistribution;
  context_job: VizDistribution;
}

export function fetchMatchExplanation(
  matchId: string,
  token: string,
): Promise<MatchExplanationData> {
  return apiFetch<MatchExplanationData>(
    `/viz/matches/${matchId}/explanation`,
    token,
  );
}

/* ── Shared vocabulary (mirrors admin matching console labels) ───────── */

export const DIMENSION_LABELS: Record<string, string> = {
  trade_program_alignment: "Trade and program alignment",
  geography_alignment: "Geography",
  credential_readiness: "Credential readiness",
  timing_readiness: "Timing readiness",
  experience_internship_alignment: "Experience and internships",
  industry_alignment: "Industry",
  compensation_alignment: "Compensation",
  work_style_signal_alignment: "Work style",
  employer_soft_pref_alignment: "Employer soft preferences",
};

export const GATE_LABELS: Record<string, string> = {
  job_family_compatibility: "Trade family compatibility",
  required_credential_compatibility: "Required credentials",
  readiness_timing_compatibility: "Availability timing",
  geography_feasibility: "Geography feasibility",
  explicit_minimum_requirement_compatibility: "Explicit minimum requirements",
  seniority_compatibility: "Seniority level",
};

/** Which scored dimension each hard gate bears on (for attention accents). */
export const GATE_TO_DIMENSION: Record<string, string> = {
  job_family_compatibility: "trade_program_alignment",
  required_credential_compatibility: "credential_readiness",
  readiness_timing_compatibility: "timing_readiness",
  geography_feasibility: "geography_alignment",
  explicit_minimum_requirement_compatibility: "experience_internship_alignment",
  seniority_compatibility: "experience_internship_alignment",
};

export function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension.replaceAll("_", " ");
}

/** Gates that did not cleanly pass (fail / near_fit / warn). */
export function unpassedGates(gates: VizGate[]): VizGate[] {
  return gates.filter((g) => g.result && g.result !== "pass");
}

/** Dimensions to render in the attention tone: tied to an unpassed gate. */
export function attentionDimensions(gates: VizGate[]): Set<string> {
  const set = new Set<string>();
  for (const g of unpassedGates(gates)) {
    const dim = GATE_TO_DIMENSION[g.gate_name];
    if (dim) set.add(dim);
  }
  return set;
}

/** Sentence-case a stored rationale fragment ("adjacent families: …"). */
export function sentenceCase(text: string): string {
  const t = text.trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

/** Format a score for direct labels — whole points, tabular rendering. */
export function fmtScore(value: number): string {
  return String(Math.round(value));
}

/** Trim trailing zero: 6.5 -> "6.5", 15 -> "15". */
export function fmt1(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}
