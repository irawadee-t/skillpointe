# Production sync runbook — get prod to parity with local

Written 2026-08-25, the night before the Turner demo. Prod diagnosis:
web (Vercel) and API (Railway) auto-deploy every push, but database
migrations never ran in prod — so prod runs TODAY'S code against JULY'S
schema. Result: the site loads, login works, and every matches page 500s.
Prod data is also the July seed (393 jobs, no PSA applicants).

Time to full parity: ~2.5–4 hours, mostly unattended.

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
