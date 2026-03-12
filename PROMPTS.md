# PROMPTS.md — Reusable Claude + LLM Prompts for SkillPointe Match

## Purpose

This file contains:

1. **Reusable Claude build prompts** for repo development
2. **Reusable Claude review/debug prompts** for iteration
3. **Base LLM prompts** for extraction, verification, explanation, and planning chat

Use this file together with:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`

---

# Part 1 — How to Start Any Claude Build Session

At the start of a Claude build session, first paste:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`
- optionally this `PROMPTS.md`

Then use this session header:

```text
Before doing any work, read and follow:
- CLAUDE.md
- DECISIONS.md
- SCORING_CONFIG.yaml
- BUILD_PLAN.md
- PROMPTS.md

At the start of your response, always state:
- Current Phase
- Current Step
- Depends On
- What exists already
- What this task will change
- What must be tested after this task
- Next Step

Do not add batch matching or deferred acceptance to MVP.
Do not make LLMs the sole ranking engine.
Do not skip geography, admin review, RBAC, or auditability.
Keep deterministic fit estimation separate from policy reranking and LLM-assisted interpretation.
```

Phase 6.2 is complete. Here's a summary of everything built:

---

Backend — 3 files

File: app/schemas/employer.py  
 What it does: Pydantic schemas for all employer responses (EmployerCompanySummary,  
 EmployerJobSummary, ApplicantMatchSummary — safe fields only, no user_id/email,
RankedApplicantsResponse, JobCreate/UpdateRequest)
────────────────────────────────────────
File: app/routers/employers.py
What it does: 5 endpoints: GET /company, GET /jobs, POST /jobs, PATCH /jobs/{id}, GET
/jobs/{id}/applicants — every query scoped to employer via employer_contacts JOIN;
is_visible_to_employer=TRUE enforced on all match queries; dynamic filter params
(eligibility, min_score, state, relocate)
────────────────────────────────────────
File: app/main.py
What it does: Registered employers.router

Key visibility enforcement in every applicant query:
WHERE j.id = $1 -- specific job
AND j.employer_id = $2 -- CRITICAL: employer scoping
AND m.is_visible_to_employer = TRUE

Frontend — 5 files

File: lib/api/employer.ts
What it does: Types + fetchMyCompany, fetchMyJobs, fetchJobApplicants, createJob,
updateJob, display helpers
────────────────────────────────────────
File: components/employer/ApplicantMatchCard.tsx
What it does: Compact applicant card (name, program, location, mobility, score, badges,
strengths/gaps)
────────────────────────────────────────
File: employer/page.tsx
What it does: Dashboard: company summary, partner badge, active/total job counts, jobs
list with per-job eligible/near-fit counts
────────────────────────────────────────
File: employer/jobs/new/page.tsx
What it does: Create job form (server action → POST /employer/me/jobs) with shared
JobFormFields component
────────────────────────────────────────
File: employer/jobs/[jobId]/edit/page.tsx
What it does: Edit job form (server action → PATCH /employer/me/jobs/{id})
────────────────────────────────────────
File: employer/jobs/[jobId]/applicants/page.tsx
What it does: Ranked applicants page: stat cards, URL-based filter bar (GET form),
ApplicantMatchCard list

Tests — test_employer_visibility.py
8 test classes covering: cross-employer access blocked (→ 404),
is_visible_to_employer=FALSE excluded, ineligible hidden by default,
eligibility/min_score filters, RBAC (applicant → 403, no employer_contacts → 404), safe
fields (no user_id/email), geography note derivation.

Next step: Phase 6.3 — Explanation surfaces.
