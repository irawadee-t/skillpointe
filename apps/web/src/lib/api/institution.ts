/**
 * Institution partner portal (self-serve).
 * Backend: apps/api/app/routers/institution.py
 */
import { apiFetch } from "./client";
import type { IngestSummary } from "./ingest";

export interface Institution {
  id: string;
  name: string;
  slug: string | null;
  credentials_issued: number;
  learners: number;
}

export interface RosterRow {
  applicant_name: string;
  credential_name: string;
  verification_badge: string;
  issued_date: string | null;
}

export interface ImportRun {
  id: string;
  row_count: number;
  success_count: number;
  error_count: number;
  status: string;
  created_at: string;
}

export const getInstitution = (token: string) =>
  apiFetch<Institution>("/institution/me", token);

export const getRoster = (token: string) =>
  apiFetch<RosterRow[]>("/institution/me/roster", token);

export const getImports = (token: string) =>
  apiFetch<ImportRun[]>("/institution/me/imports", token);

export const uploadCompletions = (token: string, csvText: string, dryRun: boolean) =>
  apiFetch<IngestSummary>("/institution/me/ingest", token, {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText, dry_run: dryRun }),
  });
