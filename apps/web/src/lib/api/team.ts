/**
 * Employer team + invites + delegated scheduling API.
 *
 * The join endpoints are PUBLIC (token-in-URL, no session) — they use a
 * local unauthenticated fetch with the same problem+json error handling as
 * apiFetch.
 */
import { API_BASE, ApiError, apiFetch, apiSend } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type OrgRole = "owner" | "admin" | "member";

export interface TeamMember {
  contact_id: string;
  name?: string | null;
  email: string;
  title?: string | null;
  role: OrgRole;
  is_primary: boolean;
  is_me: boolean;
  joined_at: string;
}

export interface TeamInvite {
  id: string;
  email: string;
  role: OrgRole;
  title?: string | null;
  invited_by_email?: string | null;
  sent_at: string;
  expires_at: string;
  expired: boolean;
  email_sent: boolean;
}

export interface TeamOverview {
  company_name: string;
  my_role: OrgRole;
  can_manage: boolean;
  members: TeamMember[];
  invites: TeamInvite[];
}

export interface JoinInfo {
  status: "valid" | "expired" | "revoked" | "used";
  company_name?: string | null;
  inviter_name?: string | null;
  invited_email?: string | null;
  role?: OrgRole | null;
  title?: string | null;
  expires_at?: string | null;
  account_exists: boolean;
}

export interface SchedulingRequest {
  id: string;
  application_id: string;
  status: "pending" | "fulfilled" | "cancelled";
  note?: string | null;
  created_at: string;
  assignee_contact_id: string;
  assignee_name?: string | null;
  assignee_email?: string | null;
  requested_by_me: boolean;
  assigned_to_me: boolean;
  requester_name?: string | null;
  applicant_name?: string | null;
  job_title?: string | null;
}

export interface SchedulingInbox {
  assigned_to_me: SchedulingRequest[];
  waiting_on_others: SchedulingRequest[];
}

// ---------------------------------------------------------------------------
// Team (auth required)
// ---------------------------------------------------------------------------

export const getTeamOverview = (token: string) =>
  apiFetch<TeamOverview>("/employer/me/team/overview", token);

export const createTeamInvite = (
  token: string,
  body: { email: string; role: OrgRole; title?: string },
) =>
  apiFetch<TeamInvite>("/employer/me/team/invites", token, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const resendTeamInvite = (token: string, inviteId: string) =>
  apiFetch<TeamInvite>(`/employer/me/team/invites/${inviteId}/resend`, token, {
    method: "POST",
  });

export const revokeTeamInvite = (token: string, inviteId: string) =>
  apiSend(`/employer/me/team/invites/${inviteId}/revoke`, token, { method: "POST" });

// ---------------------------------------------------------------------------
// Join (public — token in URL, no session)
// ---------------------------------------------------------------------------

async function publicFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export const getJoinInfo = (token: string) =>
  publicFetch<JoinInfo>(`/auth/join/${encodeURIComponent(token)}`);

export const acceptJoin = (
  token: string,
  body: { full_name: string; password: string },
) =>
  publicFetch<{ email: string; company_name: string }>(
    `/auth/join/${encodeURIComponent(token)}/accept`,
    { method: "POST", body: JSON.stringify(body) },
  );

export const acceptJoinSignedIn = (joinToken: string, accessToken: string) =>
  apiFetch<{ email: string; company_name: string }>(
    `/auth/join/${encodeURIComponent(joinToken)}/accept-session`,
    accessToken,
    { method: "POST" },
  );

// ---------------------------------------------------------------------------
// Delegated scheduling (auth required)
// ---------------------------------------------------------------------------

export const createSchedulingRequest = (
  token: string,
  applicationId: string,
  body: { assignee_contact_id: string; note?: string },
) =>
  apiFetch<SchedulingRequest>(
    `/employer/me/applications/${applicationId}/scheduling-request`,
    token,
    { method: "POST", body: JSON.stringify(body) },
  );

export const getSchedulingRequestForApplication = (
  token: string,
  applicationId: string,
) =>
  apiFetch<SchedulingRequest | null>(
    `/employer/me/applications/${applicationId}/scheduling-request`,
    token,
  );

export const listSchedulingRequests = (token: string) =>
  apiFetch<SchedulingInbox>("/employer/me/scheduling-requests", token);

export const cancelSchedulingRequest = (token: string, requestId: string) =>
  apiSend(`/employer/me/scheduling-requests/${requestId}/cancel`, token, {
    method: "POST",
  });
