/**
 * SKILLED NATION wordmark — maroon-boxed "SKILLED" over letter-spaced "NATION".
 * On the dark Studio Black canvas, the mark uses a maroon border with a
 * transparent (dark) interior and Warm Cream text — the maroon reads as a
 * chromatic border rule instead of a light card. The `mono` and `invert`
 * variants stay available for legacy call sites.
 */
const MAROON = "#9E1B32";
const INK    = "#0c0a09";
const GREY   = "#58595B";
const CREAM  = "#ffedd7";

export function SkilledNationLogo({
  width = 150,
  className,
  mono = false,
  invert = false,
}: {
  width?: number;
  className?: string;
  /** Single-color (ink) variant. */
  mono?: boolean;
  /** Cream-on-transparent variant for dark surfaces (e.g. hero video overlay). */
  invert?: boolean;
}) {
  const boxStroke = invert ? CREAM : mono ? INK : MAROON;
  const boxFill   = invert ? "none" : "#ffffff";
  const skilled   = invert ? CREAM : INK;
  const nation    = invert ? "rgba(255,237,215,0.8)" : mono ? INK : GREY;
  return (
    <svg
      width={width}
      height={width * (120 / 320)}
      viewBox="0 0 320 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="SKILLED NATION"
    >
      <rect x="3" y="3" width="314" height="68" rx="2" fill={boxFill} stroke={boxStroke} strokeWidth="6" />
      <text
        x="160" y="56" textAnchor="middle"
        fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fontSize="50"
        letterSpacing="-1" fill={skilled}
      >
        SKILLED
      </text>
      <text
        x="160" y="108" textAnchor="middle"
        fontFamily="Arial, Helvetica, sans-serif" fontWeight="600" fontSize="26"
        letterSpacing="11" fill={nation}
      >
        NATION
      </text>
    </svg>
  );
}
