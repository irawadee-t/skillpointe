# DEPLOY.md

Step-by-step guide for deploying SkillPointe Match to production.

**Stack:** Next.js (Vercel) · FastAPI (Railway) · Supabase Cloud · Upstash Redis

---

## Phase 1: Clean up local DB before deploying

The scraped jobs in `jobs` and `employers` have no connection to test user accounts, so you can safely delete just the duplicate users.

### Option A — Full reset (simplest, wipes everything)

```bash
supabase db reset                        # replays all migrations + seed.sql
python scripts/seed_test_users.py        # creates test accounts once, clean
```

### Option B — Surgical delete (keeps scraped jobs)

Run in Supabase Studio (`http://localhost:54323`) or `psql`:

```sql
-- Delete test auth users (cascades to user_profiles)
DELETE FROM auth.users
WHERE email IN ('admin@test.local', 'applicant@test.local', 'employer@test.local');

-- Remove orphaned applicant records
DELETE FROM public.applicants
WHERE user_id NOT IN (SELECT id FROM auth.users);

-- Remove orphaned employer_contacts
DELETE FROM public.employer_contacts
WHERE user_id NOT IN (SELECT id FROM auth.users);

-- Optional: remove Acme Industrial test company too
-- DELETE FROM public.employers WHERE name = 'Acme Industrial';
```

Then re-seed once:

```bash
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/seed_test_users.py
```

---

## Phase 2: Set up Supabase Cloud

1. Go to **supabase.com → New project**
2. Choose a region close to your users, set a strong DB password, save it
3. Once the project is ready, go to **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_ANON_KEY`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY` *(keep secret)*
4. Go to **Settings → API → JWT Settings** → copy **JWT Secret** → `SUPABASE_JWT_SECRET`

### Push schema to cloud

```bash
# Link your local CLI to the cloud project
# PROJECT_REF is in Settings > General (looks like: abcdefghijklmnop)
supabase link --project-ref YOUR_PROJECT_REF

# Push all migrations (schema + RLS policies)
supabase db push
```

### Migrate scraped jobs data (optional but recommended)

If you want production to start with your existing scraped jobs:

```bash
# Export scraped data from local postgres
pg_dump postgresql://postgres:postgres@localhost:54322/postgres \
  --data-only \
  --table=public.employers \
  --table=public.jobs \
  -f scraped_data_export.sql

# Import to Supabase cloud
# Connection string is in Settings > Database > Connection string (URI)
psql "postgresql://postgres:[DB-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres" \
  -f scraped_data_export.sql
```

### Configure Auth redirect URLs

In Supabase cloud dashboard → **Auth → URL Configuration**, add:

```
https://[your-vercel-app].vercel.app/**
```

You can update this after Vercel deployment once you have the URL.

---

## Phase 3: Set up Redis (Upstash)

1. Go to **upstash.com → Create database**
2. Choose the region closest to where your Railway backend will be hosted
3. Copy the **Redis URL** (format: `rediss://default:PASSWORD@HOST:PORT`) → `REDIS_URL`

---

## Phase 4: Deploy FastAPI backend on Railway

1. Go to **railway.app → New Project → Deploy from GitHub repo**
2. Select your repo
3. In the service settings set **Root Directory** to `apps/api`
4. Set the **Start Command** to:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. Go to **Variables** and add:

```
APP_ENV=production
SUPABASE_URL=https://[your-project-ref].supabase.co
SUPABASE_ANON_KEY=[your anon key]
SUPABASE_SERVICE_ROLE_KEY=[your service role key]
SUPABASE_JWT_SECRET=[your jwt secret]
REDIS_URL=[your upstash redis url]
OPENAI_API_KEY=[your openai key]
LLM_MODEL=gpt-4o
LLM_EXTRACTION_MODEL=gpt-4o-mini
CORS_ORIGINS=https://[your-vercel-app].vercel.app
```

> **Note:** Leave `CORS_ORIGINS` blank for now and fill it in after Vercel deployment once you have the URL.

6. Deploy. Railway gives you a URL like `https://your-api.railway.app` — copy it.

### Seed test users against cloud (after backend is live)

```bash
# Temporarily update apps/api/.env with your cloud Supabase values, then:
python scripts/seed_test_users.py
```

---

## Phase 5: Deploy Next.js frontend on Vercel

1. Go to **vercel.com → Add New Project → Import Git Repository**
2. Select your GitHub repo
3. Configure the project:

| Setting | Value |
|---------|-------|
| Framework Preset | Next.js (auto-detected) |
| Root Directory | `apps/web` |
| Build Command | *(leave default — `next build`)* |
| Install Command | `cd ../.. && pnpm install --frozen-lockfile` |
| Output Directory | *(leave default — `.next`)* |

4. Add **Environment Variables**:

```
NEXT_PUBLIC_SUPABASE_URL=https://[your-project-ref].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=[your anon key]
NEXT_PUBLIC_API_URL=https://[your-api].railway.app
```

5. Click **Deploy**
6. Copy your Vercel URL (e.g. `https://skillpointe.vercel.app`)
7. Go back to **Railway → Variables** and update `CORS_ORIGINS` to your Vercel URL
8. Go back to **Supabase → Auth → URL Configuration** and add your Vercel URL

---

## Environment Variables Reference

| Variable | Used in | Secret? |
|----------|---------|---------|
| `SUPABASE_URL` | Railway | No |
| `SUPABASE_ANON_KEY` | Railway + Vercel | No |
| `SUPABASE_SERVICE_ROLE_KEY` | Railway only | **Yes — never expose to frontend** |
| `SUPABASE_JWT_SECRET` | Railway only | **Yes — never expose to frontend** |
| `REDIS_URL` | Railway only | **Yes** |
| `OPENAI_API_KEY` | Railway only | **Yes — never expose to frontend** |
| `LLM_MODEL` | Railway only | No |
| `LLM_EXTRACTION_MODEL` | Railway only | No |
| `CORS_ORIGINS` | Railway only | No |
| `NEXT_PUBLIC_SUPABASE_URL` | Vercel | No |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel | No |
| `NEXT_PUBLIC_API_URL` | Vercel | No |

---

## Pre-launch Checklist

- [ ] `CORS_ORIGINS` on Railway exactly matches your Vercel URL (no trailing slash)
- [ ] Vercel URL added to Supabase Auth → URL Configuration
- [ ] `SUPABASE_SERVICE_ROLE_KEY` and `OPENAI_API_KEY` are only in Railway, never in Vercel
- [ ] `.env` files are in `.gitignore` — run `git status` to confirm nothing sensitive is staged
- [ ] `supabase db push` completed without errors
- [ ] Test a login, a job browse, and an AI feature end-to-end after deployment
