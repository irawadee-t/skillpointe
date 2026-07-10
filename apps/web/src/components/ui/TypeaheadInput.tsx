"use client";

import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { Loader2, Search } from "lucide-react";
import { useTypeahead } from "@/hooks/useTypeahead";
import { cn } from "@/lib/utils";

/**
 * Editorial typeahead input with dropdown of results. Debounced fetch,
 * keyboard navigable (↑ ↓ Enter Esc), click-outside to close.
 *
 *   <TypeaheadInput
 *     placeholder="Search applicants…"
 *     fetch={async (q, signal) => (await fetch(`/api/search?q=${q}`, {signal})).json()}
 *     renderResult={(a) => <span>{a.name}, {a.email}</span>}
 *     onSelect={(a) => router.push(`/admin/applicants/${a.id}`)}
 *     getKey={(a) => a.id}
 *   />
 *
 * a11y: implements the ARIA 1.2 combobox pattern (input owns a listbox of options).
 */
export function TypeaheadInput<T>({
  placeholder,
  fetch,
  renderResult,
  onSelect,
  getKey,
  getLabel,
  className,
  inputClassName,
  minChars = 2,
  emptyLabel = "No matches",
  autoFocus,
  error: externalError,
  ariaLabel,
}: {
  placeholder?: string;
  fetch: (q: string, signal: AbortSignal) => Promise<T[]>;
  renderResult: (item: T, active: boolean) => ReactNode;
  onSelect: (item: T) => void;
  getKey: (item: T) => string;
  /** Optional plain-text label used for the live-region announcement on select. */
  getLabel?: (item: T) => string;
  className?: string;
  inputClassName?: string;
  minChars?: number;
  emptyLabel?: string;
  autoFocus?: boolean;
  /** External error state (e.g. from validation). When set, marks the input aria-invalid. */
  error?: string | null;
  /** Accessible name for the input when there is no visible label. */
  ariaLabel?: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  const reactId = useId();
  const listboxId = `typeahead-listbox-${reactId}`;
  const errorId = `typeahead-error-${reactId}`;
  const statusId = `typeahead-status-${reactId}`;

  const { results, loading, error: fetchError } = useTypeahead(query, fetch, { minChars });
  const error = externalError ?? fetchError;

  useEffect(() => { setActiveIdx(0); }, [results]);

  // Close on click outside.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const pick = (item: T) => {
    onSelect(item);
    setOpen(false);
    const label = getLabel ? getLabel(item) : "item";
    setAnnouncement(`Selected: ${label}`);
  };

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(results.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter" && results[activeIdx]) { e.preventDefault(); pick(results[activeIdx]); }
    else if (e.key === "Escape") setOpen(false);
  };

  const showDropdown = open && query.trim().length >= minChars;
  const activeOptionId = showDropdown && results[activeIdx] ? `${listboxId}-opt-${getKey(results[activeIdx])}` : undefined;

  const describedBy = [
    error ? errorId : null,
    statusId,
  ].filter(Boolean).join(" ") || undefined;

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-muted" strokeWidth={1.75} aria-hidden="true" />
        <input
          type="text"
          role="combobox"
          aria-expanded={showDropdown}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeOptionId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-label={ariaLabel}
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          className={cn(
            "w-full rounded-md border border-hairline bg-white pl-9 pr-3 py-2 text-[13px] text-cohere-ink placeholder:text-slate-muted focus-visible:border-studio-maroon focus-visible:outline-none focus-visible:shadow-focus",
            error && "border-studio-maroon",
            inputClassName,
          )}
        />
        {loading && <Loader2 className="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-slate-muted" aria-hidden="true" />}
      </div>

      {error && (
        <p id={errorId} role="alert" className="mt-1 text-[12px] text-studio-maroon">
          {error}
        </p>
      )}

      {/* SR-only status region for select announcements */}
      <span id={statusId} role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>

      {showDropdown && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-auto rounded-lg border border-hairline bg-white shadow-lg">
          {error ? (
            <div className="px-3 py-2 text-[12px] text-studio-maroon">{error}</div>
          ) : loading && results.length === 0 ? (
            <div className="px-3 py-2 text-[12px] text-slate">Searching…</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-2 text-[12px] text-slate">{emptyLabel}</div>
          ) : (
            <ul id={listboxId} role="listbox">
              {results.map((r, i) => {
                const optId = `${listboxId}-opt-${getKey(r)}`;
                const selected = i === activeIdx;
                return (
                  <li key={getKey(r)} id={optId} role="option" aria-selected={selected}>
                    <button
                      type="button"
                      tabIndex={-1}
                      onMouseEnter={() => setActiveIdx(i)}
                      onClick={() => pick(r)}
                      className={cn(
                        "flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors",
                        selected ? "bg-parchment text-cohere-ink" : "text-slate hover:bg-parchment/60 hover:text-cohere-ink",
                      )}
                    >
                      {renderResult(r, selected)}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
