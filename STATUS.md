# STATUS.md — SkillPointe Match Build Handoff

> Last updated: 2026-03-26
>
> For: teammates picking up where development left off.
> Read this alongside `CLAUDE.md` (product rules) and `BUILD_PLAN.md` (execution plan).

---

## What this project is

Three-role workforce matching platform:
- **Applicants** see ranked job matches, score explanations, interest signals, and a career planning chat
- **Employers** see ranked matched candidates per job, can reach out with AI-drafted messages, report hire outcomes, and view engagement analytics
- **Admins** manage imports, browse all applicants/employers, view analytics dashboards and a geography map

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
| 6.4 | Admin applicant/employer directories + employer detail page + map | ✅ Complete |
| 7 | LLM extraction + verification + job scraper | ✅ Complete |
| 8 | Engagement features: interest signals, outreach, hire outcomes, planning chat, auto-recompute | ✅ Complete |
| 9 | Admin review queue + policy config UI | ⬜ Not started |
| 10 | QA + end-to-end testing | ⬜ Not started |
| 11 | Deployment + production readiness | ⬜ Not started |

**Where we are:** Phases 1–8 are complete. The platform now supports the full candidate engagement loop: match → signal interest → employer reaches out → hire outcome reported. Planning chat is live for applicants. Matches recompute automatically every 6 hours and on job creation / profile update.

---

## Getting set up (new developer)

### 1. Prerequisites

- [Node.js 20+](https://nodejs.org) + [pnpm](https://pnpm.io/installation)
- [Python 3.11+](https://python.org)
- [Supabase CLI](https://supabase.com/docs/guides/cli): `brew install supabase/tap/supabase`
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### 2. Clone and install

```bash
git clone <repo-url>
cd skillpointe

pnpm install

cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../..
```

### 3. Start local services

```bash
supabase start
supabase db reset          # applies all 14 migrations + seed
docker compose -f infra/docker-compose.local.yml up -d   # Redis
```

### 4. Configure environment variables

```bash
supabase status            # get local keys
```

**`apps/api/.env`:**
```env
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<from supabase status>
SUPABASE_SERVICE_ROLE_KEY=<from supabase status>
SUPABASE_JWT_SECRET=<from supabase status>
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=<optional — required for AI outreach drafts and planning chat>
```

**`apps/web/.env.local`:**
```env
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from supabase status>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 5. Seed test users

```bash
cd apps/api && source .venv/bin/activate && cd ../..
python scripts/seed_test_users.py
```

| Role | Email | Password | Goes to |
|---|---|---|---|
| Applicant | `applicant@skillpointe.test` | `Test1234!` | `/applicant` |
| Employer | `employer@skillpointe.test` | `Test1234!` | `/employer` |
| Admin | `admin@skillpointe.test` | `Test1234!` | `/admin` |

### 6. Start the app

```bash
# Terminal 1 — API (hot reload)
cd apps/api && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend (from repo root)
pnpm dev:web
```

Open `http://localhost:3000`. The API schedule starts automatically on `uvicorn` launch.

---

## What was built — detailed breakdown

### Phase 1 — Repo + Environment

- Monorepo: `apps/web`, `apps/api`, `packages/{etl,matching,extraction,types,ui}`, `scripts/`, `infra/`
- Supabase CLI local config + Docker Compose for Redis
- Service ports: Next.js :3000, FastAPI :8000, Supabase :54321, Postgres :54322, Studio :54323, Redis :6379

---

### Phase 2 — Auth + RBAC

**Backend:**
- JWT validation (HS256 + ES256 both supported — Supabase CLI v2 uses ES256 via JWKS)
- RBAC dependency functions: `require_admin`, `require_applicant`, `require_employer`, `require_employer_or_admin`
- `GET /auth/me`, `POST /auth/complete-signup`, `POST /auth/invite-employer`

**Frontend:**
- Supabase client helpers: `lib/supabase/client.ts`, `lib/supabase/server.ts`
- Route protection: `middleware.ts`
- Auth pages: login, signup, forgot/reset password

**Tests:** `tests/test_auth.py` (13 tests)

> **Note:** Supabase CLI v2 signs JWTs with ES256. The decoder reads the JWT header and fetches JWKS automatically. Do not revert to HS256-only.

---

### Phase 3 — Core Data Model

**14 SQL migrations** in `supabase/migrations/`:

| Migration | Tables |
|-----------|--------|
| 000000 | `user_profiles` |
| 000001 | enums + pgvector extension |
| 000002 | `canonical_job_families`, `geography_regions` |
| 000003 | `applicants`, `employers`, `employer_contacts`, `jobs` |
| 000004 | `applicant_documents`, `extracted_fields` (documents + signals) |
| 000005 | `matches`, `match_dimension_scores`, `saved_jobs` |
| 000006 | `policy_configs`, `scoring_runs`, `audit_logs`, `review_queue_items` |
| 000007 | `chat_sessions`, `chat_messages` |
| 000008 | `import_runs`, `import_rows` |
| 000009 | expanded applicant profile columns |
| 000010 | scraped jobs support (`source_site`, `source_url`, etc.) |
| 000011 | `employer_outreach` |
| 000012 | `engagement_events` |
| 000013 | `hire_outcomes` |

**Seed data** (`supabase/seed.sql`): 15 canonical job families, 5 geography regions, `policy_config v1`.

---

### Phase 4 — ETL Import Pipeline

**`packages/etl/`:** loader, applicant_mapper, job_mapper, coerce, models, db, reporting

**Scripts:**
- `import_applicants.py` — XLSX/CSV → `applicants` table
- `import_jobs.py` — XLSX/CSV → `jobs` table
- `normalize_data.py` — program names → canonical job families, pay parsing, region resolution

**Tests:** `tests/test_etl_import.py` (79 tests)

---

### Phase 5 — Matching Engine

**`packages/matching/`:**

| File | What it does |
|------|-------------|
| `config.py` | Loads `SCORING_CONFIG.yaml` → `ScoringConfig` |
| `normalizer.py` | Normalization functions + `JOB_FAMILY_ADJACENCY` map |
| `gates.py` | 5 hard eligibility gates (job family, credentials, timing, geography, min requirements) |
| `scorer.py` | 9 structured scoring dimensions |
| `engine.py` | `compute_match()` orchestrator — gates → structured score → semantic score → policy reranking |

**Three-stage pipeline:**
1. Hard gates → `eligibility_status` + `hard_gate_cap` (1.0 / 0.75 / 0.35)
2. Base fit → `gate_cap × (structured × 0.75 + semantic × 0.25)`
3. Policy reranking → partner/geography/readiness modifiers → `policy_adjusted_score`

**Tests:** `tests/test_matching.py` (122 tests, no DB required)

---

### Phase 6.1 — Applicant Dashboard + Ranked Matches

**API endpoints:**
- `GET /applicant/me/profile` — profile summary
- `PATCH /applicant/me/profile` — partial update (auto-normalizes program → job family, state → region)
- `GET /applicant/me/matches` — ranked jobs (eligible + near-fit sections, policy_adjusted_score DESC)
- `GET /applicant/me/matches/{match_id}` — full match detail (dimensions, gates, policy modifiers)
- `GET /applicant/me/matches/{match_id}/interest` — get interest signal *(Phase 8)*
- `POST /applicant/me/matches/{match_id}/interest` — set signal (interested/applied/not_interested) *(Phase 8)*

**Frontend pages:**
- `/applicant` — profile summary dashboard
- `/applicant/matches` — ranked job list (eligible + near-fit sections)
- `/applicant/matches/[matchId]` — full match detail (strengths, gaps, gates, dimension bars, score transparency, **interest panel**, apply link)
- `/applicant/profile` — edit profile form
- `/applicant/jobs` — browse all jobs

**Key components:**
- `components/matches/JobMatchCard.tsx` — match summary card
- `components/matches/MatchLabel.tsx` — eligibility + quality badges
- `components/matches/DimensionBreakdown.tsx` — 9-dimension score bars
- `components/matches/InterestSignalPanel.tsx` — interest signal buttons + "Apply externally" link *(Phase 8)*

---

### Phase 6.2 — Employer Dashboard + Job Management

**API endpoints:**
- `GET /employer/me/company` — company summary
- `GET /employer/me/jobs` — job list with per-job match stats
- `POST /employer/me/jobs` — create job (triggers fire-and-forget recompute)
- `PATCH /employer/me/jobs/{job_id}` — update job fields
- `GET /employer/me/jobs/{job_id}/applicants` — ranked matched candidates (filterable by eligibility, min score, state, relocate)
- `POST /employer/me/outreach/draft` — AI-draft outreach message *(Phase 8)*
- `POST /employer/me/outreach/send` — record sent outreach *(Phase 8)*
- `POST /employer/me/jobs/{job_id}/candidates/{applicant_id}/hire` — report hire outcome *(Phase 8)*
- `GET /employer/me/analytics` — outreach + interest + hire metrics *(Phase 8)*

**Critical safety rules in SQL:**
- Every query resolves `employer_id` via `employer_contacts` — cross-employer access is impossible
- All match queries require `is_visible_to_employer = TRUE`
- Admin role bypasses employer scoping for support purposes

**Frontend pages:**
- `/employer` — company summary, active/total jobs, jobs list with match counts
- `/employer/jobs/new` — create job form (server action)
- `/employer/jobs/[jobId]/edit` — edit job form (server action)
- `/employer/jobs/[jobId]/applicants` — ranked matched candidates with filter bar, "Reach out" and "Mark as hired" buttons
- `/employer/analytics` — outreach count, interested/applied/hired stats, recent outreach history *(Phase 8)*

**Key components:**
- `components/employer/ApplicantMatchCard.tsx` — candidate card (name, program, location, mobility, score, strengths/gaps)
- `components/employer/CandidateActions.tsx` — "Reach out" + "Mark as hired" client buttons *(Phase 8)*
- `components/employer/OutreachModal.tsx` — AI draft + edit + mark-as-sent modal *(Phase 8)*

---

### Phase 6.3 — Match Explanation Surfaces

Built within 6.1 and 6.2:
- Full 9-dimension score breakdown with per-dimension score, weight, and contribution bar
- Hard gate results (pass/near_fit/fail per gate, with reason text)
- Policy modifier breakdown (partner bonus, geography boost, readiness boost, penalties)
- `top_strengths`, `top_gaps`, `required_missing_items`, `recommended_next_step` on every match
- Geography note derived from job work_setting + applicant location + preferences
- Confidence level and review status flags

---

### Phase 6.4 — Admin Directories + Map

**API endpoints:**
- `GET /admin/applicants` — list all applicants (filter: name/email, state, job_family; paged 50/page)
- `GET /admin/employers` — list all employers (filter: name, state, is_partner; paged 50/page)
- `GET /admin/employers/{employer_id}` — employer detail (jobs, counts, contact info)
- `GET /admin/analytics/dashboard` — overview stats + jobs by family/source/state + match quality
- `GET /admin/analytics/job-map` — city-level job clusters for map view
- `GET /admin/analytics/cluster-jobs` — drill-down jobs for a map cluster

**Frontend pages:**
- `/admin` — analytics dashboard (overview stats, charts, data quality metrics)
- `/admin/map` — interactive Leaflet.js map of job clusters (click cluster → job list drill-down)
- `/admin/applicants` — applicant directory with search, state, and job family filters; shows match counts + profile completeness badge + contact email
- `/admin/employers` — employer directory with search, state, partner filter; clickable employer names
- `/admin/employers/[employerId]` — employer detail (company info, description, partner since, active/archived jobs with match counts)

**Notes:**
- Terminology: the employer-facing view calls matched candidates "matched candidates" (not "applicants") since they haven't necessarily applied yet
- Admin can view any job's matched candidates via `/employer/jobs/[jobId]/applicants` (employer scoping bypassed for admin role)

---

### Phase 7 — LLM Extraction + Verification + Job Scraper

**`packages/extraction/`:**
- `applicant_extractor.py` — extracts skills, certs, desired families, work style, readiness from profile text
- `job_extractor.py` — extracts required/preferred skills, credentials, job family, experience level, physical requirements
- `embeddings.py` — generates `text-embedding-3-small` embeddings (1536-dim) for semantic scoring
- `verifier.py` — heuristic + LLM verification, flags low-confidence items for `review_queue_items`

**`packages/scraper/`:** adapters for Southwire, Ford, GE Vernova, Ball, Delta, Schneider

**Matching engine upgrades (all backward-compatible):**
- Credential gate uses extracted cert match ratio
- Min-requirement gate uses extracted skill match ratio
- Semantic score uses real cosine similarity on embeddings (was hardcoded 50.0)
- Experience and employer soft-pref scorers use extracted signals

**Scripts:**
- `run_extraction.py` — processes all applicants + jobs through LLM extraction + embeddings
- `recompute_matches.py` — full recompute using extracted signals when available

---

### Phase 8 — Engagement + Planning Chat

Everything here was added on top of Phases 1–7. Three new DB tables, new API endpoints, and new frontend surfaces.

#### Feature 1 — Automatic Match Recompute

- **`apps/api/app/worker/scheduler.py`** — APScheduler `AsyncIOScheduler` fires `recompute_matches.py` as a subprocess every 6 hours, guarded by a Redis distributed lock (`skillpointe:recompute_lock`) so only one instance runs at a time
- **`apps/api/app/main.py`** — lifespan context manager starts/stops the scheduler on app startup/shutdown
- **Job creation** (`POST /employer/me/jobs`) fires `trigger_recompute_for_job(job_id)` as a background task
- **Profile updates** (`PATCH /applicant/me/profile`) fires `trigger_recompute_for_applicant(applicant_id)` when significant fields change (state, program, job family, relocate)

#### Feature 2 — Interest Signals + Apply Link

- `saved_jobs` table (existing, migration 005) stores `interest_level`: `interested` | `applied` | `not_interested`
- `GET /applicant/me/matches/{match_id}/interest` — fetch current signal
- `POST /applicant/me/matches/{match_id}/interest` — upsert signal; logs `engagement_events` row
- **`InterestSignalPanel.tsx`** — client component shown on match detail page; three-button selector + "Apply externally" link (opens `source_url` in new tab, auto-sets signal to "applied")

#### Features 3 & 4 — Employer Outreach + AI Draft

- **`employer_outreach`** table (migration 011): employer_id, job_id, applicant_id, match_id, subject, body, ai_generated, status, sent_at
- `POST /employer/me/outreach/draft` — generates AI draft via `services/chat.py:generate_outreach_draft()` (OpenAI gpt-4o-mini, JSON response_format)
- `POST /employer/me/outreach/send` — records sent outreach + logs `engagement_events` row
- **`OutreachModal.tsx`** — modal dialog: AI draft button, editable subject/body, "Mark as sent" button, success state
- **`CandidateActions.tsx`** — client component rendered in every `ApplicantMatchCard`; houses "Reach out" and "Mark as hired" buttons

#### Feature 5 — Engagement Event Tracking

- **`engagement_events`** table (migration 012): applicant_id, employer_id, job_id, match_id, event_type, event_data, created_at
- Event types logged: `interest_set`, `apply_click`, `outreach_sent`, `hire_reported`, `chat_message_sent`
- All engagement-modifying endpoints write an event row (no separate event API needed)

#### Feature 6 — Hire Outcome Reporting + Employer Analytics

- **`hire_outcomes`** table (migration 013): applicant_id, job_id, employer_id, match_id, outcome_type (hired/declined/withdrew), hire_date, notes, reported_by
- UNIQUE constraint on (applicant_id, job_id) — upsert semantics (re-reporting updates in place)
- `POST /employer/me/jobs/{job_id}/candidates/{applicant_id}/hire` — report outcome + log engagement event
- `GET /employer/me/analytics` — returns: outreach_sent, candidates_interested, candidates_applied, hired_count, declined_count, recent_outreach (last 10)
- **`/employer/analytics`** page — stat cards + recent outreach history

#### Feature 7 — Applicant Planning Chat

- `chat_sessions` + `chat_messages` tables already existed (migration 007); now fully implemented
- Context snapshot built at session creation from applicant's top 5 matches (scores, strengths, gaps, next steps)
- LLM grounded in context snapshot — cannot fabricate matches; stays within provided data
- `GET  /applicant/me/chat/sessions` — list sessions (most recent first)
- `POST /applicant/me/chat/sessions` — create session; optional `job_id` makes it job-focused (builds targeted snapshot + generates an AI opening message about that specific job)
- `GET  /applicant/me/chat/sessions/{id}` — session + full message history
- `POST /applicant/me/chat/sessions/{id}/messages` — send user message, get AI reply (gpt-4o-mini)
- **`/applicant/chat`** — session list page; shows **ChatJobPicker** modal before session creation (pick from eligible matches, near-fit matches, or search all jobs) then starts a job-focused chat
- **`/applicant/chat/[sessionId]`** — session page (server-rendered history + client chat input)
- **`ChatClient.tsx`** — client component: message bubbles, optimistic UI, Enter to send
- **`ChatJobPicker.tsx`** — modal: two tabs ("Your matches" filtered by eligibility; "Browse all jobs" debounced search)
- **`apps/api/app/services/chat.py`** — `generate_chat_response()`, `generate_outreach_draft()`, `_build_job_focused_snapshot()`, `_generate_opening_message()`
- "Plan" nav link added for applicants

#### Feature 8 — Direct Messaging (Applicant ↔ Employer)

- New migration `20260326000014_conversations.sql` adds `conversations` + `direct_messages` tables
- `conversations`: applicant_id, employer_id, job_id, match_id, last_message_at, employer_unread, applicant_unread
- `direct_messages`: conversation_id, sender_role (employer|applicant), content, read_at
- `GET /conversations`, `POST /conversations` — list and create conversations (role-aware)
- `GET /conversations/{id}/messages`, `POST /conversations/{id}/messages` — thread read/write
- `POST /conversations/{id}/read` — mark messages read (resets unread count for caller's role)
- All DM sends log `dm_sent` to `engagement_events`
- **`/applicant/messages`** + **`/applicant/messages/[conversationId]`** — applicant inbox + thread
- **`/employer/messages`** + **`/employer/messages/[conversationId]`** — employer inbox + thread
- **`MessageThread.tsx`** — client component with 5-second polling (no WebSockets — simpler for MVP)
- "Message" button added to `CandidateActions.tsx` — creates or opens conversation thread
- "Messages" nav link added for both applicant and employer dashboards

#### Feature 9 — AI Candidate Prioritisation

- `GET /employer/me/jobs/{job_id}/applicants/ai-priority` — fetches top 10 eligible/near-fit candidates ranked by score, then calls gpt-4o-mini to write a 1-sentence reason per candidate; falls back to score-based order when `OPENAI_API_KEY` is absent
- Response includes `match_id` (needed for action buttons)
- **`AIPriorityPanel.tsx`** — collapsible panel above the filter bar; lazy-loads on first click; shows ranked list with "Top pick" badge, score, eligibility, AI reason, and full action buttons (Reach out, Message, Mark as hired) per row
- Admin viewing employer pages sees the panel in read-only mode (action buttons hidden via `isAdmin` prop)

#### Feature 10 — Admin Engagement Analytics Dashboard

- `GET /admin/analytics/engagement` — platform-wide counts: total events, DMs, outreach, interest signals, apply clicks, hires, active conversations
- `GET /admin/analytics/engagement/applicants` — per-applicant breakdown: interest_signals, apply_clicks, chat_messages, dms_sent, total_events (sortable)
- `GET /admin/analytics/engagement/employers` — per-employer breakdown: outreach_sent, dms_sent, hires_reported, candidates_viewed, total_actions (sortable)
- **`/admin/engagement`** — three URL-driven tab views (`?view=general|applicants|employers`); server-rendered, bookmarkable
- "Engagement" nav link added to admin dashboard

#### Feature 11 — Interest Signals on Matches List

- `GET /applicant/me/matches` now LEFT JOINs `saved_jobs` and returns `applicant_interest` per match
- `InterestSignalPanel` is now rendered inline on every match card in the matches list (not just the detail page)
- For jobs with `source_url`: shows "Interested / Applied externally / Not interested" + external apply button
- For jobs without `source_url`: shows "Planning to apply / I've applied / Not interested" with clipboard header
- `applicant_interest` also returned by employer's ranked applicants endpoint and shown as a badge on `ApplicantMatchCard`

---

## API routes reference

### Applicant

| Method | Path | Description |
|--------|------|-------------|
| GET | `/applicant/me/profile` | Profile summary |
| PATCH | `/applicant/me/profile` | Partial profile update + auto-normalize |
| GET | `/applicant/me/matches` | Ranked job matches |
| GET | `/applicant/me/matches/{id}` | Full match detail + dimensions |
| GET | `/applicant/me/matches/{id}/interest` | Get interest signal |
| POST | `/applicant/me/matches/{id}/interest` | Set interest signal |
| GET | `/applicant/me/chat/sessions` | List chat sessions |
| POST | `/applicant/me/chat/sessions` | Start new chat session |
| GET | `/applicant/me/chat/sessions/{id}` | Session + messages |
| POST | `/applicant/me/chat/sessions/{id}/messages` | Send message, get AI reply |

### Employer

| Method | Path | Description |
|--------|------|-------------|
| GET | `/employer/me/company` | Company summary |
| GET | `/employer/me/jobs` | Job list + match counts |
| POST | `/employer/me/jobs` | Create job (triggers recompute) |
| PATCH | `/employer/me/jobs/{id}` | Update job |
| GET | `/employer/me/jobs/{id}/applicants` | Ranked matched candidates (filtered) |
| GET | `/employer/me/jobs/{id}/applicants/ai-priority` | AI-ranked top 10 with 1-sentence reasons |
| POST | `/employer/me/outreach/draft` | AI-draft outreach message |
| POST | `/employer/me/outreach/send` | Record sent outreach |
| POST | `/employer/me/jobs/{jid}/candidates/{aid}/hire` | Report hire outcome |
| GET | `/employer/me/analytics` | Engagement + hire analytics |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/applicants` | All applicants (search + filter) |
| GET | `/admin/employers` | All employers (search + filter) |
| GET | `/admin/employers/{id}` | Employer detail + jobs |
| GET | `/admin/analytics/dashboard` | Full analytics dashboard data |
| GET | `/admin/analytics/job-map` | City-level job clusters |
| GET | `/admin/analytics/cluster-jobs` | Jobs in a map cluster |
| GET | `/admin/analytics/engagement` | Platform-wide engagement stats |
| GET | `/admin/analytics/engagement/applicants` | Per-applicant engagement breakdown |
| GET | `/admin/analytics/engagement/employers` | Per-employer engagement breakdown |

### Messaging (Both Roles)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/conversations` | List conversations for current user |
| POST | `/conversations` | Start or retrieve conversation (applicant_id + job_id) |
| GET | `/conversations/{id}/messages` | Full message thread |
| POST | `/conversations/{id}/messages` | Send a message |
| POST | `/conversations/{id}/read` | Mark messages read (resets unread count) |

### Public

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/auth/me` | Current user info |
| POST | `/auth/complete-signup` | Complete applicant signup |
| POST | `/auth/invite-employer` | Admin: invite employer |
| GET | `/jobs/browse` | Browse all jobs (paginated, filtered) |

---

## Frontend pages reference

### Applicant
| Route | Description |
|-------|-------------|
| `/applicant` | Profile dashboard |
| `/applicant/matches` | Ranked job matches (eligible + near-fit sections) |
| `/applicant/matches/[matchId]` | Full match detail with interest panel + apply link |
| `/applicant/jobs` | Browse all jobs |
| `/applicant/profile` | Edit profile |
| `/applicant/setup` | Onboarding flow |
| `/applicant/chat` | Planning chat session list |
| `/applicant/chat/[sessionId]` | Chat conversation |

### Employer
| Route | Description |
|-------|-------------|
| `/employer` | Company summary + jobs list |
| `/employer/jobs/new` | Create job |
| `/employer/jobs/[jobId]/edit` | Edit job |
| `/employer/jobs/[jobId]/applicants` | Ranked matched candidates + AI priority panel + outreach/hire actions |
| `/employer/analytics` | Engagement + hire analytics (outreach sent, interested, applied, hired) |
| `/employer/messages` | DM inbox |
| `/employer/messages/[conversationId]` | DM thread (5s polling) |

### Admin
| Route | Description |
|-------|-------------|
| `/admin` | Analytics dashboard |
| `/admin/map` | Job geography map (Leaflet) |
| `/admin/applicants` | Applicant directory |
| `/admin/employers` | Employer directory |
| `/admin/employers/[employerId]` | Employer detail (read-only; no employer actions) |
| `/admin/engagement` | Platform engagement analytics (3 views: general / applicants / employers) |

### Applicant (additions since Phase 6.1)
| Route | Description |
|-------|-------------|
| `/applicant/chat` | Planning chat — job picker modal → job-focused AI session |
| `/applicant/chat/[sessionId]` | Chat conversation |
| `/applicant/messages` | DM inbox |
| `/applicant/messages/[conversationId]` | DM thread (5s polling) |

---

## Key files map

```
skillpointe/
├── CLAUDE.md                       ← Product rules + guardrails (read first)
├── DECISIONS.md                    ← Architecture decision log
├── SCORING_CONFIG.yaml             ← Scoring weights + policy config
├── PROMPTS.md                      ← LLM prompt library
├── STATUS.md                       ← This file
│
├── supabase/
│   ├── migrations/                 ← 14 SQL migrations (000000–000013)
│   └── seed.sql                    ← Taxonomy + policy config v1
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── auth/               ← JWT (HS256+ES256), RBAC deps, schemas
│   │   │   ├── routers/            ← auth, health, applicants, employers, jobs, admin, chat
│   │   │   ├── schemas/            ← applicant.py, employer.py (Pydantic models)
│   │   │   ├── services/           ← chat.py (LLM context builder + response generator)
│   │   │   ├── worker/             ← scheduler.py (APScheduler 6h recompute + Redis lock)
│   │   │   ├── config.py
│   │   │   ├── db.py               ← asyncpg connection helper
│   │   │   └── main.py             ← app factory + lifespan (scheduler start/stop)
│   │   ├── tests/
│   │   │   ├── test_auth.py               (13 tests)
│   │   │   ├── test_etl_import.py         (79 tests)
│   │   │   ├── test_matching.py           (122 tests)
│   │   │   └── test_employer_visibility.py
│   │   └── requirements.txt
│   │
│   └── web/src/
│       ├── lib/
│       │   ├── supabase/            ← client.ts + server.ts
│       │   └── api/                 ← client.ts, applicant.ts, employer.ts, admin.ts
│       ├── middleware.ts             ← route protection
│       ├── components/
│       │   ├── matches/             ← JobMatchCard, MatchLabel, DimensionBreakdown, InterestSignalPanel
│       │   ├── employer/            ← ApplicantMatchCard, CandidateActions, OutreachModal, AIPriorityPanel
│       │   ├── chat/                ← ChatClient, ChatStartButton, ChatJobPicker
│       │   └── messages/            ← MessageThread (5s polling)
│       └── app/
│           ├── (auth)/              ← login, signup, forgot/reset password
│           └── (dashboard)/
│               ├── layout.tsx        ← nav bar (role-aware)
│               ├── applicant/        ← dashboard, matches, matches/[id], jobs, profile, chat/, messages/
│               ├── employer/         ← dashboard, jobs/new, jobs/[id]/edit, jobs/[id]/applicants, analytics, messages/
│               └── admin/            ← dashboard, map, applicants, employers, employers/[id], engagement/
│
├── packages/
│   ├── etl/                         ← Import + normalization (pure Python)
│   ├── matching/                    ← Matching engine (pure Python, no DB)
│   ├── extraction/                  ← LLM extraction + embeddings (pure Python)
│   └── scraper/                     ← Job scraper adapters
│
└── scripts/
    ├── import_applicants.py
    ├── import_jobs.py
    ├── normalize_data.py
    ├── run_extraction.py            ← LLM extraction + embedding generation
    ├── recompute_matches.py         ← Full match recompute
    ├── inspect_matches.py
    ├── seed_admin.py
    ├── seed_test_users.py
    ├── verify_schema.py
    └── check_connections.py
```

---

## Things to know before touching the matching engine

1. **`base_fit_score` and `policy_adjusted_score` are stored separately.** Never merge them (`DECISIONS.md 1.6`).
2. **Hard gate failures cap the score.** `ineligible` → 0.35 cap regardless of structured score (`DECISIONS.md 1.12`).
3. **Semantic score uses embedding cosine similarity** when extraction has been run; falls back to neutral (50.0) without it.
4. **Credential and min-requirement gates use extracted signals** when available; fall back to `near_fit` without them.
5. **`packages/matching/` has zero DB I/O.** All DB reads/writes happen in `scripts/` and `app/routers/`.
6. **`packages/extraction/` also has zero DB I/O.** Returns dataclasses; caller handles storage.
7. **Null handling is neutral, not punitive.** Missing data → neutral default score, never 0.
8. **Geography is first-class.** Affects hard gates, structured score, and policy reranking.

---

## Things to know before touching the engagement features

1. **`employer_outreach` records outreach intent, not actual email delivery.** There is no email-sending integration — outreach is marked as sent by the employer after they send manually.
2. **`engagement_events` is append-only.** Never update or delete rows. Add new event_type values as needed.
3. **`saved_jobs.interest_level`** is upserted — one row per (applicant, job) pair. Values: `interested`, `applied`, `not_interested`.
4. **`hire_outcomes`** is upserted on (applicant_id, job_id). Re-reporting an outcome updates in place.
5. **The scheduler uses `sys.executable`** to call `recompute_matches.py` as a subprocess, so it always uses the same Python virtualenv the API runs in.
6. **Redis lock key:** `skillpointe:recompute_lock` (2-hour TTL). If a recompute is still running when the next 6h tick fires, the second run is skipped silently.
7. **"System improves over time" is data-collection only.** `hire_outcomes` and `engagement_events` are fully populated, but there is no automated feedback loop that adjusts `SCORING_CONFIG.yaml` weights based on hire success. This is intended for Phase 9+ (admin config UI).
8. **DM system uses polling (5s interval), not WebSockets.** `MessageThread.tsx` polls `GET /conversations/{id}/messages`. Simple and reliable for MVP; upgrade to WebSockets later if needed.
9. **Admin cannot act as employer.** `CandidateActions` and AI priority action buttons are conditionally hidden via `isAdmin` prop when the page is viewed under an admin session. The employer applicants page passes `isAdmin={role === "admin"}`.
10. **`_resolve_employer_id()` in `employers.py` raises HTTP 404 for non-employer users.** Any endpoint shared between employer + admin must check `is_admin` first: `employer_id = None if is_admin else await _resolve_employer_id(conn, ...)`. Never call it unconditionally on a `require_employer_or_admin` route.
11. **Always use `get_settings()` for env vars.** `os.environ.get()` does not read `.env` files with Pydantic Settings. Use `from app.config import get_settings; get_settings().openai_api_key`.

---

## Test suite

```bash
cd apps/api
source .venv/bin/activate
pytest tests/ -v
```

- `test_auth.py` — 13 tests
- `test_etl_import.py` — 79 tests
- `test_matching.py` — 122 tests (no DB required)
- `test_employer_visibility.py` — employer scoping, visibility flags, RBAC

---

## Data pipeline (with real SkillPointe data)

Real data files are stored locally (not committed to git): ~335 applicants, ~300 jobs.

```bash
supabase db reset
python scripts/import_applicants.py data/applicants.xlsx
python scripts/import_jobs.py data/jobs.xlsx
python scripts/normalize_data.py
python scripts/run_extraction.py --verbose   # requires OPENAI_API_KEY
python scripts/recompute_matches.py
python scripts/inspect_matches.py --stats
```

Without `run_extraction.py`, the engine falls back to placeholder behavior (neutral semantic score, near_fit credential gates). Scores still work — extraction just improves them.

---

## Known infrastructure quirks

**Supabase CLI v2 uses ES256 JWTs:** The `decode_supabase_jwt` function handles both HS256 and ES256. Do not revert to HS256-only.

**`seed_test_users.py`:** Activate the API `.venv` before running. Uses psycopg2 + supabase-py.

**`match_label_enum` values:** `strong_fit`, `good_fit`, `moderate_fit`, `low_fit`. If you see `invalid input value for enum`, run `supabase db reset`.

**Map dots not showing on first load:** Leaflet requires a CSS invalidate after mount. The `JobMapClient.tsx` uses `setTimeout(300ms)` + `mapInstance.current` ref to avoid React 18 strict-mode double-invocation issues.

**Running `seed_test_users.py` twice:** The jobs `INSERT` uses a UUID PK with no natural unique constraint, so running twice creates duplicate jobs. Always `supabase db reset` before re-seeding.
