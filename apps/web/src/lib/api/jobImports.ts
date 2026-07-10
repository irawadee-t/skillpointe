/**
 * Employer self-serve job import + admin approval workflow.
 * Backend: apps/api/app/routers/job_imports.py
 */
import { apiFetch } from "./client";

export interface ImportRow {
  id: string;
  status: "staged" | "excluded" | "published" | "rejected";
  title_raw: string;
  description_raw?: string | null;
  responsibilities_raw?: string | null;
  requirements_raw?: string | null;
  preferred_qualifications_raw?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string;
  work_setting?: string | null;
  travel_requirement?: string | null;
  pay_min?: number | null;
  pay_max?: number | null;
  pay_type?: string | null;
  pay_raw?: string | null;
  experience_level?: string | null;
  employment_type?: string | null;
  req_id?: string | null;
  source_url?: string | null;
  job_category?: string | null;
}

export interface ImportBatch {
  id: string;
  employer_id: string;
  employer_name?: string | null;
  source: "url" | "csv" | "sheet" | "doc" | "manual";
  source_label?: string | null;
  platform?: string | null;
  status: "draft" | "pending" | "approved" | "rejected" | "published";
  rows_total: number;
  rows_approved: number;
  rows_rejected: number;
  submitted_at?: string | null;
  reviewed_at?: string | null;
  reviewer_note?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface BatchDetail extends ImportBatch {
  rows: ImportRow[];
}

// Employer
export const listMyBatches = (token: string) =>
  apiFetch<ImportBatch[]>("/employer/jobs/imports", token);

export const getBatch = (token: string, id: string) =>
  apiFetch<BatchDetail>(`/employer/jobs/imports/${id}`, token);

export const importFromUrl = (token: string, url: string, maxJobs = 200) =>
  apiFetch<BatchDetail>("/employer/jobs/imports/url", token, {
    method: "POST",
    body: JSON.stringify({ url, max_jobs: maxJobs }),
  });

export const importFromCsv = (token: string, csvText: string, label?: string) =>
  apiFetch<BatchDetail>("/employer/jobs/imports/csv", token, {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText, label }),
  });

export const importManual = (token: string, rows: Partial<ImportRow>[]) =>
  apiFetch<BatchDetail>("/employer/jobs/imports/manual", token, {
    method: "POST",
    body: JSON.stringify(rows),
  });

export const editRow = (token: string, batchId: string, rowId: string, row: Partial<ImportRow>) =>
  apiFetch<{ ok: boolean }>(
    `/employer/jobs/imports/${batchId}/rows/${rowId}`, token,
    { method: "PATCH", body: JSON.stringify(row) },
  );

export const excludeRow = (token: string, batchId: string, rowId: string) =>
  apiFetch<{ ok: boolean }>(
    `/employer/jobs/imports/${batchId}/rows/${rowId}/exclude`, token, { method: "POST" },
  );

export const submitBatch = (token: string, batchId: string, note?: string) =>
  apiFetch<ImportBatch>(
    `/employer/jobs/imports/${batchId}/submit`, token,
    { method: "POST", body: JSON.stringify({ note }) },
  );

export const resyncBatch = (token: string, batchId: string) =>
  apiFetch<BatchDetail>(
    `/employer/jobs/imports/${batchId}/resync`, token,
    { method: "POST" },
  );

export const setAutoSync = (token: string, batchId: string, intervalDays: number | null) =>
  apiFetch<{ ok: boolean; interval_days: number | null }>(
    `/employer/jobs/imports/${batchId}/auto-sync`, token,
    { method: "POST", body: JSON.stringify({ interval_days: intervalDays }) },
  );

// Admin
export const listAdminBatches = (token: string, statusFilter?: string) => {
  const q = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
  return apiFetch<ImportBatch[]>(`/admin/job-imports${q}`, token);
};

export const getAdminBatch = (token: string, id: string) =>
  apiFetch<BatchDetail>(`/admin/job-imports/${id}`, token);

export const approveBatch = (token: string, id: string, note?: string, rowDecisions?: Record<string, "approve" | "reject">) =>
  apiFetch<ImportBatch>(
    `/admin/job-imports/${id}/approve`, token,
    { method: "POST", body: JSON.stringify({ note, row_decisions: rowDecisions }) },
  );

export const rejectBatch = (token: string, id: string, note: string) =>
  apiFetch<ImportBatch>(
    `/admin/job-imports/${id}/reject`, token,
    { method: "POST", body: JSON.stringify({ note }) },
  );

// Notifications
export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body?: string | null;
  link_href?: string | null;
  read: boolean;
  created_at: string;
}

export const adminNotifications = (token: string) =>
  apiFetch<NotificationItem[]>("/admin/job-imports/notifications/admin", token);

export const employerNotifications = (token: string) =>
  apiFetch<NotificationItem[]>("/employer/notifications", token);
