import Image from "next/image";
import Link from "next/link";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

const NAV_ITEMS: Record<string, { label: string; href: string }[]> = {
  applicant: [
    { label: "Dashboard", href: "/applicant" },
    { label: "Matches", href: "/applicant/matches" },
    { label: "Jobs", href: "/applicant/jobs" },
    { label: "Plan", href: "/applicant/chat" },
    { label: "Messages", href: "/applicant/messages" },
    { label: "Profile", href: "/applicant/profile" },
  ],
  employer: [
    { label: "Dashboard", href: "/employer" },
    { label: "Post a job", href: "/employer/jobs/new" },
    { label: "Messages", href: "/employer/messages" },
    { label: "Analytics", href: "/employer/analytics" },
  ],
  admin: [
    { label: "Dashboard", href: "/admin" },
    { label: "Map", href: "/admin/map" },
    { label: "Applicants", href: "/admin/applicants" },
    { label: "Employers", href: "/admin/employers" },
    { label: "Engagement", href: "/admin/engagement" },
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

  return (
    <div className="min-h-screen bg-zinc-950">
      <nav className="sticky top-0 z-50 bg-zinc-950/80 backdrop-blur-md border-b border-white/5 transition-all duration-300">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-8">
              <Link href={navItems[0]?.href ?? "/"} className="flex-shrink-0">
                <Image
                  src="/spf-logo.png"
                  alt="SkillPointe"
                  width={140}
                  height={38}
                  className="brightness-0 invert"
                />
              </Link>
              <div className="flex items-center gap-1">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="relative px-3 py-1.5 text-sm text-zinc-400 hover:text-white transition-colors duration-200 group"
                  >
                    {item.label}
                    <span className="absolute bottom-0 left-0 right-0 h-px bg-white scale-x-0 group-hover:scale-x-100 transition-transform duration-200 origin-left" />
                  </Link>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs text-zinc-500 hidden sm:inline">{user.email}</span>
              <Link
                href="/api/auth/signout"
                prefetch={false}
                className="text-xs text-zinc-400 hover:text-white transition-colors duration-200"
              >
                Sign out
              </Link>
            </div>
          </div>
        </div>
      </nav>
      {children}
    </div>
  );
}
