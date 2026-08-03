// Route-level loading for every dashboard page — shows instantly on navigation
// while the server component fetches, instead of a blank frozen screen.
export default function DashboardLoading() {
  return (
    <div className="mx-auto max-w-5xl px-5 py-10" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="animate-pulse space-y-6 motion-reduce:animate-none">
        <div className="h-4 w-32 rounded bg-hairline" />
        <div className="h-9 w-2/3 max-w-md rounded bg-hairline" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-32 rounded-md border border-hairline bg-parchment/40" />
          ))}
        </div>
      </div>
    </div>
  );
}
