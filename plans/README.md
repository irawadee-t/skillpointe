# Animation improvement plans

Produced by the `improve-animations` audit at commit `666ce88` (2026-07-21).
Each plan is self-contained: exact file:line citations, target values, boundaries,
and a feel-check. Execute with any agent; review the diff with `review-animations`.

## Plans

| # | Plan | Severity | Category | Status |
| --- | --- | --- | --- | --- |
| 001 | [Press feedback on every pressable](001-press-feedback.md) | HIGH | Physicality | DONE |
| 002 | [Honor reduced motion in Motion components](002-motion-reduced-motion.md) | HIGH | Accessibility | DONE |
| 003 | [Scope `transition-all`, remove card hover lifts](003-scope-transitions-remove-lifts.md) | HIGH | Performance / Cohesion | DONE |
| 004 | [Normalize bar fills, consolidate viz easing](004-bar-fills-and-viz-easing.md) | MEDIUM | Easing / Performance | DONE |
| 005 | [Retune dashboard scroll reveals](005-dashboard-reveal-retune.md) | HIGH | Purpose & frequency | DONE |

## Recommended execution order

1. **005** (globals.css only, biggest per-visit feel change, zero dependencies)
2. **001** (globals.css + one component; independent)
3. **003** (component sweep; its "done when" grep expects 004's sites to remain)
4. **004** (finishes the `transition-all` cleanup started in 003)
5. **002** (independent; last so the feel-check of 001/003/005 happens with motion fully on)

Dependencies: 003 and 004 share the `grep -rn "transition-all"` acceptance check —
after both run, the grep must return zero hits. 001/002/005 are independent.

## Findings not planned (tracked for a future pass)

- Toast entrance uses `@keyframes` (`components/ui/Toast.tsx:126`) — stacking toasts restart from zero; convert to transitions/`@starting-style`. MEDIUM.
- Expand/collapse height tweens (`MatchesClient`, `JobBrowseClient`, `AIPriorityPanel`, `DashboardNav`) — fixed-duration `height: auto` tweens; springs would carry velocity on rapid toggle. MEDIUM.
- WebGL orbs (`InteractiveOrb`, `LiquidInk`, `AuroraWater`, `SmokeOrb`, `ui/Orb`) never pause when scrolled offscreen. MEDIUM.
- Aurora surface animates a 34px-blurred layer continuously (`globals.css:93-94`) — over the 20px blur budget. Marketing/auth-only surface; HIGH cost, low frequency.
- Blanket reduced-motion rule flattens even opacity feedback to 0.01ms (`globals.css:324-336`) — gentler handling would keep short fades. LOW-MEDIUM.
- Missed opportunities: match-card removal teleports (`MatchesClient.tsx:87,120`), chat bubbles appear without entrance (`ChatClient.tsx:77,94`), notification tray teleports from bell (`NotificationTray.tsx:95`), mobile sidebar drawer doesn't slide (`AppSidebar.tsx:303`).
