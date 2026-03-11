# CLAUDE.md — SkillPointe Match Canonical Build Context (Supabase Version)

## Project Identity

Build **SkillPointe Match**, a three-role operational platform with:

1. **Admin** (SkillPointe staff)
2. **Applicant** (scholar / trainee / candidate)
3. **Employer** (can manage one or more jobs)

This is **NOT** a batch placement clearinghouse in MVP.
Do **NOT** build:

- deferred acceptance
- stable matching rounds
- centralized batch allocation
- preference-clearing workflows

MVP is a **bi-directional ranking, explanation, and planning platform**:

- Applicants see ranked job matches and why
- Applicants see lower-fit jobs, what is missing, and how to close the gap
- Applicants can use a grounded chat/planning interface
- Employers see their jobs and, for each job, ranked applicant matches and why
- Admins manage data, policies, review queues, users, jobs, and analytics

---

## What Alvin Actually Asked For

We spoke with Alvin. He did **not** request batch matching or formal placement rounds.

The product we are building now is:

- applicant ranked job recommendations
- employer ranked applicant recommendations per job
- rationale / explanation
- missing requirements analysis
- geography-aware filtering and ranking
- a planning/chat interface for applicants
- admin controls for data quality, policy, and review

Do not architect MVP around centralized matching.

---

## Product Boundary

### Core MVP

Build:

- applicant login + profile
- employer login + company/job management
- admin login + management console
- ranked job recommendations for applicants
- ranked applicant recommendations per job for employers
- explainable scoring
- “missing requirements” analysis
- geography-aware matching
- applicant planning/chat interface
- admin review tools for extraction and taxonomy issues

### Explicitly Out of Scope for MVP

Do NOT build:

- deferred acceptance
- stable matching / batch placement
- centralized market-clearing
- autonomous multi-step agents
- full learning-to-rank pipelines
- complex labor-market forecasting
- full training-program marketplace
- automatic contacting of employers or applicants without explicit UI action

---

## Core Product Principle

This system is a **two-sided labor-market recommendation platform**, but MVP behavior is **continuous ranking and explanation**, not centralized matching.

Keep these concepts separate in code:

1. **Base Fit Estimation**
   - deterministic estimate of compatibility between applicant and job

2. **Policy Reranking**
   - configurable reordering/visibility changes based on SkillPointe priorities

3. **LLM-Assisted Interpretation**
   - extraction, verification, explanation, chat
   - never the sole source of ranking

Do not blur these layers.

---

## User Roles and Authorization

### 1. Admin

Admins can:

- log in
- import applicants/jobs/employers
- create/manage employer accounts
- create/manage admin users
- view all applicants, employers, jobs, and matches
- manage taxonomy and canonical mappings
- manage policy/scoring configs
- trigger recomputation
- review low-confidence extraction results
- review borderline matches
- view analytics and audit logs
- manage chat prompts/guardrails/config

Admins cannot:

- edit records without audit logging
- impersonate users without explicit audit trail

### 2. Applicant

Applicants can:

- create account / log in
- edit profile
- upload resume/documents
- set location, relocation willingness, travel willingness
- view ranked jobs
- view explanations
- view missing requirements and suggested next steps
- use planning/chat interface
- save jobs / mark interest / apply if enabled
- message employers if enabled by policy

Applicants cannot:

- see other applicants
- see employer internal notes
- access admin functions
- edit jobs

### 3. Employer

Employers can:

- create/login via invite or approved signup
- manage company profile
- create/edit one or more jobs
- view ranked applicant lists for each of their jobs
- filter applicants surfaced for their jobs
- shortlist applicants
- message/contact applicants if enabled
- view rationale for applicant ranking

Employers cannot:

- access all candidates globally unless explicitly enabled by admin policy
- see admin-only notes/config
- alter global scoring logic
- see other employers’ data

---

## Authentication / Authorization Requirements

Implement:

- role-based login for admin, applicant, employer
- email/password auth via Supabase Auth
- password reset
- invite-based admin/employer onboarding
- applicant self-signup allowed
- protected routes by role
- backend JWT validation against Supabase Auth
- RBAC middleware in API

Recommended stack:

- Next.js frontend
- FastAPI backend
- Supabase Auth for authentication
- JWT validation in backend using Supabase JWTs

Important:

- Supabase Auth handles identity
- application role/authorization logic must still exist in app tables and backend middleware
- do not rely only on frontend checks

---

## Data Platform / Infra

Use:

- **Database:** Supabase Postgres
- **Auth:** Supabase Auth
- **Storage:** Supabase Storage
- **Vector support:** pgvector in Supabase Postgres if enabled for semantic retrieval
- **Queue / async jobs:** Redis (separate from Supabase)
- **Backend:** FastAPI
- **Frontend:** Next.js
- **Observability:** Sentry + audit logs

Important separation:

- Supabase is the system of record for relational data, auth, and file storage
- Redis is still required for async/background jobs
- FastAPI owns business logic, matching, extraction orchestration, admin workflows, and audit-safe actions

---

## Ranking System: What the System Must Actually Do

### High-Level Goal

For every applicant-job pair, compute:

- `eligibility_status`
- `base_fit_score`
- `policy_adjusted_score`
- `match_label`
- `top_strengths`
- `top_gaps`
- `required_missing_items`
- `recommended_next_step`
- `confidence_level`

Then:

- rank jobs for each applicant by `policy_adjusted_score`
- rank applicants for each job by `policy_adjusted_score`

---

## Deterministic Ranking Pipeline

### Stage 0: Normalize Inputs

Before any matching:

- normalize applicant program names into canonical job/trade families
- normalize job titles into canonical job families
- normalize locations into city/state/region
- normalize pay ranges into numeric min/max where possible
- normalize availability/completion timing
- normalize certifications/licenses if explicitly present
- store extracted skills separately from raw text

All normalization should preserve original source text.

---

## Stage 1: Hard Eligibility Gates

Each applicant-job pair must first be classified as:

- `eligible`
- `near_fit`
- `ineligible`

### Hard Gate Rules

Use these, where data exists:

1. **Job Family Compatibility**
   - Pass if applicant program/career path aligns directly with job family
   - Near-fit if adjacent trade family
   - Fail if clearly unrelated

2. **Required Credential Compatibility**
   - Pass if required credential/license is present
   - Near-fit if missing but plausibly acquirable soon
   - Fail if required and clearly absent with no current path

3. **Readiness / Timing Compatibility**
   - Pass if applicant is available now or within allowed hiring window
   - Near-fit if still enrolled but close enough to completion
   - Fail if timing is clearly incompatible

4. **Geography Feasibility**
   - Pass if local, remote-compatible, or relocation/travel willingness satisfies job
   - Near-fit if strong fit but relocation/travel assumptions are needed
   - Fail if job requires presence in a region applicant is not willing to support

5. **Explicit Minimum Requirement Compatibility**
   - If job explicitly requires an associate degree/certificate/apprenticeship/etc. and applicant clearly lacks it, mark near-fit or fail depending on severity

### Eligibility Label Rules

- `eligible`: no critical hard failures
- `near_fit`: one or more important gaps, but role still plausibly useful to surface
- `ineligible`: critical mismatch; do not rank highly or recommend prominently

### Critical Rule

No applicant-job pair may be labeled “high fit” if a critical hard gate fails.

---

## Stage 2: Base Fit Score

Compute a deterministic `base_fit_score` from 0 to 100.

### Base Fit Score Formula

Use:

`base_fit_score = hard_gate_cap * (weighted_structured_score * 0.75 + semantic_score * 0.25)`

Where:

- `weighted_structured_score` is 0–100
- `semantic_score` is 0–100
- `hard_gate_cap` is:
  - `1.0` if eligible
  - `0.75` if near_fit
  - `0.35` if ineligible

This ensures hard-gate failures cap the score.

---

## Stage 2A: Structured Score

Compute this from normalized structured fields.

### Default Structured Weights

Use these exact defaults for MVP:

- **trade_program_alignment**: 25
- **geography_alignment**: 20
- **credential_readiness**: 15
- **timing_readiness**: 10
- **experience_internship_alignment**: 10
- **industry_alignment**: 5
- **compensation_alignment**: 5
- **work_style_signal_alignment**: 5
- **employer_soft_pref_alignment**: 5

Total = 100

### Structured Score Formula

`weighted_structured_score = sum(weight_i * score_i) / 100`

Use the rubrics defined in `SCORING_CONFIG.yaml`.

---

## Stage 2B: Semantic Score

The semantic layer is supportive, not primary.

Use embeddings and extracted structured concepts from:

- applicant essays
- internship details
- extracurriculars
- resume text
- job descriptions
- required/preferred qualifications
- responsibilities

### Semantic Score Formula

`semantic_score = 0.4*skills_overlap + 0.3*job_family_similarity + 0.2*experience_text_relevance + 0.1*intent_alignment`

### Critical Rule

Semantic score may support confidence and improve ordering within viable groups, but must not override a hard eligibility failure.

---

## Stage 3: Policy Reranking

After base fit is computed, apply policy adjustments.

### Important Rule

Policy must modify **ordering/visibility**, not the underlying estimated compatibility.

Store separately:

- `base_fit_score`
- `policy_adjusted_score`

Use default policy rules from `SCORING_CONFIG.yaml`.

---

## Geography is a First-Class Dimension

Geography must be central in applicant-side and employer-side ranking.

Track and use:

- applicant city/state/region
- applicant willingness to relocate
- applicant willingness to travel
- job city/state/region
- remote/hybrid/on-site
- travel requirement
- commute radius if available

Geography affects:

- hard gates
- structured score
- policy reranking
- explanation text

---

## LLM Usage Policy

### Important

LLMs are supporting components, not the primary match engine.
Never let an LLM be the sole source of fit score ranking.

LLMs are used for:

1. extraction
2. verification/judgment on ambiguous cases
3. explanation generation
4. applicant planning chat

Use the base prompts defined in `PROMPTS.md` or in the implementation layer.
All LLM outputs must be stored with:

- raw output
- parsed structured output
- confidence
- prompt version
- timestamp
- review status if applicable

---

## Human-in-the-Loop Requirements

Admin review is core.

Support review for:

- extracted skills/certifications
- low-confidence parser outputs
- taxonomy mismatches
- borderline eligibility cases
- weird geography interpretation
- low-confidence verifier judgments
- suspicious or low-quality job postings

All overrides must be auditable.

---

## Data Reality and Constraints

Current applicant data is semantically rich but structurally weak.
Current job data is semi-structured and noisy.

Expect:

- inconsistent program names
- missing certifications
- weak explicit skill tags
- important signals buried in essays/internships

Therefore prioritize:

- normalization
- extraction
- explainability
- review tooling
- confidence-aware outputs

Do not assume:

- complete skill ontologies
- perfect credential fields
- clean preference lists
- fully structured employer job feeds

---

## Canonical Applicant Experience

Applicants should be able to:

1. log in
2. complete/edit profile
3. upload resume
4. set location + relocation/travel preferences
5. view ranked jobs
6. view detailed match explanation
7. see missing qualifications for lower-fit jobs
8. see suggested actions to improve fit
9. use chat/planning interface

---

## Canonical Employer Experience

Employers should be able to:

1. log in
2. manage company profile
3. create/edit one or more jobs
4. view ranked applicants per job
5. see rationale for fit
6. filter by geography, readiness, credentials, etc.
7. shortlist or contact applicants if enabled

---

## Canonical Admin Experience

Admins should be able to:

1. log in
2. manage users and roles
3. import and review applicant/job data
4. manage taxonomy mappings
5. review extraction confidence issues
6. configure policy weights and toggles
7. recompute matches
8. view analytics
9. review audit logs

---

## Recommended Tech Stack

Use:

- **Frontend:** Next.js
- **Backend:** FastAPI
- **Database:** Supabase Postgres
- **Auth:** Supabase Auth
- **Storage:** Supabase Storage
- **Vector support:** pgvector if enabled in Supabase
- **Queue:** Redis + worker
- **Observability:** Sentry + audit logs

---

## Suggested Monorepo Structure

- apps/web
- apps/api
- packages/ui
- packages/types
- packages/matching
- packages/etl
- docs
- scripts
- infra

---

## Build Order

Build in this order:

1. Supabase project + local dev environment
2. auth + RBAC
3. applicant/employer/admin data model
4. job/applicant import pipeline
5. taxonomy normalization
6. hard eligibility gates
7. structured compatibility scoring
8. geography support
9. policy reranking engine
10. explanation views
11. employer ranked-applicant views
12. applicant ranked-job views
13. LLM extraction layer
14. verifier/judge workflow
15. applicant planning chat
16. admin review tooling
17. analytics + audits

Do not start with chat.
Do not start with autonomous agents.
Do not start with deferred acceptance.

---

## Critical Guardrails for Claude

When building:

- do not reintroduce batch matching into MVP
- do not hide hard failures inside opaque scores
- do not make LLMs the sole match engine
- do not skip geography
- do not skip admin review flows
- do not collapse policy reranking into raw fit estimation
- do not overbuild chat
- do not assume clean structured skills data
- do not expose all candidates to all employers by default

---

## Deliverable Standard

All code and architecture should reflect:

- auditable match generation
- explainable scores
- role-safe data visibility
- geography-aware ranking
- Supabase-backed auth/data/storage
- Redis-backed async job processing
- LLMs as extraction/verifier/explainer/planning assistants
- clean separation of deterministic logic and LLM-assisted interpretation
