/**
 * SKILLED NATION lockup — boxed "SKILLED" over letter-spaced "NATION",
 * exactly per the Skilled Nation Logo Usage Guide:
 *
 *   primary    Crimson box, black SKILLED on white, cool-gray NATION (light bg)
 *   black      All-black box and letters (light bg, single color)
 *   secondary  Crimson-bordered box on dark; white SKILLED, light-gray NATION
 *   white      All-white (for crimson/maroon surfaces, e.g. the sidebar)
 *
 * Brand palette (guide): Pantone 201C #9D2235, Black #000000,
 * Cool Gray 11C #53565A, Cool Gray 1C #D9D9D6.
 * Face: TT Commons Pro (Bold / Medium) with sans fallbacks.
 *
 * The guide's improper-usage rules (no skew, no recoloring, no strike-through)
 * are enforced by construction: these four variants are the only renderings.
 * Legacy props `mono` and `invert` map onto black/secondary for old call sites.
 */
const CRIMSON = "#9D2235";   // Pantone 201 C
const BLACK = "#000000";
const COOL_GRAY_11 = "#53565A";
const COOL_GRAY_1 = "#D9D9D6";
const FACE = "'TT Commons Pro', 'Helvetica Neue', Arial, sans-serif";

export type LogoVariant = "primary" | "black" | "secondary" | "white";

export function SkilledNationLogo({
  width = 150,
  className,
  variant,
  mono = false,
  invert = false,
}: {
  width?: number;
  className?: string;
  variant?: LogoVariant;
  /** @deprecated legacy alias for variant="black" */
  mono?: boolean;
  /** @deprecated legacy alias for variant="secondary" */
  invert?: boolean;
}) {
  const v: LogoVariant = variant ?? (invert ? "secondary" : mono ? "black" : "primary");
  const palette = {
    primary:   { box: CRIMSON, fill: "#ffffff", skilled: BLACK,    nation: COOL_GRAY_11 },
    black:     { box: BLACK,   fill: "#ffffff", skilled: BLACK,    nation: COOL_GRAY_11 },
    secondary: { box: CRIMSON, fill: "none",    skilled: "#ffffff", nation: COOL_GRAY_1 },
    white:     { box: "#ffffff", fill: "none",  skilled: "#ffffff", nation: "#ffffff" },
  }[v];

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
      <rect x="4" y="4" width="312" height="66" fill={palette.fill} stroke={palette.box} strokeWidth="8" />
      <text
        x="160" y="55" textAnchor="middle"
        fontFamily={FACE} fontWeight="700" fontSize="48"
        letterSpacing="0.5" fill={palette.skilled}
      >
        SKILLED
      </text>
      <text
        x="160" y="108" textAnchor="middle"
        fontFamily={FACE} fontWeight="500" fontSize="25"
        letterSpacing="12" fill={palette.nation}
      >
        NATION
      </text>
    </svg>
  );
}
