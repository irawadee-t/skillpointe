# SKILLED Nation — Product Design Contract (v2 — ElevenLabs-clean)

The product reads like elevenlabs.io: near-white canvas, black ink, clean sans
type at modest weights, generous whitespace, hairline separation, pill buttons,
and ONE brand moment — the deep-red sidebar chrome. Binding for every product
surface (`/applicant`, `/employer`, `/admin`, `/account`). Marketing + auth may
keep their atmospheric surfaces.

## The v2 identity (supersedes any older rule below that conflicts)
- **Type:** `font-display` IS the sans (tight tracking −0.02em, weight 450 via
  globals). The serif is retired from the product; `font-serif` exists for rare
  marketing moments only. Never reintroduce serif on product pages.
- **Chrome:** sidebar/drawer = deep brand red `#5c101e` (skilled-nation.org
  crimson family, darkened), cream/white text, white active rail. Never pink,
  never brown.
- **Buttons:** ElevenLabs pills (`rounded-full`). Primary = `bg-ink` black,
  white text, hover pure black. Secondary/ghost = white pill, hairline border,
  ink text. Commit (Apply/Verify/Confirm) = brand red `bg-studio-maroon`.
- **No brown anywhere.** `bg-studio-dark-cork` is retired from product
  surfaces; intentional dark chips/toasts use neutral `bg-ink`.
- **Orb:** deep-red family only (#9d2235 / #5c101e), never pink/salmon.

## Banned patterns ("AI tells") — remove on sight
1. **Gradient/ombre panel fills** on product surfaces. `aurora-surface` /
   `card-green` are retired from product code (marketing/auth only).
2. **Big numeral + tiny label under it** (the KPI-card pattern). Numbers live
   inside sentences ("337 workers · 12 this week") or in `MetricCard`, which is
   now a flat phrase-stat. Never build a bespoke big-number/whisper-label block.
3. **ALL-CAPS microcopy** — buttons, chips, section labels. Sentence case
   everywhere. (The `btn-*` classes are already sentence case — do not add
   `uppercase` back.)
4. **Icon-in-a-tinted-circle** decorations next to list items or stats.
   Icons are rare, small (16px), inline, and functional only.
5. **Progress rings / donut gauges** for single percentages. Use a thin linear
   bar or a sentence.
6. **Card-grid-of-everything.** Cards are for actionable list items only
   (a match, a candidate). Informational content sits directly on the canvas
   under a display heading, or in ONE flat white sheet with hairline rows.
7. **Tone circus** — no per-card color themes (green/navy/coral panels).
   Color carries meaning only: eligibility accents and the single brand accent.

## The canvas — clean near-white (ElevenLabs-grade, NOT beige)
The page floor is **near-white `canvas` `#fcfcfb`** — not the old warm cream.
The whole product reads white + ink + generous whitespace, calm and
uncluttered, like elevenlabs.io. Neutrals are cool/neutral, never warm-beige:
`parchment #f5f5f4` and `stone #f2f2f1` are neutral light grays used only for a
rare subtle inset (a showcase panel), never a heavy fill; secondary text is
neutral charcoal `slate #33322f` / muted `#5c5a55`; hairline `#e7e5e2`. There is
no beige anywhere in the light UI. (The dark sidebar chrome `#1c0a10` and the
marketing/auth aurora hero are intentional brand moments and stay.)

## The one surface style — Airbnb card language
Cards read as **white on the near-white canvas**, separated by a hairline and a
hover shadow. The target is "90% white + ink".

- **Surface: pure white `bg-white`.** No tint, ever — not on match cards,
  credential cards, application cards, job cards, candidate cards, or metric
  cards. There are no tinted card fills in this system.
- **Radius ladder:** cards `rounded-[14px]`; buttons and inputs 8px
  (`rounded-[8px]`); pills and chips fully round (`rounded-full`).
  Essentially no hard corners on interactive elements.
- **Border:** 1px hairline — `border border-hairline` (`#d9d5cc`). One
  hairline token only; never add a second.
- **Elevation: ONE tier, and only on hover.** Cards are FLAT at rest — no
  resting shadow. Hover applies `shadow-float`, defined once in
  `tailwind.config.ts` as:

  ```
  box-shadow: rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.04) 0 2px 6px 0, rgba(0,0,0,0.1) 0 4px 8px 0
  ```

  The same token is the only elevation for floating surfaces (dropdowns,
  notification tray, command palette). Never write a bespoke
  `shadow-[0_16px_40px…]`, and never use `shadow-subtle` on a card.
- **No hover lift.** Hover = the shadow appears (plus any existing color
  change). No `translate-y`, no `scale`, no movement of any kind. Transition
  stays 200ms over color/background/border/box-shadow — never `transition-all`.
- **Internal padding:** 24px (`p-6`) for content cards; 16px (`p-4`) for dense
  meta blocks such as `MetricCard`.
- **Grid gutters:** 16px between cards (`gap-4` / `space-y-4`).
- **Type inside cards** (our existing families — the sans; serif discipline
  below still applies): item title 16px/600, secondary meta 14px/400 in the
  muted tone, micro/badge 11px/600. Modest weights — nothing 700+ inside a card.
- **No tinted card fills, no progressive elevation tiers, no hover lift.**
  - *Scoped exception — badge showcase cards only:* earned achievement badges
    (`components/badges/`) may use a pointer-move 3D tilt capped at ±8deg,
    eased and settling back on leave — pointer-only (no touch) and disabled
    under `prefers-reduced-motion`. Content and list cards remain flat.
- White sheet: `rounded-[10px] border border-hairline bg-white` — for
  informational content, forms, and grouped hairline-row lists.
- Rows inside a sheet divide with `border-t border-hairline`, padding `px-5 py-3.5`.
- Section = display heading (`font-display text-feature text-cohere-ink`) +
  optional right-aligned quiet action (`text-body text-slate hover:text-cohere-ink`).
- Page = `page-shell` container, sections separated by `mt-10`, NOT stacked cards.
- Dark panels: only when hierarchy truly demands one per page, flat
  `bg-studio-dark-cork`, never washed.

### No red text on dark surfaces
On any dark or brown ground — the sidebar/drawer chrome (`#1c0a10`),
`bg-studio-dark-cork` panels, `Card tone="ink"`, `SectionBand`/`DarkBand` —
the brand red (`#9d2235` family: `text-studio-maroon`, `text-cohere-coral`,
`text-error-red`, `text-[#c34f63]`) **must never be used for text**. It reads
muddy and fails contrast against those grounds.

- Text on dark = `text-studio-cream` / `text-white`, dimmed with opacity
  (`/70`, `/60`, `/45`) for secondary and muted levels. Icons follow the same
  rule.
- Red may appear on dark **only as a small non-text accent** — an active-item
  rail, a status dot, a hairline — and only where it clears 3:1 against the
  ground. The sidebar's active rail uses `#d45c72` (5.1:1 on `#1c0a10`);
  do not darken it back toward `#9d2235`.
- Error and warning states inside a dark panel use cream text plus an icon,
  not red text.
- Red text remains correct on light grounds (canvas, white sheets, white cards).

## Typography
- **Serif discipline.** The display serif (`font-display`) is reserved for
  page-level H1s and top-level section headings that sit directly on the
  canvas — nothing else. Every content-item title (match card titles,
  credential names, application titles in lists, chat/session headers) and
  every panel/modal heading ("What the employer saw", wizard steps, dialog
  titles) uses the sans: `text-[1.0625rem] font-medium` for item titles and
  panel headings, `text-[1.25rem] font-semibold` for large item titles
  (e.g. the match-card title). If a heading lives inside a card, sheet, or
  modal, it is sans. Display-serif numerals (scores, headline stats) are
  allowed.
- Headings: `font-display` ink (within the rule above). Body: `text-body`.
  Secondary: `text-slate`.
- Muted: `text-slate-muted`. Numbers: `tabular-nums`, same size as body text
  unless they are the page's single headline fact.

## Chips & status labels
- Status chips ("Self-reported", "In review", "Eligible", "Verified, NCCER")
  are quiet metadata, never title-sized: `text-[11px] px-2 py-0.5`,
  sentence case, `font-medium` at most. A chip must read clearly smaller
  than the title it sits beside.

## Status & chip color semantics
One semantic color system governs EVERY status/label chip in the product.
The single source of truth is `src/components/ui/statusTones.ts`
(`STATUS_TONE_CLASSES` + one exported map per domain). Never hand-roll a
status color — import the slot.

**The rule: one visual dimension = one meaning.** Hue encodes the semantic
slot. The same entity renders identically everywhere it appears — list,
detail, card, modal, admin console. Verification/level/tier is an **affix**
(a small icon + micro-label, or a separate chip like `VerificationBadge`) —
**never a recolor of the entity's name.**

**The fill rule: status chips are SOLID DARK fills with white text — never a
light tint with darker same-hue text.** The tint-plus-matching-text pair
("highlighter" chips: light green bg + dark green text, wash-blue + blue
text, maroon-wash + maroon text) is a banned AI tell — remove on sight.
Intensity within a slot is encoded as outline (white bg, colored border/
text — allowed) → solid dark. Neutral/muted stay quiet grays (stone/slate is
not the highlighter pattern). Every solid fill must pass AA (≥4.5:1) with
white text: `cohere-blue` #1863dc 5.4:1 · `cohere-navy` #071829 17+:1 ·
`cohere-green` #4a4b2f 9.0:1 · `cohere-green-deep` #31321f 12+:1 ·
`studio-maroon` #9E1B32 7.9:1 · `error-red` #b30000 7.2:1.

The same rule extends to **banners/alerts**: a tinted panel may keep its soft
wash ONLY with `text-cohere-ink` body text (hue lives in the border and
icon). Never same-hue text on a same-hue tint.

### The semantic slots
| Slot | Classes | Means |
|---|---|---|
| `neutral` | `border-hairline bg-white text-slate` | informational metadata, categories, skills, credential names, self-reported |
| `progress` | `border-cohere-blue bg-cohere-blue text-white` | in-flight: in review, pending, proposed, awaiting |
| `progressSolid` | `border-cohere-navy bg-cohere-navy text-white` | actively engaged (interviewing) |
| `positive` | `border-cohere-green bg-cohere-green text-white` | good: shortlisted, verified, approved, healthy, confirmed |
| `positiveOutline` | `border-cohere-green/50 bg-white text-cohere-green` | positive awaiting acceptance (offered) |
| `positiveSolid` | `border-cohere-green-deep bg-cohere-green-deep text-white` | strong terminal positive (hired) |
| `attention` | `border-studio-maroon bg-studio-maroon text-white` | needs action NOW: new application, stale, near fit, gaps — use sparingly |
| `danger` | `border-error-red bg-error-red text-white` | true failure/error only (sync down, broken link, error toast) |
| `muted` | `border-hairline bg-stone/40 text-slate-muted` | terminal/inactive: rejected, withdrawn, closed, disabled, draft |

Chip shell: `STATUS_CHIP_BASE` = `rounded-full border px-2 py-0.5 text-[11px]
font-medium`, sentence case. Solid `bg-ink` is reserved for **emphasis that is
not a status** ("Top pick", "Partner") and for active filter/selection states.

### Domain mappings (each has ONE exported map)
- **Application stages** (`APPLICATION_STATUS_TONES`, rendered only via
  `<ApplicationStatusChip>`): submitted/New = attention → reviewed/In review =
  progress → shortlisted = positive → interviewing = progressSolid → offered =
  positiveOutline → hired = positiveSolid → rejected/withdrawn = muted.
  Employer and applicant views may word labels differently ("New" vs
  "Submitted") but the COLORS are identical for the same status.
- **Interview scheduling** (`INTERVIEW_STATUS_TONES`): proposed/pending =
  progress, accepted/confirmed = positive, completed/declined/cancelled =
  muted, no_show = attention.
- **Credentials**: the credential NAME chip is always `CREDENTIAL_CHIP_CLASS`
  (neutral) — "OSHA 10" looks identical on every card, page, and console.
  Verification is the affix: `VERIFICATION_LEVEL_META` — level ≥1 = positive
  solid (dark green, white text) + ShieldCheck/BadgeCheck and the level in the LABEL
  ("SKILLED-verified" / "Institution-verified"); level 0 = neutral
  "Self-reported". Review-pending = progress ("In review"/"Needs review").
- **Match tiers** (shared `MatchLabel`/`EligibilityBadge` only): strong fit =
  green outline, good fit = blue outline, moderate = slate, low = slate-muted;
  Eligible = green outline, Near fit = maroon outline. Never re-derive tier
  colors or labels locally.
- **Sync/import health** (`HEALTH_TONES`): ok/approved/live = positive,
  running/pending/in review = progress, stale/needs-attention = attention,
  failed/down = danger, draft/paused/disabled = muted.
- **Interest signals**: applied = positive, interested = progress,
  not interested = neutral/muted — same hues on the applicant's toggle and the
  employer's badge.
- **Notifications** (`KIND_META`): good news = positive, informational =
  progress, action-required = attention.
- **Unread indicators**: always `bg-cohere-blue` (dot or count bubble) — never
  green, never maroon.

`error-red` vs `studio-maroon`: maroon = "a human should act" (attention);
`error-red` = "the system failed" (danger). Never mix them.
`studio-forest` and `cohere-coral` are retired from status chips — use
`cohere-green` / `studio-maroon`. `border-studio-maroon-soft` does not exist
as a token; use `border-studio-maroon/30`.

## Chat surfaces
- Consecutive same-role messages group: 4px gaps inside a group, avatar
  (OrbMark) only on the first message of an assistant group.
- Bubbles max out at `65ch`; timestamps appear on hover only.
- Composer: single-row input at 44px min height, square send button matching.
- Suggested-question chips share one style everywhere:
  `rounded-full border-hairline bg-white px-3 py-1.5 text-caption`.

## Data visualization (D3)
- d3 for scales/shape/interpolation; render as inline SVG in React (no
  d3-selection DOM manipulation).
- One accent (`#9d2235` family) + ink/hairline neutrals. No categorical rainbow.
- No gridline cages, no heavy axes: hairline baseline, 3–4 tick labels max,
  direct labeling on the data instead of legends wherever possible.
- Motion: one entrance transition (≤400ms, ease-out), then still. Tooltips are
  quiet white sheets with hairline borders.
- A chart must answer a real question; if a sentence answers it better, use
  the sentence.
