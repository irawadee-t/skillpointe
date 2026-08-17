/**
 * Shared constants for the SkillPointe web app.
 * Program taxonomy derived from SPF Skilled Trades Scholarship data.
 */

export const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
] as const;

// CAREER_PATHS / PROGRAM_FIELDS (the pre-2026 SPF taxonomy) are retired.
// Sector and career-field options now come from taxonomy.generated.ts,
// generated from Tasha's Industry & Career List by scripts/gen_taxonomy.py.

export const ENROLLMENT_STATUSES = [
  { value: "high_school", label: "High School (Senior)" },
  { value: "dual_enrollment", label: "Dual Enrollment (HS + College)" },
  { value: "community_college", label: "Community College / Technical School" },
  { value: "vocational_certificate", label: "Vocational Certificate Program" },
  { value: "apprenticeship", label: "Apprenticeship Program" },
  { value: "bachelors_plus", label: "4-Year College (Bachelor's+)" },
  { value: "not_enrolled", label: "Not currently enrolled" },
  { value: "other", label: "Other" },
] as const;

export const DEGREE_TYPES = [
  { value: "skilled_trades_certificate", label: "Skilled Trades Certificate" },
  { value: "associates", label: "Associate's Degree" },
  { value: "apprenticeship", label: "Apprenticeship" },
  { value: "dual_enrollment", label: "Dual Enrollment" },
  { value: "bachelors", label: "Bachelor's Degree" },
  { value: "other", label: "Other" },
] as const;

export const TRAVEL_OPTIONS = [
  { value: "no_travel", label: "No travel", desc: "I only want to work at a fixed location" },
  { value: "within_metro", label: "Within my metro area", desc: "Up to ~50 miles from home" },
  { value: "within_state", label: "Within my state", desc: "Anywhere in my state" },
  { value: "within_region", label: "Within my region", desc: "Multi-state regional travel" },
  { value: "anywhere", label: "Anywhere in the US", desc: "Open to national travel" },
] as const;

/** Preset commute radii (miles) for "How far will you travel for work?". */
export const COMMUTE_RADIUS_PRESETS = [10, 25, 50, 100] as const;

export const RELOCATION_OPTIONS = [
  { value: "stay_current", label: "Stay in my current area", desc: "I don't want to move" },
  { value: "within_state", label: "Within my state", desc: "Open to moving within my state" },
  { value: "specific_states", label: "Specific states", desc: "I'd move to certain states" },
  { value: "anywhere", label: "Anywhere in the US", desc: "Open to relocating anywhere" },
] as const;

export const WAGE_RANGES = [
  { value: "I am not currently working", label: "Not currently working" },
  { value: "$0-$15/hour", label: "$0–$15/hr" },
  { value: "$16-$30/hour", label: "$16–$30/hr" },
  { value: "$31-$45/hour", label: "$31–$45/hr" },
  { value: "$45+/hour", label: "$45+/hr" },
  { value: "Prefer not to answer", label: "Prefer not to answer" },
] as const;

export const AGE_RANGES = [
  "Under 18", "18-24", "25-34", "35-44", "45-54", "Prefer not to answer",
] as const;

export const GENDER_OPTIONS = [
  "Male", "Female", "Non-Binary", "Other", "Prefer Not to Answer",
] as const;
