import { cn } from "@/lib/utils";

type Tone = "green" | "navy" | "coral" | "stone" | "white";

const TONE: Record<Tone, { card: string; value: string; label: string; iconWrap: string; icon: string; sub: string }> = {
  green: {
    card: "aurora-surface",
    value: "text-white",
    label: "text-white/60",
    iconWrap: "bg-white/10",
    icon: "text-white/80",
    sub: "text-white/55",
  },
  navy: {
    card: "bg-cohere-navy",
    value: "text-white",
    label: "text-white/60",
    iconWrap: "bg-white/10",
    icon: "text-white/80",
    sub: "text-white/55",
  },
  coral: {
    card: "bg-cohere-coral",
    value: "text-white",
    label: "text-white/75",
    iconWrap: "bg-white/15",
    icon: "text-white/90",
    sub: "text-white/70",
  },
  stone: {
    card: "bg-stone",
    value: "text-cohere-ink",
    label: "text-slate",
    iconWrap: "bg-white",
    icon: "text-cohere-green",
    sub: "text-slate",
  },
  white: {
    card: "bg-white border border-border-light",
    value: "text-cohere-ink",
    label: "text-slate",
    iconWrap: "bg-stone",
    icon: "text-cohere-green",
    sub: "text-slate",
  },
};

/**
 * Metric / KPI card. Defaults to the deep-green brand field with a big white
 * number — high contrast, no whisper-grey. Used across dashboards.
 */
export function MetricCard({
  label,
  value,
  icon: Icon,
  sub,
  tone = "green",
  className,
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ElementType;
  sub?: string;
  tone?: Tone;
  className?: string;
}) {
  const t = TONE[tone];
  return (
    <div
      className={cn(
        "rounded-xl p-5 transition-shadow duration-300 ease-cohere",
        tone === "white" || tone === "stone" ? "shadow-[0_1px_2px_rgba(12,10,9,0.04)] hover:shadow-[0_8px_28px_-12px_rgba(12,10,9,0.12)]" : "",
        t.card,
        className,
      )}
    >
      {/* Phrase metric: the number and its noun share a baseline and read as
          one fragment ("337 workers"), not a labeled stat block. */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span className={cn("font-display text-[2.5rem] leading-none tabular-nums", t.value)}>
            {value}
          </span>
          <span className={cn("text-body font-medium", t.label)}>{label}</span>
        </div>
        {Icon && <Icon className={cn("h-4 w-4 shrink-0 self-start", t.icon)} strokeWidth={1.75} aria-hidden />}
      </div>
      {sub && <p className={cn("mt-2.5 text-caption", t.sub)}>{sub}</p>}
    </div>
  );
}
