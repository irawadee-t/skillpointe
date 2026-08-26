# Production sync runbook — get prod to parity with local

Written 2026-08-25, the night before the Turner demo. Prod diagnosis:
web (Vercel) and API (Railway) auto-deploy every push, but database
migrations never ran in prod — so prod runs TODAY'S code against JULY'S
schema. Result: the site loads, login works, and every matches page 500s.
Prod data is also the July seed (393 jobs, no PSA applicants).

Time to full parity: ~2.5–4 hours, mostly unattended.

## Phase 0 — THE BLOCKER FOUND IN THE DASHBOARD (2026-08-26)

The Supabase org (irawadee-t's Org) is on the FREE plan and the banner
reads EXCEEDING USAGE LIMITS: Database Size 0.691 / 0.5 GB (138%) — with
only July's data. Free-tier overage triggers service restrictions, and
the launch dataset needs far more room: the full local database is 16 GB
(matches ~7 GB + per-dimension scores ~9 GB, including bloat; a fresh
load lands roughly 4–8 GB).

REQUIRED FIRST: upgrade the org to Pro ($25/mo, 8 GB disk included,
auto-expanding beyond) in the Supabase dashboard -> Organization ->
Billing. This is a purchase — only you can click it. Without it, the
migration push may fail against an over-quota project and the data sync
cannot fit at all.

Optional slimming if you want to stay near 8 GB: per-dimension score rows
for VISIBLE matches only (the invisible ineligible rows' breakdowns are
never rendered) — say the word and Claude will add that switch to the
recompute before you run Phase 2.

## Phase 0.5 — The slowness incident, RESOLVED (2026-08-26 afternoon)

Symptom: every page crawled (10s+ loads), Supabase auth intermittently
failed to issue tokens, the dashboard SQL editor stalled. Cause: the
deployed API's background machinery (minute-cadence match-worker
supervision, freshness probes, sweeps) was hammering the nano-compute
prod database — 37/60 connections, 56% sustained DB CPU.

Two fixes shipped and verified:

1. **Background jobs are now opt-in in production** (65b8afd, a588314).
   The deployed API serves requests only. To turn background processing
   on later (after the DB is provisioned for it — Supabase compute
   upgrade beyond nano recommended first), set `BACKGROUND_JOBS_ENABLED=true`
   in Railway service variables and redeploy. Until then, job/profile
   edits in prod still enqueue to `match_queue` (cheap, lossless) — the
   work runs whenever a worker is next enabled, and match reads use the
   precomputed rows.

2. **Railway watch paths fixed** (bba0997 + dashboard). The API service
   was watching `/apps/web/**` (the frontend dir!), so backend pushes
   were skipped as "No changes to watched files" — this is why prod ran
   stale code through both incidents. Patterns now: `/apps/api/**`,
   `/packages/**`, `/scripts/**`, `/railway.json`, `/Dockerfile` — in
   the dashboard AND in `railway.json` (config-as-code).

Verified after deploy: auth ~0.5s, matches/profile 0.2–0.4s warm, no
worker sessions on the DB, 0 blocked queries.

## Phase 1 — YOU (needs the prod DB password; ~10 minutes)

From the repo root:

```bash
supabase link --project-ref ywgnrlpogioftbhhshlt
```

```bash
supabase db push
```

That applies every pending migration (taxonomy, ontology columns, n_gaps,
score_evidence_pct, match_queue, enqueue triggers, partner staging — the
lot). It is additive; nothing existing is dropped.

Then set the prod database URL in your shell for Phase 2's import scripts
(replace the password placeholder; do not paste the URL anywhere else):

```bash
export DATABASE_URL="postgresql://postgres:YOUR_DB_PASSWORD@db.ywgnrlpogioftbhhshlt.supabase.co:5432/postgres"
```

Also, in the Railway dashboard → the API service → Variables: set
`SUPABASE_ANON_KEY` (from Supabase dashboard → Settings → API). The
health endpoint has reported it missing since day one.

## Phase 2 — YOU run, unattended (~60–90 min total)

```bash
cd apps/api && source .venv/bin/activate && cd ../..
```

```bash
python scripts/remap_taxonomy.py
```

```bash
python scripts/import_psa_applicants.py --file "/Users/riyakarumanchi/Downloads/PSA Migration Data_For Tasha_July2026.xlsx"
```

```bash
python scripts/classify_applicant_fields.py
```

```bash
python scripts/extract_job_ontology.py
```

```bash
for K in 0 1 2 3 4 5 6 7; do python scripts/recompute_matches.py --prefilter --skip-geocode --shard $K/8 & done; wait
```

## Phase 3 — Claude can drive (through the prod API, no secrets needed)

Once Phase 1–2 are done, say the word and I will, against prod:
- create the six new partner employers + career sources
- run all partner pulls (Workday / Cornerstone / m-cloud / sitemap paths)
- approve the trades batches; the triggers + recompute handle matching
- verify the demo flows end-to-end (login → matches → admin readiness)

## Demo fallback for tomorrow (zero risk)

If Phase 1 can't happen tonight: demo from the LOCAL environment
(everything in this repo works fully at localhost:3000) via screen share,
and send Alvin the corrected link for the meeting:

    https://skilled-nation.vercel.app      <- CURRENT
    https://skillpointe.vercel.app         <- DEAD (project renamed; 451)

Test logins (work in prod already): admin@test.local / applicant@test.local
/ employer@test.local — password Test1234!  (rotate before any public beta).
