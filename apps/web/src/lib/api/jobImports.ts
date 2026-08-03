/**
 * Employer self-serve job import + admin approval workflow.
 * Backend: apps/api/app/routers/job_imports.py
 */
import { apiFetch } from "./client";
import { formatDateShort } from "@/lib/format";

export interface ImportRow {
  id: string;
  status: "staged" | "excluded" | "published" | "rejected" | "stale" | "held";
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
  link_status?: "ok" | "broken" | "blocked" | null;
  link_checked_at?: string | null;
  posted_date?: string | null;
  first_seen_at?: string | null;   // when this posting first entered the batch
  last_synced_at?: string | null;  // last time a sync touched this row
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
  // Admin-console enrichment (present on /admin/job-imports responses)
  review_state?:
    | "awaiting_review" | "staged_from_careers" | "draft"
    | "approved" | "rejected" | "published" | null;
  from_career_source?: boolean;
  rows_staged?: number;
  rows_held?: number;
}

export interface BatchDetail extends ImportBatch {
  rows: ImportRow[];
  rows_count?: number;
  rows_by_status?: Record<string, number>;
}

export interface AdminBatchList {
  items: ImportBatch[];
  total: number;
  limit: number;
  offset: number;
  // ONE shared awaiting-review definition (backend util.review_queue) —
  // same numbers as the dashboard inbox and career sources.
  awaiting: { batches: number; rows: number };
}

/**
 * Human title for a batch: the filename / page it came from when we have one,
 * else "<Source> import · Aug 2". Counts belong on the meta line, never here.
 */
export function batchDisplayTitle(
  b: Pick<ImportBatch, "source" | "source_label" | "created_at">,
): string {
  const date = formatDateShort(b.created_at);
  const label = b.source_label?.trim() ?? "";
  switch (b.source) {
    case "csv":
      // Legacy labels baked counts into the title ("CSV upload (2 rows, 0 skipped)").
      return !label || /^csv (upload|import)\b/i.test(label)
        ? `CSV import · ${date}`
        : label;
    case "url": {
      try {
        const host = new URL(label).hostname;
        if (host) return `Sync from ${host}`;
      } catch {
        // source_label wasn't a URL — fall through.
      }
      return label || `Careers page sync · ${date}`;
    }
    case "manual":
      return `Manual entry · ${date}`;
    default:
      return label || `Import · ${date}`;
  }
}

// Employer
export const listMyBatches = (token: string) =>
  apiFetch<ImportBatch[]>("/employer/jobs/imports", token);

export const getBatch = (token: string, id: string) =>
  apiFetch<BatchDetail>(`/employer/jobs/imports/${id}`, token);

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

/** Undo an exclude — the row goes back to staged. */
export const restoreRow = (token: string, batchId: string, rowId: string) =>
  apiFetch<{ ok: boolean }>(
    `/employer/jobs/imports/${batchId}/rows/${rowId}/restore`, token, { method: "POST" },
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

// Admin
export const listAdminBatches = (
  token: string, statusFilter = "awaiting", limit = 50, offset = 0,
) =>
  apiFetch<AdminBatchList>(
    `/admin/job-imports?status_filter=${encodeURIComponent(statusFilter)}&limit=${limit}&offset=${offset}`,
    token,
  );

export const getAdminBatch = (token: string, id: string) =>
  apiFetch<BatchDetail>(`/admin/job-imports/${id}`, token);

export type RowDecision = "approve" | "reject" | "hold";

export const approveBatch = (token: string, id: string, note?: string, rowDecisions?: Record<string, RowDecision>) =>
  apiFetch<ImportBatch>(
    `/admin/job-imports/${id}/approve`, token,
    { method: "POST", body: JSON.stringify({ note, row_decisions: rowDecisions }) },
  );

export const rejectBatch = (token: string, id: string, note: string) =>
  apiFetch<ImportBatch>(
    `/admin/job-imports/${id}/reject`, token,
    { method: "POST", body: JSON.stringify({ note }) },
  );
