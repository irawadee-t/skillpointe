# DEPLOY_RUNBOOK.md — shipping `matching-alg-updates` to the EXISTING production

> This is **not** the from-scratch guide (that's `DEPLOY.md`). This runbook updates
> your already-live production with the SKILLED Pro overhaul on `matching-alg-updates`.
>
> **Your live stack:**
> - Frontend (Next.js) → **Vercel** project `skilled-nation` (deploys from `main`) → `skilled-nation.vercel.app`
> - Backend (FastAPI) → **Railway**
> - Database + Auth → **Supabase Cloud**
> - Redis → **Upstash**
> - GitHub repo → `irawadee-t/skillpointe`

---

## ⚠️ The one rule that matters

This branch adds **11 new DB migrations** + a large new backend (new routers + 8 new
Python deps). **Migrate the database FIRST**, then deploy the code. If the new frontend
goes live while the DB/backend are still old, the app breaks (missing tables/endpoints).

**Correct order: ① Supabase → ② Railway backend → ③ Vercel frontend (push `main`).**

---

## Step 0 — Find your credentials (the "where is it stored" step)

1. **Supabase project ref:** Vercel → your project → Settings → Environment Variables →
   click 👁 on `NEXT_PUBLIC_SUPABASE_URL`. It reads `https://<PROJECT_REF>.supabase.co`.
   That `<PROJECT_REF>` opens your project at supabase.com.
2. **Supabase DB password:** Supabase dashboard → Settings → Database → Connection string.
   (If you forgot it, you can reset it there — but that also means updating `REDIS_URL`? No,
   only the DB password; update it anywhere it's used.)
3. **Railway backend URL:** Vercel env var `NEXT_PUBLIC_API_URL` (👁) → that's your Railway
   service URL. Find the service at railway.app.
4. Have the **service_role key** and **JWT secret** handy (Supabase → Settings → API).

---

## Step 1 — Migrate the production database (Supabase Cloud)

From the repo root, with the Supabase CLI installed:

```bash
# Link the CLI to your PROD project (one time)
supabase link --project-ref <PROJECT_REF>
# (it will prompt for the DB password)

# SAFETY CHECK FIRST — see what's already applied vs. pending.
supabase migration list --linked
```

You should see the 11 new migrations (`...15_skilled_pro_core` … `...0001_recompute_runs_and_deletion`
+ `...0001_public_schema_grants`) listed as **not yet applied** remotely.

```bash
# Apply ONLY new migrations. db push is additive — it does NOT reset or wipe data.
supabase db push
```

- ✅ `supabase db push` runs pending migrations in order and never drops existing data.
- ❌ Do **NOT** run `supabase db reset` against prod — that wipes everything.
- If a migration errors partway, fix and re-run `db push`; it resumes from the failure.

**Verify:** `supabase migration list --linked` should now show all migrations applied.

> Since you said prod is likely test data: if you instead want a clean prod DB with the
> new schema + demo jobs, tell me and I'll give you the safe cloud-seed commands. Default
> here is **additive, no data loss**.

---

## Step 2 — Redeploy the backend (Railway)

Railway builds from GitHub. **Check which branch the Railway service tracks**
(Railway → your service → Settings → look for the deployed branch/trigger).

- **If Railway auto-deploys from `main`:** it will redeploy automatically when you push
  `main` in Step 3. That's fine *because the DB is already migrated* — backend and frontend
  go live together against the new schema. Just make sure Step 1 is done first.
- **If Railway tracks `matching-alg-updates` or is manual:** trigger a redeploy now
  (Deployments → Redeploy, or push the branch — already done).

**Env vars to confirm on Railway** (Variables tab) — most already exist from before:

| Var | Needed for | Note |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | core | already set |
| `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | core | already set — keep secret |
| `REDIS_URL` | scheduler locks | already set (Upstash) |
| `OPENAI_API_KEY` | AI chat, résumé, priority | **confirm it's set** — new features use it |
| `LLM_MODEL`, `LLM_EXTRACTION_MODEL` | AI | already set |
| `CORS_ORIGINS` | browser access | must equal `https://skilled-nation.vercel.app` (no trailing slash) |
| `GOOGLE_MAPS_API_KEY` / `MAPBOX_ACCESS_TOKEN` | commute drive-time | **optional** — falls back to straight-line if absent |

The new `requirements.txt` deps install automatically on the Railway build. Watch the
build logs for a green deploy, then hit `https://<railway-url>/health` — it should return
`{"status":"ok", ...}` with `supabase` and `redis` both `ok`.

---

## Step 3 — Deploy the frontend (Vercel) via merge to `main`

Only after Steps 1–2 are green:

```bash
git checkout main
git pull origin main
git merge --ff-only matching-alg-updates    # clean fast-forward, no conflicts
git push origin main
```

Pushing `main` triggers Vercel to build & deploy production automatically
(and Railway too, if it tracks `main`). Watch the Vercel deployment go **Ready**.

> If instead you chose to switch Vercel's Production Branch to `matching-alg-updates`
> (Vercel → Settings → Git → Production Branch), skip the merge and just ensure that
> branch is pushed (it is). But merging to `main` is the recommended path.

---

## Step 4 — Post-deploy verification

1. **Backend:** `curl https://<railway-url>/health` → all deps `ok`.
2. **Auth redirect:** Supabase → Auth → URL Configuration includes
   `https://skilled-nation.vercel.app/**`.
3. **Smoke test on the live site:**
   - Log in (each role).
   - Applicant: matches load, open a match detail, AI planning chat replies.
   - Employer: verified-worker search + candidate list load; open a DM thread.
   - Admin: dashboard counts render; new pages (Credentials, SKILLED ID, Sync,
     Foundation, Institution) load without 500s.
4. **Watch logs:** Vercel → Logs and Railway → Logs for any `permission denied`
   (would mean the grants migration didn't apply) or `relation does not exist`
   (a migration didn't run).

---

## Rollback

- **Frontend:** Vercel → Deployments → previous `main` deploy → **Instant Rollback**.
- **Backend:** Railway → Deployments → redeploy the previous build.
- **Database:** migrations are additive; the new tables are unused by old code, so a
  code rollback is safe without touching the schema. Do **not** try to "un-migrate" —
  just roll back the code.

---

## Quick reference — what changed vs. old `main`

- **11 new migrations:** skilled_pro_core, verified_worker_search, event_sync,
  foundation_outcomes, institution_portal, job_import_workflow, robustness_pack,
  geocode_cache, credential_taxonomy_and_verification, transactions_and_scheduling,
  recompute_runs_and_deletion (+ public_schema_grants).
- **Backend:** whole `app/skilled_pro/` module + ~25 new routers, 8 new pip deps.
- **Frontend:** new pages (credentials, consent, résumé, applications, verified-workers,
  institution, admin credentials/foundation/job-imports/skilled-id/sync, account).
- **Scheduler:** 5 jobs (6h recompute, interview reminders, ATS resync, daily GDPR
  deletion sweep, stuck-recompute recovery).

---

## ADDENDUM — `riya-updates` (security / scale / compliance hardening on top of the above)

This branch adds **4 more migrations** and **new env vars** on top of the 11 above.
The deploy order is unchanged (**DB → backend → frontend**); the migration
*mechanism* is the same — `supabase db push` picks these up automatically because
they follow the same timestamped filenames in `supabase/migrations/`.

### 4 new migrations (all additive — no data loss, safe to `db push`)
- `20260720000001_account_change_attempt_lockout` — adds `account_change_requests.attempts` (brute-force lockout on confirmation codes).
- `20260720000002_credential_source_badge_checkr` — widens the `credentials.source` CHECK (superset of old values → validates existing rows) + new `checkr_verifications` table.
- `20260720000003_scale_search_and_indexes` — pg_trgm / tsvector / composite indexes for search-at-scale. (Built without `CONCURRENTLY`; trivial on current data volume. On a large prod table, build these in a maintenance window or switch to `CREATE INDEX CONCURRENTLY` run outside a migration.)
- `20260721000001_dob_minor_protection` — adds `applicants.date_of_birth` + partial index; under-18 applicants are excluded from employer discovery by default.

`supabase migration list --linked` should show these 4 as pending before `db push`, applied after.

### New Railway (backend) env vars
**Required in production — the app now REFUSES TO BOOT without these** (`app/config.py::enforce_production_safety`, gated on `APP_ENV=production`):
| Var | Generate / value |
|---|---|
| `APP_ENV` | must be `production` — this is what arms all the prod safety checks |
| `SCREENING_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — PII-at-rest key; **keep it stable** (rotating it strands existing ciphertext) |
| `SKILLED_SIGNING_PRIVATE_KEY` | `openssl genpkey -algorithm ed25519 -out signing.pem` (paste PEM) — stable Ed25519 key for signed credentials |
| `SKILLED_SIGNING_KEY_ID` | any stable id that is **not** `dev-ephemeral` |

**Optional** (features degrade gracefully if unset): `CHECKR_API_KEY`, `CHECKR_WEBHOOK_SECRET`, `OCR_PROVIDER`, `SIS_PROVIDER`, `RESEND_API_KEY`, `TWILIO_*`, `GOOGLE_MAPS_API_KEY`/`MAPBOX_ACCESS_TOKEN`. Pool tuning: `DB_POOL_MAX_SIZE` (default 10 per replica — keep `N_replicas × DB_POOL_MAX_SIZE` under the Postgres/Supavisor ceiling; set `DB_USE_PGBOUNCER=true` when `DATABASE_URL` points at Supabase's transaction pooler on :6543).

### Supabase dashboard settings (not code — do these once)
- **Auth → Rate Limits / Bot protection:** login and password-reset run *client-side* against Supabase Auth, not this backend, so brute-force protection there depends on Supabase project settings. Confirm rate limiting / CAPTCHA is enabled in prod.
- **Auth → URL Configuration:** already covered in Step 4.

### Post-deploy security smoke
- `POST /employer/jobs/imports/url` with `http://169.254.169.254/…` or `http://localhost/…` must be rejected (SSRF egress guard), not fetched.
- As an **admin**, hiring/rejecting an application or proposing interview slots must return 403 (admin cannot act as employer); GET/list on those pages still works.

---

## Addendum (2026-08-01) — taxonomy industries + scholarship import migration

One new migration to push (additive — no data loss, safe to `supabase db push`):

- `20260801062752_taxonomy_industries_and_scholarship_import` —
  1) `canonical_job_families.industries TEXT[]` (industry grouping: healthcare/construction/transportation/energy/manufacturing);
  2) `applicants.scholarship_review_status TEXT` (the SPF export's 'Folder - Name' review status — never a person's name);
  3) 15 new canonical job families (pharmacy, surgical_tech, veterinary, lab_sciences, health_information, dietetics, civil_survey, field_service, rail_transit, marine, power_plant, building_automation, data_center, industrial_maintenance, electronics);
  4) alias extensions for existing families — aliases are **merged** (array union), never overwritten, so admin/demo-added aliases survive;
  5) 8 `canonical_career_pathways` umbrella rows (`path_*`) for the CSV 'Career Path' values.

`supabase/seed.sql` mirrors the same upserts so `supabase db reset` ends in the same state.
After pushing, re-run on the target environment: `python scripts/normalize_data.py --all` then `python scripts/recompute_matches.py`.
