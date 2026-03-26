# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Is

**SkillPointe Match** — a three-role labor-market recommendation platform for Admin (SkillPointe staff), Applicant (scholar/trainee), and Employer. MVP is **continuous ranking and explanation**, not batch matching or deferred acceptance.

Phases 1–8 are substantially complete. Phase 9 (admin review + config UI) is next.

---

## Development Commands

### Prerequisites

Node.js 20+, pnpm 9, Python 3.11+, Docker, Supabase CLI

### First-time Setup

```bash
# Frontend deps
pnpm install

# Backend deps
cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ../..

# Infrastructure
supabase start
supabase db reset                                              # applies all migrations + seed
docker compose -f infra/docker-compose.local.yml up -d        # Redis

# Get credentials from: supabase status
# Copy into: apps/api/.env  and  apps/web/.env.local

# Seed test users (requires API .env to be configured)
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/seed_test_users.py
```

### Running

```bash
# Terminal 1 — FastAPI (hot reload)
cd apps/api && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Next.js
pnpm dev:web
```

### Testing

```bash
cd apps/api && source .venv/bin/activate

pytest tests/ -v                               # all tests
pytest tests/test_matching.py -v              # matching tests
pytest tests/test_etl_import.py -v            # ETL tests
pytest tests/test_auth.py -v                  # auth tests
pytest tests/test_auth.py::test_login -v      # single test

# Frontend
pnpm lint
pnpm typecheck
```

### Database

```bash
supabase db reset                              # wipe + replay all migrations + seed
supabase migration new <name>                 # create new migration file
supabase migration up                         # apply pending migrations only
supabase gen types typescript --local > packages/types/src/database.types.ts
```

### Matching & ETL Scripts

All scripts run from repo root with the API virtualenv active (`cd apps/api && source .venv/bin/activate && cd ../..`):

```bash
python scripts/check_connections.py           # verify DB + Redis connectivity

# Data import
python scripts/import_applicants.py --file data.xlsx --dry-run
python scripts/import_jobs.py --file jobs.xlsx --dry-run

# Processing pipeline (run in order)
python scripts/normalize_data.py --verbose    # map programs → job families, parse pay, resolve regions
python scripts/run_extraction.py --verbose    # LLM extraction + embeddings (requires OPENAI_API_KEY)
python scripts/recompute_matches.py           # recompute all applicant-job match scores

# Inspection
python scripts/inspect_matches.py --stats
python scripts/verify_schema.py
```

### Service Ports

| Service | URL |
|---------|-----|
| Next.js | http://localhost:3000 |
| FastAPI + Swagger | http://localhost:8000 / http://localhost:8000/docs |
| Supabase (REST/Auth/Storage) | http://localhost:54321 |
| Supabase Studio | http://localhost:54323 |
| Postgres | localhost:54322 |
| Inbucket (email) | http://localhost:54324 |
| Redis | localhost:6379 |

---

## Architecture

### Repo Layout

```
apps/web/           Next.js 15 (React 19, Tailwind, Supabase SSR)
apps/api/           FastAPI backend — auth, RBAC, all business logic
packages/matching/  Deterministic matching engine (pure Python, no DB I/O)
packages/extraction/ LLM extraction pipeline (OpenAI, pure Python, no DB I/O)
packages/etl/       CSV/XLSX import + normalization (psycopg2 for writes)
packages/scraper/   Job scraper adapters (Southwire, Ford, GE Vernova, Ball, Delta, Schneider)
packages/ui/        Shared React components
packages/types/     Auto-generated Supabase TypeScript types
supabase/migrations/ SQL migration files (full schema)
scripts/            CLI scripts for import, normalization, extraction, recomputation
infra/              docker-compose.local.yml (Redis only)
```

### Three-Layer Matching Pipeline

Never blur these layers. Each has a distinct role and is stored separately:

**Layer 1 — Base Fit Estimation** (`packages/matching/`)
Pure deterministic. No LLM calls. No DB I/O. Inputs are normalized structs; output is a `MatchResult`.

- `gates.py` — 5 hard gates: job family compatibility, required credentials, readiness/timing, geography feasibility, explicit minimum requirements. Returns `eligible` / `near_fit` / `ineligible`. A failed gate caps the final score.
- `scorer.py` — 9 structured dimensions (weights in `SCORING_CONFIG.yaml`): trade_program_alignment (25), geography_alignment (20), credential_readiness (15), timing_readiness (10), experience_alignment (10), industry_alignment (5), compensation_alignment (5), work_style_alignment (5), employer_soft_pref_alignment (5).
- `text_scorer.py` — Semantic score via cosine similarity on embeddings; used as 25% of base fit, never overrides hard gates.
- `engine.py` — Orchestrates: normalize → gates → structured score → semantic score → combine. Formula: `base_fit_score = hard_gate_cap × (structured × 0.75 + semantic × 0.25)`

**Layer 2 — Policy Reranking** (`packages/matching/config.py`, `SCORING_CONFIG.yaml`)
Reads `ScoringConfig` from YAML. Modifies ordering/visibility only. Stored as `policy_adjusted_score` — separate from `base_fit_score`. Never change the underlying compatibility estimate.

**Layer 3 — LLM Interpretation** (`packages/extraction/`)
- `applicant_extractor.py` — extracts skills, certs, desired families, work style, readiness, intent from essays/resumes
- `job_extractor.py` — extracts required/preferred skills, certs, job family, experience level, physical requirements
- `embeddings.py` — generates 1536-dim embeddings (text-embedding-3-small) for semantic scoring
- `verifier.py` — heuristic + LLM verification; flags low-confidence items for admin review queue
- Extraction data feeds into Layer 1 when available; engine falls back to placeholders when absent

### Auth & RBAC

- Supabase Auth issues JWTs (HS256 + ES256 both supported)
- App roles (`admin` / `applicant` / `employer`) live in `user_profiles` table — not solely in JWT claims
- FastAPI validates JWTs in `apps/api/app/auth/dependencies.py`; role-guard dependencies (`require_admin`, `require_applicant`, `require_employer_or_admin`) are applied per router
- Backend uses **service-role key** (bypasses RLS) for all writes; frontend uses anon key with RLS policies
- Employer data isolation: employers only see their own jobs and the applicants surfaced for those jobs
- **Admin can view employer pages** (e.g. `/employer/jobs/[jobId]/applicants`) but `CandidateActions` (Reach out / Message / Mark as hired) are hidden — admin must not act on behalf of employers
- `_resolve_employer_id()` in `employers.py` raises HTTP 404 for non-employer users. Any endpoint shared between employer + admin **must** check `is_admin` first and skip this call: `employer_id = None if is_admin else await _resolve_employer_id(conn, ...)`
- Config is read via Pydantic Settings (`get_settings()`). Never use `os.environ.get()` for env vars — it does not read `.env` files.

### Frontend Routes

```
/                                   landing
/(auth)/login                       email/password login
/(auth)/signup                      applicant self-signup
/(auth)/forgot-password
/(auth)/reset-password
/(dashboard)/applicant/             profile summary
/(dashboard)/applicant/setup        onboarding
/(dashboard)/applicant/profile      edit profile
/(dashboard)/applicant/jobs         browse all jobs
/(dashboard)/applicant/matches      ranked job matches (inline interest signal panel per card)
/(dashboard)/applicant/matches/[matchId]  full match detail + dimension breakdown + interest panel
/(dashboard)/applicant/chat         planning chat (job picker → job-focused AI session)
/(dashboard)/applicant/messages     DM inbox
/(dashboard)/applicant/messages/[conversationId]  DM thread
/(dashboard)/employer/              company summary + jobs list
/(dashboard)/employer/jobs/new      create job
/(dashboard)/employer/jobs/[jobId]/edit
/(dashboard)/employer/jobs/[jobId]/applicants  ranked applicants + AI priority panel + outreach/hire buttons
/(dashboard)/employer/analytics     engagement + hire analytics (outreach sent, interested, applied, hired)
/(dashboard)/employer/messages      DM inbox
/(dashboard)/employer/messages/[conversationId]  DM thread
/(dashboard)/admin/                 analytics dashboard
/(dashboard)/admin/map              job geography map
/(dashboard)/admin/applicants       applicant list
/(dashboard)/admin/employers        employer list
/(dashboard)/admin/employers/[employerId]  employer detail + jobs (read-only; no employer actions)
/(dashboard)/admin/engagement       platform engagement analytics (3 views: general / applicants / employers)
/auth/callback                      Supabase auth callback
/api/auth/signout                   sign-out route handler
```

### API Routes

```
GET  /health
GET  /auth/me
POST /auth/complete-signup
POST /auth/invite-employer

GET  /applicant/me/profile
PATCH /applicant/me/profile
GET  /applicant/me/matches
GET  /applicant/me/matches/{id}
GET  /applicant/me/matches/{id}/interest
POST /applicant/me/matches/{id}/interest      (logs interest_set + apply_click to engagement_events)
GET  /applicant/me/chat/sessions
POST /applicant/me/chat/sessions              (job_id optional; creates job-focused session with AI opening msg)
GET  /applicant/me/chat/sessions/{id}
POST /applicant/me/chat/sessions/{id}/messages

GET  /employer/me/company
GET  /employer/me/jobs
POST /employer/me/jobs                        (triggers fire-and-forget match recompute)
PATCH /employer/me/jobs/{id}
GET  /employer/me/jobs/{id}/applicants
GET  /employer/me/jobs/{id}/applicants/ai-priority   (gpt-4o-mini: ranks top 10 with 1-sentence reasons)
POST /employer/me/outreach/draft              (AI-draft outreach message — no email sending, records intent)
POST /employer/me/outreach/send              (records sent outreach + logs engagement event)
POST /employer/me/jobs/{jid}/candidates/{aid}/hire   (upserts hire_outcomes + logs hire_reported event)
GET  /employer/me/analytics                  (outreach_sent, candidates_interested, applied, hired counts)

GET  /jobs/browse              (filters: trade, state, employer, work_setting, source, pagination)

GET  /conversations
POST /conversations
GET  /conversations/{id}/messages
POST /conversations/{id}/messages
POST /conversations/{id}/read

GET  /admin/applicants
GET  /admin/employers
GET  /admin/employers/{id}
GET  /admin/analytics/dashboard
GET  /admin/analytics/job-map
GET  /admin/analytics/cluster-jobs
GET  /admin/analytics/engagement
GET  /admin/analytics/engagement/applicants
GET  /admin/analytics/engagement/employers
```

### Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `user_profiles` | Auth bridge: links `auth.users` → app role |
| `applicants` | Applicant profiles (40 real SkillPointe columns) |
| `employers` / `employer_contacts` | Company profiles |
| `jobs` | Job postings (scraped + imported + manually created) |
| `matches` | Computed scores: `base_fit_score`, `policy_adjusted_score`, `eligibility_status`, `match_label`, `top_strengths`, `top_gaps`, `required_missing_items`, `recommended_next_step`, `confidence_level` |
| `match_dimension_scores` | Per-dimension score breakdown (9 dimensions) |
| `saved_jobs` | Applicant self-reported interest per job: `interested` / `applied` / `not_interested` |
| `engagement_events` | Platform activity log: `interest_set`, `apply_click`, `dm_sent`, `outreach_sent`, `hire_reported`, etc. |
| `conversations` / `direct_messages` | Applicant ↔ Employer DM system; unread counts per side; polled every 5s |
| `extracted_applicant_signals` | LLM extraction results for applicants |
| `extracted_job_signals` | LLM extraction results for jobs |
| `audit_logs` | All admin actions — auditable overrides |
| `policy_configs` | Scoring weights + reranking rules (configurable per run) |
| `review_queue_items` | Admin review tasks: low-confidence extractions, borderline matches |
| `chat_sessions` / `chat_messages` | Applicant AI planning chat — job-focused sessions with opening message |
| `import_runs` / `import_rows` | ETL import tracking |

---

## Key Config Files

| File | What it controls |
|------|-----------------|
| `SCORING_CONFIG.yaml` | Hard gate rules, structured dimension weights, policy reranking rules, feature flags |
| `PROMPTS.md` | LLM prompt templates for extraction, verification, explanation, and chat |
| `apps/api/app/config.py` | Backend env var schema (Pydantic Settings) |
| `supabase/seed.sql` | Taxonomy reference data + test users |
| `DECISIONS.md` | Architectural decision register |

### Required Environment Variables

**`apps/api/.env`:**
```
APP_ENV=local
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=                    # required for extraction + AI priority + chat
LLM_MODEL=gpt-4o
LLM_EXTRACTION_MODEL=gpt-4o-mini
CORS_ORIGINS=http://localhost:3000
```

**`apps/web/.env.local`:**
```
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Get Supabase values from `supabase status`.

---

## Build Status

| Phase | What | Status |
|-------|------|--------|
| 1 | Supabase project + local infra | ✅ Done |
| 2 | Auth + RBAC | ✅ Done |
| 3 | Core data model (migrations) | ✅ Done |
| 4 | ETL import pipeline | ✅ Done |
| 5 | Matching engine (gates + scoring + policy) | ✅ Done |
| 6 | All product UIs (applicant, employer, admin) | ✅ Done |
| 7 | LLM extraction + verification + job scraper | ✅ Done |
| 8 | Applicant planning chat, DM system, engagement analytics, AI candidate prioritisation, interest signals | ✅ Done |
| 9 | Admin review + config UI | 🔲 Not started |
| 10 | QA + end-to-end tests | 🔲 Not started |
| 11 | Production deployment | 🔲 Not started |

---

## Critical Guardrails

- **No batch matching** — MVP is continuous ranking only; never reintroduce deferred acceptance or stable matching
- **Hard gate failures cap scores** — a failed critical gate cannot produce a high-fit label; do not hide failures inside opaque scores
- **LLMs are supporting, not primary** — deterministic engine ranks; LLMs assist extraction, verification, explanation, and chat
- **Geography is first-class** — must appear in hard gates, structured score, policy, and explanation text
- **Separate base fit from policy** — `base_fit_score` and `policy_adjusted_score` are stored and computed separately; never merge them
- **All admin overrides are auditable** — write to `audit_logs` on any admin mutation
- **Employer data isolation** — employers never see candidates outside their own jobs unless explicitly enabled by admin policy
- **Admin cannot act as employer** — admin may view employer pages in read-only mode; never render employer-action UI (outreach, message, hire) for admin sessions
- **Backward-compatible extraction** — engine falls back to neutral defaults when extraction data is absent; never hard-require LLM output for core ranking
- **Always use `get_settings()` for env vars in backend** — `os.environ.get()` does not read `.env` files with Pydantic Settings
