"use client";

/**
 * Persistent debug bar for admin "view as applicant" mode.
 *
 * Dark ink bar pinned above the applicant UI while an admin is impersonating
 * (read-only): shows who is being viewed, a type-ahead applicant switcher
 * (searches GET /admin/applicants), and an Exit control.
 *
 * Mounted by the dashboard layout only when role === "admin" AND the
 * sp_view_as cookie is set — normal sessions never render this.
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";

import { fetchAdminApplicants, startViewAsApplicant } from "@/lib/api/admin";
import { API_BASE } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/client";
import { useTypeahead } from "@/hooks/useTypeahead";
import {
  clearViewAsClient, readViewAsReturnTo, setViewAsClient, type ViewAsTarget,
} from "@/lib/viewAs";

interface SwitchCandidate {
  id: string;
  name: string;
  email: string | null;
  location: string;
}

export function ViewAsBanner({ target }: { target: ViewAsTarget }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, sess) =>
      setToken(sess?.access_token ?? null),
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const { results, loading } = useTypeahead<SwitchCandidate>(
    query,
    async (q) => {
      if (!token) return [];
      const data = await fetchAdminApplicants(token, { q, page: 1 });
      return data.applicants.slice(0, 8).map((a) => ({
        id: a.id,
        name: [a.first_name, a.last_name].filter(Boolean).join(" ") || "Unnamed",
        email: a.email,
        location: [a.city, a.state].filter(Boolean).join(", "),
      }));
    },
    { minChars: 1, debounceMs: 200 },
  );

  async function switchTo(candidate: SwitchCandidate) {
    if (!token || switching) return;
    setSwitching(true);
    setNotice(null);
    try {
      // Audited session start — one audit_logs row per selection. Works for
      // every applicant, including bulk-imported ones with no login account.
      await startViewAsApplicant(token, candidate.id);
      setViewAsClient({ id: candidate.id, name: candidate.name, email: candidate.email });
      setQuery("");
      setOpen(false);
      router.push("/applicant");
      router.refresh();
    } catch {
      setNotice("Could not switch applicant. Try again.");
    } finally {
      setSwitching(false);
    }
  }

  // Read-only guard: while impersonating, any non-GET API call from the
  // applicant UI is intercepted client-side with a clear notice (the backend
  // also rejects it with 403 — this makes the refusal instant and friendly).
  // The admin's own view-as controls (/admin/* endpoints) are exempt.
  useEffect(() => {
    const orig = window.fetch;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = (
        init?.method ?? (input instanceof Request ? input.method : "GET")
      ).toUpperCase();
      const url =
        typeof input === "string" ? input
        : input instanceof URL ? input.href
        : input.url;
      const isApi = url.startsWith(API_BASE);
      const isAdminEndpoint = url.includes("/admin/");
      if (isApi && !isAdminEndpoint && method !== "GET" && method !== "HEAD") {
        setNotice("Read-only debug session. Changes are disabled while viewing as an applicant.");
        return new Response(
          JSON.stringify({ detail: "Read-only debug session" }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        );
      }
      return orig(input as RequestInfo, init);
    };
    return () => { window.fetch = orig; };
  }, []);

  function exit() {
    clearViewAsClient();
    // Return to the admin route the session started from, not a fixed page.
    router.push(readViewAsReturnTo());
    router.refresh();
  }

  return (
    <div className="relative z-40 bg-ink text-white">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 md:px-6">
        <p className="text-caption text-white/90">
          <span className="font-medium">Debug</span>
          <span className="mx-2 text-white/40" aria-hidden>
            ·
          </span>
          viewing as <span className="font-medium">{target.name}</span>
          {target.email ? <span className="text-white/60"> ({target.email})</span> : null}
          <span className="ml-2 rounded-full border border-white/25 px-2 py-0.5 text-[11px] text-white/70">
            Read-only
          </span>
        </p>

        <div ref={boxRef} className="relative ml-auto flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/50" />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              placeholder="Switch applicant…"
              className="h-8 w-52 rounded-full border border-white/25 bg-transparent pl-8 pr-3 text-caption text-white placeholder:text-white/50 focus:border-white/60 focus:outline-none"
            />
            {open && query.trim().length > 0 && (
              <div className="absolute right-0 top-full z-50 mt-1.5 w-72 overflow-hidden rounded-[10px] border border-hairline bg-white shadow-float">
                {loading && (
                  <p className="px-4 py-3 text-caption text-slate">Searching…</p>
                )}
                {!loading && results.length === 0 && (
                  <p className="px-4 py-3 text-caption text-slate">No applicants found.</p>
                )}
                {!loading &&
                  results.map((r, i) => (
                    <button
                      key={r.id}
                      type="button"
                      disabled={switching}
                      onClick={() => switchTo(r)}
                      className={`block w-full px-4 py-2.5 text-left transition-colors hover:bg-parchment/60 disabled:opacity-50 ${
                        i > 0 ? "border-t border-hairline" : ""
                      }`}
                    >
                      <span className="block truncate text-caption font-medium text-cohere-ink">
                        {r.name}
                      </span>
                      <span className="block truncate text-[11px] text-slate">
                        {[r.email, r.location].filter(Boolean).join(" · ") || "No contact info"}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={exit}
            className="inline-flex h-8 items-center gap-1.5 rounded-full border border-white/25 px-3 text-caption text-white/90 transition-colors hover:border-white/60 hover:text-white"
          >
            <X className="h-3.5 w-3.5" /> Exit
          </button>
        </div>
      </div>
      {notice && (
        <p className="border-t border-white/10 px-4 py-1.5 text-[11px] text-white/70 md:px-6">
          {notice}
        </p>
      )}
    </div>
  );
}
