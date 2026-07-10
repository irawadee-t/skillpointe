import { cn } from "@/lib/utils";

/**
 * Skeleton line/box for loading states. Uses stone/parchment tones so it
 * doesn't flash white on the warm canvas.
 */
export function SkeletonLine({
  width = "w-full",
  height = "h-4",
  className,
}: {
  width?: string;
  height?: string;
  className?: string;
}) {
  return (
    <div className={cn("animate-pulse rounded-md bg-stone/70", width, height, className)} />
  );
}

/**
 * A row of skeleton lines — useful for list-item placeholders while data loads.
 */
export function SkeletonRow({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2.5", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonLine
          key={i}
          width={i === 0 ? "w-3/4" : i === rows - 1 ? "w-1/2" : "w-full"}
        />
      ))}
    </div>
  );
}

/** A card-shaped placeholder used for cards during load. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-hairline bg-white p-4", className)}>
      <SkeletonRow rows={3} />
    </div>
  );
}
