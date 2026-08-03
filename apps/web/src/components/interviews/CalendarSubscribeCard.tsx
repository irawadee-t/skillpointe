"use client";

/**
 * "Subscribe in your calendar app" — the quiet affordance that makes external
 * calendars stay in sync without OAuth. Fetches the user's personal ICS feed
 * URL (signed, revocable token) lazily on expand, offers copy + reset, and —
 * only when the corresponding OAuth keys are provisioned server-side — shows
 * "Connect Google Calendar / Connect Outlook" buttons that start the real
 * auth-code + PKCE flow (the READ tier: your busy times overlaid on the
 * interview time grid). Connections are managed in account settings.
 */

import { useState } from "react";
import { CalendarClock, Check, Copy, Loader2, RefreshCw } from "lucide-react";

import { API_BASE } from "@/lib/api/client";
import {
  CalendarFeedInfo, CalendarProviders,
  getCalendarFeed, getCalendarProviders, rotateCalendarFeed,
  startCalendarConnect,
} from "@/lib/api/transactions";

export function CalendarSubscribeCard({ token }: { token: string }) {
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState<CalendarFeedInfo | null>(null);
  const [providers, setProviders] = useState<CalendarProviders | null>(null);
  const [busy, setBusy] = useState<"load" | "rotate" | "google" | "microsoft" | null>(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const feedUrl = feed ? `${API_BASE}${feed.feed_path}` : null;

  async function expand() {
    setOpen(true);
    if (feed) return;
    setBusy("load");
    setErr(null);
    try {
      const [f, p] = await Promise.all([
        getCalendarFeed(token),
        getCalendarProviders(token).catch(() => null),
      ]);
      setFeed(f);
      setProviders(p);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load your calendar link");
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    if (!feedUrl) return;
    try {
      await navigator.clipboard.writeText(feedUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setErr("Copy failed. Select the URL and copy it manually.");
    }
  }

  async function connect(provider: "google" | "microsoft") {
    setBusy(provider);
    setErr(null);
    try {
      const { authorize_url } = await startCalendarConnect(token, provider);
      window.location.assign(authorize_url);
      // Navigation takes over from here.
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not start the connection");
      setBusy(null);
    }
  }

  async function rotate() {
    setBusy("rotate");
    setErr(null);
    try {
      setFeed(await rotateCalendarFeed(token));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not reset the link");
    } finally {
      setBusy(null);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={expand}
        className="inline-flex items-center gap-1.5 text-caption text-slate transition-colors duration-200 hover:text-cohere-ink"
      >
        <CalendarClock className="h-3.5 w-3.5" /> Subscribe in your calendar app
      </button>
    );
  }

  return (
    <section className="rounded-[14px] border border-hairline bg-white p-4">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-4 w-4 text-cohere-ink" strokeWidth={1.75} />
        <h3 className="text-body font-medium text-cohere-ink">Subscribe in your calendar app</h3>
      </div>
      <p className="mt-1 text-caption text-slate">
        Your confirmed interviews as a live calendar. New bookings and cancellations show up on
        their own. Works with Google Calendar, Outlook, and Apple Calendar.
      </p>

      {err && <p className="mt-2 text-caption text-studio-maroon" role="alert">{err}</p>}
      {busy === "load" && (
        <p className="mt-2 inline-flex items-center gap-2 text-caption text-slate">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Getting your link…
        </p>
      )}

      {feedUrl && (
        <>
          <div className="mt-3 flex items-center gap-2">
            <input
              readOnly
              value={feedUrl}
              onFocus={(e) => e.currentTarget.select()}
              aria-label="Your personal calendar feed URL"
              className="input-cohere flex-1 text-micro text-slate"
            />
            <button
              type="button"
              onClick={copy}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1.5 text-caption font-medium text-cohere-ink transition-colors duration-200 hover:border-cohere-ink"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-cohere-green" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy URL"}
            </button>
          </div>
          <p className="mt-2 text-micro text-slate-muted">
            In your calendar app, choose &ldquo;Add calendar → From URL / Subscribe&rdquo; and paste this link.
            It&rsquo;s personal to you.{" "}
            <button
              type="button"
              onClick={rotate}
              disabled={busy === "rotate"}
              className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-cohere-ink"
            >
              {busy === "rotate" ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Reset the link
            </button>{" "}
            if it ever leaks (the old URL stops working).
          </p>
          {(providers?.google_configured || providers?.outlook_configured) && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
              {providers.google_configured && (
                <button
                  type="button"
                  onClick={() => connect("google")}
                  disabled={busy === "google"}
                  className="btn-pill-outline inline-flex items-center gap-1.5"
                >
                  {busy === "google" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Connect Google Calendar
                </button>
              )}
              {providers.outlook_configured && (
                <button
                  type="button"
                  onClick={() => connect("microsoft")}
                  disabled={busy === "microsoft"}
                  className="btn-pill-outline inline-flex items-center gap-1.5"
                >
                  {busy === "microsoft" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Connect Outlook
                </button>
              )}
              <span className="text-micro text-slate-muted">
                Shows your busy times on the interview grid.{" "}
                <a href="/account/settings#calendar" className="underline underline-offset-2 hover:text-cohere-ink">
                  Manage connections
                </a>
              </span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
