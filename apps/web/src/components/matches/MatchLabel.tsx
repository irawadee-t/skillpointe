/**
 * MatchLabel — colour-coded badge for match_label and eligibility_status.
 *
 * match_label colours (fit quality):
 *   strong_fit  → green
 *   good_fit    → blue
 *   moderate_fit → yellow/amber
 *   low_fit     → gray
 *
 * eligibility_status colours (gate result):
 *   eligible  → green outline
 *   near_fit  → orange outline
 */

interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "bg-green-100  text-green-800  border-green-200",
  good_fit:     "bg-blue-100   text-blue-800   border-blue-200",
  moderate_fit: "bg-amber-100  text-amber-800  border-amber-200",
  low_fit:      "bg-gray-100   text-gray-600   border-gray-200",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "bg-gray-100 text-gray-500 border-gray-200";
  const text = LABEL_TEXT[label ?? ""] ?? "—";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}
    >
      {text}
    </span>
  );
}

interface EligibilityBadgeProps {
  status: "eligible" | "near_fit";
  size?: "sm" | "md";
}

export function EligibilityBadge({ status, size = "sm" }: EligibilityBadgeProps) {
  const isEligible = status === "eligible";
  const styles = isEligible
    ? "bg-green-50 text-green-700 border-green-200"
    : "bg-orange-50 text-orange-700 border-orange-200";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${styles} ${padding}`}
    >
      {text}
    </span>
  );
}
