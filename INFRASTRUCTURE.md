# INFRASTRUCTURE.md — SKILLED Nation / SkillPointe Match

**Everything about where the app lives, how it's wired, and how to ship changes.**
Read this before touching production. You do **not** need to run anything locally to make
updates — see [How to ship changes](#how-to-ship-changes).

> 🔐 **Secrets are NOT stored in this file.** This doc says *where* each key lives and how
> to get it. Actual values live in the deployment dashboards (Railway/Vercel/Supabase) and
> should be mirrored in a shared password manager (1Password/Bitwarden). Never commit real
> secret values to git.

---

## 1. The big picture — 4 services

The app is **three deployed services + a database**, not one thing on Vercel.

| Layer | Runs on | What it is | URL |
|-------|---------|-----------|-----|
| **Frontend** | **Vercel** | Next.js UI (`apps/web`) | https://skilled-nation.vercel.app |
| **Backend / API** | **Railway** | FastAPI (`apps/api`) — all business logic, matching, AI | https://web-production-6f34.up.railway.app |
| **Database + Auth** | **Supabase Cloud** | Postgres — all data + user logins | https://ywgnrlpogioftbhhshlt.supabase.co |
| **Redis (cache/locks)** | **Upstash** | Scheduler locks, rate limits | (Upstash console) |
| **LLM** | **OpenAI** | AI chat, résumé parsing, summaries | api.openai.com |

**Data flow:** Browser → Vercel (UI) → Railway (API) → Supabase (Postgres) / Upstash (Redis) / OpenAI.
The browser also talks directly to Supabase for **login/auth**.

**Source of truth:** GitHub repo **`irawadee-t/skillpointe`**, production branch **`main`**.
Both Vercel and Railway deploy from `main`.

---

## 2. Where to log in (dashboards)

| Service | Console | What you manage there |
|---------|---------|----------------------|
| GitHub | https://github.com/irawadee-t/skillpointe | Code, the `main` branch |
| Vercel | https://vercel.com/iras-projects-5a45915a/skilled-nation | Frontend deploys, frontend env vars, domains |
| Railway | https://railway.app → project `skilled-nation` → service `web` | Backend deploys, backend env vars, logs |
| Supabase | https://supabase.com/dashboard/project/ywgnrlpogioftbhhshlt | Database, migrations, auth users, API keys |
| Upstash | https://console.upstash.com | Redis instance |
| OpenAI | https://platform.openai.com | API key + usage/billing |

---

## 3. Key facts / identifiers (non-secret)

| Thing | Value |
|-------|-------|
| Supabase **project ref** | `ywgnrlpogioftbhhshlt` |
| Supabase URL | `https://ywgnrlpogioftbhhshlt.supabase.co` |
| Supabase region | `us-east-1` (East US, N. Virginia) |
| Railway backend URL | `https://web-production-6f34.up.railway.app` |
| Railway service name | `web` (⚠️ named "web" but it's the **API backend**) |
| Railway **Root Directory** | `/apps/api` |
| Vercel domain | `skilled-nation.vercel.app` |
| Vercel **Root Directory** | `apps/web` |
| Production branch | `main` |
| Signing key ID (non-secret) | `SKILLED_SIGNING_KEY_ID = skilled-prod-2026-01` |

---

## 4. Environment variables — who has what, and where to get it

Secrets are split by sensitivity: **public `NEXT_PUBLIC_*` vars on Vercel**, **everything
secret on Railway**. Never put service-role keys or the DB password on Vercel.

### 4a. Vercel (frontend) — public vars only
Set at: Vercel → project → **Settings → Environment Variables**

| Variable | Value / where to get it | Secret? |
|----------|-------------------------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://ywgnrlpogioftbhhshlt.supabase.co` | No |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → Settings → **API Keys** → `anon public` | No (public by design) |
| `NEXT_PUBLIC_API_URL` | `https://web-production-6f34.up.railway.app` | No |
| `API_URL` | same Railway URL (server-side) | No |
| `NEXT_PUBLIC_SITE_URL` | `https://skilled-nation.vercel.app` | No |

### 4b. Railway (backend) — the sensitive ones
Set at: Railway → service `web` → **Variables** tab

| Variable | Where to get the value | Secret? |
|----------|------------------------|---------|
| `APP_ENV` | `production` | No |
| `SUPABASE_URL` | `https://ywgnrlpogioftbhhshlt.supabase.co` | No |
| `SUPABASE_ANON_KEY` | Supabase → Settings → **API Keys** → `anon public` | No |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → **API Keys** → `service_role` | **YES — full DB access** |
| `SUPABASE_JWT_SECRET` | Supabase → Settings → **JWT Keys** → JWT Secret | **YES** |
| `DATABASE_URL` | Supabase → Settings → **Database** → Connection string (URI, includes password) | **YES** |
| `REDIS_URL` | Upstash → your Redis DB → connection string (`rediss://…`) | **YES** |
| `OPENAI_API_KEY` | OpenAI → API keys | **YES** |
| `LLM_MODEL` | `gpt-4o` | No |
| `LLM_EXTRACTION_MODEL` | `gpt-4o-mini` | No |
| `CORS_ORIGINS` | `https://skilled-nation.vercel.app` (no trailing slash) | No |
| `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` (allows preview URLs) | No |
| `SKILLED_SIGNING_PRIVATE_KEY` | Ed25519 PEM — generated once, **stored in Railway + password manager** | **YES — do not change** |
| `SKILLED_SIGNING_KEY_ID` | `skilled-prod-2026-01` | No |
| `SCREENING_ENCRYPTION_KEY` | Fernet key — generated once, **stored in Railway + password manager** | **YES — do not change** |

> **`SKILLED_SIGNING_PRIVATE_KEY` and `SCREENING_ENCRYPTION_KEY` must stay stable.**
> Changing the signing key makes all previously-signed credential records fail verification.
> Changing the encryption key makes previously-encrypted screening answers undecryptable.
> The backend **refuses to boot in production** without these three signing/encryption vars.

### Regenerating the signing/encryption keys (only if you must)
```bash
# Ed25519 signing private key (PEM)
python -c "from cryptography.hazmat.primitives.asymmetric import ed25519; from cryptography.hazmat.primitives import serialization; print(ed25519.Ed25519PrivateKey.generate().private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()).decode())"

# Screening encryption key (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 🔑 Put these in the team password manager (the actual values)
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL` (has DB password),
`REDIS_URL`, `OPENAI_API_KEY`, `SKILLED_SIGNING_PRIVATE_KEY`, `SCREENING_ENCRYPTION_KEY`,
plus the raw **Supabase DB password**.

---

## 5. How to ship changes

You don't need to run anything locally. Both services auto-deploy from **`main`**.

### 5a. App code change (frontend OR backend)
```bash
git checkout main
git pull origin main
# make your edits in apps/web (frontend) or apps/api (backend)
git add -A
git commit -m "your change"
git push origin main
```
- Push to `main` → **Vercel** rebuilds the frontend **and** **Railway** rebuilds the backend.
- Watch: Vercel → Deployments (Ready), Railway → Deployments (green/Active).
- Verify backend: open https://web-production-6f34.up.railway.app/health → `status: ok`.

> ⚠️ **Known Railway quirk:** Railway sometimes skips a deploy with *"No changes to watched
> files"* and keeps running old code. It only watches changes under `/apps/api` (its Root
> Directory), so a **frontend-only** change won't trigger a backend rebuild (that's fine).
> If a backend change doesn't deploy, either (a) Railway → Deployments → find your commit →
> **⋮ → Redeploy**, or (b) permanent fix below.
>
> **Permanent fix for the skip glitch:** Railway → service → **Settings → Source** →
> **Disconnect** the branch, then reconnect `main`. A fresh connection always deploys HEAD.

### 5b. Database change (schema / new tables / columns)
Migrations live in `supabase/migrations/`. To change the DB you write a migration and push it
to the **cloud** project — you do **not** edit tables by hand in the dashboard.

```bash
# One-time: link the CLI to the prod project (asks for the DB password)
supabase link --project-ref ywgnrlpogioftbhhshlt

# Create a new migration file, edit it with your SQL
supabase migration new your_change_name
#   → edit supabase/migrations/<timestamp>_your_change_name.sql

# See what's pending vs. what's applied on cloud
supabase migration list --linked

# Apply to the CLOUD database (ADDITIVE — never wipes data)
supabase db push
```
- ✅ `supabase db push` only applies **new** migrations; it never drops existing data.
- ❌ **Never run `supabase db reset` against production** — it wipes everything.
- Commit the new migration file to `main` so it's version-controlled.

### 5c. If a change needs a new environment variable
Add it in **both** the code default (`apps/api/app/config.py`) **and** the right dashboard
(Railway for backend/secret vars, Vercel for `NEXT_PUBLIC_*`). Redeploy.

---

## 6. Test logins (production)

Created by seed scripts; safe demo accounts.

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@test.local` | `Test1234!` |
| Employer | `employer@test.local` | `Test1234!` |
| Applicant (real profile — welder) | `marcus.reyes@skillednation-demo.test` | `Test1234!` |

---

## 7. Current known limitations (as of this deploy)

1. **`packages/` is not shipped to Railway.** Railway's Root Directory is `/apps/api`, so the
   sibling `packages/` dir (matching, extraction, scraper, verification) isn't deployed. The
   backend boots and everything core works, but these features **degrade gracefully**:
   - External credential verification (NCCER/NSC) → returns 503 (they're stubbed anyway).
   - URL job-scraping import → returns an error.
   - Scheduled auto-recompute of matches → skipped (matches are precomputed).
   - **Proper fix (optional):** change Railway Root Directory to the repo root and adjust the
     build/start commands so `packages/` ships. Then those features work fully.
2. **`/health` shows `supabase: degraded (HTTP 401)`** = cosmetic. The health check pings
   Supabase with `SUPABASE_ANON_KEY`; if that var on Railway is stale, it 401s. Real DB access
   uses the service-role key and works fine. Fix: set `SUPABASE_ANON_KEY` on Railway to the
   current `anon public` key from Supabase → Settings → API Keys.
3. **Matches are static in production.** They were precomputed. Because auto-recompute is
   disabled on Railway (see #1), new applicants/jobs won't get scored automatically. To
   recompute, run `scripts/recompute_matches.py` against the cloud DB (needs `packages/` +
   `DATABASE_URL`), or fix #1.

---

## 8. How to run the data pipeline against the cloud DB (advanced / rare)

Only needed to re-seed or recompute matches. Requires the cloud `DATABASE_URL`,
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (from the dashboards) exported as env vars.

```bash
# From repo root, with the API virtualenv active and cloud vars exported:
python scripts/seed_test_users.py        # (re)create test logins
python scripts/import_applicants.py --file <data.csv>
python scripts/normalize_data.py
python scripts/recompute_matches.py      # score all applicant/job pairs
```
> Note: `recompute_matches.py` writes row-by-row and is **slow over the network** — for large
> recomputes against cloud, batch the writes. See the team lead if you need this.

---

## 9. Security checklist / hygiene

- [ ] Actual secret values stored in a **shared password manager**, not in git.
- [ ] `.env` files are git-ignored (they are) — never commit them.
- [ ] `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_JWT_SECRET` only on **Railway**, never Vercel.
- [ ] Supabase → **Auth → URL Configuration** includes `https://skilled-nation.vercel.app/**`
      (so login redirects work in production).
- [ ] Rotate any secret that was ever pasted into chat/email/Slack, then update Railway.
- [ ] `SOC 2` / audit posture: audit logs and signed records are in place; formal cert is future.

---

## 10. Quick reference — "I want to…"

| Task | Where |
|------|-------|
| Change the UI | edit `apps/web`, push `main` → Vercel deploys |
| Change API logic | edit `apps/api`, push `main` → Railway deploys (redeploy if skipped) |
| Add a DB table/column | `supabase migration new …` → `supabase db push`, commit the file |
| Add a secret | Railway Variables (backend) or Vercel env (frontend `NEXT_PUBLIC_*`) |
| See backend health | https://web-production-6f34.up.railway.app/health |
| See backend logs | Railway → service → **Deployments → View logs** |
| See frontend logs | Vercel → project → **Logs** |
| Browse/query the DB | Supabase → **Table Editor** / **SQL Editor** |
| Roll back frontend | Vercel → Deployments → previous → **Instant Rollback** |
| Roll back backend | Railway → Deployments → previous → **Redeploy** |
</content>
