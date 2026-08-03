# 005 — Retune scroll reveals for daily-use dashboards

- **Status**: DONE
- **Commit**: 666ce88
- **Severity**: HIGH
- **Category**: Purpose & frequency / Easing & duration
- **Estimated scope**: 1 file (globals.css), ~15 line edits

## Problem

`.reveal` / `.stagger` are marketing-length entrances (550–600ms, 20px travel, stagger tail up to 600ms delay) applied to product dashboards the user opens many times a day — applicant dashboard (`app/(dashboard)/applicant/page.tsx:63+`), employer dashboard (`employer/page.tsx:80,95,158`), job browse (`JobBrowseClient.tsx:135`), message inboxes, chat session list, employer analytics. The IntersectionObserver in `components/ui/Reveal.tsx` latches per mount, so the full choreography replays on every route visit. The 11th+ list item waits 600ms and finishes fading ~1.15s after mount — content-blocking on lists that are the product's daily surface.

```css
/* apps/web/src/app/globals.css:247-254 — current */
.reveal {
  opacity: 0;
  transform: translateY(20px);
  transition:
    opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}

/* apps/web/src/app/globals.css:264-271 — current */
.stagger > * {
  opacity: 0;
  transform: translateY(20px);
  transition:
    opacity 0.55s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.55s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}

/* apps/web/src/app/globals.css:276-286 — current ladder */
.stagger.is-visible > *:nth-child(1) { transition-delay: 0s; }
.stagger.is-visible > *:nth-child(2) { transition-delay: 0.06s; }
.stagger.is-visible > *:nth-child(3) { transition-delay: 0.12s; }
.stagger.is-visible > *:nth-child(4) { transition-delay: 0.18s; }
.stagger.is-visible > *:nth-child(5) { transition-delay: 0.24s; }
.stagger.is-visible > *:nth-child(6) { transition-delay: 0.30s; }
.stagger.is-visible > *:nth-child(7) { transition-delay: 0.36s; }
.stagger.is-visible > *:nth-child(8) { transition-delay: 0.42s; }
.stagger.is-visible > *:nth-child(9) { transition-delay: 0.48s; }
.stagger.is-visible > *:nth-child(10) { transition-delay: 0.54s; }
.stagger.is-visible > *:nth-child(n + 11) { transition-delay: 0.6s; }
```

Rule violated: frequency table — surfaces seen tens-to-100+ times/day get "remove or drastically reduce"; UI budget < 300ms; stagger must never block interaction.

## Target

Drastically reduce (not delete — the settle still prevents a hard pop on slower data loads): 300ms, 8px travel, 40ms stagger steps capped at 160ms. Worst-case list item now completes ~0.46s after mount instead of ~1.15s.

```css
/* target */
.reveal {
  opacity: 0;
  transform: translateY(8px);
  transition:
    opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}

.stagger > * {
  opacity: 0;
  transform: translateY(8px);
  transition:
    opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}

.stagger.is-visible > *:nth-child(1) { transition-delay: 0s; }
.stagger.is-visible > *:nth-child(2) { transition-delay: 0.04s; }
.stagger.is-visible > *:nth-child(3) { transition-delay: 0.08s; }
.stagger.is-visible > *:nth-child(4) { transition-delay: 0.12s; }
.stagger.is-visible > *:nth-child(n + 5) { transition-delay: 0.16s; }
```

## Repo conventions to follow

- The curve `cubic-bezier(0.16, 1, 0.3, 1)` is the house `ease-cohere` token — keep it, change only durations/distances/delays.
- These utilities live in `@layer utilities` in `apps/web/src/app/globals.css`; edit in place. The reduced-motion guard at globals.css:331-335 (`.reveal, .stagger > * { opacity: 1 !important; … }`) must remain untouched.
- Marketing pages share these classes; 300ms/8px still reads as an editorial settle there — accepted tradeoff, do not fork a marketing variant.

## Steps

1. In `apps/web/src/app/globals.css`, edit `.reveal`: `translateY(20px)` → `translateY(8px)`; both `0.6s` → `0.3s`.
2. Edit `.stagger > *`: `translateY(20px)` → `translateY(8px)`; both `0.55s` → `0.3s`.
3. Replace the 11-rule delay ladder with the 5-rule ladder shown in Target (steps of 0.04s, cap 0.16s at `:nth-child(n + 5)`).

## Boundaries

- Do NOT edit `components/ui/Reveal.tsx` (the IO logic and 1400ms visibility fallback are correct).
- Do NOT remove `.reveal`/`.stagger` from any page.
- Do NOT touch the reduced-motion block.
- If the current values differ from the excerpts (drift), STOP and report.

## Verification

- **Mechanical**: `pnpm --filter web typecheck`, `pnpm --filter web lint` — no errors.
- **Feel check**: reload /applicant and /applicant/jobs several times in a row:
  - Content settles into place in ~a third of a second; nothing feels like a landing page intro.
  - On the jobs list, the last visible card starts within ~160ms of the first — no row is still invisible half a second after mount.
  - DevTools > Rendering > prefers-reduced-motion: reduce → everything appears instantly, fully opaque.
- **Done when**: no `.reveal`/`.stagger` transition exceeds 0.3s and no stagger delay exceeds 0.16s.
