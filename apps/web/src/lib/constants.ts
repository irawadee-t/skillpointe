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

export const CAREER_PATHS = [
  { value: "Building", label: "Building & Construction" },
  { value: "Energy", label: "Energy" },
  { value: "Healthcare", label: "Healthcare" },
  { value: "Industrial", label: "Industrial" },
  { value: "Manufacturing", label: "Manufacturing" },
  { value: "Transportation", label: "Transportation" },
  { value: "Emerging Technologies", label: "Emerging Technologies" },
  { value: "Other Skilled Trade Career Pathway", label: "Other" },
] as const;

export const PROGRAM_FIELDS: { value: string; label: string; careerPath: string }[] = [
  // Building & Construction
  { value: "Construction - Carpentry", label: "Carpentry", careerPath: "Building" },
  { value: "Construction  - Electrician", label: "Electrician", careerPath: "Building" },
  { value: "Construction  - HVAC Technician", label: "HVAC Technician", careerPath: "Building" },
  { value: "Construction  - Plumbing", label: "Plumbing", careerPath: "Building" },
  { value: "Construction  - Welder", label: "Welder", careerPath: "Building" },
  { value: "Construction  - Pipefitter, Steamfitter", label: "Pipefitter / Steamfitter", careerPath: "Building" },
  { value: "Construction  - Metal Fabricator", label: "Metal Fabricator", careerPath: "Building" },
  { value: "Construction  - Construction Equipment Operator", label: "Construction Equipment Operator", careerPath: "Building" },
  { value: "Construction  - Heavy Equipment Technician", label: "Heavy Equipment Technician", careerPath: "Building" },
  { value: "Construction -  Construction Management", label: "Construction Management", careerPath: "Building" },
  { value: "Construction - Building & Construction Technology", label: "Building & Construction Technology", careerPath: "Building" },
  { value: "Construction - Building Automation/Technology", label: "Building Automation / Technology", careerPath: "Building" },
  { value: "Construction - Architectural Drafter", label: "Architectural Drafter", careerPath: "Building" },
  { value: "Construction - Electrical Engineering", label: "Electrical Engineering", careerPath: "Building" },
  // Energy
  { value: "Energy  - Electrical Lineman", label: "Electrical Lineman", careerPath: "Energy" },
  { value: "Energy  - Solar Energy Technician", label: "Solar Energy Technician", careerPath: "Energy" },
  { value: "Energy  - Wind Turbine Technician", label: "Wind Turbine Technician", careerPath: "Energy" },
  // Healthcare
  { value: "Healthcare  - Medical Assistant", label: "Medical Assistant", careerPath: "Healthcare" },
  { value: "Healthcare  - Dental Assistant", label: "Dental Assistant", careerPath: "Healthcare" },
  { value: "Healthcare  - Dental Hygienist", label: "Dental Hygienist", careerPath: "Healthcare" },
  { value: "Healthcare  - Medical Sonographer", label: "Medical Sonographer", careerPath: "Healthcare" },
  { value: "Healthcare  - Nurse LPN or LVN", label: "Nurse (LPN / LVN)", careerPath: "Healthcare" },
  { value: "Healthcare  - Occupational Therapy Assistant", label: "Occupational Therapy Assistant", careerPath: "Healthcare" },
  { value: "Healthcare  - Physical Therapy Assistant", label: "Physical Therapy Assistant", careerPath: "Healthcare" },
  { value: "Healthcare  - Radiology Tech", label: "Radiology Tech", careerPath: "Healthcare" },
  { value: "Healthcare  - Respiratory Therapist", label: "Respiratory Therapist", careerPath: "Healthcare" },
  // Manufacturing
  { value: "Manufacturing  - Machinist", label: "Machinist", careerPath: "Manufacturing" },
  { value: "Manufacturing  - Industrial Machinery Technician", label: "Industrial Machinery Technician", careerPath: "Manufacturing" },
  { value: "Manufacturing  - Electrical and Electronics Engineering Technician", label: "Electrical / Electronics Engineering Tech", careerPath: "Manufacturing" },
  { value: "Manufacturing  - Electro Mechanical Technician", label: "Electro-Mechanical Technician", careerPath: "Manufacturing" },
  { value: "Manufacturing - Automation Technology", label: "Automation Technology", careerPath: "Manufacturing" },
  { value: "Manufacturing - Mechatronics", label: "Mechatronics", careerPath: "Manufacturing" },
  { value: "Manufacturing - Robotics", label: "Robotics", careerPath: "Manufacturing" },
  // Transportation
  { value: "Transportation  - Auto Technician", label: "Auto Technician", careerPath: "Transportation" },
  { value: "Transportation  - Auto Body Technician", label: "Auto Body Technician", careerPath: "Transportation" },
  { value: "Transportation  - Diesel Technician", label: "Diesel Technician", careerPath: "Transportation" },
  { value: "Transportation  - Aircraft Technician", label: "Aircraft Technician", careerPath: "Transportation" },
  // Other
  { value: "Other", label: "Other (specify below)", careerPath: "Other Skilled Trade Career Pathway" },
];

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
