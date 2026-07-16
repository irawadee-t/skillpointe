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
