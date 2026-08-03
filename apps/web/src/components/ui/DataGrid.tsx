"use client";

/**
 * DataGrid — the operator data-grid foundation on TanStack Table.
 *
 * One generic, typed grid for every admin/employer directory:
 *   - sortable columns with visible sort state (aria-sort + arrow glyph)
 *   - sticky header on a single scroll container
 *   - keyboard row navigation: roving tabindex, Arrow keys / Home / End,
 *     Enter activates the row, Space toggles selection
 *   - multi-select: shift-click ranges, select-all-page, bulk-action slot
 *   - right-aligned tabular-nums numeric cells (column meta.align = "right")
 *   - virtualization (@tanstack/react-virtual) above `virtualizeThreshold`
 *   - empty / loading (skeleton matching the loaded shape — no layout
 *     shift) / error-with-retry states built in
 *
 * Density per the design contract: white ground, hairline row dividers,
 * 44px rows, sentence-case 13px header labels, flat at rest.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp } from "lucide-react";

/** Per-column extras read from `column.meta`. */
export interface DataGridColumnMeta {
  /** "right" renders the cell right-aligned with tabular-nums (numeric). */
  align?: "left" | "right";
  /** Skeleton block width in px for the loading state (default 96). */
  skeletonWidth?: number;
}

export interface DataGridProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  getRowId?: (row: T, index: number) => string;
  /** Loading skeleton keeps the loaded shape — pass while fetching. */
  loading?: boolean;
  /** One human sentence; renders the error state with a retry button. */
  error?: string | null;
  onRetry?: () => void;
  emptyMessage?: string;
  /** Enter key / double-click on a row. */
  onRowActivate?: (row: T) => void;
  /** Adds the selection checkbox column + bulk-action bar. */
  enableSelection?: boolean;
  /** Renders inside the bulk bar when rows are selected. */
  bulkActions?: (selected: T[], clearSelection: () => void) => ReactNode;
  /** Row count above which virtualization kicks in (default 60). */
  virtualizeThreshold?: number;
  /** Fixed row height in px — keyboard nav + virtualizer both rely on it. */
  rowHeight?: number;
  /** Scroll container height when virtualized (default 560). */
  maxHeight?: number;
  initialSorting?: SortingState;
  /** aria-label for the table. */
  label?: string;
  className?: string;
}

const SKELETON_ROWS = 8;

export function DataGrid<T>({
  data,
  columns,
  getRowId,
  loading = false,
  error = null,
  onRetry,
  emptyMessage = "Nothing here yet.",
  onRowActivate,
  enableSelection = false,
  bulkActions,
  virtualizeThreshold = 60,
  rowHeight = 44,
  maxHeight = 560,
  initialSorting = [],
  label,
  className,
}: DataGridProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [focusIndex, setFocusIndex] = useState(0);
  const lastClickedIndex = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  const allColumns = useMemo<ColumnDef<T, unknown>[]>(() => {
    if (!enableSelection) return columns;
    const select: ColumnDef<T, unknown> = {
      id: "__select",
      size: 40,
      enableSorting: false,
      header: ({ table }) => (
        <input
          type="checkbox"
          aria-label="Select all rows on this page"
          className="h-4 w-4 accent-ink"
          checked={table.getIsAllRowsSelected()}
          ref={(el) => {
            if (el) el.indeterminate = table.getIsSomeRowsSelected();
          }}
          onChange={table.getToggleAllRowsSelectedHandler()}
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label="Select row"
          className="h-4 w-4 accent-ink"
          checked={row.getIsSelected()}
          onChange={row.getToggleSelectedHandler()}
          // Click handled on the <td> wrapper so shift-ranges work; stop the
          // row-activate double handling here.
          onClick={(e) => e.stopPropagation()}
        />
      ),
    };
    return [select, ...columns];
  }, [columns, enableSelection]);

  const table = useReactTable({
    data,
    columns: allColumns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableRowSelection: enableSelection,
  });

  const rows = table.getRowModel().rows;
  const virtualized = rows.length > virtualizeThreshold;

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
    enabled: virtualized,
  });

  // Shift-click range selection over the CURRENT sorted order.
  const handleRowClick = useCallback(
    (row: Row<T>, index: number, e: React.MouseEvent) => {
      setFocusIndex(index);
      if (!enableSelection) return;
      if (e.shiftKey && lastClickedIndex.current !== null) {
        const [a, b] = [lastClickedIndex.current, index].sort((x, y) => x - y);
        const next: RowSelectionState = { ...rowSelection };
        for (let i = a; i <= b; i++) next[rows[i].id] = true;
        setRowSelection(next);
      } else {
        row.toggleSelected();
        lastClickedIndex.current = index;
      }
    },
    [enableSelection, rowSelection, rows],
  );

  // Roving tabindex keyboard model.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (rows.length === 0) return;
      const move = (next: number) => {
        e.preventDefault();
        const clamped = Math.max(0, Math.min(rows.length - 1, next));
        setFocusIndex(clamped);
        if (virtualized) virtualizer.scrollToIndex(clamped);
      };
      switch (e.key) {
        case "ArrowDown":
          move(focusIndex + 1);
          break;
        case "ArrowUp":
          move(focusIndex - 1);
          break;
        case "Home":
          move(0);
          break;
        case "End":
          move(rows.length - 1);
          break;
        case "PageDown":
          move(focusIndex + 10);
          break;
        case "PageUp":
          move(focusIndex - 10);
          break;
        case "Enter":
          e.preventDefault();
          onRowActivate?.(rows[focusIndex]?.original as T);
          break;
        case " ":
          if (enableSelection) {
            e.preventDefault();
            rows[focusIndex]?.toggleSelected();
            lastClickedIndex.current = focusIndex;
          }
          break;
      }
    },
    [rows, focusIndex, onRowActivate, enableSelection, virtualized, virtualizer],
  );

  // After arrow-key movement (or virtual scroll), put DOM focus on the row.
  useEffect(() => {
    const el = bodyRef.current?.querySelector<HTMLTableRowElement>(
      `tr[data-index="${focusIndex}"]`,
    );
    if (el && bodyRef.current?.contains(document.activeElement)) el.focus();
  }, [focusIndex, rows.length]);

  const selectedRows = table.getSelectedRowModel().rows.map((r) => r.original);
  const clearSelection = useCallback(() => setRowSelection({}), []);

  const colgroup = (
    <colgroup>
      {table.getAllLeafColumns().map((col) => (
        <col
          key={col.id}
          style={col.id === "__select" ? { width: 40 } : undefined}
        />
      ))}
    </colgroup>
  );

  const header = (
    <thead className="sticky top-0 z-[1] bg-white">
      {table.getHeaderGroups().map((hg) => (
        <tr key={hg.id} className="border-b border-hairline">
          {hg.headers.map((h) => {
            const meta = (h.column.columnDef.meta ?? {}) as DataGridColumnMeta;
            const sortDir = h.column.getIsSorted();
            const sortable = h.column.getCanSort();
            return (
              <th
                key={h.id}
                aria-sort={
                  sortDir === "asc"
                    ? "ascending"
                    : sortDir === "desc"
                      ? "descending"
                      : "none"
                }
                className={`px-3 py-2.5 text-caption font-medium text-slate ${
                  meta.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {h.isPlaceholder ? null : sortable ? (
                  <button
                    type="button"
                    onClick={h.column.getToggleSortingHandler()}
                    className={`inline-flex items-center gap-1 transition-colors duration-200 hover:text-cohere-ink ${
                      sortDir ? "text-cohere-ink" : ""
                    } ${meta.align === "right" ? "flex-row-reverse" : ""}`}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {sortDir === "asc" ? (
                      <ArrowUp aria-hidden size={13} />
                    ) : sortDir === "desc" ? (
                      <ArrowDown aria-hidden size={13} />
                    ) : null}
                  </button>
                ) : (
                  flexRender(h.column.columnDef.header, h.getContext())
                )}
              </th>
            );
          })}
        </tr>
      ))}
    </thead>
  );

  const renderRow = (row: Row<T>, index: number, style?: React.CSSProperties) => (
    <tr
      key={row.id}
      data-index={index}
      tabIndex={index === focusIndex ? 0 : -1}
      aria-selected={enableSelection ? row.getIsSelected() : undefined}
      onClick={(e) => handleRowClick(row, index, e)}
      onDoubleClick={() => onRowActivate?.(row.original)}
      onFocus={() => setFocusIndex(index)}
      style={style}
      className={`border-b border-hairline outline-none transition-colors duration-200 focus-visible:bg-parchment ${
        row.getIsSelected() ? "bg-parchment" : "bg-white hover:bg-canvas"
      } ${onRowActivate || enableSelection ? "cursor-pointer" : ""}`}
    >
      {row.getVisibleCells().map((cell) => {
        const meta = (cell.column.columnDef.meta ?? {}) as DataGridColumnMeta;
        return (
          <td
            key={cell.id}
            className={`truncate px-3 text-label text-cohere-ink ${
              meta.align === "right" ? "text-right tabular-nums" : "text-left"
            }`}
            style={{ height: rowHeight }}
          >
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </td>
        );
      })}
    </tr>
  );

  // ── Error state ─────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        className={`rounded-[10px] border border-hairline bg-white p-6 ${className ?? ""}`}
      >
        <p className="text-body text-cohere-ink">{error}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded-full border border-hairline bg-white px-4 py-1.5 text-button text-cohere-ink transition-colors duration-200 hover:border-ink"
          >
            Try again
          </button>
        ) : null}
      </div>
    );
  }

  // ── Loading skeleton — same shell, same row height, no layout shift ─────
  if (loading) {
    return (
      <div
        className={`overflow-hidden rounded-[10px] border border-hairline bg-white ${className ?? ""}`}
        aria-busy="true"
        aria-label={label ? `${label} (loading)` : "Loading table"}
      >
        <table className="w-full border-collapse">
          {colgroup}
          {header}
          <tbody>
            {Array.from({ length: SKELETON_ROWS }).map((_, ri) => (
              <tr key={ri} className="border-b border-hairline">
                {table.getAllLeafColumns().map((col) => {
                  const meta = (col.columnDef.meta ?? {}) as DataGridColumnMeta;
                  return (
                    <td key={col.id} className="px-3" style={{ height: rowHeight }}>
                      <div
                        className={`relative h-3.5 max-w-full overflow-hidden rounded-full bg-stone ${
                          meta.align === "right" ? "ml-auto" : ""
                        }`}
                        style={{
                          width: col.id === "__select" ? 16 : (meta.skeletonWidth ?? 96),
                        }}
                      >
                        <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/70 to-transparent" />
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ── Empty state ─────────────────────────────────────────────────────────
  if (rows.length === 0) {
    return (
      <div
        className={`rounded-[10px] border border-hairline bg-white ${className ?? ""}`}
      >
        <table className="w-full border-collapse">
          {colgroup}
          {header}
        </table>
        <p className="px-5 py-10 text-center text-caption text-slate-muted">
          {emptyMessage}
        </p>
      </div>
    );
  }

  const totalHeight = virtualizer.getTotalSize();
  const virtualRows = virtualized ? virtualizer.getVirtualItems() : null;
  const padTop = virtualRows?.length ? virtualRows[0].start : 0;
  const padBottom = virtualRows?.length
    ? totalHeight - virtualRows[virtualRows.length - 1].end
    : 0;

  return (
    <div className={className}>
      {enableSelection && selectedRows.length > 0 ? (
        <div className="mb-2 flex items-center gap-3 rounded-[10px] border border-hairline bg-white px-4 py-2">
          <span className="text-caption tabular-nums text-cohere-ink">
            {selectedRows.length} selected
          </span>
          {bulkActions?.(selectedRows, clearSelection)}
          <button
            type="button"
            onClick={clearSelection}
            className="ml-auto text-caption text-slate transition-colors duration-200 hover:text-cohere-ink"
          >
            Clear
          </button>
        </div>
      ) : null}

      <div
        ref={scrollRef}
        onKeyDown={handleKeyDown}
        className="overflow-auto overscroll-contain rounded-[10px] border border-hairline bg-white"
        style={virtualized ? { maxHeight } : undefined}
      >
        <table
          className="w-full border-collapse"
          aria-label={label}
          aria-rowcount={rows.length}
        >
          {colgroup}
          {header}
          <tbody ref={bodyRef}>
            {virtualRows ? (
              <>
                {padTop > 0 ? (
                  <tr aria-hidden style={{ height: padTop }} />
                ) : null}
                {virtualRows.map((v) => renderRow(rows[v.index], v.index))}
                {padBottom > 0 ? (
                  <tr aria-hidden style={{ height: padBottom }} />
                ) : null}
              </>
            ) : (
              rows.map((row, i) => renderRow(row, i))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
