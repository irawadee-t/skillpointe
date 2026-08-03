# 001 — Add press feedback to every pressable element

- **Status**: DONE
- **Commit**: 666ce88
- **Severity**: HIGH
- **Category**: Physicality & origin
- **Estimated scope**: 2 files (globals.css, InterestSignalPanel.tsx), ~10 line edits

## Problem

There is no press feedback anywhere in the product. `grep -rn ":active\|active:scale\|whileTap" apps/web/src` returns zero hits. Buttons and toggle pills — the highest-frequency tap targets — give no tactile confirmation of a press.

```css
/* apps/web/src/app/globals.css:144-153 — current (.btn-md; same pattern in .btn-sm:157, .btn-lg:169, .btn-ghost:181, .btn-commit:203, .btn-primary-inverse:222) */
.btn-md {
  @apply inline-flex items-center justify-center gap-1.5 rounded-[6px]
         bg-studio-dark-cork px-4 py-2 min-h-[36px]
         text-[14px] font-medium text-studio-cream
         border border-studio-dark-cork
         transition-colors duration-150 ease-cohere
         hover:bg-studio-maroon hover:border-studio-maroon
         ...;
}
```

```tsx
{/* apps/web/src/components/matches/InterestSignalPanel.tsx:149 — current */}
className={`inline-flex items-center gap-1 rounded-full border bg-white px-2.5 py-1 text-[12px] transition-colors ${
```

## Target

Rule: press feedback is `transform: scale(0.97)` on `:active` with a transform transition of 100–160ms ease-out, subtle (0.95–0.98). Buttons already transition at `duration-150 ease-cohere` (a strong ease-out) — extend the transitioned property list to include `transform` and add `active:scale-[0.97]`:

```css
/* target — every filled/outline button variant */
transition-[color,background-color,border-color,transform] duration-150 ease-cohere
active:scale-[0.97]
```

Pills are smaller; use `active:scale-[0.96]`:

```tsx
/* target — InterestSignalPanel pill */
className={`inline-flex items-center gap-1 rounded-full border bg-white px-2.5 py-1 text-[12px] transition-[color,background-color,border-color,transform] duration-150 ease-cohere active:scale-[0.96] ${
```

## Repo conventions to follow

- All button styling lives in `@layer components` in `apps/web/src/app/globals.css` as `@apply` blocks — edit there, not at call sites.
- The easing token is `ease-cohere` = `cubic-bezier(0.16, 1, 0.3, 1)` (apps/web/tailwind.config.ts, `transitionTimingFunction.cohere`). Use it; do not introduce a new curve.

## Steps

1. In `apps/web/src/app/globals.css`, for each of `.btn-md`, `.btn-sm`, `.btn-lg`, `.btn-ghost`, `.btn-commit`, `.btn-primary-inverse`: replace `transition-colors duration-150 ease-cohere` with `transition-[color,background-color,border-color,transform] duration-150 ease-cohere` and add `active:scale-[0.97]` to the same `@apply` block. Do NOT touch `.btn-link` (underlined text link — scaling text reads as a glitch).
2. Guard disabled buttons: append `disabled:active:scale-100` to each variant edited in step 1 so a disabled button does not compress.
3. In `apps/web/src/components/matches/InterestSignalPanel.tsx:149`, replace `transition-colors` with `transition-[color,background-color,border-color,transform] duration-150 ease-cohere active:scale-[0.96]`.

## Boundaries

- Do NOT add press feedback to plain text links, nav links, or `.btn-link`.
- Do NOT change any color, padding, or hover values.
- Do NOT add new dependencies or new CSS custom properties.
- If a `.btn-*` block does not match the excerpt above (drift), STOP and report.

## Verification

- **Mechanical**: `pnpm --filter web typecheck` and `pnpm --filter web lint` — no errors.
- **Feel check**: run the app, hold mouse-down on "View match & plan" (matches page) and on an interest pill:
  - The element compresses to ~0.97 while held and springs back instantly on release.
  - Disabled buttons do not compress.
  - In DevTools > Rendering, enable `prefers-reduced-motion: reduce` — the global reduced-motion rule collapses the transition to 0.01ms; the scale still applies (instant), which is acceptable feedback.
- **Done when**: every `.btn-md/.btn-sm/.btn-lg/.btn-ghost/.btn-commit/.btn-primary-inverse` and the interest pills visibly respond to press; typecheck + lint pass.
