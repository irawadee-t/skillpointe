import { cn } from "@/lib/utils";

/**
 * Route-segment loading skeletons — the instant first paint for every
 * dashboard tab switch.
 *
 * Why this exists: the App Router only re-shows a `loading.tsx` fallback for
 * the segment that is newly mounted. A single shared `(dashboard)/loading.tsx`
 * boundary is already mounted after first load, so sibling tab switches showed
 * NOTHING until the next page's server render finished. Every main route now
 * ships its own `loading.tsx` built from these pieces, so a click paints a
 * shape-matched shell within one frame while the server streams the real page.
 *
 * Design contract: quiet neutral bars (stone on white/canvas), hairline
 * borders, no spinners, and container widths that match the loaded page so
 * content arrives without layout shift.
 */

function Bar({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-stone/70 motion-reduce:animate-none",
        className,
      )}
      aria-hidden
    />
  );
}

/** Mirrors <PageHeader> — eyebrow, title, optional lead + action button. */
function HeaderSkeleton({
  lead = true,
  actions = false,
}: {
  lead?: boolean;
  actions?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-3">
        <Bar className="h-3 w-28" />
        <Bar className="h-8 w-64 max-w-full" />
        {lead && <Bar className="h-4 w-96 max-w-full" />}
      </div>
      {actions && <Bar className="h-10 w-28 shrink-0" />}
    </div>
  );
}

/** Mirrors a FilterBar — search field + a few filter pills. */
function FilterBarSkeleton() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Bar className="h-10 w-64 max-w-full" />
      <Bar className="h-10 w-28" />
      <Bar className="h-10 w-28" />
      <Bar className="h-10 w-24" />
    </div>
  );
}

/** White card of hairline-divided rows — tables, inboxes, queues, lists. */
function RowsSkeleton({
  rows = 8,
  rowHeight = "py-4",
}: {
  rows?: number;
  rowHeight?: string;
}) {
  return (
    <div className="overflow-hidden rounded-[10px] border border-hairline bg-white">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "flex items-center justify-between gap-4 px-5",
            rowHeight,
            i > 0 && "border-t border-hairline",
          )}
        >
          <div className="min-w-0 flex-1 space-y-2">
            <Bar className="h-4 w-1/2 max-w-xs" />
            <Bar className="h-3 w-1/3 max-w-[10rem]" />
          </div>
          <Bar className="h-4 w-16 shrink-0" />
        </div>
      ))}
    </div>
  );
}

/** Grid of card placeholders — browse/cards pages. */
function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-[10px] border border-hairline bg-white p-5"
        >
          <div className="space-y-2.5">
            <Bar className="h-4 w-3/4" />
            <Bar className="h-3 w-1/2" />
            <Bar className="h-3 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Metric strip + two-column sections — dashboards/analytics. */
function DashboardSkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="rounded-[10px] border border-hairline bg-white p-4"
          >
            <div className="space-y-2.5">
              <Bar className="h-3 w-16" />
              <Bar className="h-6 w-12" />
            </div>
          </div>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-[10px] border border-hairline bg-white p-6">
          <RowLines />
        </div>
        <div className="rounded-[10px] border border-hairline bg-white p-6">
          <RowLines />
        </div>
      </div>
    </>
  );
}

function RowLines() {
  return (
    <div className="space-y-3">
      <Bar className="h-4 w-40" />
      <Bar className="h-3 w-full" />
      <Bar className="h-3 w-5/6" />
      <Bar className="h-3 w-2/3" />
      <Bar className="h-3 w-3/4" />
    </div>
  );
}

/** Stacked labeled-field blocks — profile/settings/forms. */
function FormSkeleton({ sections = 3 }: { sections?: number }) {
  return (
    <>
      {Array.from({ length: sections }).map((_, i) => (
        <div
          key={i}
          className="rounded-[10px] border border-hairline bg-white p-6"
        >
          <div className="space-y-4">
            <Bar className="h-4 w-40" />
            <div className="grid grid-cols-2 gap-4">
              <Bar className="h-10" />
              <Bar className="h-10" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Bar className="h-10" />
              <Bar className="h-10" />
            </div>
          </div>
        </div>
      ))}
    </>
  );
}

/** Message thread — a few alternating bubbles. */
function ThreadSkeleton() {
  return (
    <div className="space-y-4">
      <Bar className="ml-0 h-14 w-2/3 rounded-[10px]" />
      <Bar className="ml-auto h-10 w-1/2 rounded-[10px]" />
      <Bar className="ml-0 h-20 w-3/4 rounded-[10px]" />
      <Bar className="ml-auto h-10 w-2/5 rounded-[10px]" />
    </div>
  );
}

/** Full-height block — the map explorer. */
function MapSkeleton() {
  return <Bar className="h-[60vh] w-full rounded-[10px]" />;
}

export type RouteLoadingVariant =
  | "table" // header + filter bar + row list
  | "list" // header + row list (no filters)
  | "cards" // header + card grid
  | "dashboard" // header + metric strip + two-column sections
  | "detail" // back-crumb + header + content blocks
  | "form" // header + stacked field sections
  | "thread" // header + message bubbles
  | "map"; // header + full-height canvas

export type RouteLoadingWidth =
  | "shell" // <main py-8> + .page-shell   (most pages)
  | "narrow" // max-w-3xl                   (profile, resume, settings)
  | "wide"; // p-6 md:p-8 + max-w-5xl      (matches, admin applicants grid)

/**
 * One-line route skeleton for `loading.tsx` files. Pick the variant that
 * matches the page's loaded shape so content streams in without layout shift.
 */
export function RouteLoading({
  variant = "list",
  width = "shell",
  rows = 8,
  headerActions = false,
}: {
  variant?: RouteLoadingVariant;
  width?: RouteLoadingWidth;
  rows?: number;
  headerActions?: boolean;
}) {
  const body = (() => {
    switch (variant) {
      case "table":
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <FilterBarSkeleton />
            <RowsSkeleton rows={rows} />
          </>
        );
      case "cards":
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <FilterBarSkeleton />
            <CardGridSkeleton count={rows} />
          </>
        );
      case "dashboard":
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <DashboardSkeleton />
          </>
        );
      case "detail":
        return (
          <>
            <Bar className="h-3 w-40" />
            <HeaderSkeleton actions={headerActions} />
            <div className="rounded-[10px] border border-hairline bg-white p-6">
              <RowLines />
            </div>
            <div className="rounded-[10px] border border-hairline bg-white p-6">
              <RowLines />
            </div>
          </>
        );
      case "form":
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <FormSkeleton />
          </>
        );
      case "thread":
        return (
          <>
            <HeaderSkeleton lead={false} />
            <ThreadSkeleton />
          </>
        );
      case "map":
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <MapSkeleton />
          </>
        );
      case "list":
      default:
        return (
          <>
            <HeaderSkeleton actions={headerActions} />
            <RowsSkeleton rows={rows} />
          </>
        );
    }
  })();

  const inner =
    width === "narrow" ? (
      <div className="mx-auto w-full max-w-3xl space-y-6 px-5">{body}</div>
    ) : width === "wide" ? (
      <div className="mx-auto max-w-5xl space-y-6">{body}</div>
    ) : (
      <div className="page-shell space-y-6">{body}</div>
    );

  return (
    <main
      className={width === "wide" ? "p-6 md:p-8" : "py-8"}
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">Loading…</span>
      {inner}
    </main>
  );
}
