# 002 — Honor prefers-reduced-motion in all Motion (framer) components

- **Status**: DONE
- **Commit**: 666ce88
- **Severity**: HIGH
- **Category**: Accessibility
- **Estimated scope**: 2 files (new MotionProvider component + root layout), ~20 lines

## Problem

The global CSS reduced-motion block (`apps/web/src/app/globals.css:324-336`) only affects CSS animations/transitions. The app's ~14 Motion (`motion/react`) components animate `y`/`x`/`scale`/`height` via inline styles driven by JS, which that CSS block cannot stop. There is no `MotionConfig` anywhere (`grep -rn "MotionConfig" apps/web/src` → zero hits) and only `AnnouncementBar.tsx` calls `useReducedMotion()`. A reduced-motion user still gets the full transform choreography in, e.g.:

```tsx
/* apps/web/src/app/(dashboard)/applicant/setup/page.tsx:193-196 — current */
initial={{ opacity: 0, y: 12 }}
animate={{ opacity: 1, y: 0 }}
exit={{ opacity: 0, y: -12 }}
transition={{ duration: 0.35, ease: easeCohere }}
```

Same pattern (unbranched transforms) in: MatchesClient.tsx:349-361 and 498-512, JobBrowseClient.tsx:254-257, AIPriorityPanel.tsx:94-97 and 118-120, DashboardNav.tsx:57-62 and 94-97, OutreachModal.tsx:197-199, ChatJobPicker.tsx:228-230, VerifiedWorkersClient.tsx:281-283, SkilledIdConsole.tsx:352-353, FoundationClient.tsx:207, MarketingNav.tsx:36-38, HeroConsole.tsx:17-18 and 50-51, Card.tsx:82,95.

## Target

Motion ships exactly the right lever: `<MotionConfig reducedMotion="user">` disables transform/layout animations while keeping opacity/color animations when the OS reports reduced motion — precisely the "fewer and gentler, not zero" rule. One provider at the root covers every current and future `motion.*` component.

```tsx
/* target — apps/web/src/components/MotionProvider.tsx (new file) */
"use client";

import { MotionConfig } from "motion/react";

/** App-wide Motion config: when the OS asks for reduced motion, Motion
 *  drops transform/layout animation but keeps opacity — gentler, not zero. */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
```

```tsx
/* target — apps/web/src/app/layout.tsx: wrap the body contents */
<MotionProvider>{children}</MotionProvider>
```

## Repo conventions to follow

- The motion package is `motion` v12 (`"motion": "^12.42.0"` in apps/web/package.json); components import from `"motion/react"` — e.g. `apps/web/src/lib/motion.ts:1`.
- Shared client-side primitives live in `apps/web/src/components/` (e.g. `components/ui/Reveal.tsx`); server layouts may render client components that accept `children` — this keeps the children as server components.

## Steps

1. Create `apps/web/src/components/MotionProvider.tsx` with the exact contents shown in Target.
2. In `apps/web/src/app/layout.tsx`, import `{ MotionProvider }` and wrap the direct children of `<body>` (the existing `{children}` expression) in `<MotionProvider>…</MotionProvider>`. Change nothing else in the layout.

## Boundaries

- Do NOT edit the individual motion components — the provider covers them.
- Do NOT remove the `useReducedMotion()` branch already in `AnnouncementBar.tsx` (it is a correct, finer-grained fallback).
- Do NOT touch the global CSS reduced-motion block.
- If `layout.tsx` has no plain `{children}` inside `<body>` (drift), STOP and report.

## Verification

- **Mechanical**: `pnpm --filter web typecheck` and `pnpm --filter web lint` — no errors.
- **Feel check**: DevTools > Rendering > "Emulate CSS prefers-reduced-motion: reduce", then:
  - Expand a match card on /applicant/matches: the panel should appear essentially without the height/slide choreography (content still readable, opacity change OK).
  - Reload /applicant/setup: the step card must not slide up.
  - Turn emulation off and confirm all animations return.
- **Done when**: with reduced motion emulated, no `motion.*` component moves/scales/slides anywhere in the dashboard; with it off, behavior is unchanged.
