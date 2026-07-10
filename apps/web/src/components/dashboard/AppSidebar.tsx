"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  LayoutDashboard, Sparkles, Briefcase, MessagesSquare, Mail, BadgeCheck,
  FileText, User, ShieldCheck, Plus, BarChart3, Map, Users, Building2,
  KeyRound, RefreshCw, Activity, FlaskConical, GraduationCap, Search, Menu, X,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SkilledNationLogo } from "@/components/ui/Logo";
import { OrbMark } from "@/components/ui/Orb";

type NavItem = { label: string; href: string };

const ICONS: Record<string, typeof LayoutDashboard> = {
  Dashboard: LayoutDashboard, Matches: Sparkles, Jobs: Briefcase, Plan: MessagesSquare,
  Messages: Mail, Credentials: BadgeCheck, "Résumé": FileText, Profile: User,
  "Verified workers": ShieldCheck, "Post a job": Plus, Analytics: BarChart3,
  Map: Map, Applicants: Users, Employers: Building2, "SKILLED ID": KeyRound,
  Impact: BarChart3, Sync: RefreshCw, Engagement: Activity, "Test Matches": FlaskConical,
  Imports: Upload,
  "Add jobs": Plus,
  Applications: FileText,
};

const ROLE_LABEL: Record<string, string> = {
  applicant: "Worker workspace",
  employer: "Employer workspace",
  admin: "Admin console",
  institution: "Partner portal",
};

export function AppSidebar({
  navItems, email, role, homeHref, displayName,
}: {
  navItems: NavItem[];
  email: string;
  role: string;
  homeHref: string;
  displayName?: string | null;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const hamburgerRef = useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  // Restore focus + Esc to close + Tab-loop trap while drawer is open.
  useEffect(() => {
    if (!open) return;
    previouslyFocusedRef.current = (document.activeElement as HTMLElement) ?? null;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        return;
      }
      if (e.key === "Tab") {
        const root = drawerRef.current;
        if (!root) return;
        const focusables = root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    // Move focus into the drawer on open.
    const t = setTimeout(() => {
      const root = drawerRef.current;
      const first = root?.querySelector<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      first?.focus();
    }, 10);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(t);
      // On close, restore focus to the hamburger (or the previously focused element).
      const restore = hamburgerRef.current ?? previouslyFocusedRef.current;
      restore?.focus?.();
    };
  }, [open]);

  // Routes that live off the main nav tree but should still highlight a parent.
  // Example: /applicant/consent (data-sharing settings) lives under Credentials.
  const PARENT_ROUTES: Record<string, string> = {
    "/applicant/consent":     "/applicant/credentials",
    "/applicant/applications": "/applicant/applications",   // its own item; keep explicit
    "/employer/jobs/add":     "/employer/jobs/add",
    "/employer/jobs/new":     "/employer/jobs/add",
    "/employer/jobs/imports": "/employer/jobs/add",
    "/account/settings":      "",                             // account is in the footer, no highlight
  };

  const activePathForNav = (() => {
    for (const [prefix, parent] of Object.entries(PARENT_ROUTES)) {
      if (pathname.startsWith(prefix)) return parent;
    }
    return pathname;
  })();

  const isActive = (href: string) =>
    href === homeHref ? pathname === href : activePathForNav.startsWith(href);

  const Nav = (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-4">
      {navItems.map((item) => {
        const Icon = ICONS[item.label] ?? GraduationCap;
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            className={cn(
              "group relative flex items-center gap-3 rounded-md px-3 py-2 text-body transition-colors",
              active
                ? "bg-white/10 font-medium text-studio-cream"
                : "text-studio-cream/60 hover:bg-white/5 hover:text-studio-cream",
            )}
          >
            {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-studio-maroon" />}
            <Icon className={cn("h-[18px] w-[18px] shrink-0", active ? "text-studio-cream" : "text-studio-cream/45 group-hover:text-studio-cream/80")} strokeWidth={1.75} aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const roleLabel = role === "employer" ? "Employer" : role === "admin" ? "Admin" : role === "institution" ? "Partner" : "Worker";
  const nameToShow = (displayName && displayName.trim()) || email;
  const subLabel = displayName ? email : roleLabel;
  // The assistant's front door: a living orb, present on every page.
  const ASK_HREF: Record<string, string> = {
    applicant: "/applicant/chat",
    employer: "/employer/analytics",
    admin: "/admin/engagement",
  };
  const askHref = ASK_HREF[role];
  const Ask = askHref ? (
    <div className="px-3 pb-3">
      <Link
        href={askHref}
        onClick={() => setOpen(false)}
        className="group flex items-center gap-3 rounded-md border border-white/10 bg-white/5 px-3 py-2.5 transition-colors hover:border-white/25 hover:bg-white/10"
      >
        <OrbMark size={26} />
        <span className="min-w-0">
          <span className="block text-caption font-medium text-studio-cream">Ask SKILLED</span>
          <span className="block truncate text-micro text-studio-cream/50">
            {role === "applicant" ? "Plan your next move" : "Ask about your numbers"}
          </span>
        </span>
      </Link>
    </div>
  ) : null;

  const Footer = (
    <div className="border-t border-white/10 px-4 py-3">
      <div className="truncate text-caption font-medium text-studio-cream" title={email}>{nameToShow}</div>
      <div className="truncate text-micro text-studio-cream/50">{subLabel}</div>
      <div className="mt-1 flex items-center gap-2 text-micro text-studio-cream/50">
        <Link href="/account/settings" className="transition-colors hover:text-studio-cream">Account</Link>
        <Link href="/api/auth/signout" prefetch={false} className="transition-colors hover:text-studio-cream">
          Sign out
        </Link>
      </div>
    </div>
  );

  const Brand = (
    <div className="flex h-16 shrink-0 items-center gap-2 border-b border-white/10 px-5">
      <Link href={homeHref} className="flex items-center">
        <SkilledNationLogo width={116} invert />
      </Link>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="aurora-surface fixed inset-y-0 left-0 z-40 hidden w-64 flex-col md:flex">
        {Brand}
        <div className="px-5 pt-4">
          <span className="mono-label text-studio-cream/50">{ROLE_LABEL[role] ?? "Workspace"}</span>
        </div>
        {Nav}
        {Ask}
        {Footer}
      </aside>

      {/* Mobile top bar — visible only <md. Hamburger + logo + search icon. */}
      <div
        className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-hairline bg-white/90 px-3 backdrop-blur md:hidden"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <button
          ref={hamburgerRef}
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="mobile-nav-drawer"
          className="inline-flex h-11 w-11 items-center justify-center rounded-md text-cohere-ink hover:bg-stone/60 focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2"
        >
          <Menu className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
        </button>
        <Link href={homeHref} aria-label="SKILLED Nation home" className="flex items-center">
          <SkilledNationLogo width={100} />
        </Link>
        <button
          onClick={() => {
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("open-command-palette"));
            }
          }}
          aria-label="Open search"
          className="inline-flex h-11 w-11 items-center justify-center rounded-md text-cohere-ink hover:bg-stone/60 focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2"
        >
          <Search className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div
          id="mobile-nav-drawer"
          ref={drawerRef}
          className="fixed inset-0 z-50 md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
        >
          <div className="absolute inset-0 bg-studio-dark-cork/40" onClick={() => setOpen(false)} />
          <aside
            className="aurora-surface absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col"
            style={{
              paddingTop: "env(safe-area-inset-top)",
              paddingBottom: "env(safe-area-inset-bottom)",
            }}
          >
            <div className="flex h-16 items-center justify-between border-b border-white/10 px-5">
              <SkilledNationLogo width={120} invert />
              <button
                onClick={() => setOpen(false)}
                aria-label="Close menu"
                className="inline-flex h-11 w-11 items-center justify-center rounded-md hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2"
              >
                <X className="h-5 w-5 text-studio-cream/70" aria-hidden="true" />
              </button>
            </div>
            {Nav}
            {Ask}
            {Footer}
          </aside>
        </div>
      )}
    </>
  );
}

export { Search };
