# STATUS.md — SkillPointe Match Build Handoff

> Last updated: 2026-03-11
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
| 6.1 | Applicant dashboard + ranked job matches + explanation detail | ✅ Complete |
| 6.2 | Employer dashboard + job management + ranked applicants per job | ✅ Complete |
| 6.3 | Match explanation surfaces (dimension breakdown, strengths, gaps, next steps) | ✅ Complete |
| 7 | LLM extraction + verification | ⬜ Not started |
| 8 | Applicant planning chat | ⬜ Not started |
| 9 | Admin review + config + analytics | ⬜ Not started |
| 10 | QA + end-to-end testing | ⬜ Not started |
| 11 | Deployment + production readiness | ⬜ Not started |

**Where we are:** All backend + all product-facing surfaces (Phases 1–6) are complete. The app is testable end-to-end with seeded test users. The next major milestone is Phase 7 — LLM extraction, which upgrades the currently-placeholder credential/requirement gates and semantic score with real extraction.

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
API_URL=http://localhost:8000
```

### 5. Seed test users

```bash
# From the repo root — installs deps + creates all 3 test users
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/seed_test_users.py
```

This creates three ready-to-use accounts (password `Test1234!` for all):

| Role | Email | Goes to |
|---|---|---|
| Applicant | `applicant@skillpointe.test` | `/applicant` |
| Employer | `employer@skillpointe.test` | `/employer` |
| Admin | `admin@skillpointe.test` | `/admin` |

The script also creates: an applicant profile (Jane Smith, Welding Technology, Austin TX), an employer company (Acme Industrial, partner), 2 sample jobs, and 2 pre-computed matches so the ranked views are populated immediately.

### 6. Start the app

```bash
# Terminal 1 — API
cd apps/api && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend (from repo root)
pnpm dev:web
```

Open `http://localhost:3000`. Log in as any test user.

### 7. Run the test suite

```bash
cd apps/api
source .venv/bin/activate
pytest tests/ -v
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
- JWT validation supporting both HS256 and ES256 (Supabase CLI v2) via JWKS (`app/auth/dependencies.py`)
- RBAC dependency functions: `require_admin`, `require_applicant`, `require_employer`, `require_employer_or_admin`
- Auth router: `GET /auth/me`, `POST /auth/complete-signup`, `POST /auth/invite-employer`
- Health endpoint: `GET /health`

**Frontend (`apps/web/src/`):**
- Supabase client helpers: `lib/supabase/client.ts`, `lib/supabase/server.ts`
- Route protection middleware: `middleware.ts` (redirects wrong-role routes)
- Auth pages: login, signup, forgot-password, reset-password (`app/(auth)/`)

**Auth flow:**
- Applicants: self-signup → `POST /auth/complete-signup` → `/applicant`
- Employers: admin invites via `POST /auth/invite-employer` → email invite → `/employer`
- Admins: created via `scripts/seed_admin.py`

**Tests:** `apps/api/tests/test_auth.py` (13 tests)

**Important — Supabase CLI v2 note:**
Supabase CLI v2 signs JWTs with ES256 (ECDSA), not HS256. The `decode_supabase_jwt` function detects the algorithm from the JWT header and validates ES256 tokens via `GET /auth/v1/.well-known/jwks.json`. The JWKS response is cached in-process. This is already handled — do not revert to HS256-only.

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
- `scripts/import_applicants.py` — imports applicants from XLSX/CSV
- `scripts/import_jobs.py` — imports jobs from XLSX/CSV

**Normalization script:**
- `scripts/normalize_data.py` — maps program names/job titles → canonical job families, parses pay ranges, resolves geography regions

**Tests:** `apps/api/tests/test_etl_import.py` (79 tests)

### Phase 5 — Matching Engine v1

**`packages/matching/`:**

| File | What it does |
|------|-------------|
| `config.py` | Loads `SCORING_CONFIG.yaml` → `ScoringConfig` dataclass. Falls back to built-in defaults if YAML missing. |
| `normalizer.py` | Pure normalization functions: program→job family, pay range parsing, location→region, timing→readiness label. Defines `JOB_FAMILY_ADJACENCY` map. |
| `gates.py` | 5 hard eligibility gates (job family, credentials, timing, geography, min requirements) + `compute_eligibility` aggregator. |
| `scorer.py` | 9 structured scoring dimensions + `compute_structured_score`. Null handling defaults are neutral, not punitive. |
| `engine.py` | `compute_match(applicant, job, employer, config)` — orchestrates all stages, returns `MatchResult`. Semantic score is a placeholder (50.0) until Phase 7. |

**Three-stage pipeline:**
1. **Hard gates** → `eligibility_status` (eligible/near_fit/ineligible) + `hard_gate_cap` (1.0/0.75/0.35)
2. **Base fit** → `gate_cap × (structured_score × 0.75 + semantic_score × 0.25)`
3. **Policy reranking** → adds partner/geography/readiness modifiers → `policy_adjusted_score`

**Tests:** `apps/api/tests/test_matching.py` (122 tests)

### Phase 6 — Product Surfaces (Applicant + Employer)

#### 6.1 — Applicant dashboard + ranked jobs

**Backend:**
- `GET /applicant/me/profile` — returns applicant profile summary
- `GET /applicant/me/matches` — returns ranked job list (policy_adjusted_score DESC)
- `GET /applicant/me/matches/{match_id}` — returns full match detail with dimension scores, gate results, policy modifiers

**Frontend:**
- `apps/web/src/app/(dashboard)/applicant/page.tsx` — profile summary dashboard
- `apps/web/src/app/(dashboard)/applicant/matches/page.tsx` — ranked jobs list (eligible + near-fit sections)
- `apps/web/src/app/(dashboard)/applicant/matches/[matchId]/page.tsx` — full match detail view
- `apps/web/src/components/matches/JobMatchCard.tsx` — job match summary card
- `apps/web/src/components/matches/MatchLabel.tsx` — match quality badge
- `apps/web/src/components/matches/DimensionBreakdown.tsx` — 9-dimension score breakdown visualization
- `apps/web/src/lib/api/applicant.ts` — typed API client functions
- `apps/api/app/schemas/applicant.py` — Pydantic response schemas

#### 6.2 — Employer dashboard + job management + ranked applicants

**Backend:**
- `GET /employer/me/company` — returns company summary
- `GET /employer/me/jobs` — returns job list with per-job match stats
- `POST /employer/me/jobs` — creates new job
- `PATCH /employer/me/jobs/{job_id}` — updates job fields
- `GET /employer/me/jobs/{job_id}/applicants` — returns ranked applicant list with filters

**Critical safety rules enforced in SQL:**
- Every query resolves `employer_id` via `employer_contacts` — cross-employer access is impossible
- All match queries require `is_visible_to_employer = TRUE`

**Frontend:**
- `apps/web/src/app/(dashboard)/employer/page.tsx` — company summary + jobs list
- `apps/web/src/app/(dashboard)/employer/jobs/new/page.tsx` — create job form (server action)
- `apps/web/src/app/(dashboard)/employer/jobs/[jobId]/edit/page.tsx` — edit job form (server action)
- `apps/web/src/app/(dashboard)/employer/jobs/[jobId]/applicants/page.tsx` — ranked applicants (URL-based filters, bookmarkable)
- `apps/web/src/components/employer/ApplicantMatchCard.tsx` — applicant match card with strengths/gaps/geography
- `apps/web/src/lib/api/employer.ts` — typed API client functions
- `apps/api/app/schemas/employer.py` — Pydantic response schemas

**Tests:** `apps/api/tests/test_employer_visibility.py` (8 test classes covering employer scoping, visibility flags, RBAC, safe field exposure, geography notes)

#### 6.3 — Explanation surfaces

Built within 6.1 and 6.2:
- Full 9-dimension score breakdown with per-dimension score, weight, contribution (DimensionBreakdown component)
- Hard gate results (pass/near_fit/fail per gate, with reason)
- Policy modifier breakdown (partner bonus, geography boost, readiness boost, penalties)
- `top_strengths`, `top_gaps`, `required_missing_items`, `recommended_next_step` on every match
- Geography note derived from job work_setting + applicant location/preferences
- Confidence and review status flags

---

## Known infrastructure quirks

### Supabase CLI v2 uses ES256 JWTs (not HS256)
Supabase CLI v2 switched from symmetric HS256 to asymmetric ES256 JWT signing. The FastAPI `decode_supabase_jwt` function now handles this automatically by reading the JWT header `alg` field and fetching the JWKS when needed. **Do not change `algorithms=["HS256"]` back** — both are intentionally supported.

### Running `seed_test_users.py`
The script uses the API virtualenv dependencies. Activate `.venv` before running it, or install `psycopg2-binary` and `supabase` in whichever Python environment you're using:
```bash
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/seed_test_users.py
```

### `match_label_enum` values
The DB enum uses: `strong_fit`, `good_fit`, `moderate_fit`, `low_fit`. The migration was corrected from an earlier wrong set of values (`strong_match`, `good_match`, etc.) to match SCORING_CONFIG.yaml. If you ever see `invalid input value for enum match_label_enum`, run `supabase db reset`.

---

## What to build next — Phase 7

### Phase 7 — LLM Extraction + Verification

This is what makes the matching engine precise. Currently these are placeholders:

| Component | Current state | Phase 7 replacement |
|---|---|---|
| Credential gate | Always returns `near_fit` | Real extraction: detect credentials/licenses from applicant text |
| Min-requirements gate | Always returns `near_fit` | Real extraction: detect explicit requirements from job text |
| Semantic score | Always `50.0` | Real embeddings: pgvector similarity (extension already enabled) |
| Experience score | Based on text length only | LLM-extracted experience signals |

### Step 7.1 — Applicant extraction

Build an LLM extraction pipeline that reads applicant essay/resume text and returns structured JSON:

```
extracted skills, certifications, desired job families, work-style signals,
experience signals, readiness signals, confidence, evidence snippets
```

Store output in `extracted_applicant_signals` table with:
- `raw_llm_output` (text)
- `parsed_output` (JSONB)
- `confidence` (high/medium/low enum)
- `prompt_version`
- `review_status` (pending/reviewed/overridden)

Use prompts from `PROMPTS.md` as the base prompt library.
Flag low-confidence outputs for admin review queue.

### Step 7.2 — Job extraction

Same pattern, applied to job descriptions:

```
required/preferred skills, required credentials, experience level, physical
requirements, travel requirements, work setting, confidence
```

Store in `extracted_job_signals`.

### Step 7.3 — Verifier / judge layer

For ambiguous extractions, borderline classifications, and taxonomy mismatches:
- LLM verifier returns structured verdict (not just a score)
- Human review recommendations are stored in `review_queue_items`
- Verifier never overrides auditability

### After Phase 7 is done

- Rerun `scripts/recompute_matches.py` — this time with real extraction powering the credential/requirements gates and semantic score
- Use `scripts/inspect_matches.py` to verify ranking quality improved
- Compare top matches before/after to validate the extraction is helping

---

## What to build after Phase 7 — Phase 8

**Applicant planning chat** — grounded chat using applicant profile + ranked matches + gaps.
- Tables already exist: `chat_sessions`, `chat_messages`, `chat_prompt_configs`
- Base prompts are in `PROMPTS.md`
- Build retrieval context from ranked matches + gaps + geography first, then add the UI

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
│   │   │   ├── auth/               ← JWT validation (HS256+ES256), RBAC deps, schemas
│   │   │   ├── routers/            ← auth.py, health.py, applicants.py, employers.py
│   │   │   ├── schemas/            ← applicant.py, employer.py (Pydantic response models)
│   │   │   ├── config.py           ← Pydantic settings
│   │   │   └── main.py
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_auth.py                  ← 13 tests
│   │   │   ├── test_etl_import.py            ← 79 tests
│   │   │   ├── test_matching.py              ← 122 tests
│   │   │   └── test_employer_visibility.py   ← 8 test classes (employer scoping + visibility)
│   │   ├── requirements.txt
│   │   └── pyproject.toml
│   │
│   └── web/                        ← Next.js 15 frontend
│       └── src/
│           ├── lib/
│           │   ├── supabase/       ← client.ts + server.ts helpers
│           │   └── api/            ← client.ts, applicant.ts, employer.ts
│           ├── middleware.ts        ← route protection
│           ├── components/
│           │   ├── matches/        ← JobMatchCard, MatchLabel, DimensionBreakdown
│           │   └── employer/       ← ApplicantMatchCard
│           └── app/
│               ├── (auth)/         ← login, signup, forgot/reset password
│               └── (dashboard)/
│                   ├── applicant/  ← page.tsx, matches/page.tsx, matches/[matchId]/page.tsx
│                   ├── employer/   ← page.tsx, jobs/new, jobs/[id]/edit, jobs/[id]/applicants
│                   └── admin/      ← page.tsx (placeholder — Phase 9)
│
├── packages/
│   ├── etl/                        ← Import + normalization logic (pure Python)
│   │   ├── loader.py, coerce.py, models.py
│   │   ├── applicant_mapper.py, job_mapper.py
│   │   └── db.py, reporting.py
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
│   ├── normalize_data.py           ← Normalization pipeline
│   ├── recompute_matches.py        ← Full match recompute (run after Phase 7 extraction)
│   ├── inspect_matches.py          ← CLI match inspection + CSV export
│   ├── seed_admin.py               ← Create first admin user
│   ├── seed_test_users.py          ← Create all 3 test users for local dev
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

3. **The semantic score (50.0) is a placeholder.** Every pair receives the same semantic score until Phase 7 builds real embeddings. Within-eligibility-group ranking is driven entirely by structured score for now. See `engine.py:_PLACEHOLDER_SEMANTIC_SCORE`.

4. **The credential and minimum-requirement gates are also placeholders.** They both default to `near_fit` until Phase 7 LLM extraction runs. See comments in `gates.py`.

5. **`packages/matching/` has zero DB I/O.** All DB reads/writes happen in `scripts/`. The matching package is pure functions only.

6. **Null handling is neutral, not punitive.** If data is missing, the default score is neutral (not 0). See `SCORING_CONFIG.yaml §null_handling`.

7. **Geography is first-class.** It affects hard gates, the structured score, AND policy reranking. Don't skip it when adding features.

---

## Test suite

```bash
cd apps/api
source .venv/bin/activate
pytest tests/ -v
```

- `test_auth.py` — 13 tests (JWT, RBAC, signup flows)
- `test_etl_import.py` — 79 tests (ETL mapping, coercions, real SkillPointe columns)
- `test_matching.py` — 122 tests (normalizer, gates, scorer, engine — no DB required)
- `test_employer_visibility.py` — 8 test classes (employer scoping, visibility flags, RBAC, safe field exposure)

All matching engine tests run without Supabase or a database connection.

---

## Data

Real SkillPointe data files are stored locally (not committed to git):
- **Applicants:** 335 rows across 40 columns
- **Jobs:** 300 rows across 20 columns

Full pipeline (first-time setup with real data):
```bash
supabase db reset
python scripts/import_applicants.py data/applicants.xlsx
python scripts/import_jobs.py data/jobs.xlsx
python scripts/normalize_data.py
python scripts/recompute_matches.py
python scripts/inspect_matches.py --stats
```

After Phase 7 extraction is added, re-run `recompute_matches.py` to refresh scores with real LLM-extracted signals.
