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

docs/                  # project docs
scripts/               # import, normalize, recompute, inspect scripts
infra/                 # infra and deployment-related config
```
