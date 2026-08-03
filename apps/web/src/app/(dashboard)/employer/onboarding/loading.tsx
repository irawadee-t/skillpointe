// Instant per-segment fallback — mirrors the onboarding page's narrow
// max-w-2xl column so the real page streams in without layout shift.
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
    <main className="py-10" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="mx-auto w-full max-w-2xl space-y-6 px-5">
        <Bar className="h-8 w-64 max-w-full" />
        <Bar className="h-4 w-96 max-w-full" />
        <div className="space-y-4 rounded-[10px] border border-hairline bg-white p-6">
          <Bar className="h-4 w-40" />
          <Bar className="h-10" />
          <Bar className="h-10" />
          <Bar className="h-10 w-40" />
        </div>
      </div>
    </main>
  );
}
