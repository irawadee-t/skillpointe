"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Check, Inbox, Loader2 } from "lucide-react";

import {
  NotifItem, NotifSummary,
  getMyNotifications, markAllNotificationsRead, markNotificationRead,
} from "@/lib/api/transactions";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";
import { formatDateShort } from "@/lib/format";
import { cn } from "@/lib/utils";
import { STATUS_TONE_CLASSES } from "@/components/ui/statusTones";

/**
 * Sidebar notification tray. Bell icon with a subtle unread badge; opens a
 * scrollable panel of recent items. Each item is a link → deep-link to the
 * source (application detail, interview, credential, etc.). Read-on-click.
 *
 * Poll cadence: 30s while open, 90s while closed. Cheap enough for local dev,
 * upgradeable to Supabase Realtime later without changing the surface.
 */
export function NotificationTray({ token }: { token: string }) {
  const [summary, setSummary] = useState<NotifSummary | null>(null);
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  async function refresh() {
    try {
      const s = await getMyNotifications(token, { limit: 30 });
      setSummary(s);
    } catch { /* silent */ }
  }

  useEffect(() => {
    refresh();
    // Polling now serves as a fallback for Realtime — bumped a bit so we're
    // not double-fetching on top of the socket.
    const iv = setInterval(refresh, open ? 45_000 : 120_000);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, open]);

  // Realtime: when a new notification lands, refresh the tray immediately so
  // the badge count and top item bump into view. Optimistic tick on the badge
  // keeps the number feeling live even before the fetch resolves.
  useRealtimeChannel(
    "notifications:me",
    "INSERT",
    () => {
      setSummary((prev) => prev && ({ ...prev, unread: prev.unread + 1 }));
      refresh();
    },
    { table: "notifications" },
  );

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (btnRef.current?.contains(e.target as Node)) return;
      if (panelRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    }
    window.addEventListener("mousedown", onDoc);
    return () => window.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Keyboard: Escape closes and returns focus to the bell; Tab is contained
  // inside the open panel (minimal dialog behavior — swap for a shared
  // accessible dialog primitive if/when one lands in components/ui).
  useEffect(() => {
    if (!open) return;
    // Land keyboard focus in the tray when it opens.
    panelRef.current?.focus();

    function focusables(): HTMLElement[] {
      const root = panelRef.current;
      if (!root) return [];
      return Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
    }

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        btnRef.current?.focus();
        return;
      }
      if (e.key !== "Tab") return;
      const els = focusables();
      const root = panelRef.current;
      if (!root) return;
      if (els.length === 0) {
        e.preventDefault();
        root.focus();
        return;
      }
      const first = els[0];
      const last = els[els.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const inside = active ? root.contains(active) : false;
      if (e.shiftKey) {
        if (!inside || active === first || active === root) {
          e.preventDefault();
          last.focus();
        }
      } else if (!inside || active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const unread = summary?.unread ?? 0;
  const items = summary?.items ?? [];

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications (${unread} unread)`}
        aria-expanded={open}
        className={cn(
          "relative flex h-9 w-9 items-center justify-center rounded-md border transition-colors",
          open ? "border-cohere-ink bg-stone" : "border-transparent hover:border-hairline hover:bg-stone/60",
        )}
      >
        <Bell className="h-[18px] w-[18px] text-slate" strokeWidth={1.75} />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute -right-0.5 -top-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-studio-maroon px-1 text-[10px] font-semibold leading-none text-white"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute right-4 top-14 z-50 w-[calc(100vw-2rem)] max-w-[380px] max-h-[540px] overflow-hidden rounded-[14px] border border-hairline bg-white shadow-float focus:outline-none md:right-6 md:w-[380px]"
          role="dialog"
          aria-modal="true"
          aria-label="Notifications"
          tabIndex={-1}
        >
          <TrayHeader unread={unread} token={token} onAllRead={refresh} />
          <div className="max-h-[440px] overflow-y-auto">
            {summary === null && (
              <div className="flex items-center gap-2 p-6 text-caption text-slate">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading…
              </div>
            )}
            {items.length === 0 && summary !== null && (
              <div className="flex flex-col items-center gap-2 p-8 text-center">
                <Inbox className="h-6 w-6 text-slate-muted" strokeWidth={1.5} />
                <p className="text-body text-cohere-ink">Nothing here right now.</p>
                <p className="text-caption text-slate">You'll see new matches and employer messages first.</p>
              </div>
            )}
            {items.length > 0 && (
              <ul className="divide-y divide-hairline">
                {items.map((n) => (
                  <NotificationRow
                    key={n.id}
                    item={n}
                    token={token}
                    onRead={() => {
                      setSummary((prev) => prev && {
                        unread: Math.max(0, prev.unread - (n.read ? 0 : 1)),
                        items: prev.items.map((x) => x.id === n.id ? { ...x, read: true } : x),
                      });
                    }}
                    onNavigate={() => setOpen(false)}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function TrayHeader({ unread, token, onAllRead }: { unread: number; token: string; onAllRead: () => void }) {
  const [busy, setBusy] = useState(false);
  async function readAll() {
    if (unread === 0) return;
    setBusy(true);
    await markAllNotificationsRead(token).catch(() => null);
    setBusy(false);
    onAllRead();
  }
  return (
    <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
      <div>
        <div className="mono-label text-studio-maroon">Notifications</div>
        <div className="text-caption text-slate">
          {unread > 0 ? `${unread} unread` : "Nothing new"}
        </div>
      </div>
      <button
        onClick={readAll}
        disabled={busy || unread === 0}
        className="inline-flex items-center gap-1 text-caption text-slate transition-colors hover:text-cohere-ink disabled:opacity-40"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
        Mark all read
      </button>
    </div>
  );
}

function NotificationRow({
  item, token, onRead, onNavigate,
}: {
  item: NotifItem;
  token: string;
  onRead: () => void;
  onNavigate: () => void;
}) {
  const meta = KIND_META[item.kind] ?? KIND_META.default;

  const inner = (
    <div className={cn("flex gap-3 px-4 py-3 transition-colors", !item.read && "bg-stone/40")}>
      <div className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border", meta.tone)}>
        <meta.Icon className="h-4 w-4" strokeWidth={1.75} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <div className={cn("truncate text-caption font-medium", item.read ? "text-slate" : "text-cohere-ink")}>{item.title}</div>
          <span className="shrink-0 text-micro text-slate-muted">{formatWhen(item.created_at)}</span>
        </div>
        {item.body && (
          <p className="mt-0.5 line-clamp-2 text-caption text-slate">{item.body}</p>
        )}
      </div>
      {!item.read && (
        <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-studio-maroon" />
      )}
    </div>
  );

  async function activate() {
    if (!item.read) {
      markNotificationRead(token, item.id).catch(() => null);
      onRead();
    }
    onNavigate();
  }

  if (item.link_href) {
    return (
      <li>
        <Link href={item.link_href} onClick={activate} className="block hover:bg-stone/40 transition-colors">
          {inner}
        </Link>
      </li>
    );
  }

  return (
    <li>
      <button onClick={activate} className="block w-full text-left hover:bg-stone/40 transition-colors">{inner}</button>
    </li>
  );
}

function formatWhen(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const m = Math.floor(diff / 60_000);
  if (m < 1)    return "just now";
  if (m < 60)   return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7)    return `${d}d`;
  return formatDateShort(iso);
}

// ---------------------------------------------------------------------------
// Per-kind icon + subtle tone map — keeps rows scan-able. Any unknown kind
// falls back to a neutral bell so the tray never breaks on new event types.
// ---------------------------------------------------------------------------
import {
  Sparkles, Eye, Calendar, ShieldCheck, ShieldAlert, Send, FileWarning, Mail, MessageSquare, UserRound,
} from "lucide-react";

// Tones come from the semantic slot system (statusTones.ts): good news =
// positive (solid dark green), informational = progress (solid blue),
// action-required = attention (solid maroon). Solid dark fill + white icon —
// never a light tint with a same-hue icon (banned highlighter pattern).
const KIND_META: Record<string, { Icon: typeof Bell; tone: string }> = {
  default:                    { Icon: Bell,        tone: "border-hairline text-slate-muted bg-white" },
  new_match:                  { Icon: Sparkles,    tone: STATUS_TONE_CLASSES.positive },
  application_submitted:      { Icon: Send,        tone: STATUS_TONE_CLASSES.progress },
  application_viewed:         { Icon: Eye,         tone: STATUS_TONE_CLASSES.progress },
  interview_proposed:         { Icon: Calendar,    tone: STATUS_TONE_CLASSES.positive },
  interview_accepted:         { Icon: Calendar,    tone: STATUS_TONE_CLASSES.positive },
  interview_declined:         { Icon: Calendar,    tone: STATUS_TONE_CLASSES.attention },
  interview_cancelled:        { Icon: Calendar,    tone: STATUS_TONE_CLASSES.attention },
  offer_received:             { Icon: Sparkles,    tone: STATUS_TONE_CLASSES.positive },
  credential_verified:        { Icon: ShieldCheck, tone: STATUS_TONE_CLASSES.positive },
  credential_needs_review:    { Icon: ShieldAlert, tone: STATUS_TONE_CLASSES.attention },
  credential_review_dismissed: { Icon: ShieldAlert, tone: STATUS_TONE_CLASSES.attention },
  job_import_submitted:       { Icon: Send,        tone: STATUS_TONE_CLASSES.progress },
  job_import_approved:        { Icon: ShieldCheck, tone: STATUS_TONE_CLASSES.positive },
  job_import_rejected:        { Icon: FileWarning, tone: STATUS_TONE_CLASSES.attention },
  sla_dormant_application:    { Icon: MessageSquare, tone: STATUS_TONE_CLASSES.attention },
  account_email_change_code:  { Icon: Mail,        tone: STATUS_TONE_CLASSES.progress },
  account_phone_change_code:  { Icon: MessageSquare, tone: STATUS_TONE_CLASSES.progress },
  account_recovery_ticket:    { Icon: UserRound,   tone: STATUS_TONE_CLASSES.attention },
  account_recovery_resolved:  { Icon: ShieldCheck, tone: STATUS_TONE_CLASSES.positive },
};
