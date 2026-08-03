import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { getViewAsTarget } from "@/lib/viewAs.server";
import { AppSidebar } from "@/components/dashboard/AppSidebar";
import { Topbar } from "@/components/dashboard/Topbar";
import { CommandPalette } from "@/components/dashboard/CommandPalette";
import { ViewAsBanner } from "@/components/admin/ViewAsBanner";
import { ToastProvider } from "@/components/ui/Toast";
import { TourProvider } from "@/components/tour/TourProvider";

const SEARCH: Record<string, { href: string; placeholder: string }> = {
  applicant: { href: "/applicant/jobs", placeholder: "Search jobs, trades, employers…" },
  employer: { href: "/employer/verified-workers", placeholder: "Search verified workers by trade, credential…" },
  admin: { href: "/admin/applicants", placeholder: "Search applicants, employers, credentials…" },
  institution: { href: "/institution", placeholder: "Search your students…" },
};

const NAV_ITEMS: Record<string, { label: string; href: string }[]> = {
  applicant: [
    // Home
    { label: "Dashboard", href: "/applicant" },
    // Discover
    { label: "Matches", href: "/applicant/matches" },
    { label: "Jobs", href: "/applicant/jobs" },
    // Activity
    { label: "Applications", href: "/applicant/applications" },
    { label: "Messages", href: "/applicant/messages" },
    { label: "Plan", href: "/applicant/chat" },
    // My record
    { label: "Profile", href: "/applicant/profile" },
    { label: "Credentials", href: "/applicant/credentials" },
    { label: "Résumé", href: "/applicant/resume" },
  ],
  institution: [
    { label: "Dashboard", href: "/institution" },
  ],
  employer: [
    // Home
    { label: "Dashboard", href: "/employer" },
    // Hiring flow
    { label: "Applications", href: "/employer/applications" },
    { label: "Verified workers", href: "/employer/verified-workers" },
    { label: "Messages", href: "/employer/messages" },
    // Post & manage — single entry point that branches into single-post + import
    { label: "Post jobs", href: "/employer/jobs/add" },
    { label: "Jobs", href: "/employer/jobs" },
    // Insight
    { label: "Analytics", href: "/employer/analytics" },
    // Company
    { label: "Team", href: "/employer/team" },
  ],
  admin: [
    { label: "Dashboard", href: "/admin" },
    // Insights — surfaced directly under Dashboard (see AppSidebar NAV_GROUPS).
    { label: "Engagement", href: "/admin/engagement" },
    { label: "Impact", href: "/admin/foundation" },
    // Review queue
    { label: "Imports", href: "/admin/job-imports" },
    { label: "Review", href: "/admin/review" },
    { label: "Credentials", href: "/admin/credentials" },
    { label: "Career sources", href: "/admin/career-sources" },
    // Marketplace
    { label: "Applicants", href: "/admin/applicants" },
    { label: "Employers", href: "/admin/employers" },
    { label: "Jobs", href: "/admin/jobs" },
    { label: "Map", href: "/admin/map" },
    // Operations
    { label: "Matching", href: "/admin/matching" },
    { label: "Test matches", href: "/admin/test-matches" },
    { label: "Audit log", href: "/admin/audit" },
    { label: "View as applicant", href: "/admin/view-as" },
  ],
};

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();

  // getClaims() verifies the access token's ES256 signature against the
  // project's cached JWKS, in-process. getUser() sent a request to the Auth
  // server on every single dashboard navigation, and this layout re-renders on
  // each one, so that round trip sat in front of every tab switch.
  //
  // This is still real verification, not decoding: the signature is checked and
  // `exp` is enforced (allowExpired defaults to false), so expired or tampered
  // tokens are rejected exactly as before. Requires asymmetric signing, which
  // this project uses; on a symmetric secret the SDK falls back to a server
  // call on its own, so the redirect below stays correct either way.
  // getClaims THROWS on an expired token ("JWT has expired") rather than
  // returning an error, so this has to catch: an expired session must land on
  // /login, not on a 500. redirect() stays outside the try because it signals
  // by throwing and must not be swallowed here.
  type Claims = NonNullable<Awaited<ReturnType<typeof supabase.auth.getClaims>>["data"]>["claims"];
  let claims: Claims | null = null;
  try {
    const { data, error } = await supabase.auth.getClaims();
    if (!error) claims = data?.claims ?? null;
  } catch {
    claims = null;
  }

  if (!claims?.sub) {
    redirect("/login");
  }

  const userId = claims.sub;
  const role = (claims.app_metadata?.role as string) ?? "applicant";
  const isAdmin = role === "admin";

  // Everything below depends only on the verified claims, so it all goes in one
  // round trip.
  // These used to run as three sequential awaits (view-as, then the name
  // lookups, then the session) and this layout re-renders on every dashboard
  // navigation, so each tab switch paid all three before the child page's
  // loading state could even paint.
  const [viewAs, { data: applicant }, { data: emp }, sessionResult] = await Promise.all([
    isAdmin ? getViewAsTarget() : Promise.resolve(null),
    supabase
      .from("applicants")
      .select("first_name, last_name, preferred_name")
      .eq("user_id", userId)
      .maybeSingle(),
    supabase
      .from("employer_contacts")
      .select("first_name, last_name")
      .eq("user_id", userId)
      .maybeSingle(),
    // Fetched for admins up front; discarded below if "view as" is active, which
    // is cheaper than serialising this behind the view-as lookup.
    isAdmin ? supabase.auth.getSession() : Promise.resolve(null),
  ]);

  // Admin "view as applicant" debug mode (read-only). While active, the chrome
  // mirrors the applicant experience so the admin sees what the applicant sees;
  // the ViewAsBanner is the persistent reminder + exit path.
  const chromeRole = viewAs ? "applicant" : role;
  const navItems = NAV_ITEMS[chromeRole] ?? NAV_ITEMS.applicant;
  const search = SEARCH[chromeRole] ?? SEARCH.applicant;

  // Best-effort display name — applicant profile wins, then employer contact.
  let displayName: string | null = null;
  if (applicant) {
    const first = applicant.preferred_name || applicant.first_name;
    displayName = [first, applicant.last_name].filter(Boolean).join(" ").trim() || null;
  }
  if (!displayName && emp) {
    displayName = [emp.first_name, emp.last_name].filter(Boolean).join(" ").trim() || null;
  }

  // Live pending-work badges (Imports / Review / Credentials) need a token
  // client-side — admin chrome only, never while impersonating an applicant.
  const badgeToken =
    chromeRole === "admin" ? sessionResult?.data.session?.access_token ?? null : null;

  return (
    <ToastProvider>
      <TourProvider userId={userId} role={chromeRole}>
      <div className="min-h-screen bg-canvas">
        <AppSidebar
          navItems={navItems}
          email={(claims.email as string) ?? ""}
          role={chromeRole}
          homeHref={navItems[0]?.href ?? "/"}
          displayName={displayName}
          badgeToken={badgeToken}
        />
        <div className="md:pl-64">
          {viewAs && <ViewAsBanner target={viewAs} />}
          <Topbar searchHref={search.href} placeholder={search.placeholder} role={chromeRole} />
          {children}
        </div>
        <CommandPalette role={chromeRole} />
      </div>
      </TourProvider>
    </ToastProvider>
  );
}
