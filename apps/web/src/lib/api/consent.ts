/**
 * SKILLED Pro — granular consent API (Consent Center).
 * Backend: apps/api/app/routers/consent.py
 */
import { apiFetch } from "./client";

// Mirrors DATA_CATEGORIES + RequesterCategory in the backend.
export const DATA_CATEGORIES = [
  "certifications",
  "employment_history",
  "education",
  "wage_expectations",
  "contact_info",
  "portfolio",
] as const;
export type DataCategory = (typeof DATA_CATEGORIES)[number];

export const REQUESTER_CATEGORIES = [
  "employer",
  "staffing_agency",
  "job_board",
  "background_check",
  "government",
  "union",
] as const;
export type RequesterCategory = (typeof REQUESTER_CATEGORIES)[number];

export interface ConsentSetting {
  data_category: string;
  display: boolean;
  internal_use: boolean;
  external_sharing: string[];
}

export interface ConsentUpdate {
  display: boolean;
  internal_use: boolean;
  external_sharing: string[];
}

export function listConsent(token: string): Promise<ConsentSetting[]> {
  return apiFetch<ConsentSetting[]>("/applicant/me/consent", token);
}

export function updateConsent(
  token: string,
  dataCategory: string,
  body: ConsentUpdate,
): Promise<ConsentSetting> {
  return apiFetch<ConsentSetting>(`/applicant/me/consent/${dataCategory}`, token, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// Human-readable labels.
export const DATA_CATEGORY_LABELS: Record<string, string> = {
  certifications: "Certifications & licenses",
  employment_history: "Employment history",
  education: "Education",
  wage_expectations: "Wage expectations",
  contact_info: "Contact information",
  portfolio: "Portfolio & work samples",
};

export const REQUESTER_LABELS: Record<string, string> = {
  employer: "Employers",
  staffing_agency: "Staffing agencies",
  job_board: "Job boards (Indeed, Glassdoor)",
  background_check: "Background-check firms",
  government: "Government & workforce boards",
  union: "Unions",
};
