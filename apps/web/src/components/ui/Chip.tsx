import { cn } from "@/lib/utils";

type ChipTone = "coral" | "neutral" | "blue" | "green";

const TONE: Record<ChipTone, { active: string; inactive: string }> = {
  coral: {
    active: "bg-cohere-coral text-cohere-ink border-studio-maroon",
    inactive: "bg-studio-maroon/10 text-studio-maroon border-studio-maroon-soft",
  },
  neutral: {
    active: "bg-studio-dark-cork text-white border-cohere-ink",
    inactive: "bg-transparent text-ink border-hairline",
  },
  blue: {
    active: "bg-cohere-blue text-white border-cohere-blue",
    inactive: "bg-wash-blue text-cohere-blue border-cohere-blue/20",
  },
  green: {
    active: "bg-cohere-green text-white border-cohere-green",
    inactive: "bg-wash-green text-cohere-green border-cohere-green/20",
  },
};

/** Taxonomy / status chip. Coral by default per the editorial system.
 *
 * a11y: set `decorative` when the chip duplicates content that is already
 * available to assistive tech (e.g. a status label rendered separately).
 * Decorative chips are hidden from the a11y tree via `aria-hidden`.
 *
 * When `onClick` is provided the chip renders as a button with a larger
 * touch area on mobile (36px min-height) that collapses to compact on sm+
 * so desktop UI stays dense. Non-interactive chips stay compact.
 */
export function Chip({
  children,
  tone = "coral",
  active = false,
  className,
  size = "md",
  decorative = false,
  onClick,
  ariaLabel,
}: {
  children: React.ReactNode;
  tone?: ChipTone;
  active?: boolean;
  className?: string;
  size?: "sm" | "md";
  decorative?: boolean;
  onClick?: () => void;
  ariaLabel?: string;
}) {
  const t = TONE[tone];
  const baseSize =
    size === "sm"
      ? "px-2.5 py-1 text-micro"
      : "px-3.5 py-1.5 text-caption";
  // Interactive chips: bigger tap target on mobile, dense on sm+.
  const interactiveSize = onClick
    ? "min-h-[36px] px-3 py-1.5 sm:min-h-[28px] sm:px-2.5 sm:py-1"
    : baseSize;
  const classes = cn(
    "inline-flex items-center gap-1.5 rounded-sm border font-medium transition-colors duration-200",
    interactiveSize,
    active ? t.active : t.inactive,
    onClick && "cursor-pointer hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-studio-maroon focus-visible:ring-offset-1",
    className,
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        aria-pressed={active}
        aria-hidden={decorative || undefined}
        className={classes}
      >
        {children}
      </button>
    );
  }
  return (
    <span aria-hidden={decorative || undefined} className={classes}>
      {children}
    </span>
  );
}
