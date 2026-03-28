interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "bg-emerald-500/20 text-emerald-600 border-emerald-200",
  good_fit:     "bg-spf-navy/10 text-spf-navy border-spf-navy/20",
  moderate_fit: "bg-zinc-100 text-zinc-500 border-zinc-200",
  low_fit:      "bg-zinc-100 text-zinc-400 border-zinc-200",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "bg-zinc-100 text-zinc-400 border-zinc-200";
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
    ? "bg-emerald-500/20 text-emerald-600 border-emerald-200"
    : "bg-amber-50 text-amber-600 border-amber-200";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}>
      {text}
    </span>
  );
}
