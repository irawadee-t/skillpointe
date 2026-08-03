/**
 * Server-side helpers for admin "view as applicant" debug mode.
 * Only import this from server components — it uses next/headers.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { parseViewAsCookie, VIEW_AS_COOKIE, type ViewAsTarget } from "./viewAs";

/** Read the view-as target from the request cookies (server components). */
export async function getViewAsTarget(): Promise<ViewAsTarget | null> {
  const store = await cookies();
  return parseViewAsCookie(store.get(VIEW_AS_COOKIE)?.value);
}

/**
 * Gate for applicant pages: real applicants always pass; admins pass only in
 * view-as debug mode (read-only). An admin with NO active view-as session is
 * sent to the applicant picker (/admin/view-as) instead of bouncing to login —
 * the applicant workspace is always one selection away for admins. Everyone
 * else should be redirected by the caller.
 */
export async function canViewApplicantPages(role: string | undefined): Promise<boolean> {
  if (role === "applicant") return true;
  if (role === "admin") {
    if ((await getViewAsTarget()) !== null) return true;
    redirect("/admin/view-as");
  }
  return false;
}
