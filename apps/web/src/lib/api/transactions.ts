/**
 * API client for the transaction stack:
 *   - Applications (apply + screening + pipeline)
 *   - Interviews (availability + proposals + accept/decline)
 *   - Notifications (list + read)
 *   - Account recovery (email/phone/account access)
 *   - SLA (admin dormant applications)
 */
import { apiFetch, apiSend } from "./client";

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
  /** FALSE when the posting went inactive (removed from the source site or
   *  paused/filled/closed by the employer) after this application was made. */
  job_active?: boolean;
  cover_note?: string | null;
  submitted_at: string;
  employer_viewed_at?: string | null;
  reviewed_at?: string | null;
  decision_at?: string | null;
  days_since_submitted: number;
  resume_snapshot: Record<string, unknown>;
  screening_answers: Array<{ question_id: string; prompt: string; answer: string; knockout_pass: boolean }>;
}

// ---------------------------------------------------------------------------
// Apply context — one round-trip powering the apply sheet
// ---------------------------------------------------------------------------

/** Profile-sourced groups an employer may require at apply time. */
export type ProfileGroupKey =
  | "contact" | "location" | "program" | "availability" | "credentials" | "resume";

export const PROFILE_GROUP_LABELS: Record<ProfileGroupKey, string> = {
  contact: "Contact info",
  location: "Location",
  program: "Program or trade",
  availability: "Availability",
  credentials: "Credentials",
  resume: "Resume",
};

export interface ApplyContextProfile {
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  state: string | null;
  program: string | null;
  available_from_date: string | null;
  expected_completion_date: string | null;
  credentials: string[];
  resume_filename: string | null;
}

export interface AlreadyAppliedInfo {
  id: string;
  status: Application["status"];
  submitted_at: string;
  can_reapply: boolean;
}

export interface ApplyContext {
  job_id: string;
  job_title: string;
  employer_name: string | null;
  job_active: boolean;
  internal_apply_enabled: boolean;
  external_url: string | null;
  already_applied: AlreadyAppliedInfo | null;
  required_fields: ProfileGroupKey[];
  missing_required: ProfileGroupKey[];
  profile: ApplyContextProfile;
  questions: ScreeningQuestion[];
}

/** Fields the applicant may complete inline inside the apply sheet. */
export interface ProfileInlineUpdates {
  first_name?: string;
  last_name?: string;
  phone?: string;
  city?: string;
  state?: string;
  program_name_raw?: string;
  available_from_date?: string;
}

export const getApplyContext = (token: string, jobId: string) =>
  apiFetch<ApplyContext>(`/applicant/me/jobs/${jobId}/apply-context`, token);

export const applyToJob = (
  token: string,
  jobId: string,
  payload: {
    answers: ScreeningAnswer[];
    cover_note?: string;
    profile_updates?: ProfileInlineUpdates;
  },
) =>
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

/**
 * REAL undo for an employer decision: shortlist → previous stage, reject →
 * reopened (note archived server-side), hired → previous stage with the
 * hire outcome voided so analytics stay true. 409 when nothing is revertible.
 */
export const revertEmployerApplication = (token: string, id: string) =>
  apiFetch<Application>(`/employer/me/applications/${id}/revert`, token, { method: "POST" });

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

export interface InterviewSlot {
  id: string;
  application_id: string;
  start_at: string;
  end_at: string;
  status: "proposed" | "accepted" | "declined" | "cancelled" | "completed";
  /** TRUE when this slot was ever the booked (accepted) time — a cancelled
   *  slot with this flag reads "booked interview cancelled", not "declined". */
  was_accepted?: boolean;
  location?: string | null;
  meeting_url?: string | null;
  notes?: string | null;
  job_title?: string | null;
  employer_name?: string | null;
  applicant_name?: string | null;
  interviewer_contact_id?: string | null;
  interviewer_name?: string | null;
  interviewer_email?: string | null;
  interviewer_title?: string | null;
}

/** Who runs the interview. Omit entirely (or send all-empty) = "Me". */
export interface InterviewerAssignment {
  contact_id?: string;   // a teammate from /employer/me/team
  name?: string;
  email?: string;
  title?: string;
}

/** A teammate assignable as the interviewer (employer_contacts row). */
export interface TeamContact {
  contact_id: string;
  email: string;
  name?: string | null;          // auth user's full_name when set
  title?: string | null;
  role?: "owner" | "admin" | "member";
  is_primary: boolean;
  is_me: boolean;
}

export const getEmployerTeam = (token: string) =>
  apiFetch<TeamContact[]>("/employer/me/team", token);

export const proposeInterviewSlots = (
  token: string,
  applicationId: string,
  slots: Array<{ start_at: string; end_at: string; location?: string; meeting_url?: string; notes?: string }>,
  interviewer?: InterviewerAssignment,
) =>
  apiFetch<InterviewSlot[]>(`/employer/me/applications/${applicationId}/propose`, token, {
    method: "POST",
    body: JSON.stringify({ slots, ...(interviewer ? { interviewer } : {}) }),
  });

/** Full slot history (all statuses) for one application — employer owner or admin read-only. */
export const getEmployerApplicationSlots = (token: string, applicationId: string) =>
  apiFetch<InterviewSlot[]>(`/employer/me/applications/${applicationId}/slots`, token);

export const listMyInterviews = (token: string) =>
  apiFetch<InterviewSlot[]>("/applicant/me/interviews", token);

export const acceptInterviewSlot = (token: string, slotId: string) =>
  apiFetch<InterviewSlot>(`/applicant/me/interviews/${slotId}/accept`, token, { method: "POST" });

export const declineInterviewSlot = (token: string, slotId: string, reason?: string) =>
  apiFetch<InterviewSlot>(`/applicant/me/interviews/${slotId}/decline`, token, {
    method: "POST",
    ...(reason ? { body: JSON.stringify({ reason }) } : {}),
  });

/**
 * Employer cancels a proposed or booked (accepted) slot. When the last open
 * slot goes, the application returns to its pre-interview stage server-side
 * and the applicant is notified.
 */
export const cancelInterviewSlot = (token: string, slotId: string, reason?: string) =>
  apiFetch<InterviewSlot>(`/employer/me/interviews/${slotId}/cancel`, token, {
    method: "POST",
    ...(reason ? { body: JSON.stringify({ reason }) } : {}),
  });

// ---------------------------------------------------------------------------
// Calendar feed (subscribe-in-your-calendar-app) + OAuth provider gates
// ---------------------------------------------------------------------------

export interface CalendarFeedInfo {
  token: string;
  /** Path + query on the API origin — compose the absolute URL with API_BASE. */
  feed_path: string;
  rotated_at?: string | null;
}

export interface CalendarProviders {
  google_configured: boolean;
  outlook_configured: boolean;
  /** Local-only deterministic demo calendar (never available in production). */
  demo_available?: boolean;
}

export const getCalendarFeed = (token: string) =>
  apiFetch<CalendarFeedInfo>("/me/calendar/feed", token);

export const rotateCalendarFeed = (token: string) =>
  apiFetch<CalendarFeedInfo>("/me/calendar/feed/rotate", token, { method: "POST" });

export const getCalendarProviders = (token: string) =>
  apiFetch<CalendarProviders>("/me/calendar/providers", token);

// ---------------------------------------------------------------------------
// Calendar OAuth connections (read tier — busy overlay on the slot grid)
// ---------------------------------------------------------------------------

export interface CalendarConnection {
  id: string;
  provider: "google" | "microsoft" | "demo";
  account_email: string;
  connected_at: string;
  last_used_at?: string | null;
}

export interface CalendarBusyResponse {
  busy: { start: string; end: string }[];
  sources: { provider: string; account_email: string; ok: boolean }[];
}

/** Mint the provider authorize URL (state + PKCE handled server-side);
 *  the caller then does `window.location.assign(authorize_url)`. */
export const startCalendarConnect = (token: string, provider: "google" | "microsoft") =>
  apiFetch<{ authorize_url: string }>(`/me/calendar/connect/${provider}`, token);

/** Local-only: create the deterministic demo connection. */
export const connectDemoCalendar = (token: string) =>
  apiFetch<CalendarConnection>("/me/calendar/connect/demo", token, { method: "POST" });

export const getCalendarConnections = (token: string) =>
  apiFetch<CalendarConnection[]>("/me/calendar/connections", token);

export const disconnectCalendarConnection = (token: string, connectionId: string) =>
  apiSend(`/me/calendar/connections/${connectionId}`, token, { method: "DELETE" });

/** Merged busy intervals for [start, end) across the user's connections.
 *  tzOffset is `new Date().getTimezoneOffset()` (demo provider placement). */
export const getCalendarBusy = (token: string, startIso: string, endIso: string, tzOffset: number) =>
  apiFetch<CalendarBusyResponse>(
    `/me/calendar/busy?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}&tz_offset=${tzOffset}`,
    token,
  );

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
