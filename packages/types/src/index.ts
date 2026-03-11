// Shared TypeScript types for SkillPointe Match.
// Phase 1 scaffold — types will be defined in Phase 3+.

// ------------------------------------------------
// Roles
// ------------------------------------------------
export type UserRole = "admin" | "applicant" | "employer";

// ------------------------------------------------
// Eligibility
// ------------------------------------------------
export type EligibilityStatus = "eligible" | "near_fit" | "ineligible";

// ------------------------------------------------
// Match output fields (from SCORING_CONFIG.yaml)
// ------------------------------------------------
export interface MatchOutput {
  eligibility_status: EligibilityStatus;
  base_fit_score: number;
  policy_adjusted_score: number;
  match_label: string;
  top_strengths: string[];
  top_gaps: string[];
  required_missing_items: string[];
  recommended_next_step: string;
  confidence_level: "high" | "medium" | "low";
}

// ------------------------------------------------
// Geography
// ------------------------------------------------
export interface ApplicantGeography {
  city?: string;
  state?: string;
  region?: string;
  willing_to_relocate: boolean;
  willing_to_travel: boolean;
  commute_radius_miles?: number;
}

export interface JobGeography {
  city?: string;
  state?: string;
  region?: string;
  work_setting: "remote" | "hybrid" | "on_site";
  travel_requirement?: string;
}
