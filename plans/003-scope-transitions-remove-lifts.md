# 003 — Scope every `transition-all` and remove hover lifts from product cards

- **Status**: DONE
- **Commit**: 666ce88
- **Severity**: HIGH (cluster: performance + cohesion + contract violation + ungated hover motion)
- **Category**: Performance / Cohesion & tokens
- **Estimated scope**: 8 files, ~12 line edits

## Problem

Two overlapping defects on the most-hovered surfaces in the product:

1. **`transition-all`** animates every changed property off-GPU (always a finding). 9 sites in this plan (2 more are handled by plan 004).
2. **Hover lifts + hover shadow gloss on product cards.** DESIGN_CONTRACT.md says card hover "deepens to bg-sand-deep" — color-swap only, no lift. One match-card variant lifts (`hover:-translate-y-0.5`) while its sibling variants don't, the shared `Card` primitive lifts via a main-thread Motion shorthand (`whileHover={{ y: -4 }}`), and none of these hover transforms are gated behind `@media (hover: hover)` so they fire on touch taps. Card hovers also run at 300ms while every button hover runs at 150ms — two canonical durations for one gesture.

Current code:

```tsx
/* apps/web/src/app/(dashboard)/applicant/matches/MatchesClient.tsx:266 */
className={`relative overflow-hidden rounded-xl border border-hairline border-l-[3px] bg-sand transition-all hover:bg-sand-deep duration-300 hover:shadow-[0_10px_28px_-14px_rgba(12,10,9,0.15)] ${railClass}`}

/* apps/web/src/app/(dashboard)/applicant/matches/MatchesClient.tsx:437 */
<article className="group rounded-2xl border border-hairline bg-sand p-7 shadow-subtle hover:bg-sand-deep transition-all duration-300 ease-cohere hover:-translate-y-0.5 hover:shadow-[0_16px_40px_-20px_rgba(12,10,9,0.18)]">

/* apps/web/src/components/matches/JobMatchCard.tsx:62,67 */
"group relative block overflow-hidden rounded-xl border border-hairline bg-sand p-5 hover:bg-sand-deep shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-all duration-300 ease-cohere",
"hover:-translate-y-0.5 hover:border-cohere-ink/20 hover:shadow-[0_10px_28px_-14px_rgba(12,10,9,0.15)]",

/* apps/web/src/app/(dashboard)/applicant/applications/MyApplicationsClient.tsx:93 */
className={`block rounded-xl border border-hairline bg-sand p-4 shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-all hover:bg-sand-deep hover:shadow-[0_6px_20px_-10px_rgba(12,10,9,0.14)] ${muted ? "opacity-70" : ""}`}

/* apps/web/src/app/(dashboard)/admin/AdminDashboardClient.tsx:36 */
<div className="rounded-md bg-cohere-green p-5 text-white transition-transform duration-300 ease-cohere hover:-translate-y-1">

/* apps/web/src/app/(dashboard)/applicant/setup/page.tsx:265 */
className={`rounded-xl border p-4 text-left transition-all ${ ... }`}

/* apps/web/src/components/marketing/MarketingNav.tsx:42 */
"fixed inset-x-0 top-0 z-50 transition-all duration-300",

/* apps/web/src/components/applicant/FirstRunTour.tsx:88 */
className={`h-1.5 rounded-full transition-all ${idx === i ? "w-6 bg-studio-dark-cork" : "w-1.5 bg-stone"}`}

/* apps/web/src/components/applicant/CoachMarkTour.tsx:203 */
className={`h-1.5 rounded-full transition-all ${i === stepIx ? "w-6 bg-studio-dark-cork" : "w-1.5 bg-stone"}`}

/* apps/web/src/components/ui/Card.tsx:80-85 (same pattern again at :93-97) */
<motion.div
  whileHover={interactive ? { y: -4 } : undefined}
  transition={{ duration: 0.3, ease: easeCohere }}
>
```

## Target

One hover language on product cards: background deepens, nothing moves, 200ms with the house curve.

```tsx
/* MatchesClient.tsx:266 — target */
className={`relative overflow-hidden rounded-xl border border-hairline border-l-[3px] bg-sand transition-colors duration-200 ease-cohere hover:bg-sand-deep ${railClass}`}

/* MatchesClient.tsx:437 — target */
<article className="group rounded-2xl border border-hairline bg-sand p-7 shadow-subtle hover:bg-sand-deep transition-colors duration-200 ease-cohere">

/* JobMatchCard.tsx:62,67 — target (line 67 keeps only the border tint) */
"group relative block overflow-hidden rounded-xl border border-hairline bg-sand p-5 hover:bg-sand-deep shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-colors duration-200 ease-cohere",
"hover:border-cohere-ink/20",

/* MyApplicationsClient.tsx:93 — target */
className={`block rounded-xl border border-hairline bg-sand p-4 shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-colors duration-200 ease-cohere hover:bg-sand-deep ${muted ? "opacity-70" : ""}`}

/* AdminDashboardClient.tsx:36 — target (stat tile: delete the animation) */
<div className="rounded-md bg-cohere-green p-5 text-white">

/* setup/page.tsx:265 — target */
className={`rounded-xl border p-4 text-left transition-colors duration-150 ease-cohere ${ ... }`}

/* MarketingNav.tsx:42 — target (bg/border swap on scroll; backdrop-blur may snap) */
"fixed inset-x-0 top-0 z-50 transition-colors duration-300",

/* FirstRunTour.tsx:88 and CoachMarkTour.tsx:203 — target (tiny 6px dot; scoped width+color) */
className={`h-1.5 rounded-full transition-[width,background-color] duration-200 ease-cohere ${ ... }`}

/* Card.tsx — target: drop the lift entirely, both branches */
<motion.div>
```

## Repo conventions to follow

- `ease-cohere` = `cubic-bezier(0.16, 1, 0.3, 1)` (tailwind.config.ts) — the house curve for everything.
- Exemplar of the correct card hover already in the repo: the buttons in `apps/web/src/app/globals.css` (`transition-colors duration-150 ease-cohere hover:bg-studio-maroon` — color swap, no movement).
- DESIGN_CONTRACT.md (binding): "hover deepens to `bg-sand-deep`" — nothing about lift or shadow.

## Steps

1. `MatchesClient.tsx:266` — replace the className with the target string (drop `transition-all`, `duration-300`, hover shadow; add `transition-colors duration-200 ease-cohere`).
2. `MatchesClient.tsx:437` — replace with target (drop lift + hover shadow, `transition-all duration-300` → `transition-colors duration-200`).
3. `JobMatchCard.tsx:62` — replace `transition-all duration-300 ease-cohere` with `transition-colors duration-200 ease-cohere`; line 67: reduce to `"hover:border-cohere-ink/20",` (remove `hover:-translate-y-0.5` and `hover:shadow-[…]`).
4. `MyApplicationsClient.tsx:93` — target string (scoped colors, no hover shadow).
5. `AdminDashboardClient.tsx:36` — remove `transition-transform duration-300 ease-cohere hover:-translate-y-1` (informational stat tile; no hover motion).
6. `setup/page.tsx:265` — `transition-all` → `transition-colors duration-150 ease-cohere`.
7. `MarketingNav.tsx:42` — `transition-all duration-300` → `transition-colors duration-300`.
8. `FirstRunTour.tsx:88` and `CoachMarkTour.tsx:203` — `transition-all` → `transition-[width,background-color] duration-200 ease-cohere`. (Width is a layout property, but this is a 6×24px dot on a rarely-seen tour — scoping the property list is the fix; converting dots to transforms is out of scope.)
9. `Card.tsx` — in both branches remove the `whileHover={interactive ? { y: -4 } : undefined}` and `transition={{ duration: 0.3, ease: easeCohere }}` props. Keep the `motion.div` wrappers and everything else (interactive bg-hover classes above line 75 already provide hover feedback). Remove the now-unused `easeCohere` import if lint flags it.

## Boundaries

- Do NOT touch `AdminDashboardClient.tsx:76,262` or `DimensionBreakdown.tsx:62` — those `transition-all` bars belong to plan 004.
- Do NOT change any static (non-hover) shadows, colors, spacing, or markup structure (except deleting the two Card props).
- Do NOT add `@media (hover: hover)` wrappers — removing the hover transforms resolves the touch-hover issue for these sites.
- If a cited line does not match its excerpt (drift), STOP and report.

## Verification

- **Mechanical**: `pnpm --filter web typecheck` and `pnpm --filter web lint` — no errors (especially no unused-import errors in Card.tsx).
- **Feel check**: on /applicant/matches and /applicant/jobs, hover cards:
  - Background deepens to sand-deep in ~200ms; nothing translates, no shadow bloom.
  - Buttons (150ms) and cards (200ms) feel like one family.
  - FirstRunTour dots still stretch smoothly between steps.
  - In DevTools Animations panel at 10% speed, confirm card hover animates only background/border colors.
- **Done when**: `grep -rn "transition-all" apps/web/src` returns only AdminDashboardClient:76,262 and DimensionBreakdown:62 (plan 004's sites), and no product card moves on hover.
