interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  good_fit:     "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  moderate_fit: "bg-zinc-800 text-zinc-400 border-zinc-700",
  low_fit:      "bg-zinc-800/50 text-zinc-500 border-zinc-700",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "bg-zinc-800 text-zinc-500 border-zinc-700";
  const text = LABEL_TEXT[label ?? ""] ?? label ?? "—";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}>
      {text}
    </span>
  );
}

interface EligibilityBadgeProps {
  status: string;
  size?: "sm" | "md";
}

export function EligibilityBadge({ status, size = "sm" }: EligibilityBadgeProps) {
  const isEligible = status === "eligible";
  const styles = isEligible
    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
    : "bg-amber-500/10 text-amber-400 border-amber-500/30";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}>
      {text}
    </span>
  );
}
