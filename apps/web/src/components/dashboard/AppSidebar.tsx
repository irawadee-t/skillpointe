"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  LayoutDashboard, Sparkles, Briefcase, MessagesSquare, Mail, BadgeCheck,
  FileText, User, ShieldCheck, Plus, BarChart3, Map, Users, Building2,
  Activity, FlaskConical, GraduationCap, Search, Menu, X,
  Upload, Link2, SlidersHorizontal, Eye, ClipboardCheck, ScrollText, Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SkilledNationLogo } from "@/components/ui/Logo";
import { OrbMark } from "@/components/ui/Orb";
import { fetchPendingCounts, type PendingCounts } from "@/lib/api/admin";

type NavItem = { label: string; href: string };

const ICONS: Record<string, typeof LayoutDashboard> = {
  Dashboard: LayoutDashboard, Matches: Sparkles, Jobs: Briefcase, Plan: MessagesSquare,
  Messages: Mail, Credentials: BadgeCheck, "Résumé": FileText, Profile: User,
  "Verified workers": ShieldCheck, "Post a job": Plus, Analytics: BarChart3,
  Map: Map, Applicants: Users, Employers: Building2,
  Impact: BarChart3, Engagement: Activity, "Match quality": Target, "Test matches": FlaskConical,
  Imports: Upload,
  Review: ClipboardCheck,
  "Audit log": ScrollText,
  "Career sources": Link2,
  Matching: SlidersHorizontal,
  "Post jobs": Plus,
  Applications: FileText,
  "View as applicant": Eye,
  Team: Users,
};

const ROLE_LABEL: Record<string, string> = {
  applicant: "Worker workspace",
  employer: "Employer workspace",
  admin: "Admin console",
  institution: "Partner portal",
};

// Deep wine-black chrome — the hero's #9d2235 family taken to a near-black
// ground, replacing the old brown cork. One value, used for sidebar + drawer.
// Deep brand red — the skilled-nation.org crimson family, darkened for chrome.
// Deep shade of Pantone 201C (#9D2235) — the guide's crimson, darkened
// for a chrome surface the white logo variant sits on.
const CHROME_BG = "bg-[#5e141f]";

// Thoughtful nav order: grouped by what the user is DOING, not a flat list.
// Items are matched by label; anything not listed falls into a trailing group
// so new nav items never disappear.
const NAV_GROUPS: Record<string, Array<{ heading: string | null; items: string[] }>> = {
  applicant: [
    { heading: null, items: ["Dashboard"] },
    { heading: "Find work", items: ["Matches", "Jobs"] },
    { heading: "Your activity", items: ["Applications", "Messages", "Plan"] },
    { heading: "You", items: ["Profile", "Credentials", "Résumé"] },
  ],
  employer: [
    { heading: null, items: ["Dashboard"] },
    { heading: "Hiring", items: ["Post jobs", "Jobs", "Verified workers", "Applications", "Interviews"] },
    { heading: "Activity", items: ["Messages", "Analytics"] },
    { heading: "Company", items: ["Team"] },
  ],
  admin: [
    { heading: null, items: ["Dashboard"] },
    // Insights surfaced at the top — the numbers are the morning read.
    { heading: "Insights", items: ["Engagement", "Impact", "Match quality"] },
    // Ordered by review frequency: the daily queue next.
    { heading: "Review", items: ["Imports", "Review", "Credentials", "Career sources"] },
    { heading: "Marketplace", items: ["Applicants", "Employers", "Jobs", "Map"] },
    { heading: "Operations", items: ["Matching", "Test matches", "Audit log", "View as applicant"] },
  ],
};

// Nav labels that carry a live pending-work badge, and which count feeds them.
const BADGE_KEYS: Record<string, keyof PendingCounts> = {
  Imports: "imports_awaiting_batches",
  Review: "review_items_pending",
  Credentials: "credentials_needs_review",
};

export function AppSidebar({
  navItems, email, role, homeHref, displayName, badgeToken,
}: {
  navItems: NavItem[];
  email: string;
  role: string;
  homeHref: string;
  displayName?: string | null;
  badgeToken?: string | null;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Live pending-work badges (admin only): the counts come from the SAME
  // shared backend definitions the destination pages use, refreshed every
  // 60s and on route change so the sidebar never disagrees with the page.
  const [pending, setPending] = useState<PendingCounts | null>(null);
  useEffect(() => {
    if (!badgeToken || role !== "admin") return;
    let cancelled = false;
    const load = () => {
      fetchPendingCounts(badgeToken)
        .then((c) => { if (!cancelled) setPending(c); })
        .catch(() => { /* badge is decoration — never break nav */ });
    };
    load();
    const iv = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [badgeToken, role, pathname]);

  const badgeFor = (label: string): number => {
    if (!pending) return 0;
    const key = BADGE_KEYS[label];
    return key ? pending[key] : 0;
  };
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

  // Longest-prefix wins so nested routes (e.g. /employer/jobs vs
  // /employer/jobs/add) highlight exactly ONE nav item.
  const matchedHref = (() => {
    let best = "";
    for (const n of navItems) {
      const ok =
        n.href === homeHref ? pathname === n.href : activePathForNav.startsWith(n.href);
      if (ok && n.href.length > best.length) best = n.href;
    }
    return best;
  })();
  const isActive = (href: string) => href !== "" && href === matchedHref;

  // Arrange this role's items into groups; unknown items go to a trailing
  // ungrouped section so nothing ever silently disappears from the nav.
  const groups = (() => {
    const spec = NAV_GROUPS[role] ?? [{ heading: null, items: navItems.map((n) => n.label) }];
    // (Plain record — `Map` here is the lucide icon, shadowing the global.)
    const byLabel: Record<string, NavItem> = {};
    for (const n of navItems) byLabel[n.label] = n;
    const placed = new Set<string>();
    const resolved = spec
      .map((g) => ({
        heading: g.heading,
        items: g.items
          .map((label) => { placed.add(label); return byLabel[label]; })
          .filter((n): n is NavItem => Boolean(n)),
      }))
      .filter((g) => g.items.length > 0);
    const leftovers = navItems.filter((n) => !placed.has(n.label));
    if (leftovers.length > 0) resolved.push({ heading: null, items: leftovers });
    return resolved;
  })();

  const NavLink = ({ item }: { item: NavItem }) => {
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
        {/* Non-text accent only. #d45c72 clears 5.1:1 against the #1c0a10
            chrome; the previous #c34f63 read muddy at 2px. */}
        {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-white/90" />}
        <Icon className={cn("h-[18px] w-[18px] shrink-0", active ? "text-studio-cream" : "text-studio-cream/45 group-hover:text-studio-cream/80")} strokeWidth={1.75} aria-hidden="true" />
        <span className="flex-1">{item.label}</span>
        {badgeFor(item.label) > 0 && (
          <span
            className="ml-auto inline-flex min-w-[20px] items-center justify-center rounded-full bg-white/15 px-1.5 py-0.5 text-[10px] font-semibold leading-none tabular-nums text-studio-cream"
            aria-label={`${badgeFor(item.label)} pending`}
          >
            {badgeFor(item.label) > 99 ? "99+" : badgeFor(item.label)}
          </span>
        )}
      </Link>
    );
  };

  const Nav = (
    <nav className="flex flex-1 flex-col overflow-y-auto px-3 py-4">
      {groups.map((group, gi) => (
        <div key={group.heading ?? `group-${gi}`} className={gi > 0 ? "mt-5" : ""}>
          {group.heading && (
            <p className="px-3 pb-1.5 text-micro text-studio-cream/40">{group.heading}</p>
          )}
          <div className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
          </div>
        </div>
      ))}
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
        {role !== "institution" && (
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              window.dispatchEvent(new CustomEvent("sn:start-tour"));
            }}
            className="transition-colors hover:text-studio-cream"
          >
            Take the tour
          </button>
        )}
        <Link href="/api/auth/signout" prefetch={false} className="transition-colors hover:text-studio-cream">
          Sign out
        </Link>
      </div>
    </div>
  );

  const Brand = (
    <div className="flex h-16 shrink-0 items-center gap-2 border-b border-white/10 px-5">
      <Link href={homeHref} className="flex items-center">
        <SkilledNationLogo width={116} variant="white" />
      </Link>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className={cn(CHROME_BG, "fixed inset-y-0 left-0 z-40 hidden w-64 flex-col md:flex")}>
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
          <div className="absolute inset-0 bg-[#5c101e]/50" onClick={() => setOpen(false)} />
          <aside
            className={cn(CHROME_BG, "absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col")}
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
