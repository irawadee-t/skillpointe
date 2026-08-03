// Instant per-segment fallback for the onboarding wizard — mirrors its
// two-column shell (300px step rail + form pane) so the real page streams in
// without layout shift.
function Bar({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-stone/70 motion-reduce:animate-none ${className ?? ""}`}
      aria-hidden
    />
  );
}

export default function Loading() {
  return (
    <main className="min-h-[calc(100vh-4rem)]" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-0 lg:grid-cols-[300px_1fr]">
        <div className="hidden space-y-4 border-r border-hairline p-8 lg:block">
          <Bar className="h-4 w-32" />
          <Bar className="h-3 w-40" />
          <Bar className="h-3 w-36" />
          <Bar className="h-3 w-44" />
        </div>
        <div className="space-y-6 p-8">
          <Bar className="h-8 w-64 max-w-full" />
          <Bar className="h-4 w-96 max-w-full" />
          <div className="grid grid-cols-2 gap-4">
            <Bar className="h-10" />
            <Bar className="h-10" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Bar className="h-10" />
            <Bar className="h-10" />
          </div>
          <Bar className="h-10 w-40" />
        </div>
      </div>
    </main>
  );
}
