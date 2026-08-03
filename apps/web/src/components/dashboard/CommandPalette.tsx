"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Command, ArrowRight,
  LayoutDashboard, Sparkles, Briefcase, FileText, MessagesSquare, Mail,
  BadgeCheck, User, ShieldCheck, Plus, BarChart3, Map, Users, Building2,
  RefreshCw, Activity, Upload, Settings,
} from "lucide-react";

/**
 * Global command palette — ⌘K / Ctrl+K anywhere in the dashboard.
 *
 * Two-tier UX:
 *   1. Static navigation commands, filtered by role
 *   2. Dynamic search across jobs / applications when the query is meaningful
 *
 * Filter is prefix + word-boundary + acronym match (e.g. "am" → "Applicant Matches").
 */

type Cmd = {
  id: string;
  label: string;
  sub?: string;
  href?: string;
  action?: () => void;
  icon: typeof Search;
  section: string;
};

const APPLICANT_CMDS: Cmd[] = [
  { id: "a-dash",     label: "Dashboard",       href: "/applicant",             icon: LayoutDashboard, section: "Go to" },
  { id: "a-matches",  label: "Matches",         href: "/applicant/matches",     icon: Sparkles,        section: "Go to" },
  { id: "a-apps",     label: "Applications",    href: "/applicant/applications", icon: FileText,       section: "Go to" },
  { id: "a-jobs",     label: "Browse jobs",     href: "/applicant/jobs",        icon: Briefcase,       section: "Go to" },
  { id: "a-chat",     label: "Plan (AI chat)",  href: "/applicant/chat",        icon: MessagesSquare,  section: "Go to" },
  { id: "a-msg",      label: "Messages",        href: "/applicant/messages",    icon: Mail,            section: "Go to" },
  { id: "a-cred",     label: "Credentials",     href: "/applicant/credentials", icon: BadgeCheck,      section: "Go to" },
  { id: "a-res",      label: "Résumé",          href: "/applicant/resume",      icon: FileText,        section: "Go to" },
  { id: "a-prof",     label: "Profile",         href: "/applicant/profile",     icon: User,            section: "Go to" },
  { id: "a-account",  label: "Account settings", href: "/account/settings",     icon: Settings,        section: "Account" },
];

const EMPLOYER_CMDS: Cmd[] = [
  { id: "e-dash",   label: "Dashboard",        href: "/employer",                    icon: LayoutDashboard, section: "Go to" },
  { id: "e-verify", label: "Verified workers", href: "/employer/verified-workers",   icon: ShieldCheck,     section: "Go to" },
  { id: "e-apps",   label: "Applications",     href: "/employer/applications",       icon: FileText,        section: "Go to" },
  { id: "e-new",    label: "Post a job",       href: "/employer/jobs/new",           icon: Plus,            section: "Actions" },
  { id: "e-import", label: "Import jobs",      href: "/employer/jobs/imports",       icon: Upload,          section: "Actions" },
  { id: "e-mylist", label: "My imports",       href: "/employer/jobs/imports/list",  icon: Upload,          section: "Go to" },
  { id: "e-msg",    label: "Messages",         href: "/employer/messages",           icon: Mail,            section: "Go to" },
  { id: "e-analytics", label: "Analytics",     href: "/employer/analytics",          icon: BarChart3,       section: "Go to" },
  { id: "e-account", label: "Account settings", href: "/account/settings",           icon: Settings,        section: "Account" },
];

// Parity rule: every admin nav destination has a palette command (and the
// palette may carry extras like Messages that live off the sidebar).
const ADMIN_CMDS: Cmd[] = [
  { id: "ad-dash",   label: "Command center",   href: "/admin",                 icon: LayoutDashboard, section: "Go to" },
  // Insights — mirrors the sidebar order (surfaced directly under Dashboard).
  { id: "ad-eng",    label: "Engagement",       href: "/admin/engagement",      icon: Activity,        section: "Go to" },
  { id: "ad-impact", label: "Impact",           href: "/admin/foundation",      icon: BarChart3,       section: "Go to" },
  { id: "ad-imp",    label: "Import approvals", href: "/admin/job-imports",     icon: Upload,          section: "Review" },
  { id: "ad-review", label: "Review queue",     href: "/admin/review",          icon: ShieldCheck,     section: "Review" },
  { id: "ad-cred",   label: "Credentials",      href: "/admin/credentials",     icon: BadgeCheck,      section: "Review" },
  { id: "ad-csrc",   label: "Career sources",   href: "/admin/career-sources",  icon: RefreshCw,       section: "Review" },
  { id: "ad-map",    label: "Job map",          href: "/admin/map",             icon: Map,             section: "Go to" },
  { id: "ad-apps",   label: "Applicants",       href: "/admin/applicants",      icon: Users,           section: "Go to" },
  { id: "ad-emp",    label: "Employers",        href: "/admin/employers",       icon: Building2,       section: "Go to" },
  { id: "ad-jobs",   label: "Jobs",             href: "/admin/jobs",            icon: Briefcase,       section: "Go to" },
  { id: "ad-match",  label: "Matching config",  href: "/admin/matching",        icon: Sparkles,        section: "Go to" },
  { id: "ad-test",   label: "Test matches",     href: "/admin/test-matches",    icon: Sparkles,        section: "Go to" },
  { id: "ad-audit",  label: "Audit log",        href: "/admin/audit",           icon: FileText,        section: "Go to" },
  { id: "ad-msg",    label: "Messages",         href: "/admin/messages",        icon: Mail,            section: "Go to" },
  { id: "ad-viewas", label: "View as applicant", href: "/admin/view-as",        icon: User,            section: "Go to" },
  { id: "ad-account", label: "Account settings", href: "/account/settings",     icon: Settings,        section: "Account" },
];

function commandsFor(role: string): Cmd[] {
  if (role === "employer") return EMPLOYER_CMDS;
  if (role === "admin")    return ADMIN_CMDS;
  return APPLICANT_CMDS;
}

export function CommandPalette({ role }: { role: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  const items = useMemo(() => commandsFor(role), [role]);

  const filtered = useMemo(() => {
    if (!q.trim()) return items;
    const query = q.toLowerCase();
    return items.filter((c) => {
      const label = c.label.toLowerCase();
      if (label.includes(query)) return true;
      // Acronym match — "am" matches "Applicant Matches"
      const acronym = c.label.split(/\s+/).map((w) => w[0]?.toLowerCase() ?? "").join("");
      return acronym.startsWith(query);
    });
  }, [items, q]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    }
    function onOpenEvent() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("open-command-palette", onOpenEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("open-command-palette", onOpenEvent);
    };
  }, [open]);

  // Open/close lifecycle: capture previous focus on open, restore on close.
  useEffect(() => {
    if (open) {
      previouslyFocusedRef.current = (document.activeElement as HTMLElement) ?? null;
      setQ("");
      setSel(0);
      const t = setTimeout(() => inputRef.current?.focus(), 10);
      return () => clearTimeout(t);
    } else if (previouslyFocusedRef.current) {
      // Restore focus to the element that was focused before opening.
      previouslyFocusedRef.current.focus?.();
      previouslyFocusedRef.current = null;
    }
  }, [open]);

  // Focus trap: keep Tab / Shift+Tab within the dialog.
  useEffect(() => {
    if (!open) return;
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const root = dialogRef.current;
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
    };
    document.addEventListener("keydown", trap);
    return () => document.removeEventListener("keydown", trap);
  }, [open]);

  useEffect(() => { setSel(0); }, [q]);

  function navigate(cmd: Cmd) {
    setOpen(false);
    if (cmd.action) { cmd.action(); return; }
    if (cmd.href) { router.push(cmd.href); }
  }

  function onKeyInInput(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(filtered.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const hit = filtered[sel];
      if (hit) navigate(hit);
    }
  }

  // Group by section for display
  const grouped = useMemo(() => {
    const g: Record<string, Cmd[]> = {};
    for (const c of filtered) (g[c.section] ||= []).push(c);
    return g;
  }, [filtered]);

  if (!open) return null;

  let index = 0;
  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-[70] flex items-start justify-center p-4 sm:p-16"
    >
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" onClick={() => setOpen(false)} />

      <div className="relative w-full max-w-xl overflow-hidden rounded-[14px] border border-hairline bg-white shadow-float">
        <div className="flex items-center gap-2 border-b border-hairline px-4 py-3">
          <Search className="h-4 w-4 text-slate-muted" strokeWidth={1.75} aria-hidden="true" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyInInput}
            placeholder="Jump to a page, action, or search…"
            className="flex-1 bg-transparent text-body text-cohere-ink placeholder:text-slate-muted focus:outline-none"
          />
          <kbd className="hidden rounded border border-hairline bg-stone/60 px-1.5 py-0.5 text-micro text-slate-muted sm:inline">
            esc
          </kbd>
        </div>

        <div className="max-h-[70vh] md:max-h-[420px] overflow-y-auto py-2">
          {filtered.length === 0 && (
            <p className="px-4 py-6 text-center text-caption text-slate-muted">No matches for "{q}".</p>
          )}
          {Object.entries(grouped).map(([section, cmds]) => (
            <div key={section} className="mb-1 last:mb-0">
              <div className="px-4 pb-1 pt-2 mono-label">{section}</div>
              <ul>
                {cmds.map((c) => {
                  const idx = index++;
                  const active = idx === sel;
                  const Icon = c.icon;
                  return (
                    <li key={c.id}>
                      <button
                        onClick={() => navigate(c)}
                        onMouseEnter={() => setSel(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2 text-left text-body transition-colors ${
                          active ? "bg-stone text-cohere-ink" : "text-slate hover:bg-stone/50"
                        }`}
                      >
                        <Icon className={`h-4 w-4 shrink-0 ${active ? "text-cohere-green" : "text-slate-muted"}`} strokeWidth={1.75} aria-hidden="true" />
                        <span className="flex-1">{c.label}</span>
                        {c.sub && <span className="text-caption text-slate-muted">{c.sub}</span>}
                        <ArrowRight className={`h-3.5 w-3.5 shrink-0 transition-transform ${active ? "translate-x-0.5 text-cohere-ink" : "text-slate-muted"}`} aria-hidden="true" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-hairline bg-stone/40 px-4 py-2 text-micro text-slate-muted">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><kbd className="rounded border border-hairline bg-white px-1 py-0.5">↑↓</kbd> navigate</span>
            <span className="inline-flex items-center gap-1"><kbd className="rounded border border-hairline bg-white px-1 py-0.5">↵</kbd> select</span>
          </div>
          <span className="inline-flex items-center gap-1"><Command className="h-3 w-3" aria-hidden="true" /> K to reopen</span>
        </div>
      </div>
    </div>
  );
}
