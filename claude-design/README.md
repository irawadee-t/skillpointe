# SkillPointe Match — Design System Bundle

A complete, self-contained capture of the whole product, built for a **design revamp** in
Claude Design (or any AI design tool). Everything is plain HTML — open `index.html` in a
browser to browse it all.

## What's inside

```
claude-design/
├── index.html                  ← browsable gallery of everything (start here)
├── foundations/                Color · Typography · Spacing/Radius/Elevation
├── components/                 Buttons · Cards & MetricCards · Chips/Labels/Badges · Inputs/Forms/Nav
├── architecture/               IA & routes · User flows · Data model · Design language (do's & don'ts)
└── screens/                    20 screens — each a real full-page screenshot + layout & component notes
```

Every preview file starts with a `<!-- @dsCard group="…" -->` marker, which is exactly how
Claude Design indexes cards into its Design System pane (Foundations / Components /
Architecture / Screens · per-role).

Coverage: **public** (landing, login, signup), **applicant** (setup, matches, jobs, profile,
chat, messages), **employer** (dashboard, analytics, post-a-job, messages), **admin**
(dashboard, applicants, employers, employer detail, engagement, job map, test-matches).

## How to get it into Claude Design

Pushing **directly** from this (non-terminal) environment is blocked by a one-time
design-system authorization that only works from an interactive terminal. Pick whichever
route is easiest:

**Option A — authorize once, then sync (most automated)**
1. Open an interactive terminal and run `claude`, then `/design-login` to grant design access.
2. In that session say: *"sync the `claude-design/` folder into a new Claude Design project called 'SkillPointe Match'."*
   It will create the project and upload every card via DesignSync.

**Option B — start from Claude Design's side**
1. In Claude Design, create a project → **"Send to Claude Code Web"** (this seeds the project here).
2. Then ask Claude to sync this `claude-design/` folder into it.

**Option C — use it as reference now (no setup)**
- Open `index.html` to browse, or drag the `screens/*.png` and the `architecture/*.html`
  into a Claude conversation as attachments. With the architecture + design-language docs +
  screenshots, Claude understands the whole site and can propose a revamp immediately.

## Notes
- Screenshots reflect local seed/test data; empty-state screens (e.g. a test applicant with
  no matches) look sparse simply because there's no data — the layouts fill with real data.
- The design language is documented in `architecture/04-design-language.html` (do's & don'ts)
  so any revamp stays coherent — or intentionally departs from it.
