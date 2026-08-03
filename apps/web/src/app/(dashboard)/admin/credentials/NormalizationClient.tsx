"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Wand2, X } from "lucide-react";

import {
  CredentialSuggestion,
  NormalizationList,
  NormalizationRow,
  adminFixCanonical,
  adminListNormalization,
  suggestCredentials,
} from "@/lib/api/credentials";
import { useTypeahead } from "@/hooks/useTypeahead";
import { MonoLabel } from "@/components/ui";
import { MATCH_METHOD_LABELS, humanizeEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

const FILTERS = [
  { value: "review", label: "Needs review" },
  { value: "unmatched", label: "Unmatched" },
  { value: "all", label: "All" },
] as const;

type Filter = (typeof FILTERS)[number]["value"];

const PAGE_SIZE = 100;

/**
 * Canonical-vs-raw normalization console. Identical raw strings collapse into
 * one fix-once row ("applies to N credentials"); every flag carries the match
 * method + a human reason. Every fix is audited server-side.
 */
export function NormalizationClient({ token }: { token: string }) {
  const [filter, setFilter] = useState<Filter>("review");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<NormalizationList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fixingId, setFixingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await adminListNormalization(token, filter, PAGE_SIZE, offset));
    } catch {
      setError("Could not load credentials. Try refreshing.");
    } finally {
      setLoading(false);
    }
  }, [token, filter, offset]);

  useEffect(() => { void load(); }, [load]);

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonoLabel>Review queue · taxonomy normalization</MonoLabel>
        <div className="flex gap-1.5" role="tablist" aria-label="Normalization filter">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => { setFilter(f.value); setOffset(0); }}
              className={cn(
                "rounded-full border px-3 py-1.5 text-caption transition-colors",
                filter === f.value
                  ? "border-cohere-ink bg-white font-medium text-cohere-ink"
                  : "border-hairline bg-white text-slate hover:text-cohere-ink",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-caption text-slate">
        Workers type credential names free-form; we match them to the standard
        registry automatically. Only uncertain matches (partial, fuzzy, or no
        match) land here for your call. Exact matches never do. Raw text is
        what the worker entered and is never changed; fixing a row sets the
        canonical mapping (optionally for every identical raw string) and is
        written to the audit log.
      </p>

      {error && (
        <p className="mt-3 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
          {error}
        </p>
      )}

      <div className="mt-4 rounded-[10px] border border-hairline bg-white">
        {loading ? (
          <div className="flex items-center gap-2 px-5 py-6 text-caption text-slate">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading credentials…
          </div>
        ) : rows.length === 0 ? (
          <div className="px-5 py-6 text-caption text-slate">
            {filter === "review"
              ? "Nothing needs review. Every credential matched the registry confidently."
              : filter === "unmatched"
                ? "No unmatched credentials. Everything maps to a registry entry."
                : "No credentials yet."}
          </div>
        ) : (
          rows.map((r, i) => (
            <NormalizationRowView
              key={r.id}
              row={r}
              token={token}
              first={i === 0}
              fixing={fixingId === r.id}
              onToggleFix={(open) => setFixingId(open ? r.id : null)}
              onFixed={() => {
                setFixingId(null);
                // A fix may resolve a whole group — reload the honest list.
                void load();
              }}
            />
          ))
        )}
      </div>

      {data && (
        <div className="mt-3 flex items-center justify-between text-caption text-slate">
          <span>
            Showing {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)} of{" "}
            {total.toLocaleString()} distinct raw strings
            {" "}({data.total_credentials.toLocaleString()} credential{data.total_credentials === 1 ? "" : "s"})
          </span>
          {total > PAGE_SIZE && (
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total}
                className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function NormalizationRowView({
  row,
  token,
  first,
  fixing,
  onToggleFix,
  onFixed,
}: {
  row: NormalizationRow;
  token: string;
  first: boolean;
  fixing: boolean;
  onToggleFix: (open: boolean) => void;
  onFixed: (row: NormalizationRow) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [applyToAll, setApplyToAll] = useState(true);
  const { results, loading } = useTypeahead<CredentialSuggestion>(
    fixing ? query : "",
    (q, signal) => suggestCredentials(token, q, signal),
    { minChars: 2, debounceMs: 180 },
  );

  const groupCount = row.group_count ?? 1;

  async function apply(slug: string | null) {
    setBusy(true);
    setError(null);
    try {
      await adminFixCanonical(token, row.id, slug, undefined, applyToAll && groupCount > 1);
      onFixed(row);
    } catch {
      setError("Could not save the fix. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("px-5 py-3.5", !first && "border-t border-hairline")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-body font-medium text-cohere-ink">“{row.raw_name}”</span>
            {groupCount > 1 && (
              <span className="inline-flex items-center rounded-full border border-hairline bg-stone/40 px-2 py-0.5 text-[11px] font-medium text-slate">
                applies to {groupCount} credentials
              </span>
            )}
            {row.needs_review && (
              <span className="inline-flex items-center gap-1 rounded-full border border-cohere-blue bg-cohere-blue px-2 py-0.5 text-[11px] font-medium text-white">
                <AlertTriangle className="h-3 w-3" /> Needs review
              </span>
            )}
          </div>
          <p className="mt-0.5 text-caption text-slate">
            {row.canonical_name ? (
              <>
                Canonical: <span className="text-cohere-ink">{row.canonical_name}</span>
                {" · "}{Math.round(row.normalization_confidence * 100)}% confidence
              </>
            ) : (
              "No canonical match"
            )}
            {groupCount === 1 && row.applicant_name ? <> · {row.applicant_name}</> : null}
            {" · "}{row.source}
          </p>
          {row.match_reason && (
            <p className="mt-0.5 text-caption text-slate-muted">
              {humanizeEnum(row.match_method, MATCH_METHOD_LABELS)}: {row.match_reason}
            </p>
          )}
        </div>
        <button
          onClick={() => onToggleFix(!fixing)}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2.5 py-1.5 text-micro font-medium text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink"
        >
          {fixing ? <X className="h-3.5 w-3.5" /> : <Wand2 className="h-3.5 w-3.5" />}
          {fixing ? "Close" : "Fix mapping"}
        </button>
      </div>

      {fixing && (
        <div className="mt-3 rounded-md border border-border-light bg-stone/40 p-3.5">
          <input
            className="input-cohere w-full"
            placeholder="Search the canonical registry… e.g. OSHA 10"
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search canonical credentials"
          />
          {loading && (
            <p className="mt-2 flex items-center gap-1.5 text-micro text-slate-muted">
              <Loader2 className="h-3 w-3 animate-spin" /> Searching…
            </p>
          )}
          {results.length > 0 && (
            <ul className="mt-2 overflow-hidden rounded-[10px] border border-hairline bg-white">
              {results.map((s) => (
                <li key={s.slug} className="border-t border-hairline first:border-t-0">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => apply(s.slug)}
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-caption text-slate transition-colors hover:bg-parchment/60 hover:text-cohere-ink"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-cohere-ink">{s.name}</span>
                      {s.issuer && <span className="block truncate text-micro text-slate-muted">{s.issuer}</span>}
                    </span>
                    <Check className="h-3.5 w-3.5 shrink-0" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {groupCount > 1 && (
            <label className="mt-2 flex items-center gap-2 text-micro text-slate">
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(e) => setApplyToAll(e.target.checked)}
                className="h-3.5 w-3.5 accent-studio-maroon"
              />
              Apply to all {groupCount} credentials with this exact raw text
            </label>
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={() => apply(null)}
              disabled={busy}
              className="text-micro text-slate underline hover:text-cohere-ink disabled:opacity-50"
            >
              Mark as no canonical match
            </button>
            {busy && <Loader2 className="h-3 w-3 animate-spin text-slate-muted" />}
          </div>
          {error && <p className="mt-2 text-micro text-error-red">{error}</p>}
        </div>
      )}
    </div>
  );
}
