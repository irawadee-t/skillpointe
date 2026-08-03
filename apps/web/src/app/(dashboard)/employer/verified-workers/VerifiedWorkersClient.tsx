"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  ShieldCheck,
  BadgeCheck,
  MapPin,
  X,
  CircleDashed,
  CalendarDays,
  Loader2,
  MessageSquare,
} from "lucide-react";

import {
  SearchResponse,
  WorkerCard,
  VerifyResponse,
  searchVerifiedWorkers,
  verifyWorker,
} from "@/lib/api/verifiedWorkers";
import {
  PageHeader,
  SearchSuggestField,
  UrlSearchField,
  UrlSelectField,
  UrlMultiSelectField,
  UrlDateField,
  ActiveFilterChips,
  FilterBar,
  FilterGroup,
  describeActiveFilters,
  type FilterChipDef,
  CREDENTIAL_CHIP_CLASS,
  VERIFICATION_LEVEL_META,
  statusChipClass,
} from "@/components/ui";
import { apiFetch } from "@/lib/api/client";
import { easeCohere } from "@/lib/motion";
import { toSearchParams } from "./searchParams";

const CREDENTIAL_TYPE_OPTIONS = [
  { value: "certification", label: "Certification" },
  { value: "license", label: "License" },
  { value: "degree", label: "Degree" },
  { value: "apprenticeship", label: "Apprenticeship" },
  { value: "safety", label: "Safety" },
  { value: "union", label: "Union" },
];

const VERIFICATION_OPTIONS = [
  { value: "1", label: "Institution-verified or higher" },
  { value: "2", label: "SKILLED-verified" },
];

const AVAILABILITY_NOW = [{ value: "now", label: "Available now" }];

const ACTIVITY_OPTIONS = [
  { value: "30", label: "Active in last 30 days" },
  { value: "90", label: "Active in last 90 days" },
  { value: "365", label: "Active in last year" },
];

const RELOCATE_OPTIONS = [
  { value: "true", label: "Open to relocation" },
  { value: "false", label: "Not relocating" },
];

/* Credential-name chips share ONE base style everywhere (CREDENTIAL_CHIP_CLASS).
 * Verification level is an affix — a small green check + label — never a
 * recolor of the credential name. See DESIGN_CONTRACT.md, "Status & chip
 * color semantics". */

export function VerifiedWorkersClient({
  initial,
  token,
}: {
  initial: SearchResponse;
  token: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [data, setData] = useState<SearchResponse>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<WorkerCard | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const firstRun = useRef(true);

  const spRecord = useMemo(() => {
    const rec: Record<string, string | undefined> = {};
    searchParams.forEach((v, k) => {
      rec[k] = v;
    });
    return rec;
  }, [searchParams]);

  // Every filter is URL-synced (the Url* fields write the query string), so
  // ONE effect keyed on the URL drives all fetches — back/forward and shared
  // links restore and re-run the exact same search.
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return; // initial data was fetched server-side from the same URL
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    searchVerifiedWorkers(token, toSearchParams(spRecord), { signal: controller.signal })
      .then((res) => {
        if (controller.signal.aborted) return;
        setData(res);
      })
      .catch((e) => {
        if (controller.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
        setError(
          spRecord.near_city
            ? `Search failed. Check the city name ("${spRecord.near_city}") and try again.`
            : "Search failed. Please try again.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [spRecord, token]);

  const setPage = (nextPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextPage > 1) params.set("page", String(nextPage));
    else params.delete("page");
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const page = spRecord.page ? Math.max(1, parseInt(spRecord.page)) : 1;
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  const chipFields: FilterChipDef[] = [
    { param: "q", label: "Keyword" },
    { param: "trades", label: "Trade", multi: true, options: data.facets.trades.map((t) => ({ value: t.code, label: t.name })) },
    { param: "credential", label: "Credential", options: data.facets.credentials.map((c) => ({ value: c.code, label: c.name })) },
    { param: "credential_types", label: "Type", multi: true, options: CREDENTIAL_TYPE_OPTIONS },
    { param: "min_level", label: "Verification", options: VERIFICATION_OPTIONS },
    { param: "state", label: "State" },
    { param: "available_by", label: "Available", options: AVAILABILITY_NOW },
    { param: "relocate", label: "Relocation", options: RELOCATE_OPTIONS },
    { param: "near_city", label: "Near" },
    { param: "near_state", label: "City's state" },
    { param: "active_within_days", label: "Activity", options: ACTIVITY_OPTIONS },
  ];
  const hasFilters = chipFields.some((f) => !!spRecord[f.param]);
  const hasKeywordQuery = !!spRecord.q?.trim();
  const filterSentence = describeActiveFilters(spRecord, chipFields);

  const from = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.page * data.page_size, data.total);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Hiring"
          title="Verified workers"
          lead="Discover skilled-trades workers with SKILLED-verified credentials. Only workers who consented to share with employers appear here."
        />

        {/* Filters — URL-synced, instant-apply; 3 primary controls, the rest
            behind "More filters". Applied hidden filters stay visible as chips. */}
        <div data-tour-id="workers-filters">
        <FilterBar
          footer={<ActiveFilterChips fields={chipFields} className="mt-3" />}
          moreParams={[
              "credential",
              "credential_types",
              "min_level",
              "available_by",
              "relocate",
              "near_city",
              "near_state",
              "active_within_days",
            ]}
            primary={
              <>
                <SearchSuggestField
                  param="q"
                  suggest="verified-workers"
                  token={token}
                  label="Keyword (ranks by relevance)"
                  placeholder="e.g. welding, EPA, forklift…"
                  className="flex-1 min-w-[200px]"
                  inputClassName="px-3 py-2 pl-9 text-body"
                />
                <UrlMultiSelectField
                  param="trades"
                  label="Trade"
                  options={data.facets.trades.map((t) => ({ value: t.code, label: t.name }))}
                  className="min-w-[170px]"
                />
                <UrlSearchField
                  param="state"
                  label="State"
                  placeholder="GA"
                  maxLength={2}
                  uppercase
                  className="min-w-[90px]"
                  inputClassName="px-3 py-2 pl-9 text-body"
                />
              </>
            }
          >
            <FilterGroup label="Credentials">
              <UrlSelectField
                param="credential"
                label="Credential"
                className="min-w-[160px]"
                selectClassName="px-2 py-2 text-body"
                options={[
                  { value: "", label: "Any credential" },
                  ...data.facets.credentials.map((c) => ({ value: c.code, label: c.name })),
                ]}
              />
              <UrlMultiSelectField
                param="credential_types"
                label="Credential type"
                options={CREDENTIAL_TYPE_OPTIONS}
                className="min-w-[150px]"
              />
              <UrlSelectField
                param="min_level"
                label="Verification"
                className="min-w-[160px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any verified" }, ...VERIFICATION_OPTIONS]}
              />
            </FilterGroup>
            <FilterGroup label="Availability">
              <UrlSelectField
                param="available_by"
                label="Availability"
                className="min-w-[140px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...AVAILABILITY_NOW]}
              />
              <UrlDateField
                param="available_by"
                label="…or available by"
                className="min-w-[140px]"
                inputClassName="px-2 py-1.5 text-body"
              />
              <UrlSelectField
                param="relocate"
                label="Relocation"
                className="min-w-[140px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...RELOCATE_OPTIONS]}
              />
              <UrlSelectField
                param="active_within_days"
                label="Last active"
                className="min-w-[160px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any time" }, ...ACTIVITY_OPTIONS]}
              />
            </FilterGroup>
            {/* One reachability control: the city being commuted to, plus the
                2-letter state that disambiguates it for geocoding. Distinct
                from the primary "State" filter, which is the worker's home
                state. */}
            <FilterGroup label="Reachable from a city (worker's commute radius covers it)">
              <UrlSearchField
                param="near_city"
                label="City"
                placeholder="Carrollton…"
                className="min-w-[150px]"
                inputClassName="px-3 py-2 pl-9 text-body"
              />
              <UrlSearchField
                param="near_state"
                label="City's state"
                placeholder="GA"
                maxLength={2}
                uppercase
                className="min-w-[90px]"
                inputClassName="px-3 py-2 pl-9 text-body"
              />
            </FilterGroup>
        </FilterBar>
        </div>

        {/* Result count — same predicates as the list (server-enforced parity) */}
        <p className="text-body text-slate" aria-live="polite">
          {loading
            ? "Searching…"
            : `Showing ${from}–${to} of ${data.total} ${hasFilters ? "matching " : ""}verified workers`}
        </p>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
            {error}
          </p>
        )}

        {/* Results — the grid softens (opacity) while a new search is in
            flight and the fresh set fades in: a smooth narrowing, never a
            flash. Motion-safe: collapses to an instant swap. */}
        <div
          data-tour-id="workers-results"
          className={
            "transition-opacity duration-150 motion-reduce:transition-none " +
            (loading ? "opacity-60" : "opacity-100")
          }
        >
        {data.workers.length === 0 ? (
          <div className="rounded-[10px] border border-hairline bg-white p-10 text-center">
            <ShieldCheck className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
            <p className="mt-3 text-[1.0625rem] font-medium text-cohere-ink">
              {hasFilters ? "No verified workers match these filters" : "No verified workers yet"}
            </p>
            <p className="mt-1 text-body text-slate">
              {hasFilters
                ? `Active filters: ${filterSentence || "none"}. Remove one, or clear all to widen the results.`
                : "Only workers who opted into employer sharing appear here."}
            </p>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.workers.map((w) => (
              <button
                key={w.applicant_id}
                onClick={() => setSelected(w)}
                className="rounded-[14px] border border-hairline bg-white p-5 text-left transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="text-[1.0625rem] font-medium text-cohere-ink">{w.name}</h3>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-caption text-slate">
                      {w.trade && <span>{w.trade}</span>}
                      {(w.city || w.state) && (
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3.5 w-3.5 text-slate-muted" />
                          {[w.city, w.state].filter(Boolean).join(", ")}
                        </span>
                      )}
                      {w.willing_to_relocate && <span className="text-cohere-green">Open to relocate</span>}
                      {w.available_from && <span>Available {w.available_from}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className={statusChipClass("positive")}>
                      <ShieldCheck className="h-3 w-3" /> {w.verified_count} verified
                    </span>
                    {/* Relevance is a SEARCH signal, not a match score — only
                        meaningful (and only shown) when a keyword query ranks
                        the list. Never labeled "match". */}
                    {hasKeywordQuery && (
                      <span className="text-micro text-slate-muted tabular-nums" title="How closely this worker matches your keyword search">
                        {Math.round(w.relevance * 100)}% search relevance
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {w.top_credentials.map((c, i) => (
                    <span
                      key={i}
                      className={CREDENTIAL_CHIP_CLASS}
                      title={VERIFICATION_LEVEL_META[c.verification_level]?.label}
                    >
                      {c.verification_level >= 1 && (
                        <BadgeCheck className="h-3 w-3 text-cohere-green" aria-hidden="true" />
                      )}
                      {c.canonical_name}
                      {c.verification_level >= 1 && <span className="sr-only">, verified</span>}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-micro font-medium text-cohere-blue">SKILLED Verify →</p>
              </button>
            ))}
          </div>
        )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between text-caption text-slate">
            <span>
              Page {data.page} of {totalPages}, {data.total} workers
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(page - 1)}
                disabled={page <= 1 || loading}
                className="btn-pill-outline disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(page + 1)}
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
  const router = useRouter();
  const [data, setData] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messaging, setMessaging] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);

  // This worker consented to employer discovery, and the messaging flow is the
  // sanctioned contact channel (contact details are never shown here) — so the
  // modal ends in a real next step, not a cul-de-sac.
  async function startConversation() {
    setMessaging(true);
    setMessageError(null);
    try {
      const conv = await apiFetch<{ conversation_id: string }>("/conversations", token, {
        method: "POST",
        body: JSON.stringify({ applicant_id: worker.applicant_id }),
      });
      router.push(`/employer/messages/${conv.conversation_id}`);
    } catch {
      setMessageError("Could not open a conversation. Please try again.");
      setMessaging(false);
    }
  }

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
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-6"
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
        {/* White header — the green lives in a small verification affix, not a
            solid block (contract: verification is an affix, never a recolor). */}
        <div className="border-b border-hairline bg-white p-5">
          <div className="flex items-start justify-between">
            <div>
              <span className="inline-flex items-center gap-1.5 text-caption font-medium text-cohere-green">
                <ShieldCheck className="h-4 w-4" /> SKILLED Verify
              </span>
              <h2 className="mt-1 text-[1.25rem] font-semibold text-cohere-ink">{worker.name}</h2>
              <p className="mt-0.5 text-caption text-slate">
                {[worker.trade, [worker.city, worker.state].filter(Boolean).join(", ")]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            </div>
            <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-cohere-ink">
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
                {data.verified_count} verified credential{data.verified_count !== 1 ? "s" : ""} checked by SKILLED, tamper-proof.
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
                        <span className={statusChipClass(VERIFICATION_LEVEL_META[c.verification_level]?.tone ?? "neutral", "shrink-0")}>
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

        {/* Footer — the next step. Consented workers can be messaged directly
            through the DM flow (the platform's contact channel; contact
            details stay private). */}
        <div className="border-t border-hairline bg-white p-4">
          {messageError && (
            <p className="mb-2 text-caption text-error-red" role="alert">{messageError}</p>
          )}
          <div className="flex items-center justify-between gap-3">
            <p className="text-micro text-slate-muted">
              This worker consented to be contacted by employers on SKILLED.
            </p>
            <button
              onClick={startConversation}
              disabled={messaging}
              className="btn-primary inline-flex shrink-0 items-center gap-1.5 disabled:opacity-50"
            >
              {messaging ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MessageSquare className="h-4 w-4" />
              )}
              {messaging ? "Opening…" : "Message"}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
