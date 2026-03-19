interface MatchLabelBadgeProps {
  label: string | null;
  size?: "sm" | "md";
}

const LABEL_STYLES: Record<string, string> = {
  strong_fit:   "bg-green-50 text-green-700 border-green-200",
  good_fit:     "bg-blue-50 text-blue-700 border-blue-200",
  moderate_fit: "bg-amber-50 text-amber-700 border-amber-200",
  low_fit:      "bg-gray-50 text-gray-500 border-gray-200",
};

const LABEL_TEXT: Record<string, string> = {
  strong_fit:   "Strong fit",
  good_fit:     "Good fit",
  moderate_fit: "Moderate fit",
  low_fit:      "Low fit",
};

export function MatchLabel({ label, size = "sm" }: MatchLabelBadgeProps) {
  const styles = LABEL_STYLES[label ?? ""] ?? "bg-gray-50 text-gray-500 border-gray-200";
  const text = LABEL_TEXT[label ?? ""] ?? label ?? "—";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-md border ${styles} ${padding}`}>
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
    ? "bg-green-50 text-green-700 border-green-200"
    : "bg-orange-50 text-orange-700 border-orange-200";
  const text = isEligible ? "Eligible" : "Near fit";
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span className={`inline-flex items-center font-medium rounded-md border ${styles} ${padding}`}>
      {text}
    </span>
  );
}
