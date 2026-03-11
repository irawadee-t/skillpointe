# Matching Scripts — Run Guide

Phase 4.3 + 5.1 + 5.2 scripts for normalization, match recomputation, and inspection.

---

## Prerequisites

1. Local Supabase running and schema loaded:
   ```
   supabase start
   supabase db reset        # loads migrations + seed data
   ```

2. Python virtualenv activated with dependencies:
   ```
   cd apps/api
   source .venv/bin/activate   # or: python -m venv .venv && pip install -r requirements.txt
   ```

3. `.env` file in `apps/api/` with connection details — or set `DATABASE_URL` in the environment.
   The scripts use `etl.db.get_connection()` which reads `DATABASE_URL` or falls back to local defaults (port 54322).

4. Raw data already imported (Phase 4.1 / 4.2):
   ```
   python scripts/import_applicants.py path/to/applicants.xlsx
   python scripts/import_jobs.py path/to/jobs.xlsx
   ```

---

## 1. `normalize_data.py` — Phase 4.3

Reads applicants and jobs from the DB, applies deterministic normalization, and writes results back.

**What it does:**
- Applicants: `program_name_raw` → `canonical_job_family_id` (via alias/keyword matching), `state` → `region`
- Jobs: `title_raw` / `career_pathway_raw` → `canonical_job_family_id`, parses `pay_raw` → `pay_min / pay_max / pay_type`, normalizes `region`

**Run (first time — normalize all):**
```
python scripts/normalize_data.py
```

**Re-run everything (including already-normalized rows):**
```
python scripts/normalize_data.py --all
```

**Dry-run (see what would change without writing):**
```
python scripts/normalize_data.py --dry-run
```

**Applicants only:**
```
python scripts/normalize_data.py --applicants-only
```

**Jobs only:**
```
python scripts/normalize_data.py --jobs-only
```

**Verbose (show each row result):**
```
python scripts/normalize_data.py --verbose
```

**Test on small subset:**
```
python scripts/normalize_data.py --limit 20 --verbose --dry-run
```

**Expected output:**
```
Loaded 15 job families, 5 geography regions.

Normalizing 335 applicants ...
Normalizing 300 jobs ...

============================================================
  Normalization summary
============================================================

  APPLICANTS  (335 processed)
    Family matched:  285
    No match:        50
    Needs review:    22

  JOBS  (300 processed)
    Family matched:  278
    No match:        22
    Needs review:    12

  Unmatched applicant programs (top 10 — add aliases to seed.sql):
    - 'Transportation - Custom'
    - 'Healthcare IT'
    ...
```

**If you see unmatched programs**, add aliases to `supabase/seed.sql` in the `canonical_job_families` INSERT, then re-run:
```
supabase db reset
python scripts/import_applicants.py ...
python scripts/import_jobs.py ...
python scripts/normalize_data.py
```

---

## 2. `recompute_matches.py` — Phase 5.1 + 5.2

Fetches all active applicant-job pairs, runs the deterministic matching engine (hard gates + structured scoring + policy reranking), and upserts results into `matches` + `match_dimension_scores`.

**Prerequisites:** `normalize_data.py` must have been run first — jobs and applicants need `canonical_job_family_id` populated.

**Full recompute (all active applicants × all active jobs):**
```
python scripts/recompute_matches.py
```
Expect ~2–5 minutes for 335 applicants × 300 jobs = 100,500 pairs.

**Single applicant (useful for debugging):**
```
python scripts/recompute_matches.py --applicant-id <uuid>
```

**Single job:**
```
python scripts/recompute_matches.py --job-id <uuid>
```

**Quick smoke test (first 10 applicants × 10 jobs = 100 pairs):**
```
python scripts/recompute_matches.py --limit 10
```

**Dry-run (compute but do not write to DB):**
```
python scripts/recompute_matches.py --dry-run
```

**Verbose (print score breakdown per pair):**
```
python scripts/recompute_matches.py --verbose --limit 5
```

**Expected output:**
```
Loaded policy config version: v1
Applicants: 335, Jobs: 300, Pairs: 100500
Scoring run ID: a3f2...

  ... 500/100500 committed
  ... 1000/100500 committed
  ...

============================================================
  Recompute summary: 2026-03-10
============================================================
  Total pairs:    100500
  Eligible:       42300
  Near-fit:       38200
  Ineligible:     20000
  Strong fit:     8100
  Good fit:       18500
  Errors:         0
  Run ID:         a3f2...
```

---

## 3. `inspect_matches.py` — Inspection + QA

CLI tool for querying and displaying match results from the DB. Use this after recompute to validate ranking quality.

**Top 10 jobs for a specific applicant:**
```
python scripts/inspect_matches.py --applicant-id <uuid>
```

**Top 10 applicants for a specific job:**
```
python scripts/inspect_matches.py --job-id <uuid>
```

**Show more results:**
```
python scripts/inspect_matches.py --applicant-id <uuid> --top 20
```

**Include ineligible pairs:**
```
python scripts/inspect_matches.py --applicant-id <uuid> --show-ineligible
```

**Show dimension score breakdown:**
```
python scripts/inspect_matches.py --applicant-id <uuid> --breakdown
```

**List all applicants (with IDs):**
```
python scripts/inspect_matches.py --list-applicants
```

**List all active jobs (with IDs):**
```
python scripts/inspect_matches.py --list-jobs
```

**Overall match statistics:**
```
python scripts/inspect_matches.py --stats
```

**Export top matches to CSV:**
```
python scripts/inspect_matches.py --applicant-id <uuid> --export-csv /tmp/matches.csv
```

**Example output:**
```
Top 10 jobs for: Jane Smith (app-001)
────────────────────────────────────────────────────────────
 1  ✓ ★★★  91.2  Electrician (ACME Electric ⭐)    IL / on_site
      Strengths: Trade Program Alignment: direct family match
      Next step: Strong match for 'Electrician' — consider applying

 2  ✓ ★★   78.4  Electrical Apprentice (City Power)  IL / on_site
      Strengths: Geography Alignment: same state: IL

 3  ~      61.0  HVAC Tech (Metro Heating)           OH / on_site
      Gaps: Job Family Compatibility: adjacent families: applicant=electrical, job=hvac
      Next step: Near-fit for 'HVAC Tech' — address: Job Family Compatibility
```

---

## Typical first-run sequence

```bash
# 1. Start local Supabase
supabase start
supabase db reset

# 2. Import raw data
python scripts/import_applicants.py data/applicants.xlsx
python scripts/import_jobs.py data/jobs.xlsx

# 3. Normalize
python scripts/normalize_data.py --verbose

# 4. Recompute matches
python scripts/recompute_matches.py

# 5. Inspect results
python scripts/inspect_matches.py --stats
python scripts/inspect_matches.py --list-applicants   # pick an ID
python scripts/inspect_matches.py --applicant-id <uuid> --breakdown
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ERROR connecting to DB` | Run `supabase start` and verify `supabase status` |
| `no canonical_job_families found` | Run `supabase db reset` to load seed data |
| `normalized: 0 / 335` | Check aliases in seed.sql; see unmatched programs output |
| `Errors: N` in recompute summary | Re-run with `--verbose --limit 10` to see stack traces |
| Scores all look wrong | Check that `normalize_data.py` was run before `recompute_matches.py` |
