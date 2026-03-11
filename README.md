# SkillPointe Match

SkillPointe Match is a **three-role workforce matching platform** for connecting skilled-trades applicants with employers through **explainable, geography-aware, policy-aware ranking**.

It is designed for the SkillPointe Foundation use case:

- **Applicants** see their best job matches, why they match, what is missing for lower-fit roles, and a practical planning/chat interface
- **Employers** see ranked applicant matches for each job they post, with rationale and filters
- **Admins** manage imports, taxonomy, policy/scoring, review queues, analytics, and audit logs

## MVP summary

This repo is for the **MVP**, which is a **continuous ranking and explanation platform**.

### Included in MVP

- applicant login + profile
- employer login + company + job management
- admin login + management console
- applicant ranked job recommendations
- employer ranked applicant recommendations per job
- explainable scoring
- missing requirement analysis
- geography-aware filtering and ranking
- grounded applicant planning chat
- admin review for low-confidence extraction/matching issues

### Not included in MVP

- batch matching
- deferred acceptance
- stable matching rounds
- centralized market clearing
- autonomous AI agents taking actions
- full learning-to-rank pipelines
- full training-program marketplace

---

# Product architecture

## Core idea

This is a **two-sided labor-market recommendation platform**, but MVP behavior is **continuous ranking**, not centralized matching.

The system has three layers:

1. **Base fit estimation**
   - deterministic compatibility scoring between applicant and job

2. **Policy reranking**
   - configurable reordering/visibility adjustments based on SkillPointe priorities

3. **LLM-assisted interpretation**
   - extraction
   - verification on ambiguous cases
   - explanation generation
   - applicant planning chat

These layers are intentionally separated.

---

# Tech stack

## Application

- **Frontend:** Next.js
- **Backend:** FastAPI

## Platform

- **Database:** Supabase Postgres
- **Auth:** Supabase Auth
- **Storage:** Supabase Storage
- **Queue / async jobs:** Redis
- **Vector support:** pgvector (if enabled in Supabase)

## Observability

- Sentry
- audit logs in database

---

# User roles

## Applicant

Applicants can:

- sign up and log in
- edit profile
- upload resume/documents
- set location, relocation willingness, travel willingness
- view ranked jobs
- inspect explanations and missing requirements
- use planning/chat
- save jobs / mark interest / apply if enabled

## Employer

Employers can:

- log in
- manage company profile
- create/edit jobs
- view ranked applicants for their own jobs
- filter by geography, readiness, credentials, etc.
- shortlist or contact applicants if enabled

## Admin

Admins can:

- manage imports
- manage employer accounts
- manage admin users
- view all applicants, employers, jobs, matches
- manage taxonomy and policy config
- review low-confidence extraction/matching results
- inspect analytics and audit logs
- trigger recomputation

---

# Matching model

## Outputs per applicant-job pair

The system computes and stores:

- `eligibility_status`
- `base_fit_score`
- `policy_adjusted_score`
- `match_label`
- `top_strengths`
- `top_gaps`
- `required_missing_items`
- `recommended_next_step`
- `confidence_level`

## Ranking pipeline

### 1. Normalize inputs

Normalize:

- applicant program / pathway
- job family
- geography
- pay ranges
- timing/readiness
- credentials/licenses
- extracted skill fields

### 2. Hard eligibility gates

Each applicant-job pair is labeled:

- `eligible`
- `near_fit`
- `ineligible`

Gate dimensions:

- job family compatibility
- required credential compatibility
- readiness/timing compatibility
- geography feasibility
- explicit minimum requirement compatibility

### 3. Structured score

Weighted score using normalized fields:

- trade/program alignment
- geography alignment
- credential readiness
- timing readiness
- experience/internship alignment
- industry alignment
- compensation alignment
- work-style signal alignment
- employer soft preference alignment

### 4. Semantic support score

Supportive text-based score from:

- applicant essays
- internship details
- extracurriculars
- resume text
- job descriptions
- qualifications
- responsibilities

### 5. Policy reranking

Policy modifies **ordering**, not raw compatibility.

Default policy dimensions:

- partner employer preference
- funded training pathway alignment
- geography preference
- readiness preference
- opportunity upside
- missing critical requirement penalties

---

# Repo structure

```text
apps/
  web/                 # Next.js frontend
  api/                 # FastAPI backend

packages/
  ui/                  # shared UI components
  types/               # shared types/schemas
  matching/            # gates, scoring, reranking, explanation helpers
  etl/                 # imports, normalization, parsing helpers

supabase/
  config.toml          # Supabase CLI local config
  migrations/          # SQL migrations (added from Phase 3)

docs/                  # project docs
scripts/               # import, normalize, recompute, inspect scripts
infra/                 # infra and deployment-related config
  docker-compose.local.yml   # local Redis
```

---

# Local development

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 20+ | https://nodejs.org |
| pnpm | 9+ | `npm i -g pnpm` |
| Python | 3.11+ | https://python.org |
| Docker Desktop | latest | https://docker.com |
| Supabase CLI | latest | `brew install supabase/tap/supabase` |

## 1. Clone and install

```bash
git clone <repo-url>
cd skillpointe

# Install JS dependencies
pnpm install
```

## 2. Configure environment variables

```bash
# Frontend
cp apps/web/.env.local.example apps/web/.env.local

# Backend
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` and `apps/web/.env.local` and fill in your values.
For local development the defaults work once Supabase and Redis are running (see below).

## 3. Start local Supabase

```bash
# From repo root
supabase start
```

After startup, `supabase status` will print your local URL, anon key, and service role key.
Copy these into `apps/api/.env` and `apps/web/.env.local`:

```
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<from supabase status>
SUPABASE_SERVICE_ROLE_KEY=<from supabase status>
SUPABASE_JWT_SECRET=<from supabase status>
```

Local Supabase services:
- Studio: http://localhost:54323
- REST API: http://localhost:54321/rest/v1/
- Auth: http://localhost:54321/auth/v1/
- Storage: http://localhost:54321/storage/v1/
- Inbucket (email): http://localhost:54324

## 4. Start Redis

```bash
docker compose -f infra/docker-compose.local.yml up -d
```

## 5. Verify connections

```bash
pip install redis httpx python-dotenv   # if not already installed
python scripts/check_connections.py
```

Expected output:
```
[Redis]
  OK   — connected to redis://localhost:6379
[Supabase]
  OK   — REST API reachable at http://localhost:54321
  OK   — Auth endpoint healthy
All connections OK. Local dev environment is ready.
```

## 6. Start the FastAPI backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API available at: http://localhost:8000
Health check: http://localhost:8000/health
API docs (local only): http://localhost:8000/docs

## 7. Start the Next.js frontend

```bash
# In a separate terminal, from repo root
pnpm dev:web
```

Frontend available at: http://localhost:3000

## 8. Run database migrations (Phase 3+)

```bash
supabase db reset        # resets local DB and runs all migrations
# or
supabase migration up    # applies pending migrations
```

## Normal local dev sequence

```bash
supabase start                                          # 1. Supabase
docker compose -f infra/docker-compose.local.yml up -d # 2. Redis
python scripts/check_connections.py                     # 3. Verify
cd apps/api && uvicorn main:app --reload --port 8000    # 4. API
pnpm dev:web                                            # 5. Frontend (new terminal)
```

## Stop everything

```bash
supabase stop
docker compose -f infra/docker-compose.local.yml down
```

---

# Environment variables reference

All variables are documented in `.env.example` at the repo root.
Per-app examples are in `apps/web/.env.local.example` and `apps/api/.env.example`.

| Variable | Used by | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | web | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | web | Supabase public anon key |
| `SUPABASE_URL` | api | Supabase project URL |
| `SUPABASE_ANON_KEY` | api | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | api | Supabase service role key (backend only) |
| `SUPABASE_JWT_SECRET` | api | Supabase JWT secret for token validation |
| `REDIS_URL` | api | Redis connection URL |
| `OPENAI_API_KEY` | api | LLM API key (extraction, chat) |
| `SENTRY_DSN` | api/web | Sentry error monitoring DSN |
| `CORS_ORIGINS` | api | Comma-separated allowed CORS origins |
| `APP_ENV` | api | `local` \| `test` \| `staging` \| `production` |

---

# Source of truth files

These files govern all implementation decisions:

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Platform identity, guardrails, architecture rules |
| `DECISIONS.md` | Product/policy decision register (decided / defaulted / unresolved) |
| `SCORING_CONFIG.yaml` | Canonical scoring weights, eligibility rules, policy config |
| `BUILD_PLAN.md` | Phase-by-phase build plan and completion criteria |
| `PROMPTS.md` | LLM prompt definitions for extraction, verification, explanation, chat |
