interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

/**
 * Match-quality labels — Cohere-style outlined pills.
 * No filled washes; the border colors carry the tone.
 */
const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "border-cohere-green/50 text-cohere-green",
  good_fit:     "border-cohere-blue/50  text-cohere-blue",
  moderate_fit: "border-hairline        text-slate",
  low_fit:      "border-hairline        text-slate-muted",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "border-hairline text-slate-muted";
  const text = LABEL_TEXT[label ?? ""] ?? label ?? "—";
  const padding = size === "md" ? "px-3 py-1 text-caption" : "px-2.5 py-0.5 text-micro";
  return (
    <span className={`inline-flex items-center rounded-full border bg-white font-medium ${styles} ${padding}`}>
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
    ? "border-cohere-green/50 text-cohere-green"
    : "border-studio-maroon/50 text-studio-maroon";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-caption" : "px-2.5 py-0.5 text-micro";
  return (
    <span className={`inline-flex items-center rounded-full border bg-white font-medium ${styles} ${padding}`}>
      {text}
    </span>
  );
}
