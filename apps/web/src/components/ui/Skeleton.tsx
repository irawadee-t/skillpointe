import { cn } from "@/lib/utils";

/** Placeholder skeleton surface with shimmer. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-sm", className)} />;
}
