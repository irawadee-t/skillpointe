"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, User, Building2, Briefcase, ArrowRight } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { NotificationTray } from "./NotificationTray";
import { useTypeahead } from "@/hooks/useTypeahead";

type SearchResult =
  | { kind: "applicant"; id: string; label: string; subtitle: string; href: string }
  | { kind: "employer";  id: string; label: string; subtitle: string; href: string }
  | { kind: "job";       id: string; label: string; subtitle: string; href: string };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Fetch per-role search results, unifying the response shape.
 *
 * The three roles hit different endpoints today (no unified /search yet); this
 * function papers over that so the UI can render a clean dropdown regardless.
 */
async function fetchResults(role: string, token: string | null, q: string, signal: AbortSignal): Promise<SearchResult[]> {
  if (!token) return [];
  const auth = { Authorization: `Bearer ${token}` };

  if (role === "admin") {
    // Admin can search applicants + employers.
    const [aRes, eRes] = await Promise.all([
      fetch(`${API_URL}/admin/applicants?q=${encodeURIComponent(q)}&page=1`, { headers: auth, signal }).catch(() => null),
      fetch(`${API_URL}/admin/employers?q=${encodeURIComponent(q)}&page=1`, { headers: auth, signal }).catch(() => null),
    ]);
    const results: SearchResult[] = [];
    if (aRes?.ok) {
      const data = await aRes.json();
      const apps: Array<{ id: string; first_name?: string; last_name?: string; email?: string; city?: string; state?: string }> = data.applicants ?? [];
      for (const a of apps.slice(0, 4)) {
        const name = [a.first_name, a.last_name].filter(Boolean).join(" ") || a.email || "Unnamed";
        results.push({
          kind: "applicant",
          id: a.id,
          label: name,
          subtitle: [a.email, [a.city, a.state].filter(Boolean).join(", ")].filter(Boolean).join(", "),
          href: `/admin/applicants?q=${encodeURIComponent(name)}`,
        });
      }
    }
    if (eRes?.ok) {
      const data = await eRes.json();
      const emps: Array<{ id: string; name: string; industry?: string; city?: string; state?: string }> = data.employers ?? [];
      for (const e of emps.slice(0, 4)) {
        results.push({
          kind: "employer",
          id: e.id,
          label: e.name,
          subtitle: [e.industry, [e.city, e.state].filter(Boolean).join(", ")].filter(Boolean).join(", "),
          href: `/admin/employers/${e.id}`,
        });
      }
    }
    return results;
  }

  if (role === "applicant") {
    // Applicant can search jobs.
    const res = await fetch(`${API_URL}/jobs/browse?q=${encodeURIComponent(q)}&limit=8`, { headers: auth, signal }).catch(() => null);
    if (!res?.ok) return [];
    const data = await res.json();
    const jobs: Array<{ id: string; title_raw: string; employer_name?: string; city?: string; state?: string }> = data.jobs ?? data ?? [];
    return jobs.slice(0, 8).map((j) => ({
      kind: "job" as const,
      id: j.id,
      label: j.title_raw,
      subtitle: [j.employer_name, [j.city, j.state].filter(Boolean).join(", ")].filter(Boolean).join(", "),
      href: `/applicant/jobs?q=${encodeURIComponent(j.title_raw)}`,
    }));
  }

  if (role === "employer") {
    // Employer searches verified workers — the existing endpoint expects filters, not q.
    // For now, route the query as a taxonomy hint on the workers page.
    return [];
  }

  return [];
}

function IconFor({ kind }: { kind: SearchResult["kind"] }) {
  if (kind === "applicant") return <User className="h-3.5 w-3.5 text-studio-maroon" strokeWidth={2} />;
  if (kind === "employer")  return <Building2 className="h-3.5 w-3.5 text-studio-forest" strokeWidth={2} />;
  return <Briefcase className="h-3.5 w-3.5 text-slate" strokeWidth={2} />;
}

export function Topbar({ searchHref, placeholder, role = "admin" }: { searchHref: string; placeholder: string; role?: string }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, sess) => setToken(sess?.access_token ?? null));
    return () => sub.subscription.unsubscribe();
  }, []);

  const { results, loading } = useTypeahead(
    query,
    (q, signal) => fetchResults(role, token, q, signal),
    { minChars: 2, debounceMs: 180 },
  );

  useEffect(() => { setActiveIdx(0); }, [results]);

  const pick = (r: SearchResult) => {
    setOpen(false);
    setQuery("");
    router.push(r.href);
  };

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(results.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (results[activeIdx]) pick(results[activeIdx]);
      else if (query.trim()) router.push(`${searchHref}?q=${encodeURIComponent(query.trim())}`);
    }
    else if (e.key === "Escape") setOpen(false);
  };

  const showDropdown = open && query.trim().length >= 2;

  return (
    <header
      className="sticky top-0 z-30 hidden h-16 items-center gap-4 border-b border-hairline bg-canvas/85 px-8 backdrop-blur md:flex"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
    >
      <div className="relative w-full max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-muted" strokeWidth={1.75} aria-hidden="true" />
        <input
          role="combobox"
          aria-expanded={showDropdown}
          aria-autocomplete="list"
          aria-label={placeholder}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          className="h-10 w-full rounded-md border border-hairline bg-white pl-9 pr-4 text-body text-cohere-ink placeholder:text-slate-muted focus-visible:border-studio-maroon focus-visible:outline-none focus-visible:shadow-focus"
        />

        {showDropdown && (
          <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-96 overflow-auto rounded-md border border-hairline bg-white shadow-medium">
            {loading && results.length === 0 ? (
              <div className="px-3 py-3 text-caption text-slate">Searching…</div>
            ) : results.length === 0 ? (
              <div className="px-3 py-3 text-caption text-slate">
                No matches. Press Enter to search all of <span className="font-medium">{placeholder.replace("Search ", "").replace("…", "")}</span>.
              </div>
            ) : (
              <ul role="listbox">
                {results.map((r, i) => (
                  <li key={`${r.kind}:${r.id}`}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={i === activeIdx}
                      onMouseEnter={() => setActiveIdx(i)}
                      onMouseDown={(e) => { e.preventDefault(); pick(r); }}
                      className={`flex w-full items-start gap-2 border-b border-hairline/60 px-3 py-2.5 text-left last:border-b-0 ${
                        i === activeIdx ? "bg-parchment" : "hover:bg-parchment/60"
                      }`}
                    >
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-hairline bg-white">
                        <IconFor kind={r.kind} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-caption font-medium text-cohere-ink">{r.label}</span>
                        {r.subtitle && (
                          <span className="block truncate text-micro text-slate-muted">{r.subtitle}</span>
                        )}
                      </span>
                      <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-muted" strokeWidth={1.75} />
                    </button>
                  </li>
                ))}
                {query.trim() && (
                  <li>
                    <button
                      type="button"
                      onMouseDown={(e) => { e.preventDefault(); router.push(`${searchHref}?q=${encodeURIComponent(query.trim())}`); setOpen(false); setQuery(""); }}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-micro text-studio-maroon hover:bg-parchment/60"
                    >
                      <span>See all results for &ldquo;{query.trim()}&rdquo;</span>
                      <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
                    </button>
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
      </div>
      <div className="ml-auto relative">
        {token && <NotificationTray token={token} />}
      </div>
    </header>
  );
}
