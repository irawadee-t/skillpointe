"use client";

import { useId, useMemo, useState, ReactNode } from "react";
import { ArrowUpDown, ChevronDown, ChevronUp, Search } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Editorial data table.
 *
 *   • Click a sortable column header to cycle none → asc → desc → none.
 *   • Optional quick-filter input above the table (opt-in via `filterKeys`).
 *   • Zebra rows on warm stone, hover accent, right-aligned numerics.
 *   • Sticky-ish header row for long tables (relies on parent max-height).
 *   • `isRowMuted` softens a row without hiding it (used for k-anon suppressed).
 *
 * Designed to sit inside a bordered white card — the border, hover, and zebra
 * rules do the visual work so there's no need to tint the surface.
 */

export type Column<T> = {
  key: string;
  label: string;
  /** Alignment for the *cell content*. Defaults to "left" for text, "right" for numerics — pass explicitly for numerics. */
  align?: "left" | "right" | "center";
  /** Enable click-to-sort on this column. Requires `sortValue`. */
  sortable?: boolean;
  /** Value used for comparison when sorting. Numbers sort numerically; strings lexicographically. Return null to sort a row last. */
  sortValue?: (row: T) => string | number | null | undefined;
  /** Value used for the quick-filter match. Defaults to the string of the rendered content if omitted. */
  filterValue?: (row: T) => string;
  render: (row: T) => ReactNode;
  /** Optional Tailwind classes applied to the <td> for this column. */
  className?: string;
  /** Optional narrow width — for numeric columns. */
  width?: string;
};

type SortState = { key: string; dir: "asc" | "desc" } | null;

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Show a search input above the table; only filters within these column keys. */
  filterKeys?: string[];
  filterPlaceholder?: string;
  /** Column key to sort by on initial render. */
  defaultSort?: { key: string; dir: "asc" | "desc" };
  /** Mute (soften) a row without hiding it — e.g. k-anon suppressed cohorts. */
  isRowMuted?: (row: T) => boolean;
  /** Rendered instead of the table body when there are 0 rows post-filter. */
  emptyState?: ReactNode;
  /** Optional row click handler — turns the row into a hover target. */
  onRowClick?: (row: T) => void;
  className?: string;
  /** Hard cap on rows rendered (before the "showing X of Y" footer). Omit for no cap. */
  maxRows?: number;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  filterKeys,
  filterPlaceholder = "Filter…",
  defaultSort,
  isRowMuted,
  emptyState,
  onRowClick,
  className,
  maxRows,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<SortState>(defaultSort ?? null);
  const [query, setQuery] = useState("");
  const reactId = useId();
  const tbodyId = `datatable-body-${reactId}`;
  const skipLinkId = `datatable-skip-${reactId}`;

  // Cycle: no sort → asc → desc → no sort.
  function toggleSort(key: string) {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return null;
    });
  }

  const filtered = useMemo(() => {
    if (!query.trim() || !filterKeys?.length) return rows;
    const q = query.trim().toLowerCase();
    const keySet = new Set(filterKeys);
    const relevant = columns.filter((c) => keySet.has(c.key));
    return rows.filter((row) =>
      relevant.some((c) => {
        const value = c.filterValue ? c.filterValue(row) : String(c.render(row) ?? "");
        return value.toLowerCase().includes(q);
      }),
    );
  }, [rows, query, columns, filterKeys]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return filtered;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;   // nulls always last
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sort, columns]);

  const capped = maxRows != null ? sorted.slice(0, maxRows) : sorted;
  const hidden = maxRows != null ? Math.max(0, sorted.length - maxRows) : 0;

  return (
    <div className={cn("space-y-3", className)}>
      {filterKeys?.length ? (
        <div className="relative max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-muted" strokeWidth={1.75} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={filterPlaceholder}
            className="w-full rounded-md border border-hairline bg-white pl-9 pr-3 py-1.5 text-caption text-cohere-ink placeholder:text-slate-muted focus-visible:border-studio-maroon focus-visible:outline-none focus-visible:shadow-focus"
            aria-label={filterPlaceholder}
          />
        </div>
      ) : null}

      {/* Skip-link for keyboard users navigating past a large header row */}
      <a
        id={skipLinkId}
        href={`#${tbodyId}`}
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-40 focus:rounded-md focus:bg-white focus:px-3 focus:py-1.5 focus:text-caption focus:text-cohere-ink focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2"
      >
        Skip to table data
      </a>

      <div className="relative rounded-md border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
        {/* Right-edge fade — signals horizontal scroll on mobile where scrollbars are hidden. */}
        <div
          aria-hidden
          className="pointer-events-none absolute right-0 top-0 z-10 h-full w-8 rounded-r-md bg-gradient-to-l from-white to-transparent md:hidden"
        />
        <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead className="bg-parchment/50">
            <tr className="border-b border-hairline">
              {columns.map((col) => {
                const alignClass = col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left";
                const isActive = sort?.key === col.key;
                const dir = isActive ? sort!.dir : null;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={col.width ? { width: col.width } : undefined}
                    className={cn(
                      "mono-label px-4 py-2.5 select-none",
                      alignClass,
                      col.sortable && "cursor-pointer hover:text-cohere-ink focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2",
                    )}
                    onClick={col.sortable ? () => toggleSort(col.key) : undefined}
                    onKeyDown={
                      col.sortable
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              toggleSort(col.key);
                            }
                          }
                        : undefined
                    }
                    tabIndex={col.sortable ? 0 : undefined}
                    role={col.sortable ? "button" : undefined}
                    aria-label={
                      col.sortable
                        ? `${col.label}, sortable column${
                            isActive ? `, sorted ${dir === "asc" ? "ascending" : "descending"}` : ""
                          }`
                        : undefined
                    }
                    aria-sort={isActive ? (dir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <span className={cn("inline-flex items-center gap-1", col.align === "right" && "flex-row-reverse")}>
                      {col.label}
                      {col.sortable && (
                        <span className="inline-flex h-3 w-3 items-center justify-center text-slate-muted" aria-hidden="true">
                          {dir === "asc" ? (
                            <ChevronUp className="h-3 w-3 text-cohere-ink" strokeWidth={2} />
                          ) : dir === "desc" ? (
                            <ChevronDown className="h-3 w-3 text-cohere-ink" strokeWidth={2} />
                          ) : (
                            <ArrowUpDown className="h-3 w-3 opacity-40" strokeWidth={1.75} />
                          )}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody id={tbodyId}>
            {capped.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-caption text-slate">
                  {emptyState ?? (query ? `No results for "${query}"` : "Nothing to show yet.")}
                </td>
              </tr>
            ) : (
              capped.map((row, i) => {
                const muted = isRowMuted?.(row) ?? false;
                return (
                  <tr
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(
                      "border-b border-hairline/60 last:border-0 transition-colors",
                      i % 2 === 1 && "bg-stone/25",
                      "hover:bg-parchment/60",
                      muted && "bg-stone/40 text-slate",
                      onRowClick && "cursor-pointer",
                    )}
                  >
                    {columns.map((col) => {
                      const alignClass = col.align === "right" ? "text-right tabular-nums" : col.align === "center" ? "text-center" : "text-left";
                      return (
                        <td key={col.key} className={cn("px-4 py-2.5", alignClass, col.className)}>
                          {col.render(row)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        </div>
        {hidden > 0 && (
          <p className="border-t border-hairline bg-parchment/30 px-4 py-2 text-micro text-slate">
            Showing {capped.length} of {sorted.length}
            {sort ? `, sorted by ${columns.find((c) => c.key === sort.key)?.label ?? sort.key} (${sort.dir})` : ""}
            {query ? `, filtered by "${query}"` : ""}
          </p>
        )}
      </div>
    </div>
  );
}
