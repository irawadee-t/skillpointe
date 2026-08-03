import { cn } from "@/lib/utils";

type Tone = "green" | "navy" | "coral" | "stone" | "white";

/**
 * Metric — a quiet, flat stat.
 *
 * Deliberately NOT a "KPI card": no gradient field, no icon-in-a-circle, no
 * tiny all-caps label under a huge number. The number and its noun read as one
 * phrase ("337 workers") on a plain surface; color never carries meaning here.
 * The `tone` and `icon` props are accepted for backward compatibility with the
 * ~30 existing call sites but no longer change the visual — every metric is
 * the same calm surface, which is exactly the point.
 */
export function MetricCard({
  label,
  value,
  icon: _icon,
  sub,
  tone: _tone = "white",
  className,
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ElementType;
  sub?: string;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div
      className={cn(
        // Dense meta block: white, hairline, 14px radius, 16px padding, flat.
        "rounded-[14px] border border-hairline bg-white p-4",
        className,
      )}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-display text-[1.75rem] leading-none tabular-nums text-cohere-ink">
          {value}
        </span>
        <span className="text-body text-slate">{label}</span>
      </div>
      {sub && <p className="mt-2 text-caption text-slate-muted">{sub}</p>}
    </div>
  );
}
