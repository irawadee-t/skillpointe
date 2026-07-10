import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { AppSidebar } from "@/components/dashboard/AppSidebar";
import { Topbar } from "@/components/dashboard/Topbar";
import { CommandPalette } from "@/components/dashboard/CommandPalette";
import { ToastProvider } from "@/components/ui/Toast";

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
    { label: "Add jobs", href: "/employer/jobs/add" },
    // Insight
    { label: "Analytics", href: "/employer/analytics" },
  ],
  admin: [
    { label: "Dashboard", href: "/admin" },
    { label: "Map", href: "/admin/map" },
    { label: "Applicants", href: "/admin/applicants" },
    { label: "Employers", href: "/admin/employers" },
    { label: "Imports", href: "/admin/job-imports" },
    { label: "Credentials", href: "/admin/credentials" },
    { label: "SKILLED ID", href: "/admin/skilled-id" },
    { label: "Impact", href: "/admin/foundation" },
    { label: "Sync", href: "/admin/sync" },
    { label: "Engagement", href: "/admin/engagement" },
    { label: "Test Matches", href: "/admin/test-matches" },
  ],
};

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const role = (user.app_metadata?.role as string) ?? "applicant";
  const navItems = NAV_ITEMS[role] ?? NAV_ITEMS.applicant;
  const search = SEARCH[role] ?? SEARCH.applicant;

  // Best-effort display name — tries applicant profile first, then employer contact.
  let displayName: string | null = null;
  {
    const { data: applicant } = await supabase
      .from("applicants")
      .select("first_name, last_name, preferred_name")
      .eq("user_id", user.id)
      .maybeSingle();
    if (applicant) {
      const first = applicant.preferred_name || applicant.first_name;
      displayName = [first, applicant.last_name].filter(Boolean).join(" ").trim() || null;
    }
    if (!displayName) {
      const { data: emp } = await supabase
        .from("employer_contacts")
        .select("first_name, last_name")
        .eq("user_id", user.id)
        .maybeSingle();
      if (emp) displayName = [emp.first_name, emp.last_name].filter(Boolean).join(" ").trim() || null;
    }
  }

  return (
    <ToastProvider>
      <div className="min-h-screen bg-canvas">
        <AppSidebar
          navItems={navItems}
          email={user.email ?? ""}
          role={role}
          homeHref={navItems[0]?.href ?? "/"}
          displayName={displayName}
        />
        <div className="md:pl-64">
          <Topbar searchHref={search.href} placeholder={search.placeholder} role={role} />
          {children}
        </div>
        <CommandPalette role={role} />
      </div>
    </ToastProvider>
  );
}
