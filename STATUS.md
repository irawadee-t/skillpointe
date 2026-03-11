# STATUS.md — SkillPointe Match Build Handoff

> Last updated: 2026-03-10
>
> For: teammates picking up where development left off.
> Read this alongside `CLAUDE.md` (product rules) and `BUILD_PLAN.md` (execution plan).

---

## What this project is

Three-role workforce matching platform:
- **Applicants** see ranked job matches, score explanations, and missing requirements
- **Employers** see ranked applicant lists per job with rationale
- **Admins** manage imports, taxonomy, scoring policy, review queues, and analytics

MVP is a **continuous ranking and explanation platform** — NOT batch matching, NOT deferred acceptance.
Ranking is deterministic + policy-reranked + LLM-assisted (in that order of priority).

---

## Build status at a glance

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Repo + Supabase environment foundation | ✅ Complete |
| 2 | Auth + RBAC | ✅ Complete |
| 3 | Core data model + database schema | ✅ Complete |
| 4 | Imports + ETL + normalization | ✅ Complete |
| 5 | Matching engine v1 (hard gates + structured scoring + policy) | ✅ Complete |
| 6 | Applicant and employer product surfaces (UI) | ⬜ Not started |
| 7 | LLM extraction + verification | ⬜ Not started |
| 8 | Applicant planning chat | ⬜ Not started |
| 9 | Admin review + config + analytics | ⬜ Not started |
| 10 | QA + end-to-end testing | ⬜ Not started |
| 11 | Deployment + production readiness | ⬜ Not started |

**Where we are:** The backend foundation is complete. The database, auth, import pipeline, and full matching engine are all built and tested. The next major milestone is building the product-facing UI surfaces (Phase 6).

---

## Getting set up (new developer)

### 1. Prerequisites

Install these first:

- [Node.js 20+](https://nodejs.org) + [pnpm](https://pnpm.io/installation): `npm install -g pnpm`
- [Python 3.11+](https://python.org)
- [Supabase CLI](https://supabase.com/docs/guides/cli): `brew install supabase/tap/supabase`
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (required by Supabase CLI)

### 2. Clone and install

```bash
git clone <repo-url>
cd skillpointe

# Install frontend dependencies
pnpm install

# Create Python virtualenv and install backend dependencies
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../..
```

### 3. Start local services

```bash
# Start Supabase (Postgres + Auth + Storage + Studio)
supabase start

# Load the full schema and seed data
supabase db reset

# Start local Redis (required for async job queue)
docker compose -f infra/docker-compose.local.yml up -d
```

### 4. Configure environment variables

```bash
# Get the local keys from Supabase
supabase status
```

Copy the output values into `apps/api/.env`:

```env
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<anon key from supabase status>
SUPABASE_SERVICE_ROLE_KEY=<service role key from supabase status>
SUPABASE_JWT_SECRET=<JWT secret from supabase status>
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
REDIS_URL=redis://localhost:6379
```

Copy the same values into `apps/web/.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

### 5. Create an admin user

```bash
cd apps/api
source .venv/bin/activate
python scripts/seed_admin.py --email admin@example.com --password yourpassword
```

### 6. Verify everything works

```bash
# Check DB + Redis connections
python scripts/check_connections.py

# Run all tests (201 tests — should all pass)
cd apps/api
.venv/bin/python -m pytest tests/ -v

# Start the API
uvicorn main:app --reload --port 8000

# Start the web frontend (new terminal, from repo root)
pnpm dev:web
```

---

## What was built — detailed breakdown

### Phase 1 — Repo + Environment

- Monorepo with `apps/web`, `apps/api`, `packages/etl`, `packages/matching`, `packages/types`, `packages/ui`
- Supabase CLI local config (`supabase/config.toml`)
- Redis via Docker Compose (`infra/docker-compose.local.yml`)
- Local dev guide: `docs/local-development.md`

### Phase 2 — Auth + RBAC

**Backend (`apps/api/app/`):**
- JWT validation using Supabase JWT secret (`app/auth/dependencies.py`)
- RBAC dependency functions: `require_admin`, `require_applicant`, `require_employer`, `require_employer_or_admin`
- Auth router: `GET /auth/me`, `POST /auth/complete-signup`, `POST /auth/invite-employer`
- Health endpoint: `GET /health`

**Frontend (`apps/web/src/`):**
- Supabase client helpers: `lib/supabase/client.ts`, `lib/supabase/server.ts`
- Route protection middleware: `middleware.ts` (redirects wrong-role routes)
- Auth pages: login, signup, forgot-password, reset-password (`app/(auth)/`)
- Dashboard layout placeholders: `app/(dashboard)/applicant/`, `app/(dashboard)/employer/`, `app/(dashboard)/admin/`

**Auth flow:**
- Applicants: self-signup → `POST /auth/complete-signup` → `/applicant`
- Employers: admin invites via `POST /auth/invite-employer` → email invite → `/employer`
- Admins: created via `scripts/seed_admin.py`

**Tests:** `apps/api/tests/test_auth.py` (13 tests)

### Phase 3 — Core Data Model

**9 migrations** in `supabase/migrations/`:
- `000000` — `user_profiles` table (links Supabase Auth → app role)
- `000001` — enums + pgvector extension
- `000002` — taxonomy (`canonical_job_families`, `geography_regions`)
- `000003` — core entities (`applicants`, `employers`, `jobs`)
- `000004` — documents and signals (`applicant_documents`, `extracted_fields`, etc.)
- `000005` — matches (`matches`, `match_dimension_scores`)
- `000006` — ops and config (`policy_configs`, `scoring_runs`, `audit_log`)
- `000007` — chat (`chat_sessions`, `chat_messages`, `chat_prompt_configs`)
- `000008` — import support (`import_runs`, `import_rows`)

**Seed data** (`supabase/seed.sql`): 15 canonical job families, 5 geography regions, `policy_config v1` (SCORING_CONFIG.yaml values loaded to DB).

Schema reference: `docs/schema.md`

### Phase 4 — ETL Import Pipeline

**`packages/etl/`:**
- `loader.py` — header normalization + CSV/XLSX loading
- `applicant_mapper.py` — maps all 40 real SkillPointe applicant columns
- `job_mapper.py` — maps all 20 real SkillPointe job columns
- `coerce.py` — type coercions (bool, date, int, state, text)
- `models.py` — `MappedApplicant`, `MappedJob`, `ImportResult`
- `db.py` — psycopg2 DB helpers (`insert_applicant`, `upsert_job`, `get_connection`)
- `reporting.py` — formatted import output

**Import scripts:**
- `scripts/import_applicants.py` — imports applicants from XLSX/CSV (335 rows in real data, 0 errors)
- `scripts/import_jobs.py` — imports jobs from XLSX/CSV (300 rows in real data, 0 errors)

**Normalization script:**
- `scripts/normalize_data.py` — maps program names/job titles → canonical job families, parses pay ranges, resolves geography regions

**Tests:** `apps/api/tests/test_etl_import.py` (79 tests)

### Phase 5 — Matching Engine v1

**`packages/matching/`:**

| File | What it does |
|------|-------------|
| `config.py` | Loads `SCORING_CONFIG.yaml` → `ScoringConfig` dataclass. Falls back to built-in defaults if YAML missing (safe for unit tests). |
| `normalizer.py` | Pure normalization functions: program→job family, pay range parsing, location→region, timing→readiness label. Defines `JOB_FAMILY_ADJACENCY` map. |
| `gates.py` | 5 hard eligibility gates (job family, credentials, timing, geography, min requirements) + `compute_eligibility` aggregator. |
| `scorer.py` | 9 structured scoring dimensions + `compute_structured_score`. Null handling defaults are neutral, not punitive. |
| `engine.py` | `compute_match(applicant, job, employer, config)` — orchestrates all stages, returns `MatchResult`. Semantic score is a placeholder (50.0) until Phase 7. |

**Three-stage pipeline:**
1. **Hard gates** → `eligibility_status` (eligible/near_fit/ineligible) + `hard_gate_cap` (1.0/0.75/0.35)
2. **Base fit** → `gate_cap × (structured_score × 0.75 + semantic_score × 0.25)`
3. **Policy reranking** → adds partner/geography/readiness modifiers → `policy_adjusted_score`

**Recompute + inspect scripts:**
- `scripts/recompute_matches.py` — computes all pairs, upserts to `matches` + `match_dimension_scores`
- `scripts/inspect_matches.py` — CLI for querying top results, score breakdowns, CSV export

**Run guide:** `docs/MATCHING_SCRIPTS.md`

**Tests:** `apps/api/tests/test_matching.py` (122 tests)

---

## What to build next

The entire backend foundation is solid. The next work is the **product-facing surfaces** (Phase 6) and the **LLM extraction layer** (Phase 7). These can mostly proceed in parallel.

### Immediate next: Phase 6 — Product surfaces

This is the first visible part of the product. Build in this order:

#### 6A — Applicant: ranked job list

**Backend:**
- `GET /applicant/matches` — return top N jobs for the authenticated applicant, ordered by `policy_adjusted_score`
- Include: `match_label`, `eligibility_status`, `top_strengths`, `top_gaps`, `recommended_next_step`, basic job info

**Frontend:**
- Applicant dashboard: ranked job cards
- Each card shows: job title, employer, location, match label (strong/good/moderate/low), 1-line rationale
- Detail view: full score breakdown, strengths, gaps, recommended next step

#### 6B — Employer: ranked applicant list per job

**Backend:**
- `GET /employer/jobs/{job_id}/matches` — return top N applicants for a specific job, ordered by score
- Employer can only see their own jobs' matches (RBAC enforced)

**Frontend:**
- Employer job dashboard: list of employer's jobs
- Per-job: ranked applicant list with eligibility, score, top traits
- Filter by: eligibility status, geography, readiness

#### 6C — Match explanation page

- Shared detail view usable from both applicant and employer side
- Show: all 9 dimension scores as a visual breakdown, gate results, policy modifiers, strengths/gaps/next steps

### After Phase 6: Phase 7 — LLM extraction

This is what makes the matching engine precise. Currently:
- credentials gate → always NEAR_FIT (pre-Phase 7 placeholder)
- minimum requirements gate → always NEAR_FIT (pre-Phase 7 placeholder)
- semantic score → always 50.0 (placeholder)
- experience score → based on text length only

Phase 7 replaces these with real extraction:
1. Extract structured skills, credentials, certifications from applicant essays/resume
2. Extract required credentials + explicit requirements from job descriptions
3. Real semantic similarity scoring using embeddings (pgvector already enabled)
4. Store all LLM outputs with confidence, prompt version, raw output, review status

### Phase 8 — Applicant planning chat

Grounded chat interface using applicant profile + ranked matches + gaps.
- Uses `PROMPTS.md` as the base prompt library
- Chat sessions + messages already in schema (`chat_sessions`, `chat_messages` tables)

### Phase 9 — Admin tools

- Review queue for low-confidence extractions and taxonomy mismatches
- Policy/scoring config management UI (edit weights, toggle policies)
- Import management (trigger re-imports, view import run history)
- Audit log viewer

---

## Key files map

```
skillpointe/
├── CLAUDE.md                       ← Product rules + guardrails (read first)
├── BUILD_PLAN.md                   ← Execution plan (read second)
├── DECISIONS.md                    ← Architecture decision log
├── SCORING_CONFIG.yaml             ← Scoring weights + policy config (source of truth)
├── PROMPTS.md                      ← LLM prompt library (Phase 7+)
├── STATUS.md                       ← This file
│
├── supabase/
│   ├── migrations/                 ← 9 SQL migration files (full schema)
│   └── seed.sql                    ← Taxonomy + policy config v1
│
├── apps/
│   ├── api/                        ← FastAPI backend
│   │   ├── app/
│   │   │   ├── auth/               ← JWT validation, RBAC deps, schemas
│   │   │   ├── routers/            ← auth.py, health.py (more needed in Phase 6)
│   │   │   ├── config.py           ← Pydantic settings
│   │   │   └── main.py
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_auth.py        ← 13 auth tests
│   │   │   ├── test_etl_import.py  ← 79 ETL tests
│   │   │   └── test_matching.py    ← 122 matching engine tests
│   │   ├── requirements.txt
│   │   └── pyproject.toml
│   │
│   └── web/                        ← Next.js 15 frontend
│       └── src/
│           ├── lib/supabase/       ← client.ts + server.ts helpers
│           ├── middleware.ts        ← route protection
│           └── app/
│               ├── (auth)/         ← login, signup, forgot/reset password
│               └── (dashboard)/    ← applicant/, employer/, admin/ placeholders
│
├── packages/
│   ├── etl/                        ← Import + normalization logic (pure Python)
│   │   ├── loader.py, coerce.py, models.py
│   │   ├── applicant_mapper.py, job_mapper.py
│   │   ├── db.py, reporting.py
│   │
│   └── matching/                   ← Matching engine (pure Python, no DB)
│       ├── config.py               ← ScoringConfig loader
│       ├── normalizer.py           ← Normalization + JOB_FAMILY_ADJACENCY
│       ├── gates.py                ← 5 hard eligibility gates
│       ├── scorer.py               ← 9 structured scoring dimensions
│       └── engine.py               ← compute_match orchestrator
│
├── scripts/
│   ├── import_applicants.py        ← Import applicants from XLSX
│   ├── import_jobs.py              ← Import jobs from XLSX
│   ├── normalize_data.py           ← Phase 4.3 normalization pipeline
│   ├── recompute_matches.py        ← Phase 5 full match recompute
│   ├── inspect_matches.py          ← CLI match inspection + CSV export
│   ├── seed_admin.py               ← Create first admin user
│   ├── verify_schema.py            ← Check DB schema is correct
│   └── check_connections.py        ← Verify DB + Redis connections
│
└── docs/
    ├── local-development.md        ← Dev environment reference
    ├── schema.md                   ← DB schema documentation
    └── MATCHING_SCRIPTS.md         ← How to run normalize/recompute/inspect
```

---

## Things to know before touching the matching engine

1. **`base_fit_score` and `policy_adjusted_score` must always be stored separately.** Never merge them. This is `DECISIONS.md 1.6`.

2. **Hard gate failures cap the score — they never get overridden.** `ineligible` pairs get a 0.35 cap regardless of structured score. `DECISIONS.md 1.12`.

3. **The semantic score (50.0) is a placeholder.** Every pair receives the same semantic score until Phase 7 builds real embeddings. This means within-eligibility-group ranking is driven entirely by structured score for now. See `engine.py:_PLACEHOLDER_SEMANTIC_SCORE`.

4. **The credential and minimum-requirement gates are also placeholders.** They both default to NEAR_FIT until Phase 7 LLM extraction runs. See comments in `gates.py`.

5. **`packages/matching/` has zero DB I/O.** All DB reads/writes happen in `scripts/`. The matching package is pure functions only — keeps it testable and portable.

6. **Null handling is neutral, not punitive.** If data is missing, the default score is set to a neutral value (not 0). See `SCORING_CONFIG.yaml §null_handling` and `packages/matching/config.py:NullHandlingConfig`.

7. **Geography is first-class.** It affects hard gates, the structured score, AND policy reranking. Don't skip it when adding features.

---

## Test suite

```bash
cd apps/api
.venv/bin/python -m pytest tests/ -v
```

**201 tests, all passing:**
- `test_auth.py` — 13 tests (JWT, RBAC, signup flows)
- `test_etl_import.py` — 79 tests (ETL mapping, coercions, real SkillPointe columns)
- `test_matching.py` — 122 tests (normalizer, gates, scorer, engine — no DB required)

All matching engine tests run without Supabase or a database connection.

---

## Data

Real SkillPointe data files are stored locally (not committed to git):
- **Applicants:** 335 rows across 40 columns
- **Jobs:** 300 rows across 20 columns

After importing, running normalization gives approximately:
- ~285/335 applicants matched to a canonical job family
- ~278/300 jobs matched to a canonical job family

Unmatched programs indicate missing aliases in `supabase/seed.sql`. Fix by adding aliases there, re-running `supabase db reset`, re-importing, and re-normalizing.

Full pipeline (first-time setup with real data):
```bash
supabase db reset
python scripts/import_applicants.py data/applicants.xlsx
python scripts/import_jobs.py data/jobs.xlsx
python scripts/normalize_data.py
python scripts/recompute_matches.py
python scripts/inspect_matches.py --stats
```
