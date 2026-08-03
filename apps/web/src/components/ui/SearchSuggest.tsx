"use client";

import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { createClient } from "@/lib/supabase/client";
import { useTypeahead } from "@/hooks/useTypeahead";
import { easeCohere } from "@/lib/motion";
import {
  SUGGEST_GROUP_LABELS,
  SuggestPreset,
  SuggestionItem,
  fetchSuggestionsFor,
} from "@/lib/suggest";
import { cn } from "@/lib/utils";
import { SearchInput } from "./SearchInput";
import { useUrlSyncedSearch } from "./UrlSearchField";

/**
 * The shared as-you-type suggestion layer — Google-style: from the first
 * character, an anchored dropdown of matching entities appears and narrows
 * with every keystroke. Picking one applies it to the filter exactly as
 * typing + submitting would; typing WITHOUT picking still live-filters the
 * list (the dropdown augments the existing live search, never replaces it).
 *
 *   - white hairline card, `shadow-float`, 150ms fade/rise in AND out
 *     (motion-safe via useReducedMotion)
 *   - matched substring rendered bold in each row
 *   - keyboard: ↑ ↓ Enter Esc with roving aria-activedescendant; hover syncs
 *   - shimmer row while the first fetch is in flight; honest error and
 *     "No matches for 'gx'" rows
 *   - overlays the page (absolute) — zero layout shift, never pushes content
 */

/** Bold the first case-insensitive occurrence of `query` inside `text`. */
export function HighlightMatch({ text, query }: { text: string; query: string }) {
  const q = query.trim();
  if (!q) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <span className="font-semibold text-cohere-ink">{text.slice(idx, idx + q.length)}</span>
      {text.slice(idx + q.length)}
    </>
  );
}

/**
 * The dropdown shell — ONE entrance/exit for every suggestion dropdown in the
 * product (search fields AND the admin topbar), so they all feel identical.
 */
export function SuggestShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      initial={{ opacity: 0, y: reduced ? 0 : -4, pointerEvents: "none" }}
      // The exiting copy is non-interactive: it is invisible, but it still
      // overlays the results until the exit finishes (and can linger when
      // frames are throttled), so it must never swallow a click.
      animate={{ opacity: 1, y: 0, pointerEvents: "auto" }}
      exit={{ opacity: 0, y: reduced ? 0 : -4, pointerEvents: "none" }}
      transition={{ duration: reduced ? 0 : 0.15, ease: easeCohere }}
      className={cn(
        "absolute left-0 right-0 top-full z-40 mt-1 max-h-80 overflow-auto rounded-[10px] border border-hairline bg-white shadow-float",
        className,
      )}
    >
      {children}
    </motion.div>
  );
}

function ShimmerRow() {
  return (
    <div className="px-3 py-2.5" aria-hidden="true">
      <div className="h-3.5 w-2/5 animate-pulse rounded bg-stone" />
      <div className="mt-1.5 h-3 w-3/5 animate-pulse rounded bg-stone/70" />
    </div>
  );
}

/**
 * Controlled suggestion search — input + dropdown. Parents own the value
 * (URL-synced pages use `SearchSuggestField`; in-memory lists pass their own
 * state + a local fetcher).
 */
export function SearchWithSuggestions({
  value,
  onChange,
  onPick,
  onEnter,
  fetchSuggestions,
  groupLabels = SUGGEST_GROUP_LABELS,
  placeholder,
  label,
  className,
  inputClassName,
  loading = false,
  ariaLabel,
  maxLength,
  minChars = 1,
  debounceMs = 200,
  ready = true,
}: {
  value: string;
  onChange: (v: string) => void;
  /** A suggestion was chosen (click or Enter). Apply it to the filter. */
  onPick: (item: SuggestionItem) => void;
  /** Enter with no active suggestion — flush the typed text immediately. */
  onEnter?: () => void;
  fetchSuggestions: (q: string, signal: AbortSignal) => Promise<SuggestionItem[]>;
  /** kind → group header text. Headers render whenever the kind changes. */
  groupLabels?: Record<string, string>;
  placeholder?: string;
  label?: string;
  className?: string;
  inputClassName?: string;
  /** The LIST's pending state — shows the inline spinner in the input. */
  loading?: boolean;
  ariaLabel?: string;
  maxLength?: number;
  minChars?: number;
  debounceMs?: number;
  /**
   * False while the suggestion source is not yet usable (e.g. the session
   * token is still resolving). Suppresses fetching and shows the loading
   * shimmer instead of "No matches", so a not-ready source never reads as
   * an honest empty result. Flipping it to true re-runs the query.
   */
  ready?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const reactId = useId();
  const listboxId = `suggest-${reactId}`;

  // Blanking the query while not ready both skips the fetch and makes the
  // effect re-run (query "" → value) the moment the source becomes usable.
  const {
    results,
    loading: fetching,
    error,
  } = useTypeahead(ready ? value : "", fetchSuggestions, { minChars, debounceMs });

  // New results: reset the roving highlight (nothing pre-selected — Enter
  // with no highlight submits the typed text, exactly like plain search).
  useEffect(() => {
    setActiveIdx(-1);
  }, [results]);

  // Close on click outside.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  // A pick closes the dropdown for good until the user types again. Applying
  // the filter re-renders the page and can hand focus back to the input, which
  // would otherwise re-open the panel over the results the user just chose.
  const pickedRef = useRef(false);

  const pick = (item: SuggestionItem) => {
    pickedRef.current = true;
    setOpen(false);
    onPick(item);
  };

  const showDropdown = open && !pickedRef.current && value.trim().length >= minChars;

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown) {
      if (e.key === "Enter" && onEnter) {
        e.preventDefault();
        onEnter();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(-1, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIdx >= 0 && results[activeIdx]) pick(results[activeIdx]);
      else if (onEnter) {
        setOpen(false);
        onEnter();
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const activeOptionId =
    showDropdown && activeIdx >= 0 && results[activeIdx]
      ? `${listboxId}-opt-${activeIdx}`
      : undefined;

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <SearchInput
        value={value}
        onChange={(v) => {
          pickedRef.current = false; // typing resumes suggestions
          onChange(v);
          setOpen(true);
        }}
        placeholder={placeholder}
        label={label}
        loading={loading}
        inputClassName={inputClassName}
        ariaLabel={ariaLabel}
        maxLength={maxLength}
        onKeyDown={handleKey}
        onFocus={() => setOpen(true)}
        onBlur={(e) => {
          // Tab away (focus left the whole widget) closes the dropdown.
          if (!rootRef.current?.contains(e.relatedTarget as Node)) setOpen(false);
        }}
        combobox={{ expanded: showDropdown, listboxId, activeOptionId }}
      />

      <AnimatePresence>
        {showDropdown && (
          <SuggestShell>
            {error ? (
              <div className="px-3 py-2.5 text-caption text-error-red" role="alert">
                Suggestions are unavailable right now. Typing still filters the list.
              </div>
            ) : (!ready || fetching) && results.length === 0 ? (
              <ShimmerRow />
            ) : results.length === 0 ? (
              <div className="px-3 py-2.5 text-caption text-slate">
                No matches for &ldquo;{value.trim()}&rdquo;
              </div>
            ) : (
              <ul id={listboxId} role="listbox">
                {results.map((r, i) => (
                  <li key={`${r.kind}:${r.label}:${i}`}>
                    {(i === 0 || results[i - 1].kind !== r.kind) && groupLabels[r.kind] && (
                      <div
                        aria-hidden="true"
                        className="border-b border-hairline/60 bg-stone/40 px-3 py-1 text-micro font-medium text-slate-muted"
                      >
                        {groupLabels[r.kind]}
                      </div>
                    )}
                    <button
                      type="button"
                      id={`${listboxId}-opt-${i}`}
                      role="option"
                      aria-selected={i === activeIdx}
                      tabIndex={-1}
                      onMouseEnter={() => setActiveIdx(i)}
                      onMouseDown={(e) => {
                        e.preventDefault(); // keep focus in the input
                        pick(r);
                      }}
                      className={cn(
                        "block w-full px-3 py-2 text-left text-[13px] transition-colors duration-150",
                        i === activeIdx ? "bg-parchment text-cohere-ink" : "text-slate",
                      )}
                    >
                      <span className="block truncate">
                        <HighlightMatch text={r.label} query={value} />
                      </span>
                      {r.sublabel && (
                        <span className="block truncate text-micro text-slate-muted">
                          {r.sublabel}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </SuggestShell>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * URL-synced suggestion search field for list pages — UrlSearchField's exact
 * live-filter behavior (debounced URL writes, back/forward adoption, Enter
 * flush) PLUS the suggestion dropdown. `suggest` names a preset from
 * lib/suggest.ts (a string, so server components can render this directly).
 *
 * `paramForKind` routes a picked suggestion of a given kind onto a different
 * filter param (browse page: employer → ?employer=); `pickValue` maps a
 * picked item to the applied value when the label isn't the filter value
 * (trade name → family code). Both optional; default is "apply the label to
 * this field's own param" — identical to typing it and pressing Enter.
 */
export function SearchSuggestField({
  param = "q",
  suggest,
  paramForKind,
  pickValue,
  placeholder,
  label,
  className,
  inputClassName,
  debounceMs = 250,
  resetParams = ["page"],
  maxLength,
  token: tokenProp,
}: {
  param?: string;
  suggest: SuggestPreset;
  paramForKind?: Record<string, string>;
  pickValue?: (item: SuggestionItem) => string;
  placeholder?: string;
  label?: string;
  className?: string;
  inputClassName?: string;
  debounceMs?: number;
  resetParams?: string[];
  maxLength?: number;
  /** Pass when the parent already holds a session token; otherwise self-fetched. */
  token?: string;
}) {
  const { value, setValue, apply, applyOther, isPending, urlValue } = useUrlSyncedSearch({
    param,
    debounceMs,
    resetParams,
  });

  const [selfToken, setSelfToken] = useState<string | null>(null);
  useEffect(() => {
    if (tokenProp) return;
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setSelfToken(data.session?.access_token ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, sess) =>
      setSelfToken(sess?.access_token ?? null),
    );
    return () => sub.subscription.unsubscribe();
  }, [tokenProp]);
  const token = tokenProp ?? selfToken;

  return (
    <SearchWithSuggestions
      value={value}
      onChange={setValue}
      onEnter={() => apply(value)}
      onPick={(item) => {
        const target = paramForKind?.[item.kind] ?? param;
        const applied = pickValue ? pickValue(item) : item.label;
        if (target === param) {
          setValue(applied);
          apply(applied);
        } else {
          setValue("");
          applyOther(target, applied);
        }
      }}
      ready={!!token}
      fetchSuggestions={(q, signal) =>
        token ? fetchSuggestionsFor(suggest, q, token, signal) : Promise.resolve([])
      }
      placeholder={placeholder}
      label={label}
      className={className}
      inputClassName={inputClassName}
      loading={isPending || value !== urlValue}
      maxLength={maxLength}
    />
  );
}
