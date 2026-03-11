# DECISIONS.md — SkillPointe Match Product / Policy Decision Register (Supabase Version)

## Purpose

This file records which product and policy decisions are:

- **Decided**: confirmed and should be implemented now
- **Defaulted**: current implementation defaults, used unless SkillPointe changes them
- **Unresolved**: open questions that should not be silently hard-coded as permanent truth

This file should be read together with:

- `CLAUDE.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`

---

# 1. Decided

## 1.1 MVP System Boundary

**Status:** Decided

SkillPointe Match MVP is a **bi-directional ranking, explanation, and planning platform**.

MVP includes:

- applicant login/profile
- employer login/company + job management
- admin console
- ranked jobs for applicants
- ranked applicants per job for employers
- match rationale / explanation
- missing requirement analysis
- geography-aware ranking and filtering
- applicant planning/chat interface
- admin review tools for extraction/taxonomy issues

MVP does **not** include:

- deferred acceptance
- stable matching / batch placement rounds
- centralized market clearing
- autonomous multi-step agents
- full learning-to-rank systems
- complex labor-market forecasting

---

## 1.2 What Alvin Requested

**Status:** Decided

From the call with Alvin, the current request is:

### Applicant side

Applicants should be able to:

- see best job matches in ranked order
- understand why each job matches
- see lower-fit / near-fit jobs
- understand what is missing for those jobs
- understand how to close the gap
- use a chat/planning interface to make a realistic next-step plan

### Employer side

Employers should be able to:

- manage one or more jobs
- view ranked applicant matches for each job
- understand why each applicant matches
- use filters to inspect candidate fit

### Admin side

Admins should be able to:

- manage data imports
- manage users and roles
- manage taxonomy and scoring/policy configs
- review low-confidence extraction and matching results
- manage analytics and audit logs

---

## 1.3 Three User Roles

**Status:** Decided

There are exactly three user roles in MVP:

1. **Admin**
2. **Applicant**
3. **Employer**

---

## 1.4 Supabase as Platform Foundation

**Status:** Decided

The MVP will use:

- **Supabase Postgres** as the source-of-truth relational database
- **Supabase Auth** for authentication
- **Supabase Storage** for uploaded files
- **Redis** separately for async jobs and queue processing
- **FastAPI** for business logic and orchestration
- **Next.js** for frontend

Important implementation rule:

- Supabase handles infra primitives
- business authorization, scoring, policy, review logic, and audit-safe orchestration still live in the application/backend

---

## 1.5 Authentication / RBAC

**Status:** Decided

MVP must include:

- Supabase Auth login
- applicant self-signup
- invite-based or approved employer onboarding
- admin account management
- password reset
- JWT/session validation
- protected routes by role
- backend RBAC middleware

---

## 1.6 Matching Architecture

**Status:** Decided

The ranking system must have three separate layers:

1. **Base fit estimation**
2. **Policy reranking**
3. **LLM-assisted interpretation**

These must remain separate in code and data.

---

## 1.7 Geography as First-Class Signal

**Status:** Decided

Geography must be treated as a major dimension in:

- schema
- filtering
- hard gates
- scoring
- policy reranking
- explanations

The system must track and use:

- applicant city/state/region
- job city/state/region
- applicant willingness to relocate
- applicant willingness to travel
- job travel requirement
- remote/hybrid/on-site
- commute radius if available

---

## 1.8 LLM Role

**Status:** Decided

LLMs are **supporting components**, not the primary ranking engine.

Allowed LLM roles:

- extraction
- verification/judgment for ambiguous cases
- explanation generation
- applicant planning chat

LLMs must **not** be the sole source of ranking.

---

## 1.9 Human-in-the-Loop Review

**Status:** Decided

Admin review is part of the core MVP.

Admin review must support:

- extracted skills/certifications
- low-confidence parsing
- taxonomy mismatches
- borderline eligibility cases
- weird geography interpretation
- suspicious job postings
- low-confidence verifier outputs

All admin overrides must be auditable.

---

## 1.10 Core Ranking Output

**Status:** Decided

For every applicant-job pair, the system must compute and store:

- `eligibility_status`
- `base_fit_score`
- `policy_adjusted_score`
- `match_label`
- `top_strengths`
- `top_gaps`
- `required_missing_items`
- `recommended_next_step`
- `confidence_level`

---

## 1.11 Eligibility Labels

**Status:** Decided

Each applicant-job pair must be labeled:

- `eligible`
- `near_fit`
- `ineligible`

These labels must be visible in the product and must influence ranking.

---

## 1.12 No Hidden Hard Failures

**Status:** Decided

The system must never present a candidate-job pair as a strong/high match if a critical hard requirement fails.

Hard failures must be surfaced explicitly.

---

# 2. Defaulted

## 2.1 Structured Score Weights

**Status:** Defaulted

Use these default structured weights:

- `trade_program_alignment`: 25
- `geography_alignment`: 20
- `credential_readiness`: 15
- `timing_readiness`: 10
- `experience_internship_alignment`: 10
- `industry_alignment`: 5
- `compensation_alignment`: 5
- `work_style_signal_alignment`: 5
- `employer_soft_pref_alignment`: 5

Total = 100

---

## 2.2 Semantic Layer Weight

**Status:** Defaulted

Use:

- `weighted_structured_score * 0.75`
- `semantic_score * 0.25`

Formula:
`base_fit_score = hard_gate_cap * (weighted_structured_score * 0.75 + semantic_score * 0.25)`

---

## 2.3 Hard Gate Caps

**Status:** Defaulted

Use these score caps:

- `eligible` → cap multiplier `1.0`
- `near_fit` → cap multiplier `0.75`
- `ineligible` → cap multiplier `0.35`

---

## 2.4 Default Policy Rules

**Status:** Defaulted

### Partner Employer Preference

- partner employer: `+5`
- non-partner: `+0`

Constraint:

- partner boost must not outrank another result whose base score is more than 12 points higher

### Funded Training Pathway Alignment

- direct alignment: `+6`
- adjacent alignment: `+3`
- unrelated: `+0`

### Geography Preference

- local feasible: `+6`
- same-state / regional: `+4`
- relocation required but willing: `+1`
- travel-heavy but willing: `+1`
- uncertain: `0`

### Readiness Preference

- ready now / timing aligned: `+5`
- near completion: `+3`
- materially delayed: `0`

### Opportunity Upside

- meaningful pay/upside + near_fit or better: `+2`
- otherwise: `0`

### Missing-Critical-Requirement Penalty

- missing mandatory credential: `-12`
- missing important non-mandatory skill cluster: `-6`
- minor missing items: `-2`

---

## 2.5 Applicant UI Visibility Rule

**Status:** Defaulted

Applicant UI should show two labeled sections:

1. **Best immediate opportunities**
2. **Promising near-fit opportunities**

Do not invisibly mix these without labels.

---

## 2.6 Null Handling Defaults

**Status:** Defaulted

Missing data should default to **neutral**, not punitive, unless the field is explicitly required.

Use:

- unknown compensation alignment → `70`
- unknown employer soft-pref alignment → `50`
- unknown work-style alignment → `50`
- unknown geography → `50` if partial info exists, `35` if fully unknown
- unknown credentials → `50` unless job explicitly requires credential
- unknown experience → `50`

If required credential exists on the job and applicant credential data is missing:

- mark as `near_fit`
- do not auto-fail
- set `requires_review = true` if extraction confidence is low

---

## 2.7 Confidence Tiers

**Status:** Defaulted

### Extraction confidence

- `high`
- `medium`
- `low`

### Match confidence

- `high`: strong structured evidence, low ambiguity
- `medium`: moderate inference, some unknowns
- `low`: important inferred/missing/conflicting evidence

Low-confidence matches should be reviewable by admin.

---

## 2.8 Employer Candidate Visibility

**Status:** Defaulted

Default employer visibility rule:

- employers may see only candidates surfaced to **their own jobs**
- they do **not** get unrestricted global candidate search by default

This can be changed later if SkillPointe explicitly wants broader employer search.

---

## 2.9 Messaging

**Status:** Defaulted

Messaging/contact is allowed **only if enabled by policy**.
Do not assume fully open messaging by default.

Default behavior:

- keep messaging as a controlled feature behind configuration
- do not auto-contact anyone

---

## 2.10 Applicant Planning Chat Scope

**Status:** Defaulted

The applicant chat should be:

- grounded
- practical
- profile-aware
- match-aware
- non-autonomous

It should answer:

- what jobs to target first
- what is missing
- whether to apply now or prepare first
- what nearby opportunities exist
- what path leads to a target role

It should **not**:

- act as a freeform life coach
- invent opportunities
- autonomously take actions

---

## 2.11 Training Guidance Scope

**Status:** Defaulted

Training/gap-closing support is included only as:

- missing requirement analysis
- suggested next steps
- possible training/certification guidance if available in system context

It is **not** yet a full training-program marketplace.

---

## 2.12 Recommended Tech Stack

**Status:** Defaulted

Use:

- Frontend: Next.js
- Backend: FastAPI
- Database: Supabase Postgres
- Auth: Supabase Auth
- Storage: Supabase Storage
- Vector support: pgvector if enabled
- Queue: Redis + worker
- Observability: Sentry + audit logs

---

# 3. Unresolved

## 3.1 Exact Partner Priority Strength

**Status:** Unresolved

We currently default to a mild `+5` boost for partner employers.

Implementation guidance:

- make partner preference configurable in admin policy

---

## 3.2 Exact Weight of Funded Program Alignment

**Status:** Unresolved

We currently default to:

- `+6` direct
- `+3` adjacent

Implementation guidance:

- make this configurable per program or globally

---

## 3.3 Financial Need in Ranking

**Status:** Unresolved

Current working view:

- financial hardship should **not** be part of employer-facing raw fit by default

Implementation guidance:

- do not include financial hardship in employer-facing base fit
- keep financial-need handling configurable and likely admin-side only

---

## 3.4 Applicant-to-Employer Messaging Permissions

**Status:** Unresolved

Implementation guidance:

- keep messaging behind feature flags / policy config

---

## 3.5 Employer Access to Global Candidate Search

**Status:** Unresolved

Implementation guidance:

- default to job-scoped access only
- keep global search as an optional admin-enabled capability

---

## 3.6 Exact Readiness Window

**Status:** Unresolved

Implementation guidance:

- make timing thresholds configurable
- default to conservative near-completion logic

---

## 3.7 How to Treat Near-Fit Jobs in Final Applicant Ordering

**Status:** Unresolved

Implementation guidance:

- default to separate labeled sections
- keep display mode configurable in UI policy

---

## 3.8 How Much Geography Should Dominate Ranking

**Status:** Unresolved

Implementation guidance:

- keep geography policy configurable
- preserve both base fit and geography explanation

---

## 3.9 Compensation / Upward Mobility Influence

**Status:** Unresolved

Implementation guidance:

- keep upside as a small additive modifier for now
- make it configurable

---

## 3.10 Training Program Integration

**Status:** Unresolved

Implementation guidance:

- for MVP, support only lightweight gap-closing recommendations
- do not overbuild a training marketplace yet

---

## 3.11 Employer Soft Preferences

**Status:** Unresolved

Implementation guidance:

- keep soft preferences lightweight
- cap their influence
- store separately from hard requirements

---

## 3.12 Outcome Metrics Hierarchy

**Status:** Unresolved

Implementation guidance:

- keep analytics and policy knobs flexible
- do not assume a single permanent KPI hierarchy

---

# 4. Implementation Rules for Unresolved Items

For every unresolved decision:

1. make it configurable in admin policy where possible
2. store current active value/version
3. do not bury it in code constants only
4. expose it in audit/config history
5. preserve separate fields for:
   - raw fit
   - policy-adjusted score
   - explanation metadata

---

# 5. Current Working Summary

## Build now

- ranking engine
- explanation engine
- applicant planning chat
- geography-aware logic
- admin review tooling
- employer per-job ranked applicant lists
- applicant ranked job lists
- auth and RBAC
- policy configuration layer
- Supabase-backed auth/storage/data

## Do not build now

- batch matching
- deferred acceptance
- centralized clearinghouse
- autonomous agents
- heavy ML ranking systems
- full training marketplace

---

# 6. Quick Reference for Claude

If unsure, follow these rules:

- prefer simple deterministic ranking over complex ML
- keep LLMs supportive, not primary
- keep geography first-class
- keep admin review first-class
- separate base fit from policy reranking
- do not assume unresolved items are permanently decided
- do not add batch matching to MVP
- do not expose all candidates to all employers by default
- use Supabase for auth/storage/database primitives
- keep Redis for async jobs
