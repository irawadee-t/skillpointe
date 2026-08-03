"use client";

import { Loader2, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Presentational live-search input — search icon, subtle inline spinner while
 * results are loading, and a clear (×) button. Controlled: the parent narrows
 * its list on every `onChange` (debounce upstream if the list is server-driven;
 * in-memory lists can filter instantly).
 *
 * This is THE search-bar shell for the product — do not hand-roll per page.
 */
export function SearchInput({
  value,
  onChange,
  placeholder,
  loading = false,
  label,
  className,
  inputClassName,
  onEnter,
  onKeyDown,
  onFocus,
  onBlur,
  ariaLabel,
  autoFocus,
  maxLength,
  combobox,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  /** Show the inline spinner (server-driven lists while a request is in flight). */
  loading?: boolean;
  /** Optional mono-label rendered above the input. */
  label?: string;
  className?: string;
  inputClassName?: string;
  /** Fires on Enter — an immediate "search now" trigger (typing already filters live). */
  onEnter?: () => void;
  /** Raw keydown hook (suggestion dropdowns own ↑ ↓ Enter Esc). Runs first;
      call e.preventDefault() to suppress the built-in Enter behavior. */
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onFocus?: () => void;
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  ariaLabel?: string;
  autoFocus?: boolean;
  maxLength?: number;
  /** ARIA 1.2 combobox wiring when a suggestion listbox is attached. */
  combobox?: {
    expanded: boolean;
    listboxId: string;
    activeOptionId?: string;
  };
}) {
  return (
    <div className={className}>
      {label && <span className="mono-label mb-1.5 block">{label}</span>}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-slate-muted"
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            onKeyDown?.(e);
            if (e.defaultPrevented) return;
            if (e.key === "Enter" && onEnter) {
              e.preventDefault();
              onEnter();
            }
          }}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          aria-label={ariaLabel ?? placeholder ?? "Search"}
          autoFocus={autoFocus}
          maxLength={maxLength}
          role={combobox ? "combobox" : undefined}
          aria-expanded={combobox ? combobox.expanded : undefined}
          aria-controls={combobox ? combobox.listboxId : undefined}
          aria-autocomplete={combobox ? "list" : undefined}
          aria-activedescendant={combobox?.activeOptionId}
          className={cn("input-cohere w-full pl-9 pr-8", inputClassName)}
        />
        {loading ? (
          <Loader2
            className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-slate-muted"
            aria-hidden="true"
          />
        ) : value ? (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-slate-muted transition-colors hover:text-cohere-ink"
          >
            <X className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
        ) : null}
      </div>
    </div>
  );
}
