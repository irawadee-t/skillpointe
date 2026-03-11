# Local Development Guide

Detailed reference for running SkillPointe Match locally.
Quick-start instructions are also in the root `README.md`.

---

## Stack overview

| Service | Local address | How to start |
|---------|--------------|--------------|
| Next.js (web) | http://localhost:3000 | `pnpm dev:web` |
| FastAPI (api) | http://localhost:8000 | `uvicorn main:app --reload --port 8000` |
| Supabase Studio | http://localhost:54323 | auto-started by `supabase start` |
| Supabase REST | http://localhost:54321/rest/v1/ | auto-started |
| Supabase Auth | http://localhost:54321/auth/v1/ | auto-started |
| Supabase Storage | http://localhost:54321/storage/v1/ | auto-started |
| Inbucket (email) | http://localhost:54324 | auto-started |
| Redis | localhost:6379 | `docker compose -f infra/docker-compose.local.yml up -d` |

---

## Supabase CLI commands

```bash
supabase start              # start local Supabase stack
supabase stop               # stop local Supabase stack
supabase status             # print URLs and keys for .env
supabase db reset           # reset local DB, run all migrations fresh
supabase migration new <name>  # create a new migration file
supabase migration up        # apply pending migrations
supabase gen types typescript --local > packages/types/src/database.types.ts  # generate types
```

---

## FastAPI commands

```bash
cd apps/api
source .venv/bin/activate

# Start (with hot reload)
uvicorn main:app --reload --port 8000

# Run tests
pytest

# Type check
pyright  # or mypy
```

---

## Next.js commands

```bash
# From repo root
pnpm dev:web          # start dev server
pnpm build:web        # production build
pnpm lint             # lint
pnpm typecheck        # TypeScript check
```

---

## Environment variable checklist

Before starting, verify these are set in `apps/api/.env`:

- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_ANON_KEY`
- [ ] `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `SUPABASE_JWT_SECRET`
- [ ] `REDIS_URL`
- [ ] `APP_ENV=local`

Verify in `apps/web/.env.local`:

- [ ] `NEXT_PUBLIC_SUPABASE_URL`
- [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- [ ] `NEXT_PUBLIC_API_URL=http://localhost:8000`

---

## Troubleshooting

### Port conflicts

If ports are in use:

```bash
# Kill process on port 8000 (API)
lsof -ti:8000 | xargs kill -9

# Kill process on port 3000 (web)
lsof -ti:3000 | xargs kill -9

# Kill Supabase (uses 5432, 54321, 54322, etc.)
supabase stop
```

### Supabase doesn't start

- Ensure Docker Desktop is running
- Check `docker ps` — supabase uses several containers
- `supabase stop && supabase start` to restart

### Redis connection refused

```bash
# Check if Redis container is running
docker ps | grep skillpointe_redis_local

# Restart
docker compose -f infra/docker-compose.local.yml down
docker compose -f infra/docker-compose.local.yml up -d
```

### Supabase JWT errors in API

Run `supabase status` to get the current local JWT secret and update `SUPABASE_JWT_SECRET` in `apps/api/.env`.

---

## Database migrations and seed data (Phase 3)

### Apply all migrations + seed from scratch

```bash
supabase db reset
# Runs every file in supabase/migrations/ in order, then supabase/seed.sql
```

### Apply new migrations to an already-running DB

```bash
supabase migration up
```

### Verify schema and seed data

```bash
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/verify_schema.py
# Expected: ✓ All checks passed.
```

### Migration file naming convention

Files are numbered sequentially:

```
supabase/migrations/
  20260310000000_user_profiles.sql         # Phase 2 — auth
  20260310000001_enums_and_extensions.sql  # Phase 3 — enum types, pgvector
  20260310000002_taxonomy.sql              # Phase 3 — canonical_job_families, pathways, regions
  20260310000003_core_entities.sql         # Phase 3 — applicants, employers, jobs
  20260310000004_documents_and_signals.sql # Phase 3 — documents, extracted signals
  20260310000005_matches.sql               # Phase 3 — matches, dimension scores, saved_jobs
  20260310000006_ops_and_config.sql        # Phase 3 — imports, audit_logs, policy_configs, review queue
  20260310000007_chat.sql                  # Phase 3 — chat sessions and messages
```

### Creating a new migration

```bash
supabase migration new <descriptive_name>
# Creates supabase/migrations/<timestamp>_<descriptive_name>.sql
```

### Generate TypeScript types (after schema changes)

```bash
supabase gen types typescript --local > packages/types/src/database.types.ts
```

---

## Data dev workflow (Phase 4+)

Once Phase 4 import scripts are built:

```bash
python scripts/import_applicants.py --file data/applicants.csv
python scripts/import_jobs.py --file data/jobs.csv
python scripts/normalize_data.py
python scripts/recompute_matches.py
python scripts/inspect_matches.py --applicant-id <id> --top 10
```

Per BUILD_PLAN.md §7: inspect ranking quality on real data **before** polishing UI.
