"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronDown } from "lucide-react";

import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { SearchInput } from "./SearchInput";
import { cn } from "@/lib/utils";

/**
 * URL-sync engine behind UrlSearchField AND SearchSuggestField: keeps a query
 * param in sync with what the user types (debounced `router.replace` with
 * `scroll: false`), adopts external URL changes (back/forward, Clear link)
 * without stomping in-flight typing, and exposes `applyOther` so a suggestion
 * can land on a DIFFERENT param (e.g. picking a trade on the browse page).
 */
export function useUrlSyncedSearch({
  param = "q",
  debounceMs = 250,
  resetParams = ["page"],
}: {
  param?: string;
  debounceMs?: number;
  resetParams?: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlValue = searchParams.get(param) ?? "";

  const [value, setValue] = useState(urlValue);
  const [isPending, startTransition] = useTransition();
  // Last value THIS field pushed to the URL — lets us tell our own navigation
  // apart from external ones (Clear link, back button) without stomping typing.
  const lastPushed = useRef(urlValue);

  // External URL change (back/forward, Clear link): adopt it.
  useEffect(() => {
    if (urlValue !== lastPushed.current) {
      lastPushed.current = urlValue;
      setValue(urlValue);
    }
  }, [urlValue]);

  const apply = (next: string) => {
    if (next === (searchParams.get(param) ?? "")) return;
    lastPushed.current = next;
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set(param, next);
    else params.delete(param);
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  /** Apply a value to ANOTHER param, clearing this field's own param. */
  const applyOther = (targetParam: string, targetValue: string) => {
    lastPushed.current = "";
    const params = new URLSearchParams(searchParams.toString());
    params.delete(param);
    if (targetValue) params.set(targetParam, targetValue);
    else params.delete(targetParam);
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  const debounced = useDebouncedValue(value, debounceMs);
  useEffect(() => {
    apply(debounced);
    // apply is stable enough for our purposes; key on the debounced text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return { value, setValue, apply, applyOther, isPending, urlValue };
}

/**
 * Live type-ahead search field for SERVER-rendered list pages.
 *
 * Keeps a query param in the URL in sync with what the user types (debounced,
 * `router.replace` with `scroll: false` so refresh/back preserve the search and
 * the page never jumps). The server component re-renders on each URL change, so
 * results narrow with every letter typed. Clearing the input restores the full
 * list. Enter flushes immediately.
 *
 * Use one per text filter — pair with `UrlSelectField` for dropdown filters.
 * When the surface has a suggestion source, use `SearchSuggestField` instead —
 * same URL behavior plus the as-you-type dropdown.
 */
export function UrlSearchField({
  param = "q",
  placeholder,
  label,
  className,
  inputClassName,
  debounceMs = 250,
  resetParams = ["page"],
  maxLength,
  uppercase = false,
}: {
  /** Query-string key this field controls. */
  param?: string;
  placeholder?: string;
  label?: string;
  className?: string;
  inputClassName?: string;
  debounceMs?: number;
  /** Params dropped whenever the value changes (pagination must reset). */
  resetParams?: string[];
  maxLength?: number;
  /** Uppercase the value as typed (state codes). */
  uppercase?: boolean;
}) {
  const { value, setValue, apply, isPending, urlValue } = useUrlSyncedSearch({
    param,
    debounceMs,
    resetParams,
  });

  return (
    <SearchInput
      value={value}
      onChange={(v) => setValue(uppercase ? v.toUpperCase() : v)}
      onEnter={() => apply(value)}
      placeholder={placeholder}
      label={label}
      loading={isPending || value !== urlValue}
      className={className}
      inputClassName={inputClassName}
      maxLength={maxLength}
    />
  );
}

/**
 * URL-synced select — companion to UrlSearchField. Applies immediately on
 * change (no debounce needed for a discrete choice).
 */
export function UrlSelectField({
  param,
  options,
  label,
  className,
  selectClassName,
  resetParams = ["page"],
  defaultValue = "",
}: {
  param: string;
  options: { value: string; label: string }[];
  label?: string;
  className?: string;
  selectClassName?: string;
  resetParams?: string[];
  /** Value shown when the param is absent from the URL. */
  defaultValue?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = searchParams.get(param) ?? defaultValue;
  const [, startTransition] = useTransition();

  const apply = (next: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set(param, next);
    else params.delete(param);
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  return (
    <div className={className}>
      {label && <span className="mono-label mb-1.5 block">{label}</span>}
      <select
        value={current}
        onChange={(e) => apply(e.target.value)}
        aria-label={label ?? param}
        className={cn("input-cohere", selectClassName)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * URL-synced searchable multi-select — the third member of the Url* filter
 * family. Stores selections as ONE comma-separated param (`?families=a,b`),
 * applying instantly on toggle. For long option lists (44 job families) a
 * type-ahead inside the dropdown narrows the choices — never render a
 * 44-item dropdown wall.
 */
export function UrlMultiSelectField({
  param,
  options,
  label,
  placeholder = "Any",
  className,
  resetParams = ["page"],
  searchThreshold = 8,
}: {
  param: string;
  options: { value: string; label: string }[];
  label?: string;
  /** Summary text when nothing is selected. */
  placeholder?: string;
  className?: string;
  resetParams?: string[];
  /** Show the in-dropdown search once options exceed this count. */
  searchThreshold?: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  const selected = useMemo(() => {
    const raw = searchParams.get(param) ?? "";
    return raw ? raw.split(",").filter(Boolean) : [];
  }, [searchParams, param]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = (value: string) => {
    const next = selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value];
    const params = new URLSearchParams(searchParams.toString());
    if (next.length) params.set(param, next.join(","));
    else params.delete(param);
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  const byValue = useMemo(
    () => new Map(options.map((o) => [o.value, o.label])),
    [options],
  );
  const summary =
    selected.length === 0
      ? placeholder
      : selected.length === 1
        ? (byValue.get(selected[0]) ?? selected[0])
        : `${selected.length} selected`;

  const visible = filter
    ? options.filter((o) => o.label.toLowerCase().includes(filter.toLowerCase()))
    : options;

  return (
    <div className={cn("relative", className)} ref={rootRef}>
      {label && <span className="mono-label mb-1.5 block">{label}</span>}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label ?? param}
        className={cn(
          "input-cohere flex w-full items-center justify-between gap-2 text-left",
          selected.length === 0 && "text-slate-muted",
        )}
      >
        <span className="truncate">{summary}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-muted" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute z-30 mt-1 w-full min-w-[220px] rounded-[10px] border border-hairline bg-white py-1 shadow-float"
        >
          {options.length > searchThreshold && (
            <div className="px-2 pb-1 pt-1.5">
              <SearchInput
                value={filter}
                onChange={setFilter}
                placeholder="Filter options…"
                ariaLabel={`Filter ${label ?? param} options`}
                inputClassName="px-2.5 py-1.5 text-caption"
                autoFocus
              />
            </div>
          )}
          <div className="max-h-64 overflow-y-auto">
            {visible.length === 0 ? (
              <p className="px-3 py-2 text-caption text-slate-muted">No options match</p>
            ) : (
              visible.map((o) => {
                const isOn = selected.includes(o.value);
                return (
                  <button
                    key={o.value}
                    type="button"
                    role="option"
                    aria-selected={isOn}
                    onClick={() => toggle(o.value)}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-1.5 text-left text-body transition-colors hover:bg-stone/60",
                      isOn ? "text-cohere-ink" : "text-slate",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border",
                        isOn ? "border-ink bg-ink text-white" : "border-hairline bg-white",
                      )}
                    >
                      {isOn && <Check className="h-3 w-3" strokeWidth={2.5} aria-hidden="true" />}
                    </span>
                    <span className="truncate">{o.label}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * URL-synced date input — companion to UrlSelectField for date-range facets
 * (`posted_from` / `posted_to`). Applies immediately on change.
 */
export function UrlDateField({
  param,
  label,
  className,
  inputClassName,
  resetParams = ["page"],
}: {
  param: string;
  label?: string;
  className?: string;
  inputClassName?: string;
  resetParams?: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = searchParams.get(param) ?? "";
  const [, startTransition] = useTransition();

  const apply = (next: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set(param, next);
    else params.delete(param);
    for (const rp of resetParams) params.delete(rp);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  return (
    <div className={className}>
      {label && <span className="mono-label mb-1.5 block">{label}</span>}
      <input
        type="date"
        value={current}
        onChange={(e) => apply(e.target.value)}
        aria-label={label ?? param}
        className={cn("input-cohere", inputClassName)}
      />
    </div>
  );
}
