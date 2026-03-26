interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "bg-neutral-900 text-white border-neutral-900",
  good_fit:     "bg-neutral-100 text-neutral-700 border-neutral-200",
  moderate_fit: "bg-neutral-50 text-neutral-600 border-neutral-200",
  low_fit:      "bg-neutral-50 text-neutral-500 border-neutral-200",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "bg-neutral-50 text-neutral-500 border-neutral-200";
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
    ? "bg-neutral-900 text-white border-neutral-900"
    : "bg-neutral-100 text-neutral-600 border-neutral-200";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}>
      {text}
    </span>
  );
}
