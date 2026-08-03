# 004 — Normalize bar-fill motion and consolidate the viz easing curve

- **Status**: DONE
- **Commit**: 666ce88
- **Severity**: MEDIUM
- **Category**: Easing & duration / Performance / Cohesion & tokens
- **Estimated scope**: 6 files, ~8 line edits

## Problem

The same visual gesture — a value bar filling — is implemented at 400ms, 500ms, and 700ms with three property strategies and two hand-typed curves:

```tsx
/* apps/web/src/app/(dashboard)/admin/AdminDashboardClient.tsx:76 — 700ms transition-all on a width bar */
className="h-full bg-studio-dark-cork rounded-sm transition-all duration-700"

/* apps/web/src/app/(dashboard)/admin/AdminDashboardClient.tsx:262 — same */
className={`h-full rounded-sm transition-all duration-700 ${dq.pct > 20 ? "bg-cohere-coral" : dq.pct > 5 ? "bg-amber-500" : "bg-cohere-green"}`}

/* apps/web/src/components/matches/DimensionBreakdown.tsx:62 — 700ms transition-all width bar */
className={`h-full rounded-full transition-all duration-700 bg-cohere-blue ${isNullHandled ? "opacity-30" : ""}`}

/* apps/web/src/app/(dashboard)/admin/foundation/FoundationClient.tsx:82 — 500ms width */
className="h-full rounded-full bg-cohere-green transition-[width] duration-500 ease-cohere"

/* apps/web/src/app/(dashboard)/applicant/applications/MyApplicationsClient.tsx:153 — 500ms width, no easing specified */
className="absolute left-3 top-1.5 h-0.5 bg-studio-forest transition-[width] duration-500"

/* apps/web/src/components/viz/TrendLine.tsx:93 and MarketplaceFunnel.tsx:61 — duplicated hand-typed curve */
const ease = "cubic-bezier(0.22, 1, 0.36, 1)";
```

Violations: 700ms and 500ms exceed the ≤400ms chart-entrance budget (DESIGN_CONTRACT.md) and the sub-300ms UI budget; `transition-all` is always a finding; `width` is a layout property; a second ease-out curve almost-duplicates the house token `cubic-bezier(0.16, 1, 0.3, 1)`.

Note: these bars render once with their final width, so the 500–700ms transitions are mostly latent (they'd only run on a data change) — dead motion code that still carries the `transition-all` hazard.

## Target

One rule: value bars either don't animate (static fills that never change) or transition width at 300ms with the house curve (fills that update in place). The viz components use the house curve.

```tsx
/* AdminDashboardClient.tsx:76 — target (static fill: delete the transition) */
className="h-full bg-studio-dark-cork rounded-sm"

/* AdminDashboardClient.tsx:262 — target */
className={`h-full rounded-sm ${dq.pct > 20 ? "bg-cohere-coral" : dq.pct > 5 ? "bg-amber-500" : "bg-cohere-green"}`}

/* DimensionBreakdown.tsx:62 — target */
className={`h-full rounded-full bg-cohere-blue ${isNullHandled ? "opacity-30" : ""}`}

/* FoundationClient.tsx:82 — target */
className="h-full rounded-full bg-cohere-green transition-[width] duration-300 ease-cohere"

/* MyApplicationsClient.tsx:153 — target */
className="absolute left-3 top-1.5 h-0.5 bg-studio-forest transition-[width] duration-300 ease-cohere"

/* TrendLine.tsx:93 and MarketplaceFunnel.tsx:61 — target (house curve, one comment) */
const ease = "cubic-bezier(0.16, 1, 0.3, 1)"; // ease-cohere (tailwind.config.ts)
```

## Repo conventions to follow

- House curve: `ease-cohere` = `cubic-bezier(0.16, 1, 0.3, 1)` (tailwind.config.ts `transitionTimingFunction.cohere`). Inline styles can't reference the Tailwind token, so hand-inline the value with the `// ease-cohere` comment as shown.
- Exemplar of a correct animated bar entrance already in the repo: `apps/web/src/components/viz/ShareBars.tsx:51` — static `width` + `transform: scaleX()` from a `mounted` flag at 400ms. Do not convert the bars in this plan to that pattern (adds state/markup); just delete latent transitions or scope + retime them.

## Steps

1. `AdminDashboardClient.tsx:76` — delete `transition-all duration-700` from the className.
2. `AdminDashboardClient.tsx:262` — delete `transition-all duration-700`.
3. `DimensionBreakdown.tsx:62` — delete `transition-all duration-700`.
4. `FoundationClient.tsx:82` — `duration-500` → `duration-300` (keep `transition-[width]` and `ease-cohere`; this bar can update when a report regenerates).
5. `MyApplicationsClient.tsx:153` — `transition-[width] duration-500` → `transition-[width] duration-300 ease-cohere` (progress rail updates as an application advances).
6. `TrendLine.tsx:93` — replace the curve with `"cubic-bezier(0.16, 1, 0.3, 1)"` and add the `// ease-cohere` comment.
7. `MarketplaceFunnel.tsx:61` — same replacement.

## Boundaries

- Do NOT touch `ShareBars.tsx` (already correct at 400ms/ease-out/transform).
- Do NOT add mount-state entrance animation to any bar.
- Do NOT change bar colors, sizes, `Math.max` width floors, or markup.
- If a cited line does not match its excerpt (drift), STOP and report.

## Verification

- **Mechanical**: `pnpm --filter web typecheck`, `pnpm --filter web lint` — no errors. `grep -rn "transition-all" apps/web/src` → zero hits (assuming plan 003 ran first). `grep -rn "cubic-bezier(0.22" apps/web/src` → zero hits.
- **Feel check**: open /admin (bars render instantly, no late fill), a match detail with the dimension breakdown (bars present immediately on expand), and /admin/engagement or wherever TrendLine renders (line still draws in over 400ms with a decisive settle).
- **Done when**: greps above are clean and no bar animates longer than 300ms.
