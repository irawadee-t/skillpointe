"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ShieldCheck,
  BadgeCheck,
  MapPin,
  Search,
  X,
  Loader2,
  Award,
  CircleDashed,
  CalendarDays,
} from "lucide-react";

import {
  SearchResponse,
  WorkerCard,
  VerifyResponse,
  searchVerifiedWorkers,
  verifyWorker,
} from "@/lib/api/verifiedWorkers";
import { PageHeader, MonoLabel, MetricCard } from "@/components/ui";
import { easeCohere } from "@/lib/motion";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

function badgeClass(level: number) {
  if (level >= 2) return "bg-cohere-green text-white border-cohere-green";
  if (level >= 1) return "bg-wash-blue text-cohere-blue border-cohere-blue/25";
  return "bg-stone text-slate border-hairline";
}

export function VerifiedWorkersClient({
  initial,
  token,
}: {
  initial: SearchResponse;
  token: string;
}) {
  const [data, setData] = useState<SearchResponse>(initial);
  const [trade, setTrade] = useState("");
  const [credential, setCredential] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<WorkerCard | null>(null);

  async function runSearch(nextPage = 1) {
    setLoading(true);
    setError(null);
    try {
      const res = await searchVerifiedWorkers(token, {
        trade: trade || undefined,
        credential: credential || undefined,
        state: stateFilter || undefined,
        q: q || undefined,
        page: nextPage,
        page_size: PAGE_SIZE,
      });
      setData(res);
      setPage(nextPage);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="SKILLED Pro"
          title="Verified workers"
          lead="Discover skilled-trades workers with SKILLED-verified credentials. Only workers who consented to share with employers appear here."
        />

        {/* Filters */}
        <div className="rounded-md border border-border-light bg-white p-4">
          <label className="mb-3 block">
            <span className="mono-label mb-1.5 block">Keyword (ranks by relevance)</span>
            <input
              className="input-cohere"
              placeholder="e.g. welding, EPA, forklift…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(1); }}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-[1.4fr_1.4fr_0.6fr_auto] sm:items-end">
            <label className="block">
              <span className="mono-label mb-1.5 block">Trade</span>
              <select className="input-cohere" value={trade} onChange={(e) => setTrade(e.target.value)}>
                <option value="">All trades</option>
                {data.facets.trades.map((t) => (
                  <option key={t.code} value={t.code}>{t.name}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mono-label mb-1.5 block">Credential</span>
              <select className="input-cohere" value={credential} onChange={(e) => setCredential(e.target.value)}>
                <option value="">Any credential</option>
                {data.facets.credentials.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mono-label mb-1.5 block">State</span>
              <input
                className="input-cohere"
                maxLength={2}
                placeholder="GA"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
              />
            </label>
            <button onClick={() => runSearch(1)} disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search
            </button>
          </div>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <MetricCard label="Verified workers" value={data.total} icon={ShieldCheck} />
          <MetricCard
            label="Trades represented"
            value={data.facets.trades.length}
            icon={Award}
            tone="stone"
          />
          <MetricCard
            label="Distinct credentials"
            value={data.facets.credentials.length}
            icon={BadgeCheck}
            tone="white"
            className="col-span-2 sm:col-span-1"
          />
        </div>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-error-red">
            {error}
          </p>
        )}

        {/* Results */}
        {data.workers.length === 0 ? (
          <div className="rounded-md border border-border-light bg-white p-10 text-center">
            <ShieldCheck className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
            <p className="mt-3 font-display text-feature text-cohere-ink">No verified workers match</p>
            <p className="mt-1 text-body text-slate">
              Try widening your filters. Only workers who opted into employer sharing appear here.
            </p>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.workers.map((w) => (
              <button
                key={w.applicant_id}
                onClick={() => setSelected(w)}
                className="rounded-md border border-border-light bg-white p-5 text-left transition-colors hover:border-cohere-ink"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="font-display text-feature text-cohere-ink">{w.name}</h3>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-caption text-slate">
                      {w.trade && <span>{w.trade}</span>}
                      {(w.city || w.state) && (
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3.5 w-3.5 text-slate-muted" />
                          {[w.city, w.state].filter(Boolean).join(", ")}
                        </span>
                      )}
                      {w.willing_to_relocate && <span className="text-cohere-green">Open to relocate</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="flex items-center gap-1 rounded-sm bg-cohere-green px-2.5 py-1 text-micro font-medium text-white">
                      <ShieldCheck className="h-3 w-3" /> {w.verified_count} verified
                    </span>
                    <span className="text-micro text-slate-muted tabular-nums" title="Relevance to your search">
                      {Math.round(w.relevance * 100)}% match
                    </span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {w.top_credentials.map((c, i) => (
                    <span
                      key={i}
                      className={cn("rounded-sm border px-2 py-0.5 text-micro", badgeClass(c.verification_level))}
                    >
                      {c.canonical_name}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-micro font-medium text-cohere-blue">SKILLED Verify →</p>
              </button>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between text-caption text-slate">
            <span>
              Page {data.page} of {totalPages}, {data.total} workers
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => runSearch(page - 1)}
                disabled={page <= 1 || loading}
                className="btn-pill-outline disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => runSearch(page + 1)}
                disabled={page >= totalPages || loading}
                className="btn-pill-outline disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      <AnimatePresence>
        {selected && (
          <VerifyModal worker={selected} token={token} onClose={() => setSelected(null)} />
        )}
      </AnimatePresence>
    </main>
  );
}

function VerifyModal({
  worker,
  token,
  onClose,
}: {
  worker: WorkerCard;
  token: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch verified credentials when the modal opens.
  useEffect(() => {
    let active = true;
    verifyWorker(token, worker.applicant_id)
      .then((d) => active && setData(d))
      .catch(() => active && setError("Could not load verification for this worker."));
    return () => {
      active = false;
    };
  }, [token, worker.applicant_id]);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end justify-center bg-studio-dark-cork/40 p-0 sm:items-center sm:p-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="w-full max-w-lg overflow-hidden rounded-t-lg bg-white sm:rounded-lg"
        initial={{ y: 24, opacity: 0, scale: 0.98 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        exit={{ y: 24, opacity: 0, scale: 0.98 }}
        transition={{ duration: 0.3, ease: easeCohere }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Green verify header */}
        <div className="bg-cohere-green p-5 text-white">
          <div className="flex items-start justify-between">
            <div>
              <MonoLabel className="text-white/60">SKILLED Verify</MonoLabel>
              <h2 className="mt-1 font-display text-card text-white">{worker.name}</h2>
              <p className="mt-0.5 text-caption text-white/70">
                {[worker.trade, [worker.city, worker.state].filter(Boolean).join(", ")]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            </div>
            <button onClick={onClose} aria-label="Close" className="text-white/70 hover:text-white">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-5">
          {error ? (
            <p className="text-caption text-error-red">{error}</p>
          ) : !data ? (
            <ul className="space-y-2.5" aria-busy="true" aria-live="polite">
              {[0, 1, 2].map((i) => (
                <li key={i} className="rounded-md border border-border-light p-3.5 animate-pulse">
                  <div className="flex items-start justify-between gap-3">
                    <div className="w-full">
                      <div className="h-4 w-2/3 rounded bg-stone" />
                      <div className="mt-2 flex gap-2">
                        <div className="h-3 w-16 rounded bg-stone" />
                        <div className="h-3 w-24 rounded bg-stone" />
                        <div className="h-3 w-20 rounded bg-stone" />
                      </div>
                    </div>
                    <div className="h-5 w-20 shrink-0 rounded-sm bg-stone" />
                  </div>
                </li>
              ))}
              <li className="sr-only">Loading verified credentials…</li>
            </ul>
          ) : data.credentials.length === 0 ? (
            <p className="py-6 text-center text-body text-slate">No verified credentials on file.</p>
          ) : (
            <>
              <p className="mb-3 flex items-center gap-2 text-caption text-cohere-green">
                <ShieldCheck className="h-4 w-4" />
                {data.verified_count} credential{data.verified_count !== 1 ? "s" : ""} verified by SKILLED — cryptographically signed.
              </p>
              <ul className="space-y-2.5">
                {data.credentials.map((c, i) => {
                  const Icon = c.verification_level >= 2 ? ShieldCheck : c.verification_level >= 1 ? BadgeCheck : CircleDashed;
                  return (
                    <li key={i} className="rounded-md border border-border-light p-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-cohere-ink">{c.canonical_name ?? "—"}</div>
                          <div className="mt-0.5 flex flex-wrap gap-x-3 text-caption text-slate">
                            {c.credential_type && <span className="capitalize">{c.credential_type}</span>}
                            {c.issuer && <span>{c.issuer}</span>}
                            {(c.issued_date || c.expires_date) && (
                              <span className="flex items-center gap-1">
                                <CalendarDays className="h-3.5 w-3.5 text-slate-muted" />
                                {c.issued_date ?? "—"}{c.expires_date ? ` → ${c.expires_date}` : ""}
                              </span>
                            )}
                          </div>
                        </div>
                        <span className={cn("flex shrink-0 items-center gap-1 rounded-sm border px-2 py-1 text-micro font-medium", badgeClass(c.verification_level))}>
                          <Icon className="h-3 w-3" /> {c.verification_badge}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
