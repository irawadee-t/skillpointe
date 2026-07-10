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
        // Display — ElevenLabs editorial serif (EB Garamond / Waldenburg spirit)
        display: ["var(--font-display)", "EB Garamond", "Georgia", "Times New Roman", "serif"],
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
          black:   "#100904",  // page canvas — warm near-black
          cream:   "#ffedd7",  // sole foreground: text, borders, button outlines
          cork:    "#40372e",  // secondary structural lines (dashed dividers)
          "dark-cork": "#382416", // filled button surface
          sienna:  "#dc5000",  // accent — link underlines, warning icons, near-fit
          maroon:  "#9E1B32",  // logo brand red — prestige/verified/strong-fit
          "grey-brown": "#6c5f51", // muted text / secondary labels
          // Warm olive sampled from the hero video (dominant green tone).
          // Was #445231 Forest Grid — shifted to match the video's palette.
          forest:  "#4a4b2f",
        },
        // Brand & accent — light mode base with studio palette as chromatic accents.
        cohere: {
          black: "#0c0a09",
          ink: "#17171c",        // near-black primary text (CTAs, headings, body)
          green: "#4a4b2f",      // Warm olive sampled from hero video
          navy: "#071829",
          blue: "#1863dc",       // action blue (editorial links)
          coral: "#dc5000",      // Burnt Sienna — attention/near-fit eyebrows
          "coral-soft": "#ffd9c4",
        },
        // Surfaces — warm off-white light base
        canvas: "#faf8f3",       // Warm off-white page bg
        parchment: "#f5f1e8",    // Slightly deeper for section bands / muted surfaces
        stone: "#eeece7",        // Warm neutral for cards / KPI blocks
        "wash-green": "#edfce9",
        "wash-blue": "#f1f5ff",
        // Text & rules
        ink: "#17171c",          // primary text
        slate: {
          DEFAULT: "#4b4237",    // darker warm — passes 4.5:1 on canvas
          muted:   "#5a4f42",    // was #6c5f51 — bumped to pass WCAG AA (4.5:1) on canvas/parchment
        },
        hairline: "#d9d5cc",     // warm hairline (tinted toward the palette)
        "border-light": "#e5e0d3",
        "card-border": "#f2ede2",
        // Semantic
        focusblue: "#4c6ee6",
        "focus-violet": "#9b60aa",
        "error-red": "#b30000",
        // Backward-compat aliases — old spf tokens remapped onto the Cohere palette
        spf: {
          navy: "#1863dc", // action blue (was navy) — editorial links/accents
          "navy-light": "#4c6ee6",
          "navy-dark": "#071829",
          orange: "#ff7759", // coral
          "orange-light": "#ffad9b",
          "orange-dark": "#d4740f",
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
        micro:   ["12px", { lineHeight: "1.4" }],
        caption: ["13px", { lineHeight: "1.45" }],
        button:  ["13px", { lineHeight: "1.4", fontWeight: "600", letterSpacing: "0.03em" }],
        label:   ["14px", { lineHeight: "1.4" }],
        body:    ["15px", { lineHeight: "1.55" }],
        "body-lg": ["17px", { lineHeight: "1.5" }],
        subhead: ["20px", { lineHeight: "1.35", letterSpacing: "-0.005em" }],
        feature: ["24px", { lineHeight: "1.25", letterSpacing: "-0.01em" }],
        card:    ["30px", { lineHeight: "1.15", letterSpacing: "-0.015em" }],
        heading: ["40px", { lineHeight: "1.1",  letterSpacing: "-0.02em" }],
        section: ["56px", { lineHeight: "1.02", letterSpacing: "-0.025em" }],
        "display-product": ["72px", { lineHeight: "1.0",  letterSpacing: "-0.03em" }],
        "display-hero":    ["96px", { lineHeight: "0.98", letterSpacing: "-0.035em" }],
      },
      // Shadow scale — three tiers only. Never inline shadow-[custom].
      boxShadow: {
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
