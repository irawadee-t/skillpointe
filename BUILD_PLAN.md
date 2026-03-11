# BUILD_PLAN.md — SkillPointe Match End-to-End Build Plan (Supabase Version)

## Purpose

This file is the canonical execution plan for building SkillPointe Match.
It should be pasted into Claude at the start of build sessions together with:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`

Claude must always:

1. identify the current phase
2. state what has already been completed
3. state what the current task is
4. state what the next task is after completion
5. avoid jumping ahead unless explicitly requested

This file governs build order, repo flow, testing flow, and deployment flow.

---

# 0. Global Rules for Claude

Whenever you are asked to work on this repo, first do the following:

1. Read and follow:
   - `CLAUDE.md`
   - `DECISIONS.md`
   - `SCORING_CONFIG.yaml`
   - this `BUILD_PLAN.md`

2. In your response, always include:
   - `Current Phase: <phase name>`
   - `Current Step: <step number + title>`
   - `Depends On: <what must already exist>`
   - `Next Step: <what should happen next after this task>`

3. Do not silently invent business policy outside the files above.
4. Do not add batch matching / deferred acceptance to MVP.
5. Do not treat LLMs as the primary ranking engine.
6. Do not skip:
   - geography
   - admin review
   - auditability
   - role-based auth
   - deterministic scoring
   - separate policy reranking

---

# 1. Canonical Repository Inputs

The repo should eventually contain these key source-of-truth files:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`

All implementation should remain aligned with them.

---

# 2. Canonical Monorepo Shape

Expected repository structure:

- `apps/web`
- `apps/api`
- `packages/ui`
- `packages/types`
- `packages/matching`
- `packages/etl`
- `docs`
- `scripts`
- `infra`

Recommended stack:

- Frontend: Next.js
- Backend: FastAPI
- Database: Supabase Postgres
- Auth: Supabase Auth
- Storage: Supabase Storage
- Queue: Redis + worker
- Vector support: pgvector if enabled
- Observability: Sentry + audit logs

---

# 3. Build Phases Overview

## Phase 1 — Repo + Supabase Environment Foundation

Goal:

- create monorepo
- establish local development environment
- establish Supabase local/dev project conventions
- make project runnable locally

## Phase 2 — Auth + RBAC

Goal:

- implement Supabase Auth
- implement app roles
- protect frontend/backend routes
- establish session flow

## Phase 3 — Core Data Model + Database

Goal:

- define schema for users, applicants, employers, jobs, matches, extracted fields, audit logs, configs

## Phase 4 — Imports + ETL + Normalization

Goal:

- import applicants/jobs
- normalize taxonomy, geography, program/job families
- preserve raw source text

## Phase 5 — Matching Engine v1

Goal:

- implement hard gates
- structured scoring
- semantic support inputs
- policy reranking

## Phase 6 — Applicant and Employer Product Surfaces

Goal:

- applicant ranked jobs
- employer ranked applicants per job
- explanations and missing requirements

## Phase 7 — LLM Extraction + Verification

Goal:

- add structured extraction
- add ambiguity review/judge
- store confidences

## Phase 8 — Applicant Planning Chat

Goal:

- grounded chat using applicant profile + ranked matches + gaps + geography

## Phase 9 — Admin Review + Config + Analytics

Goal:

- review queue
- scoring/policy config display
- audit logs
- analytics views

## Phase 10 — Quality Assurance + End-to-End Testing

Goal:

- verify all systems locally and in staging

## Phase 11 — Deployment + Production Readiness

Goal:

- deploy safely
- migrate database
- verify observability and rollback plan

---

# 4. Detailed Build Steps

## Phase 1 — Repo + Supabase Environment Foundation

### Step 1.1 — Create monorepo skeleton

Build:

- workspace root
- `apps/web`
- `apps/api`
- `packages/ui`
- `packages/types`
- `packages/matching`
- `packages/etl`
- `docs`
- `scripts`
- `infra`

Artifacts:

- workspace config
- root package manager config
- README
- `.env.example`

Completion criteria:

- repo installs cleanly
- web and api directories exist
- root scripts run

Next step:

- local Supabase bootstrapping

---

### Step 1.2 — Local Supabase bootstrapping

Build:

- local Supabase setup via Supabase CLI
- local environment variables
- Redis local setup
- FastAPI + Next.js run commands

Completion criteria:

- local Supabase runs
- local Postgres inside Supabase stack is available
- local auth endpoints work
- local storage bucket config is defined
- local Redis runs
- API boots
- Web boots

Next step:

- config and secret conventions

---

### Step 1.3 — Config and secret conventions

Build:

- `.env.example`
- environment variable schema validation
- separate env conventions for:
  - local
  - test
  - staging
  - production

Include:

- Supabase URL
- Supabase anon key
- Supabase service role key
- Redis URL
- LLM API key(s)
- Sentry config
- app JWT settings if needed

Completion criteria:

- app fails clearly if required config is missing
- environment keys are documented

Next step:

- auth

---

## Phase 2 — Auth + RBAC

### Step 2.1 — Supabase Auth integration

Build:

- login/logout
- password reset
- applicant self-signup
- employer/admin invite flows
- session propagation from web to api

Completion criteria:

- all 3 roles can authenticate with Supabase Auth
- sessions work in web + api

Next step:

- RBAC

---

### Step 2.2 — Role-based authorization

Build:

- role model in app DB tables
- route protection in Next.js
- backend JWT validation against Supabase JWTs
- RBAC middleware in FastAPI

Completion criteria:

- applicant cannot access employer/admin pages
- employer cannot access admin pages
- admin can access admin tools
- unauthorized API calls are blocked

Next step:

- core DB schema

---

## Phase 3 — Core Data Model + Database

### Step 3.1 — Create database schema

Define tables for at minimum:

- users
- applicants
- employers
- employer_contacts
- jobs
- applicant_documents
- extracted_applicant_signals
- extracted_job_signals
- matches
- saved_jobs / interest actions
- audit_logs
- policy_configs
- import_runs
- review_queue_items
- chat_sessions / chat_messages

Use Supabase migrations / SQL migration flow.

Completion criteria:

- migrations run successfully in local Supabase
- schema matches `CLAUDE.md` and `DECISIONS.md`

Next step:

- seed base data

---

### Step 3.2 — Seed baseline taxonomy/config

Build:

- canonical job family taxonomy
- career pathway taxonomy
- geography region structure
- default policy/scoring config from `SCORING_CONFIG.yaml`

Completion criteria:

- initial taxonomy and config can be loaded into Supabase Postgres
- matching engine can read live config from DB or config layer

Next step:

- import/ETL

---

## Phase 4 — Imports + ETL + Normalization

### Step 4.1 — Applicant import pipeline

Build:

- spreadsheet/CSV ingestion
- raw row preservation
- mapping to applicant schema
- import status + errors table

Completion criteria:

- applicant import works on sample data
- invalid rows are surfaced cleanly
- raw text is preserved

Important:

- test this early with the real SkillPointe sample applicant file

Next step:

- job import pipeline

---

### Step 4.2 — Job import pipeline

Build:

- job CSV/XLSX ingestion
- raw row preservation
- mapping to job schema
- import status + errors table

Completion criteria:

- job import works on sample data
- malformed fields are surfaced cleanly

Important:

- test this early with the real jobs CSV/XLSX

Next step:

- normalization

---

### Step 4.3 — Normalization layer

Build deterministic normalization for:

- job families
- program/career pathways
- geography
- pay ranges
- dates/timing
- explicit credentials
- work setting

Completion criteria:

- normalized values stored separately from raw source text
- ambiguous mappings can be flagged for review

Important:

- inspect normalization quality before polishing UI

Next step:

- hard-gate engine

---

## Phase 5 — Matching Engine v1

### Step 5.1 — Hard eligibility gates

Implement:

- job family compatibility
- credential compatibility
- timing/readiness compatibility
- geography feasibility
- explicit minimum requirement compatibility

Outputs:

- eligible
- near_fit
- ineligible
- gate rationales
- review flag if ambiguous

Completion criteria:

- deterministic classification works on sample applicant-job pairs

Next step:

- structured scoring

---

### Step 5.2 — Structured scoring engine

Implement exact weights and rubrics from `SCORING_CONFIG.yaml`.

Outputs:

- dimension-level scores
- weighted structured score
- rationale inputs

Completion criteria:

- score breakdown is inspectable
- null handling follows config

Next step:

- semantic score support

---

### Step 5.3 — Semantic support scoring

Implement:

- embeddings or placeholder semantic scoring pipeline
- semantic score components
- combined base fit score formula

Completion criteria:

- base fit score computed correctly
- hard gate cap applied correctly

Next step:

- policy reranking

---

### Step 5.4 — Policy reranking engine

Implement:

- partner preference
- funded pathway alignment
- geography preference
- readiness preference
- opportunity upside
- missing critical requirement penalties

Outputs:

- policy modifier breakdown
- policy adjusted score

Completion criteria:

- base fit remains distinct from policy-adjusted fit
- reranking follows config
- tie-break rules implemented

Important:

- after this step, run recomputation against real imported applicant and job data
- inspect top 10 matches for a few applicants and jobs early

Next step:

- explanation and product views

---

## Phase 6 — Applicant and Employer Product Surfaces

### Step 6.1 — Applicant dashboard and ranked jobs

Build:

- applicant dashboard
- ranked jobs list
- labels for:
  - best immediate opportunities
  - promising near-fit opportunities
- detailed match card

Completion criteria:

- applicant can log in and see ranked jobs
- near-fit jobs are labeled correctly
- geography and missing requirements are visible

Next step:

- employer views

---

### Step 6.2 — Employer dashboard and ranked applicants per job

Build:

- employer dashboard
- jobs list
- ranked applicants for each job
- applicant fit explanation panels
- filters

Completion criteria:

- employer can log in and see applicants ranked for their own jobs only
- job-scoped visibility enforced

Next step:

- explanation generation

---

### Step 6.3 — Explanation surfaces

Build:

- match explanation UI
- top strengths
- top gaps
- mandatory vs improvable items
- next-step recommendation

Completion criteria:

- explanation is grounded in computed data
- no opaque “magic score only” views remain

Next step:

- LLM extraction

---

## Phase 7 — LLM Extraction + Verification

### Step 7.1 — Applicant extraction

Implement prompt-driven extraction for:

- essays
- internships
- extracurriculars
- resumes

Store:

- extracted skills
- certifications
- desired job families
- work-style signals
- experience signals
- readiness signals
- confidence
- evidence spans/snippets if possible

Completion criteria:

- structured JSON stored successfully
- low-confidence outputs flagged

Next step:

- job extraction

---

### Step 7.2 — Job extraction

Implement prompt-driven extraction for:

- required/preferred qualifications
- responsibilities
- pre-employment requirements

Store:

- job family
- required/preferred skills
- required/preferred credentials
- experience level
- travel requirements
- work setting
- physical requirements
- confidence

Completion criteria:

- structured JSON stored successfully
- confidence tracked

Next step:

- verifier/judge layer

---

### Step 7.3 — Ambiguity verifier / judge layer

Implement LLM verifier for:

- ambiguous extractions
- borderline classifications
- taxonomy mismatches
- weak evidence situations

Completion criteria:

- verifier returns structured verdict
- human review recommendations are stored
- verifier does not override auditability

Next step:

- applicant chat

---

## Phase 8 — Applicant Planning Chat

### Step 8.1 — Grounded retrieval context

Build retrieval context from:

- applicant profile
- ranked jobs
- near-fit jobs
- missing requirements
- geography
- extracted signals

Completion criteria:

- chat context is grounded and inspectable

Next step:

- chat UI and response layer

---

### Step 8.2 — Applicant planning chat UI

Build:

- chat interface
- prompt orchestration
- response rendering
- disclaimers/guardrails

Completion criteria:

- applicant can ask practical questions
- responses stay grounded
- chat does not invent jobs or take autonomous actions

Next step:

- admin review tooling

---

## Phase 9 — Admin Review + Config + Analytics

### Step 9.1 — Review queue

Build:

- queue for low-confidence extraction
- queue for ambiguous matches
- queue for suspicious imports or taxonomy issues

Completion criteria:

- admin can review and resolve flagged items
- actions are logged

Next step:

- policy/config visibility

---

### Step 9.2 — Policy/config views

Build:

- admin view of current policy/scoring config
- ability to inspect active version
- optionally edit via controlled UI later

Completion criteria:

- admin can see what rules drive ranking
- changes are auditable

Next step:

- analytics

---

### Step 9.3 — Analytics and audit views

Build:

- import success/failure metrics
- match volume metrics
- confidence distribution
- review queue counts
- audit log views

Completion criteria:

- admin can inspect system health and actions

Next step:

- QA

---

## Phase 10 — Quality Assurance + End-to-End Testing

### Step 10.1 — Unit tests

Write tests for:

- normalization logic
- hard eligibility gates
- structured scoring
- policy reranking
- null handling
- authorization middleware
- import parsing
- config loading

Completion criteria:

- critical deterministic logic has solid unit coverage

Next step:

- integration tests

---

### Step 10.2 — Integration tests

Write tests for:

- auth flows
- applicant import flow
- job import flow
- match generation pipeline
- employer-only job-scoped candidate visibility
- applicant ranked jobs view
- explanation generation pipeline
- admin review resolution flow
- Supabase auth token validation in backend
- Supabase storage upload flow if relevant

Completion criteria:

- core flows work across services/modules

Next step:

- end-to-end tests

---

### Step 10.3 — End-to-end tests

Create E2E tests for the main journeys:

#### Applicant journey

- sign up / log in
- upload profile/resume
- set geography
- see ranked jobs
- inspect near-fit explanations
- use planning chat

#### Employer journey

- log in
- create/edit job
- see ranked applicants
- inspect rationale

#### Admin journey

- log in
- import data
- review flagged extractions
- inspect policy config
- inspect audit logs

Completion criteria:

- all major user journeys pass in staging-like environment

Next step:

- staging deployment

---

## Phase 11 — Deployment + Production Readiness

### Step 11.1 — Staging deployment

Deploy:

- web app
- API
- Supabase staging project
- Redis
- auth config
- storage buckets/policies
- environment variables
- migrations

Completion criteria:

- staging environment fully boots
- smoke tests pass

Next step:

- production hardening

---

### Step 11.2 — Production readiness checks

Verify:

- migrations safe
- rollback plan exists
- secrets set correctly
- audit logging enabled
- error monitoring enabled
- rate limiting where needed
- backups enabled
- background jobs stable
- Supabase RLS / access patterns are correct if used

Completion criteria:

- production checklist completed

Next step:

- production deploy

---

### Step 11.3 — Production deploy

Deploy production and run:

- DB migrations
- smoke tests
- login tests
- sample ranking validation
- import validation
- review queue validation

Completion criteria:

- production usable by all 3 roles
- core ranking flows verified

---

# 5. How Claude Must Report Progress

At the start of every work session, Claude must report:

- `Current Phase`
- `Current Step`
- `What exists already`
- `What this task will change`
- `What must be tested after this task`
- `Next Step`

---

# 6. Local Development Workflow

## Expected local stack

Run locally:

- Next.js frontend
- FastAPI backend
- local Supabase via Supabase CLI
- Redis
- optional local vector support in Supabase Postgres
- optional file uploads via local Supabase Storage config

## Normal local development sequence

1. start local Supabase
2. start Redis
3. run DB migrations
4. seed taxonomy/config
5. run API
6. run frontend
7. import real sample applicant/job data early
8. run recompute script
9. inspect ranked results
10. run tests
11. iterate

Important:

- do not wait for polished UI before testing ranking quality

---

# 7. Early Data / Ranking Validation Rule

As soon as these exist:

- schema
- import scripts
- normalization
- hard gates
- structured scoring

You must:

1. import the real SkillPointe sample applicant file
2. import the real jobs file
3. run match recomputation
4. inspect top results via CLI, CSV export, or simple admin/debug view

This happens **before** polished dashboards.

Use scripts like:

- `scripts/import_applicants.py`
- `scripts/import_jobs.py`
- `scripts/normalize_data.py`
- `scripts/recompute_matches.py`
- `scripts/inspect_matches.py`

---

# 8. Testing Strategy

## Unit tests

For pure deterministic logic:

- normalization
- gating
- scoring
- reranking
- null handling
- config parsing

## Integration tests

For service interactions:

- imports
- auth
- DB writes
- extraction pipelines
- review queue logic
- policy reads
- Supabase auth token validation
- Supabase storage integration where applicable

## E2E tests

For full user journeys:

- applicant
- employer
- admin

## Manual QA checks

Use staging to manually verify:

- role permissions
- explanation honesty
- geography behavior
- low-confidence review handling
- audit logs
- chat grounding
- Supabase auth/session behavior

---

# 9. Deployment Strategy

## Recommended environments

Maintain:

- local
- test/CI
- staging
- production

## Recommended deployment split

- frontend -> Vercel
- backend -> Railway / Render / Fly / ECS / similar
- database -> Supabase project
- auth -> Supabase Auth
- storage -> Supabase Storage
- Redis -> Upstash Redis / managed Redis

## Deployment order

1. create/provision Supabase project
2. configure auth + storage
3. provision Redis
4. run migrations
5. deploy API
6. deploy frontend
7. verify auth callbacks
8. seed baseline taxonomy/config
9. run smoke tests
10. run E2E smoke flows

---

# 10. Definition of Done

The project is “done for MVP” when all of the following are true:

## Applicant side

- applicant can sign up/log in
- applicant can complete profile and upload resume
- applicant can set geography preferences
- applicant can see ranked jobs
- applicant can see missing requirements
- applicant can use grounded planning chat

## Employer side

- employer can log in
- employer can create/manage jobs
- employer can see ranked applicants per job
- employer can see rationale and geography context

## Admin side

- admin can log in
- admin can import applicants/jobs
- admin can review low-confidence extraction/matching cases
- admin can inspect scoring/policy config
- admin can inspect audit logs and analytics

## System behavior

- deterministic scoring works
- policy reranking works
- geography is first-class
- LLMs are supportive only
- role visibility is safe
- low-confidence items are reviewable
- audit logs exist
- staging and production deploys are reproducible
- Supabase auth/data/storage flows work correctly

---

# 11. Final Rule

When in doubt:

- choose the simpler deterministic implementation
- preserve auditability
- prefer explicitness over cleverness
- do not jump ahead of the current phase
- always state where you are in the plan and what comes next
- test real imports and ranking earlier than feels comfortable
