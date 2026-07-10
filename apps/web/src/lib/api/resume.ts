/**
 * SKILLED Pro — AI profile summary + PDF résumé.
 * Backend: apps/api/app/routers/resume.py
 */
import { apiFetch, API_BASE, ApiError } from "./client";

export interface SummaryOut {
  summary: string | null;
  source?: string | null;     // "ai" | "template" | "manual"
  generated_at?: string | null;
}

export const getSummary = (token: string) =>
  apiFetch<SummaryOut>("/applicant/me/summary", token);

export const generateSummary = (token: string) =>
  apiFetch<SummaryOut>("/applicant/me/summary", token, { method: "POST" });

export const saveSummary = (token: string, summary: string) =>
  apiFetch<SummaryOut>("/applicant/me/summary", token, {
    method: "PUT",
    body: JSON.stringify({ summary }),
  });

/** Fetch the authenticated PDF as a blob and trigger a download. */
export async function downloadResume(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/applicant/me/resume.pdf`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => ""));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "resume_SKILLED.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
