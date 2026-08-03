import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Display — clean sans, ElevenLabs-style (large, modest weight, tight
        // tracking). The old editorial serif is retired from the product; it
        // remains available as font-serif for rare marketing moments only.
        display: ["var(--font-body)", "Inter", "Arial", "ui-sans-serif", "system-ui"],
        serif: ["var(--font-display)", "EB Garamond", "Georgia", "serif"],
        // Body / UI (Unica77 Cohere Web spirit)
        sans: ["var(--font-body)", "Inter", "Arial", "ui-sans-serif", "system-ui"],
        // `font-mono` retired as a visual style: it now resolves to the body
        // sans so legacy call sites inherit the single product voice. Use
        // `tabular-nums` where digit alignment mattered.
        mono: ["var(--font-body)", "Inter", "Arial", "ui-sans-serif", "system-ui"],
      },
      colors: {
        // ── Studio Black palette ─────────────────────────────────────
        // Dark editorial palette — near-black warm canvas + warm-cream text.
        // Existing token names remapped so the whole codebase inherits the
        // new palette without a search-and-replace across hundreds of files.
        studio: {
          black:   "#0b0b0c",  // neutral near-black (brown retired)
          cream:   "#ffedd7",  // sole foreground: text, borders, button outlines
          cork:    "#3f3f42",  // neutral structural lines (brown retired)
          "dark-cork": "#17171c", // neutral ink surface (brown retired)
          sienna:  "#9d2235",  // accent — link underlines, warning icons, near-fit
          maroon:  "#9E1B32",  // logo brand red — prestige/verified/strong-fit
          "grey-brown": "#5c5a55", // neutral muted (brown retired)
          // Warm olive sampled from the hero video (dominant green tone).
          // Was #445231 Forest Grid — shifted to match the video's palette.
          forest:  "#4a4b2f",
        },
        // Brand & accent — light mode base with studio palette as chromatic accents.
        cohere: {
          black: "#0c0a09",
          ink: "#17171c",        // near-black primary text (CTAs, headings, body)
          green: "#4a4b2f",      // Warm olive sampled from hero video
          "green-deep": "#31321f", // deeper olive — terminal-positive chips (hired)
          navy: "#071829",
          blue: "#1863dc",       // action blue (editorial links)
          coral: "#9d2235",      // Burnt Sienna — attention/near-fit eyebrows
          "coral-soft": "#efd5da",
        },
        // Surfaces — clean near-white light base (ElevenLabs-grade, NOT beige).
        // The whole product content area reads white; separation comes from
        // hairlines and one hover shadow, never from a tinted fill.
        canvas: "#fcfcfb",       // near-white page bg (whisper-warm, reads white)
        parchment: "#f5f5f4",    // neutral light gray for section bands / muted insets
        stone: "#f2f2f1",        // neutral light gray for muted surfaces
        "wash-green": "#eef8ec",
        "wash-blue": "#eff4ff",
        // Text & rules — neutral near-charcoal, no warm brown
        ink: "#17171c",          // primary text
        slate: {
          DEFAULT: "#33322f",    // neutral charcoal secondary text (AA on canvas)
          muted:   "#5c5a55",    // neutral gray muted text (AA on canvas/parchment)
        },
        hairline: "#e7e5e2",     // clean light-neutral hairline
        "border-light": "#eceae7",
        "card-border": "#efeeec",
        // Semantic
        focusblue: "#4c6ee6",
        "focus-violet": "#9b60aa",
        "error-red": "#b30000",
        // Backward-compat aliases — old spf tokens remapped onto the Cohere palette
        spf: {
          navy: "#1863dc", // action blue (was navy) — editorial links/accents
          "navy-light": "#4c6ee6",
          "navy-dark": "#071829",
          orange: "#b34456", // coral
          "orange-light": "#d8919d",
          "orange-dark": "#7d1b2a",
          gray: "#75758a",
          "gray-light": "#93939f",
        },
      },
      // Radii — industrial-stamped feel. Sharp corners dominate; large radii
      // only on hero canvases and modal shells. Never rounded-full pills.
      borderRadius: {
        xs: "2px",  // stamp corners (buttons, chips)
        sm: "4px",  // input, small card
        md: "6px",  // card, panel
        lg: "10px", // section band, drawer
        xl: "16px", // hero canvas
        pill: "999px", // last-resort pill (avoid)
      },
      // Type scale — one canonical size per role. Kill inline text-[Npx].
      // If a size is missing, add here first before hardcoding elsewhere.
      fontSize: {
        // De-AI'd scale: 16px body baseline (browser default; below it mobile
        // users pinch-zoom), ~4 working sizes, 1.25 ratio with compressed mids
        // and an expanded top for display — per current type-scale guidance.
        micro:   ["12px", { lineHeight: "1.4" }],
        caption: ["13px", { lineHeight: "1.45" }],
        button:  ["14px", { lineHeight: "1.4", fontWeight: "500" }],
        label:   ["14px", { lineHeight: "1.4" }],
        body:    ["16px", { lineHeight: "1.5" }],
        "body-lg": ["18px", { lineHeight: "1.5" }],
        subhead: ["20px", { lineHeight: "1.3", letterSpacing: "-0.005em" }],
        feature: ["25px", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        card:    ["31px", { lineHeight: "1.2", letterSpacing: "-0.015em" }],
        heading: ["39px", { lineHeight: "1.2",  letterSpacing: "-0.02em" }],
        section: ["49px", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
        "display-product": ["72px", { lineHeight: "1.0",  letterSpacing: "-0.03em" }],
        "display-hero":    ["96px", { lineHeight: "0.98", letterSpacing: "-0.035em" }],
      },
      // Elevation — ONE tier. Cards are flat at rest; `shadow-float` is the
      // single hover/floating elevation (Airbnb's card shadow). There are no
      // progressive tiers. `subtle`/`medium`/`prominent` remain only for
      // legacy non-card surfaces and must not be used on cards.
      boxShadow: {
        float:      "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.04) 0 2px 6px 0, rgba(0,0,0,0.1) 0 4px 8px 0",
        subtle:     "0 1px 2px rgba(12,10,9,0.04)",
        medium:     "0 6px 20px -8px rgba(12,10,9,0.12)",
        prominent:  "0 14px 36px -12px rgba(12,10,9,0.20)",
        focus:      "0 0 0 3px rgba(158,27,50,0.20)", // maroon halo, for focus rings
      },
      screens: {
        // xs: tight phone — Pixel 6 at 375px
        xs: "375px",
      },
      opacity: {
        // Semantic opacities so components don't invent their own.
        disabled: "0.4",  // canonical for all disabled states
        muted:    "0.6",  // secondary content within a component
        veiled:   "0.85", // slight veil (e.g., over an image)
      },
      letterSpacing: {
        mono: "0.28px",
      },
      maxWidth: {
        container: "1280px",
        prose: "680px",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "chip-in": {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.16,1,0.3,1) both",
        "fade-in": "fade-in 0.5s ease both",
        "scale-in": "scale-in 0.4s cubic-bezier(0.16,1,0.3,1) both",
        "chip-in": "chip-in 0.15s ease-out both",
        shimmer: "shimmer 1.6s infinite",
        marquee: "marquee 40s linear infinite",
      },
      transitionTimingFunction: {
        "cohere": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
