/**
 * API client for the transaction stack:
 *   - Applications (apply + screening + pipeline)
 *   - Interviews (availability + proposals + accept/decline)
 *   - Notifications (list + read)
 *   - Account recovery (email/phone/SKILLED ID)
 *   - SLA (admin dormant applications)
 */
import { apiFetch } from "./client";

// ---------------------------------------------------------------------------
// Screening + Applications
// ---------------------------------------------------------------------------

export interface ScreeningQuestion {
  id?: string;
  position: number;
  kind: "yes_no" | "multiple_choice" | "short_text";
  prompt: string;
  options: string[];
  required_answer?: string | null;
  is_knockout: boolean;
}

export interface ScreeningAnswer {
  question_id: string;
  answer: string;
}

export interface Application {
  id: string;
  job_id: string;
  job_title: string;
  employer_id: string;
  employer_name?: string | null;
  applicant_id: string;
  applicant_name?: string | null;
  status: "submitted" | "reviewed" | "shortlisted" | "interviewing" | "offered" | "hired" | "rejected" | "withdrawn";
  knockout_failed: boolean;
  cover_note?: string | null;
  submitted_at: string;
  employer_viewed_at?: string | null;
  reviewed_at?: string | null;
  decision_at?: string | null;
  days_since_submitted: number;
  resume_snapshot: Record<string, unknown>;
  screening_answers: Array<{ question_id: string; prompt: string; answer: string; knockout_pass: boolean }>;
}

export const getScreeningForJob = (token: string, jobId: string) =>
  apiFetch<ScreeningQuestion[]>(`/applicant/me/jobs/${jobId}/screening`, token);

export const applyToJob = (token: string, jobId: string, payload: { answers: ScreeningAnswer[]; cover_note?: string }) =>
  apiFetch<Application>(`/applicant/me/jobs/${jobId}/apply`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listMyApplications = (token: string) =>
  apiFetch<Application[]>("/applicant/me/applications", token);

export const getMyApplication = (token: string, id: string) =>
  apiFetch<Application>(`/applicant/me/applications/${id}`, token);

export const withdrawApplication = (token: string, id: string) =>
  apiFetch<Application>(`/applicant/me/applications/${id}/withdraw`, token, { method: "POST" });

// Employer
export const listEmployerApplications = (token: string, status?: string) => {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<Application[]>(`/employer/me/applications${q}`, token);
};

export const getEmployerApplication = (token: string, id: string) =>
  apiFetch<Application>(`/employer/me/applications/${id}`, token);

export const patchEmployerApplication = (token: string, id: string, payload: { status?: string; decision_note?: string }) =>
  apiFetch<Application>(`/employer/me/applications/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const getEmployerScreening = (token: string, jobId: string) =>
  apiFetch<ScreeningQuestion[]>(`/employer/me/jobs/${jobId}/screening`, token);

export const replaceEmployerScreening = (token: string, jobId: string, questions: ScreeningQuestion[]) =>
  apiFetch<ScreeningQuestion[]>(`/employer/me/jobs/${jobId}/screening`, token, {
    method: "PUT",
    body: JSON.stringify({ questions }),
  });

// ---------------------------------------------------------------------------
// Interviews
// ---------------------------------------------------------------------------

export interface AvailabilityWindow {
  weekday: number;         // 0..6, Sun=0
  start_time: string;      // "09:00"
  end_time: string;        // "17:00"
  timezone: string;
}

export interface InterviewSlot {
  id: string;
  application_id: string;
  start_at: string;
  end_at: string;
  status: "proposed" | "accepted" | "declined" | "cancelled" | "completed";
  location?: string | null;
  meeting_url?: string | null;
  notes?: string | null;
  job_title?: string | null;
  employer_name?: string | null;
  applicant_name?: string | null;
}

export const getMyAvailability = (token: string) =>
  apiFetch<AvailabilityWindow[]>("/employer/me/availability", token);

export const replaceMyAvailability = (token: string, windows: AvailabilityWindow[]) =>
  apiFetch<AvailabilityWindow[]>("/employer/me/availability", token, {
    method: "PUT",
    body: JSON.stringify({ windows }),
  });

export const proposeInterviewSlots = (
  token: string,
  applicationId: string,
  slots: Array<{ start_at: string; end_at: string; location?: string; meeting_url?: string; notes?: string }>,
) =>
  apiFetch<InterviewSlot[]>(`/employer/me/applications/${applicationId}/propose`, token, {
    method: "POST",
    body: JSON.stringify({ slots }),
  });

export const listMyInterviews = (token: string) =>
  apiFetch<InterviewSlot[]>("/applicant/me/interviews", token);

export const acceptInterviewSlot = (token: string, slotId: string) =>
  apiFetch<InterviewSlot>(`/applicant/me/interviews/${slotId}/accept`, token, { method: "POST" });

export const declineInterviewSlot = (token: string, slotId: string) =>
  apiFetch<InterviewSlot>(`/applicant/me/interviews/${slotId}/decline`, token, { method: "POST" });

// ---------------------------------------------------------------------------
// Notification tray
// ---------------------------------------------------------------------------

export interface NotifItem {
  id: string;
  kind: string;
  title: string;
  body?: string | null;
  link_href?: string | null;
  read: boolean;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface NotifSummary {
  unread: number;
  items: NotifItem[];
}

export const getMyNotifications = (token: string, opts?: { limit?: number; onlyUnread?: boolean }) => {
  const q = new URLSearchParams();
  if (opts?.limit) q.set("limit", String(opts.limit));
  if (opts?.onlyUnread) q.set("only_unread", "true");
  const suffix = q.toString() ? `?${q}` : "";
  return apiFetch<NotifSummary>(`/me/notifications${suffix}`, token);
};

export const markNotificationRead = (token: string, id: string) =>
  apiFetch<{ ok: boolean }>(`/me/notifications/${id}/read`, token, { method: "POST" });

export const markAllNotificationsRead = (token: string) =>
  apiFetch<{ ok: boolean }>("/me/notifications/read-all", token, { method: "POST" });

// ---------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------

export interface ChangeRequest {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  expires_at?: string | null;
  masked_target?: string | null;
}

export const requestEmailChange = (token: string, new_email: string) =>
  apiFetch<ChangeRequest>("/me/account/email/change", token, { method: "POST", body: JSON.stringify({ new_email }) });

export const confirmEmailChange = (token: string, code: string) =>
  apiFetch<ChangeRequest>("/me/account/email/confirm", token, { method: "POST", body: JSON.stringify({ token: code }) });

export const requestPhoneChange = (token: string, new_phone: string) =>
  apiFetch<ChangeRequest>("/me/account/phone/change", token, { method: "POST", body: JSON.stringify({ new_phone }) });

export const confirmPhoneChange = (token: string, code: string) =>
  apiFetch<ChangeRequest>("/me/account/phone/confirm", token, { method: "POST", body: JSON.stringify({ token: code }) });

export const startSkilledIdRecovery = (token: string, reason: string) =>
  apiFetch<ChangeRequest>("/me/account/skilled-id/recover", token, { method: "POST", body: JSON.stringify({ reason }) });

// ---------------------------------------------------------------------------
// Admin: SLA
// ---------------------------------------------------------------------------

export interface DormantApplication {
  application_id: string;
  employer_id: string;
  employer_name?: string | null;
  job_id: string;
  job_title: string;
  applicant_name?: string | null;
  submitted_at: string;
  days_dormant: number;
  knockout_failed: boolean;
}

export interface SLASummary {
  dormant_count: number;
  dormant_employers: number;
  threshold_days: number;
  items: DormantApplication[];
}

export const getSLASummary = (token: string) =>
  apiFetch<SLASummary>("/admin/analytics/sla", token);

export const nudgeEmployer = (token: string, applicationId: string, note?: string) =>
  apiFetch<{ ok: boolean }>("/admin/analytics/sla/nudge", token, {
    method: "POST",
    body: JSON.stringify({ application_id: applicationId, note }),
  });

// ---------------------------------------------------------------------------
// Public employer profile
// ---------------------------------------------------------------------------

export interface EmployerPublicJob {
  id: string;
  title: string;
  city?: string | null;
  state?: string | null;
  work_setting?: string | null;
}

export interface EmployerPublic {
  id: string;
  name: string;
  industry?: string | null;
  website?: string | null;
  city?: string | null;
  state?: string | null;
  description?: string | null;
  verified_worker_count: number;
  open_job_count: number;
  jobs: EmployerPublicJob[];
}

export const getEmployerPublic = (token: string, employerId: string) =>
  apiFetch<EmployerPublic>(`/employers/${employerId}/public`, token);
