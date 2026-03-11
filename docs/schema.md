# SkillPointe Match — Database Schema Reference
Phase 3 — Core Data Model

---

## Overview

All tables live in the `public` schema of Supabase Postgres.
Row Level Security (RLS) is enabled on every table.
The FastAPI backend uses the **service-role key** (bypasses RLS) for all writes
and cross-user reads.  Direct Supabase client access from the frontend is limited
to the policies documented below.

### Column conventions

| Column | Meaning |
|--------|---------|
| `*_raw` | Preserved original imported / entered value — never overwritten |
| `*_normalized` | Computed canonical value |
| `canonical_*_id` | FK to taxonomy table after normalisation |
| `confidence_level` | `high` / `medium` / `low` — extraction or match confidence |
| `requires_review` | Routes row to admin review queue when `TRUE` |
| `review_status` | `pending` / `reviewed` / `overridden` / `dismissed` |
| `source` | `'import'`, `'self_signup'`, `'admin'`, etc. |
| `import_run_id` | FK-quality reference to `import_runs.id` for imported rows |
| `created_at` / `updated_at` | Immutable create time + auto-updated via trigger |

---

## Migration files

| File | Tables created |
|------|---------------|
| `20260310000000_user_profiles.sql` | `user_profiles` |
| `20260310000001_enums_and_extensions.sql` | enum types, pgvector extension |
| `20260310000002_taxonomy.sql` | `canonical_job_families`, `canonical_career_pathways`, `geography_regions` |
| `20260310000003_core_entities.sql` | `applicants`, `employers`, `employer_contacts`, `jobs` |
| `20260310000004_documents_and_signals.sql` | `applicant_documents`, `extracted_applicant_signals`, `extracted_job_signals` |
| `20260310000005_matches.sql` | `matches`, `match_dimension_scores`, `saved_jobs` |
| `20260310000006_ops_and_config.sql` | `import_runs`, `import_rows`, `audit_logs`, `policy_configs`, `review_queue_items` |
| `20260310000007_chat.sql` | `chat_sessions`, `chat_messages` |

---

## Enum types

| Enum | Values |
|------|--------|
| `eligibility_status_enum` | `eligible`, `near_fit`, `ineligible` |
| `confidence_level_enum` | `high`, `medium`, `low` |
| `review_status_enum` | `pending`, `reviewed`, `overridden`, `dismissed` |
| `match_label_enum` | `strong_match`, `good_match`, `near_fit`, `low_fit`, `ineligible` |
| `work_setting_enum` | `remote`, `hybrid`, `on_site`, `flexible` |
| `document_type_enum` | `resume`, `essay`, `transcript`, `certification`, `other` |
| `import_status_enum` | `pending`, `processing`, `complete`, `failed`, `partial` |
| `review_queue_item_type_enum` | `extraction_confidence`, `taxonomy_mismatch`, `borderline_match`, `geography_ambiguity`, `credential_ambiguity`, `suspicious_import`, `low_confidence_verifier`, `admin_override_review` |
| `chat_role_enum` | `user`, `assistant`, `system` |

---

## Table reference

### `user_profiles`
Auth + RBAC bridge.  Authoritative source of app role.  FK → `auth.users`.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID | Unique FK to `auth.users` |
| `role` | TEXT CHECK | `admin`, `applicant`, `employer` |
| `onboarding_complete` | BOOLEAN | Set by `POST /auth/complete-signup` |

---

### `canonical_job_families`
Top-level trade/job family taxonomy.

| Column | Notes |
|--------|-------|
| `code` | Unique machine key e.g. `electrical` |
| `aliases` | Alternative names for fuzzy matching during normalisation |
| `parent_id` | Self-referencing FK for sub-families |

---

### `canonical_career_pathways`
Training programmes / apprenticeships within a job family.

| Column | Notes |
|--------|-------|
| `job_family_id` | FK to `canonical_job_families` |
| `typical_duration_months` | Used in timing/readiness gate |

---

### `geography_regions`
US regional groupings.  `states` is an array of 2-letter codes.

---

### `applicants`
One row per applicant user.  Both raw and normalised geography/programme fields.

| Key columns | Notes |
|------------|-------|
| `program_name_raw` | Original programme name — never overwritten |
| `city`, `state`, `region` | Geography (first-class per CLAUDE.md) |
| `willing_to_relocate`, `willing_to_travel` | Hard-gate inputs |
| `canonical_job_family_id` | Null until normalised by ETL/admin |
| `expected_completion_date`, `available_from_date` | Timing gate inputs |

---

### `employers`
One row per employer company.  `is_partner` affects policy reranking (+5 pts).

---

### `employer_contacts`
Links an `auth.users` user to an `employers` row.  One user → one employer in MVP.

---

### `jobs`
One row per job posting.

| Key columns | Notes |
|------------|-------|
| `title_raw` | Always preserved |
| `canonical_job_family_id` | Null until normalised |
| `work_setting` | `work_setting_enum` |
| `pay_min`, `pay_max` | Normalised pay range |
| `pay_raw` | Original string preserved |
| `required_credentials[]` | Drives credential hard gate |

---

### `applicant_documents`
File metadata for Supabase Storage uploads.  `storage_path` is the Storage object path.

---

### `extracted_applicant_signals`
LLM extraction output for an applicant.  Key design:
- `raw_llm_output` = full response preserved for audit
- `skills_extracted`, `certifications_extracted`, etc. = parsed structured JSONB
- `embedding` = pgvector(1536) for semantic scoring (Phase 7, nullable until then)
- `confidence_level` + `requires_review` → admin review queue when low

---

### `extracted_job_signals`
Same pattern as `extracted_applicant_signals` but for jobs.

---

### `matches`
Core ranking output.  One row per (applicant, job) pair.

**Critical separation** (per DECISIONS.md 1.6):

| Column | Meaning |
|--------|---------|
| `weighted_structured_score` | Stage 2A output (0–100) |
| `semantic_score` | Stage 2B output (0–100) |
| `base_fit_score` | Stage 2 final: `hard_gate_cap × (structured×0.75 + semantic×0.25)` |
| `policy_adjusted_score` | Stage 3 final: `clamp(base_fit + policy_modifiers, 0, 100)` |

Eligibility + score caps:
- `eligible` → cap 1.0
- `near_fit` → cap 0.75
- `ineligible` → cap 0.35

Visibility flags `is_visible_to_applicant` / `is_visible_to_employer` are controlled by policy.

---

### `match_dimension_scores`
Per-dimension breakdown of the structured score.  Dimension names match
`SCORING_CONFIG.yaml` keys: `trade_program_alignment`, `geography_alignment`,
`credential_readiness`, `timing_readiness`, `experience_internship_alignment`,
`industry_alignment`, `compensation_alignment`, `work_style_signal_alignment`,
`employer_soft_pref_alignment`.

---

### `saved_jobs`
Applicant interest actions.  `interest_level`: `saved`, `applied`, `not_interested`.

---

### `import_runs` + `import_rows`
Import batch tracking.  `import_rows.raw_data` (JSONB) preserves the original row.
`import_rows.entity_id` points to the created/updated entity if successful.

---

### `audit_logs`
Append-only.  No UPDATE/DELETE policies.  Written by FastAPI on every significant
admin or system action.  `before_state` / `after_state` are JSONB snapshots.

---

### `policy_configs`
Versioned scoring/policy config.  Exactly one row has `is_active = TRUE`
(enforced by partial unique index).  The matching engine reads the active config
at runtime rather than using hardcoded constants.  Config structure mirrors
`SCORING_CONFIG.yaml`.

---

### `review_queue_items`
Items flagged for admin human-in-the-loop review.  Created by the extraction
pipeline or scoring engine.  Resolved by admin via FastAPI.  All resolutions
are written to `audit_logs`.

---

### `chat_sessions` + `chat_messages`
Applicant planning chat (Phase 8).  `context_snapshot` on the session captures
the applicant's match state at session-open time for grounding.
`context_used` + `raw_llm_response` on assistant messages for audit.

---

## RLS summary

| Table | Applicant | Employer | Admin / system |
|-------|-----------|----------|----------------|
| `user_profiles` | read/update own | — | service-role |
| `applicants` | read/update own | — | service-role |
| `employers` | — | read own | service-role |
| `employer_contacts` | — | read own | service-role |
| `jobs` | read active | read/manage own employer's | service-role |
| `applicant_documents` | manage own | — | service-role |
| `extracted_applicant_signals` | read own | — | service-role |
| `extracted_job_signals` | — | read own job signals | service-role |
| `matches` | read own (visible) | read own job matches (visible) | service-role |
| `match_dimension_scores` | read own match dims | read own job match dims | service-role |
| `saved_jobs` | manage own | — | service-role |
| `import_runs` | — | — | service-role only |
| `import_rows` | — | — | service-role only |
| `audit_logs` | — | — | service-role only |
| `policy_configs` | — | — | service-role only |
| `review_queue_items` | — | — | service-role only |
| `chat_sessions` | manage own | — | service-role |
| `chat_messages` | read own | — | service-role |
| `canonical_job_families` | public read | public read | service-role write |
| `canonical_career_pathways` | public read | public read | service-role write |
| `geography_regions` | public read | public read | service-role write |

---

## Seed data (supabase/seed.sql)

Loaded automatically by `supabase db reset`:

- **6 geography regions** — northeast, southeast, midwest, southwest, west, mid-atlantic
- **15 canonical job families** — electrical, plumbing, hvac, construction, welding, automotive, manufacturing, logistics, healthcare_support, it_support, culinary, childcare_education, cosmetology, security, administrative
- **15 canonical career pathways** — apprenticeships, certificates, and programme types linked to job families
- **1 policy config (v1)** — active default config mirroring `SCORING_CONFIG.yaml`

Verify with:
```bash
python scripts/verify_schema.py
```
