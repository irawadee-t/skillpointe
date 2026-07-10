/**
 * SKILLED Foundation impact & outcomes analytics (admin).
 * Backend: apps/api/app/routers/foundation.py
 */
import { apiFetch } from "./client";

export interface Summary {
  total_served: number;
  placed: number;
  employment_rate: number | null;
  median_wage: number | null;
  attainment_rate: number | null;
  median_time_to_hire_days: number | null;
}

export interface Cohort {
  cohort: string;
  n: number;
  placed?: number | null;
  employment_rate: number | null;
  median_wage: number | null;
  attainment_rate: number | null;
  median_time_to_hire_days: number | null;
  suppressed?: boolean | null;
}

export interface ImpactReport {
  narrative: string;
  source: string;
  summary: Summary;
  top_programs: Cohort[];
}

export type GroupBy = "program" | "region" | "cohort_year";

export const getSummary = (token: string) =>
  apiFetch<Summary>("/admin/foundation/summary", token);

export const getCohorts = (token: string, groupBy: GroupBy) =>
  apiFetch<Cohort[]>(`/admin/foundation/outcomes?group_by=${groupBy}`, token);

export const getFeed = (token: string, groupBy: GroupBy, k = 10) =>
  apiFetch<Cohort[]>(`/admin/foundation/feed?group_by=${groupBy}&k=${k}`, token);

export const generateImpactReport = (token: string) =>
  apiFetch<ImpactReport>("/admin/foundation/impact-report", token, { method: "POST" });

export const pct = (x: number | null | undefined) =>
  x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`;
export const money = (x: number | null | undefined) =>
  x === null || x === undefined ? "—" : `$${x.toLocaleString()}`;
