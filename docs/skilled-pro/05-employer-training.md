# SKILLED Pro — Employer Portal + Training Programs (Architecture Research)

> Area 05 of the SKILLED Pro platform. State-of-the-art (2026) approaches, recommended designs, tooling/cost, security/privacy, and concrete fit to the existing stack: FastAPI (Python 3.11) · Supabase Postgres · Redis · OpenAI · Stripe · Next.js 15 · Railway.

## Executive Summary

This document specifies a production-grade Employer Portal and Training-Programs subsystem for SKILLED Pro, a verified-credentials + job-matching platform for skilled trades. The recommended architecture layers a deterministic data core (org profiles, structured postings, a verified-worker index, credential taxonomy) under AI-assisted surfaces (candidate ranking, weekly summaries, pre-filled applications), and monetizes through Stripe Billing subscription tiers plus a Stripe-Connect-backed "Pay When They Stay" deferred placement fee modeled as a separate-charges-and-transfers escrow-with-retention flow. Every analytics or outcomes feed that leaves the platform passes through a k-anonymity + bounded-noise privacy gate so partner institutions and wage benchmarks never receive re-identifiable rows.

---

# Part A — Employer Portal

## A1. Org profiles, structured job postings, searchable/filterable verified-worker database

### (1) 2026 state of the art
Job postings are no longer free-text blobs. Leading hiring platforms store **structured, taxonomy-tagged postings** (occupation code, required credentials, wage band, work setting, shift, geo) so they can be filtered, matched, and benchmarked deterministically, with embeddings layered on top for semantic recall. Worker discovery is a **hybrid search** problem: structured SQL/JSONB filters (trade, license status, radius) combined with vector similarity (pgvector / HNSW) for "find people like this." Verified-status is treated as a **first-class, indexed boolean+timestamp**, not a derived attribute, so "show only currently-verified electricians within 50 mi" is an index scan, not a join-time computation.

### (2) Recommended approach
- Model `employers` (you already have this) with a richer `employer_profiles` extension (logo, description, locations[], EIN-verified flag, hiring regions).
- Make `jobs` fully structured: bind every posting to an `occupation_code` (O*NET-SOC) and a `required_credentials[]` array referencing the credential taxonomy (see B1), plus `wage_min/wage_max`, `work_setting`, `shift`, and a `geo` point.
- Build a **verified-worker search view** (`worker_search_index`) materialized from applicants + their currently-valid credentials + last-verified timestamp + geo + embedding. Employers query it through a single endpoint that applies RLS-equivalent visibility rules in the API layer (employers see a curated, consent-gated subset — never the raw applicant table).
- Use **Postgres `pgvector` (HNSW)** for semantic recall and B-tree/GiST indexes for structured filters; combine with a weighted score (reuse the existing 9-dimension scorer for ordering).

### (3) Tools/libraries + tradeoffs + cost
- **pgvector** (already available in Supabase Postgres) — no extra cost, keeps vectors next to relational data; tradeoff: HNSW index rebuilds are memory-heavy at >1M rows (fine for trades-scale).
- **PostgREST/Supabase full-text (`tsvector`)** for keyword fallback — free.
- **OpenAI `text-embedding-3-small`** (already in stack) for posting + worker embeddings — ~$0.02 / 1M tokens; embed once on write, not per query.
- Tradeoff vs. a dedicated engine (Elasticsearch/OpenSearch, Typesense): an external index adds operational surface and sync lag; at trades scale Postgres hybrid search is simpler and avoids a second source of truth. Revisit only past ~5–10M searchable workers.

### (4) Security / privacy
- **Consent-gated visibility**: a worker appears in employer search only if they opted into being discoverable. Store `discoverable_at` + `discoverability_scope` (e.g., trade/region) on the applicant.
- Employer queries must be **rate-limited and audited** (`audit_logs`) to prevent scraping the worker base.
- Never return PII (full address, phone, email) in search results — return a redacted card + a "request intro" action that creates a consented `conversation`.

### (5) Concrete fit to this stack
**Data model (new/extended tables):**
```sql
-- extend employers
employer_profiles(employer_id PK/FK, logo_url, description, hiring_regions text[],
                  ein_verified bool, ein_verified_at timestamptz)

-- jobs already exist; add structured columns
ALTER TABLE jobs ADD COLUMN occupation_code text,           -- O*NET-SOC
                 ADD COLUMN required_credentials text[],     -- credential_taxonomy keys
                 ADD COLUMN wage_min numeric, ADD COLUMN wage_max numeric,
                 ADD COLUMN geo geography(Point,4326),
                 ADD COLUMN embedding vector(1536);

-- worker discovery index (materialized or live view)
worker_search_index(applicant_id, trades text[], valid_credentials text[],
                    last_verified_at timestamptz, geo geography, embedding vector(1536),
                    discoverable bool, discoverability_scope jsonb)
CREATE INDEX ON worker_search_index USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON worker_search_index USING gist (geo);
```
**Endpoints (FastAPI, employer-scoped via `require_employer_or_admin`):**
```
GET  /employer/me/workers/search   ?trade=&state=&radius_km=&credential=&q=&page=
                                     -> hybrid (filters + vector), redacted cards, audited
POST /employer/me/postings          (structured create; embeds on write; triggers recompute)
PATCH /employer/me/postings/{id}
```
Reuse the existing fire-and-forget recompute pattern from `POST /employer/me/jobs`.

### (6) Risks
- **Re-identification via narrow filters** (one verified worker in a small trade+ZIP) — enforce a minimum result-set floor or coarsen geo to metro when counts are low.
- **Vector index drift** if embeddings are not regenerated when the taxonomy changes — version embeddings with the model+taxonomy hash.
- **Scraping** of the worker base by a malicious employer account — rate limits + anomaly detection on query volume.

---

## A2. "SKILLED Verify" — instant credential / license checks against the platform DB

### (1) 2026 state of the art
Instant license verification is a solved, commoditized API problem for US trades: providers pull real-time from all 50 state licensing boards and return structured JSON (active status, issue/expiry, bond, workers' comp, classification) for electrical/HVAC/plumbing/refrigeration, typically **~$0.25/lookup**, keyed on **license number** (name searches return false positives). The differentiator in 2026 is not the lookup itself but **continuous monitoring** (re-checking expiry/status on a schedule) and **verifiable credentials** (W3C VC / digital wallets) so a worker can present a cryptographically signed, tamper-evident credential the employer verifies without a live board call.

### (2) Recommended approach
Two-tier verification:
1. **Platform-DB instant check** ("SKILLED Verify"): the fast path. The platform maintains its own `credentials` table populated at onboarding and refreshed by a background job. An employer hitting "Verify" gets an answer from our DB in milliseconds, with a `last_verified_at` freshness stamp.
2. **Source-of-truth re-verification**: when the cached record is stale (> N days) or the employer demands live proof, call an external license-verification API (Cobalt Intelligence / Verified / checklicensed) and update the cache. Issue a **signed verification receipt** (platform-signed JWT/VC) the employer can store as proof-of-check at hire time.

Run a **nightly/weekly Redis-queued sweep** that re-verifies credentials approaching expiry and flips `status` automatically (feeds A4 analytics and the search index).

### (3) Tools/libraries + tradeoffs + cost
- **External verification API**: Cobalt Intelligence / Verified.fast / checklicensed — ~$0.25/lookup, all-50-states real-time. Tradeoff: per-call cost → cache aggressively, only re-verify on staleness/expiry, batch the sweep.
- **Signing**: platform-issued **ES256 JWT** receipts (you already support ES256) or W3C **Verifiable Credentials** via `didkit`/`pyld` if you want wallet-portable proofs. Tradeoff: VC adds standards complexity; start with signed JWT receipts, add VC later if employers ask for portability.
- **Background scheduling**: existing **Redis** + an `arq`/Celery worker (or Railway cron) for the re-verify sweep.

### (4) Security / privacy
- Verification receipts must be **non-repudiable and time-boxed** (include `verified_at`, `expires_at`, source, signer key id) so a stale receipt can't be replayed as current.
- Store only what's needed: license number is sensitive — encrypt at rest (Postgres `pgcrypto` or app-layer envelope encryption) and never return the full number to employers, only masked + status.
- Log every verify action to `audit_logs` (who verified whom, when, source).

### (5) Concrete fit to this stack
```sql
credentials(id, applicant_id FK, taxonomy_key text, license_number_enc bytea,
            issuing_state text, status text,           -- active|expired|revoked|unknown
            issued_at date, expires_at date,
            last_verified_at timestamptz, source text, -- 'platform' | 'cobalt' | ...
            verification_receipt jsonb)                -- signed JWT/VC + metadata
CREATE INDEX ON credentials (applicant_id, status);
CREATE INDEX ON credentials (expires_at) WHERE status='active';  -- powers expiry sweep
```
```
POST /employer/me/verify          {applicant_id, taxonomy_key}
      -> {status, last_verified_at, fresh:bool, receipt_id}   (DB-fast; audited)
POST /employer/me/verify/live     -> forces external re-check, returns signed receipt
# background: arq job re-verifies WHERE expires_at < now()+interval '30 days'
```

### (6) Risks
- **External API outage / coverage gaps** (some boards lack APIs) — degrade gracefully to "last verified on X, source Y," never silently claim "verified."
- **Liability**: a verification receipt is a representation to the employer — make freshness and source explicit; add ToS disclaimer that platform mirrors board data, doesn't certify it.
- **Stale-status false positives** — bound cache TTL; expiring credentials must auto-flip before the sweep via `expires_at` checks at read time.

---

## A3. Subscription tiers + "Pay When They Stay" deferred placement fee

### (1) 2026 state of the art
Stripe Billing in 2026 unifies **recurring (license) fees + metered usage + credits** in a single **pricing plan** composed of **rate cards**; every metered price is backed by a **Meter** object and billed via **Meter Events** (the legacy usage-records API was removed in API version `2025-03-31.basil`). Deferred / contingent fees (pay-on-outcome, "pay when they stay") are not a native Stripe primitive — the production pattern is **Stripe Connect separate charges and transfers** with **delayed/manual payouts** to emulate escrow (Stripe explicitly does not offer escrow, but supports holding funds up to 90 days and a private-preview "funds segregation" feature). The contingent fee itself is implemented as a **deferred one-off `InvoiceItem` / PaymentIntent gated by an outcome event** (retention window elapsed), not as part of the subscription.

### (2) Recommended approach

**Subscription tiers (Free / Standard / Premium):**
- Model each tier as a **Stripe Product** with a recurring **Price** (the license fee).
- Add **metered entitlements** per tier (e.g., # of `SKILLED Verify` live checks, # of worker-search "intros," AI-priority runs) using a **Meter** + metered Price, so overages bill automatically. Free tier = $0 base + hard caps enforced in-app; Standard/Premium = base fee + higher caps + metered overage.
- Use **Entitlements** (Stripe feature flags) or a local `plan_features` table to gate features in FastAPI.

**"Pay When They Stay" deferred placement fee:**
Treat each placement as a state machine with money held until the retention window clears.
1. **Placement reported** (employer marks hire via existing `hire_outcomes`) → create a `placements` row with `retention_days` (e.g., 90) and `fee_amount`.
2. **Authorize / charge**: either (a) **manual capture** PaymentIntent authorized at hire and captured after retention (auth holds expire in 7 days — only viable for short windows), or (b, recommended) **charge at retention milestone**: no money moves until day 90; on the `retention_cleared` event, create a one-off invoice/PaymentIntent for the placement fee.
3. **If marketplace split is needed** (platform takes a cut, training partner/referrer gets a slice): use **Connect separate charges and transfers** — charge the employer to the platform balance, then `Transfer` to connected accounts only after the retention window, using **manual payouts** / delayed transfers as the escrow mechanism.
4. **Refund/no-charge** if the worker leaves before the window: simply never create the charge (model b) or cancel the uncaptured PaymentIntent (model a).

### (3) Tools/libraries + tradeoffs + cost (Stripe primitives — load-bearing)
| Primitive | Use here | Notes / cost |
|---|---|---|
| `Product` + recurring `Price` | Free/Standard/Premium base license fee | Stripe Billing 0.5–0.8% on billed amount (Billing fee) on top of payment processing |
| `Meter` + `MeterEvent` + metered `Price` | Verify checks, intros, AI runs (overage) | Must back every metered price with a Meter (post-`basil`); ingest usage via Meter Events from FastAPI |
| Pricing plan / rate card | Bundle license + metered + credits per tier | Single subscription, single invoice |
| `Entitlements` | Feature gating per tier | Free; or use local `plan_features` |
| One-off `InvoiceItem` / `PaymentIntent` | The deferred placement fee | Billed only on `retention_cleared` |
| Connect **separate charges & transfers** | Split placement fee to partners/referrers; escrow-like hold | Connect: 0.25% + $25 cap payout fee; transfers can be held/delayed up to 90 days |
| **Manual payouts / delayed transfers** | The retention "escrow" window | Stripe is not a legal escrow — disclose in contract |
| `transfer_group` / `transfer_data` / `on_behalf_of` | Tie placement charge to later partner transfers | Group charge + transfers under one placement |

Processing baseline: **2.9% + $0.30** per charge; Connect payout **0.25% (cap $25)**.

**Tradeoffs:** Manual-capture auth (model a) is simplest but auth holds expire ~7 days — unusable for 90-day retention, so use **charge-at-milestone (model b)**. Connect adds onboarding friction (connected accounts need KYC) — only introduce it when partners must be paid; for a pure employer→platform fee, skip Connect entirely and use a plain deferred PaymentIntent.

### (4) Security / privacy
- All Stripe writes go through the **service-role backend** (consistent with existing rule: backend uses service-role key); never expose secret keys to Next.js.
- **Webhook signature verification** (`Stripe-Signature`) is mandatory; process webhooks idempotently keyed on `event.id` (store in `stripe_events`).
- Store only Stripe object IDs + minimal mirror state in Postgres — Stripe is the source of truth for money. Never store raw card data (PCI scope stays with Stripe).
- "Pay When They Stay" needs an **explicit contract / ToS** because Stripe holding ≠ legal escrow; capture employer agreement to the retention terms (`placements.terms_accepted_at`).

### (5) Concrete fit to this stack
```sql
subscriptions(employer_id FK, stripe_customer_id, stripe_subscription_id,
              tier text, status text, current_period_end timestamptz)
plan_features(tier text, feature text, soft_limit int, hard_limit int)  -- gate in API
usage_meters(employer_id FK, feature text, period text, count int)      -- mirror for UI
placements(id, employer_id FK, applicant_id FK, job_id FK,
           fee_amount numeric, retention_days int, hired_at timestamptz,
           retention_cleared_at timestamptz,
           state text,            -- reported|holding|cleared|charged|cancelled|refunded
           stripe_payment_intent_id, transfer_group text, terms_accepted_at timestamptz)
stripe_events(id PK, type, received_at, processed bool)                 -- idempotency
```
**Endpoints:**
```
POST /employer/me/billing/checkout        -> Stripe Checkout/Customer Portal for tier
POST /webhooks/stripe                      -> verify sig, idempotent, update mirrors
POST /employer/me/placements               -> from hire report; sets retention window
# background (arq, daily): placements WHERE state='holding' AND now() >= hired_at + retention_days
#   -> create PaymentIntent (+ Connect transfers if partners), set state='charged'
GET  /employer/me/usage                     -> usage_meters for dashboard
```
Reuse the existing hire flow (`POST /employer/me/jobs/{jid}/candidates/{aid}/hire`) to spawn the `placements` row, and the existing `engagement_events` log for `placement_charged`.

### (6) Risks
- **Stripe ≠ escrow** — legal/compliance must approve "Pay When They Stay" language; consider a true escrow provider (e.g., Escrow.com API) if regulators require segregated funds for your jurisdiction.
- **90-day cap** on held transfers — if a retention window exceeds 90 days, you cannot hold the transfer that long; charge fresh at milestone instead of pre-charging.
- **Disputes/chargebacks** on deferred charges 90 days post-hire — keep strong evidence (hire confirmation, retention proof, signed terms).
- **Metered-billing migration risk** — the legacy usage API is gone; ensure SDK pinned to a post-`basil` version and all meters created up front.

---

## A4. Analytics dashboard: time-to-fill, candidate quality, wage benchmarking, AI weekly summaries

### (1) 2026 state of the art
TA analytics standardized on a small metric set: **time-to-fill** (req open → offer accepted; 2026 nonexec median ~39 days), **quality-of-hire** (hiring-manager rating + retention at 6/12 mo), and **wage benchmarking** against authoritative sources. Wage data is anchored on **BLS OEWS** (free, 830+ occupations, all states + 500+ metros, but 12–18 mo lag) and supplemented by commercial real-time sources (Pave, Levels.fyi, Salary.com) for currency. AI-generated narrative summaries are now expected, but the 2026 consensus is **grounding-first**: compute metrics deterministically, then have the LLM *narrate the numbers it's given*, never compute or infer them — top grounded-summarization hallucination rates fell to ~0.7–1.5% only because the facts are supplied, not generated.

### (2) Recommended approach
- **Deterministic metric layer** in Postgres/SQL: compute time-to-fill, fill rate, funnel conversion, time-in-stage, and quality-of-hire from `jobs`, `placements`, `hire_outcomes`, `engagement_events`. Cache rollups in Redis / a `metrics_rollup` table.
- **Wage benchmarking**: ingest **BLS OEWS** by `occupation_code` × geo into a `wage_benchmarks` table (annual refresh via the free BLS API); show employer's posted wage vs. the regional p25/p50/p75 band. Optionally layer a commercial source for premium tiers.
- **Candidate quality score**: reuse the existing matching engine's `base_fit_score` distribution per posting as a leading indicator, plus post-hire retention as the lagging "quality-of-hire" signal.
- **AI weekly summary**: a templated, **function-calling / structured-input** pipeline — pass the LLM a JSON bundle of the week's computed metrics + deltas; instruct it to ONLY restate and contextualize those figures (no new numbers), validate the output with a numeric-consistency check (regex/extract every number in the summary and assert it appears in the source bundle) before sending.

### (3) Tools/libraries + tradeoffs + cost
- **BLS OEWS / BLS Public Data API** — free; tradeoff: 12–18 mo lag → label data vintage in UI. Premium currency via **Pave** (free <200 emp), **Levels.fyi** (from ~$800/mo), **Salary.com CompAnalyst** — optional, gate behind Premium tier.
- **OpenAI `gpt-4o-mini`** (already used for AI priority) for weekly narrative — cheap; pass metrics as structured context, low temperature.
- **Pydantic + `instructor`** to force the summary into a validated schema and enable retry-on-invalid.
- Charting on the Next.js side (existing components); backend returns pre-aggregated series.

### (4) Security / privacy
- Wage benchmarks shown to employers are **aggregate public data** — no privacy issue, but candidate-quality and funnel metrics must be **scoped to the employer's own jobs** (existing employer-isolation guardrail).
- AI summary input must be **the employer's own aggregates only** — never cross-tenant data in the prompt.
- Cross-employer benchmarks (e.g., "your time-to-fill vs. platform median") must be **k-anonymized** (see Part B / Privacy) — suppress when the cohort is small.

### (5) Concrete fit to this stack
```sql
metrics_rollup(employer_id FK, period date, metric text, value numeric, cohort_n int)
wage_benchmarks(occupation_code, geo_code, p25 numeric, p50 numeric, p75 numeric,
                source text, vintage date)
```
```
GET  /employer/me/analytics/overview     -> time-to-fill, fill rate, funnel (deterministic)
GET  /employer/me/analytics/wages?occupation_code=&geo=   -> posted vs benchmark band
POST /employer/me/analytics/weekly-summary  -> grounded LLM narrative over computed bundle
```
Extend the existing `GET /employer/me/analytics` rather than replacing it; reuse `engagement_events` for funnel stages and `hire_outcomes` for time-to-fill endpoints.

### (6) Risks
- **LLM inventing numbers** in the summary — mandatory numeric-grounding validation; reject and regenerate on mismatch.
- **Stale wage data** misleading employers — always show vintage; consider commercial source for fast-moving trades.
- **Small-sample volatility** (an employer with 2 hires has a meaningless "median time-to-fill") — require minimum n before showing a metric; show "insufficient data."

---

# Part B — Training Programs

## B1. Program profiles & course listings mapped to a credential taxonomy

### (1) 2026 state of the art
Skills/credential data is converging on shared frameworks — **O*NET-SOC** occupations, the **Credential Engine / CTDL** (Credential Transparency Description Language) registry for credentials, and emerging **LER/CLR** (Learning & Employment Records, W3C-aligned) for portable, verifiable learner records. The pattern is a **canonical taxonomy table** with crosswalks, so a course → credential → occupation → job-posting requirement chain is fully linkable and matchable.

### (2) Recommended approach
- A single **`credential_taxonomy`** table (key, label, type, issuing_body, CTDL id, O*NET crosswalk) is the spine the whole platform shares (jobs' `required_credentials[]`, applicants' `credentials`, and programs' `awards[]` all reference it).
- **`training_programs`** (institution profile) → **`courses`** (course listing) → each course `awards[]` one or more taxonomy keys. This makes "which programs lead to the credentials this region's jobs require" a pure join.
- Seed the taxonomy from the existing `supabase/seed.sql` taxonomy reference data; extend with CTDL ids where available.

### (3) Tools/libraries + tradeoffs + cost
- **Credential Engine Registry / CTDL** — open data, free to reference; tradeoff: mapping effort, not all trade credentials are registered → allow local taxonomy entries with optional CTDL linkage.
- **O*NET** — free crosswalks (already implied by your job-family normalization in `packages/etl`).
- Reuse existing **`packages/etl` normalization** to map program names → taxonomy keys (you already map programs → job families).

### (4) Security / privacy
- Program/course data is public-ish (institutional marketing) — low sensitivity. Keep institution edit rights scoped via RBAC (a new `institution` role or extend employer-style isolation).

### (5) Concrete fit to this stack
```sql
credential_taxonomy(key PK, label, ctype text, issuing_body, ctdl_id, onet_codes text[])
training_programs(id, name, institution_profile jsonb, geo geography, partner bool)
courses(id, program_id FK, title, modality text, duration_weeks int,
        awards text[]      -- credential_taxonomy keys
       )
```
```
GET  /programs/browse                ?trade=&state=&credential=
GET  /programs/{id}
POST /institution/me/courses          (RBAC: institution)
```

### (6) Risks
- **Taxonomy drift** between jobs, credentials, and courses — single shared table + foreign keys prevent divergence; version the taxonomy.
- **Incomplete CTDL coverage** for niche trades — local-key fallback.

---

## B2. AI-driven student pipeline (pre-qualified prospects, filterable by trade/location/eligibility)

### (1) 2026 state of the art
This is the same hybrid-search problem as A1, applied to prospective *students*: structured eligibility filters (trade interest, location, age/HS-completion/funding eligibility) + semantic match (essays/intent) + a **deterministic eligibility gate** that mirrors the matching engine's hard-gate philosophy — never bury an eligibility failure inside a soft score.

### (2) Recommended approach
- Reuse the **Layer-1 gates pattern** from `packages/matching`: define program-eligibility hard gates (age, residency, prerequisite credential, funding eligibility) that return `eligible / near_fit / ineligible`, capping the recommendation score on failure.
- Build a **prospect index** analogous to `worker_search_index`: applicants who opted into being shown to training programs, filterable by trade/location/eligibility, ranked by program-fit.
- Consent is mandatory — students must opt in to appear to institutions.

### (3) Tools/libraries + tradeoffs + cost
- Reuse **existing matching engine** (`packages/matching` gates + scorer) — no new dependency; just a program-fit gate config in `SCORING_CONFIG.yaml`-style YAML.
- **pgvector** for intent/essay similarity (already in stack).

### (4) Security / privacy
- **Minors**: trades pipelines include under-18 prospects — gate visibility, require guardian consent where applicable, and minimize stored PII for minors.
- Institutions see **redacted, consented prospect cards**, not raw applicant rows (mirror A1 employer rules).

### (5) Concrete fit to this stack
```sql
prospect_index(applicant_id, trade_interests text[], geo geography,
               eligibility jsonb, embedding vector(1536),
               discoverable_to_programs bool, guardian_consent bool)
```
```
GET /institution/me/prospects/search  ?trade=&state=&radius_km=&eligibility=
                                       -> gated + ranked + redacted (audited, consent-checked)
```

### (6) Risks
- **Eligibility false positives** steering a student into a program they can't fund/enter — hard-gate, show the failed gate explicitly.
- **Minor data exposure** — strict consent + minimization.

---

## B3. Automated scholarship matching + AI pre-filled applications

### (1) 2026 state of the art
Scholarship matching is rules + embeddings (eligibility criteria → student profile). AI pre-fill is a **structured-extraction + guarded-generation** pattern: define the application schema as a **Pydantic model**, use **`instructor`** (schema-validated LLM output with auto-retry) to map the student's stored profile/credentials/essays into the target form fields, leaving anything uncertain blank for human confirmation — never fabricate. 2026 best practice: **human-in-the-loop confirmation** before any application is submitted, because hallucinated answers on a scholarship/program application are high-stakes.

### (2) Recommended approach
- **Matching**: a `scholarships` table with structured `eligibility` (trade, geo, demographic, need) + an embedding of the prose criteria; match against the student profile with hard eligibility gates (reuse the gate pattern) + semantic ranking.
- **Pre-fill**: per scholarship/program, store an application **field schema**; an LLM agent maps the student's verified data → fields, returns a **draft with provenance** (which source filled each field + confidence), surfaces low-confidence/empty fields for the student to complete. Nothing is submitted without explicit student confirmation.

### (3) Tools/libraries + tradeoffs + cost
- **`instructor` + Pydantic + OpenAI** (`gpt-4o-mini`) — schema-validated, retried, cheap; tradeoff: schema authoring per application type.
- Reuse the existing **extraction pipeline** (`packages/extraction`) for parsing essays/resumes into structured signals that feed pre-fill.
- Optional **RAG** over the student's documents for evidence-grounded answers.

### (4) Security / privacy
- Pre-fill touches sensitive data (demographics, financials for need-based aid) — **encrypt at rest**, minimize, and never send more student data to the LLM than the target form requires (field-scoped prompts).
- **Human confirmation gate** is a privacy control too: the student reviews exactly what leaves the platform.
- Audit every pre-fill + submission.

### (5) Concrete fit to this stack
```sql
scholarships(id, name, sponsor, eligibility jsonb, criteria_embedding vector(1536),
             amount numeric, deadline date, application_schema jsonb)
scholarship_applications(id, applicant_id FK, scholarship_id FK,
                         draft jsonb, provenance jsonb, status text,  -- draft|confirmed|submitted
                         confirmed_at timestamptz)
```
```
GET  /applicant/me/scholarships/matches     -> gated + ranked
POST /applicant/me/scholarships/{id}/prefill -> instructor-validated draft + provenance
POST /applicant/me/scholarships/{id}/submit  -> requires confirmed=true
```

### (6) Risks
- **Hallucinated application answers** — schema validation + provenance + mandatory human confirmation; leave uncertain fields blank, never guess.
- **Sensitive-data over-collection** — field-scoped LLM prompts; collect only what each scholarship needs.

---

## B4. Outcomes data feedback to partner institutions (anonymized — k-anonymity / differential privacy)

### (1) 2026 state of the art
Outcomes reporting (employment rate, median wage, time-to-employment by program) is the institution's core ROI signal — but releasing per-graduate rows is a re-identification risk, especially with small cohorts. The 2026 consensus is **defense in depth**: **k-anonymity / small-cell suppression** as the baseline ("never report a cell with < k graduates"), plus **bounded noise / differential privacy** on aggregate statistics (median wage, employment %) so even repeated queries can't triangulate an individual. Note the 2026 caveat: naive k-anonymity alone is increasingly weak against inference attacks — pair it with suppression *and* noise.

### (2) Recommended approach
A **privacy gate** every outcomes feed passes through:
1. **Aggregate only** — institutions receive program×cohort aggregates, never rows.
2. **k-anonymity suppression** — drop or coarsen any cohort with fewer than **k=10** graduates (tune per regulator); coarsen geo/time buckets to meet k.
3. **Bounded noise** — add calibrated noise (Laplace/Gaussian) to released counts and wage stats with a tracked **privacy budget (ε)** per institution per period.
4. **Validate before release** — run `pyCANON` to assert the released table meets k-anonymity (and ℓ-diversity/t-closeness where relevant).

### (3) Tools/libraries + tradeoffs + cost
- **`diffprivlib`** (IBM) — Laplace/Gaussian mechanisms, budget accounting; free. Tradeoff: noise reduces accuracy for small cohorts → suppression handles the smallest, DP handles the rest.
- **`pyCANON`** — verify k-anonymity / ℓ-diversity / t-closeness of the output table; free.
- Optional **SDV** (synthetic data) if institutions want row-level-shaped data for modeling without real individuals — heavier, gate behind partnership tier.
- All run server-side in the FastAPI/Python layer; no extra infra cost.

### (4) Security / privacy
- **Suppression + noise + budget** together — k-anonymity for structure, DP noise for statistics, ε-budget to bound cumulative leakage across repeated reports.
- Outcomes data derives from **employment/wage records** (highly sensitive) — strict access control, institution-scoped, fully audited.
- Document the privacy method + parameters (k, ε) in the report so institutions understand the noise.

### (5) Concrete fit to this stack
```sql
program_outcomes(program_id FK, cohort text, graduates int,
                 employed_rate numeric, median_wage numeric,
                 raw_only_for_internal bool)        -- raw never leaves platform
privacy_budget(institution_id FK, period text, epsilon_spent numeric)
```
```
GET /institution/me/outcomes?program_id=&cohort=
    # pipeline: aggregate -> suppress cells < k -> diffprivlib noise -> pyCANON assert -> return
    # records epsilon spend to privacy_budget; refuses if budget exhausted
```

### (6) Risks
- **Re-identification of small cohorts** — hard k-floor + coarsening; refuse rather than release a thin cell.
- **Utility loss** from over-noising small programs — communicate uncertainty bands; suppress instead of releasing meaningless noisy stats.
- **Budget exhaustion / repeated-query attacks** — enforce ε-budget per institution; deny over-budget requests.
- **k-anonymity-alone weakness vs. inference** — never ship k-anonymity without the noise + suppression layers.

---

## Cross-Cutting Notes (fit to existing SKILLED Pro guardrails)

- **Reuse the three-layer matching philosophy**: hard gates (eligibility/credentials) cap scores in *every* new ranking surface (worker search, prospect pipeline, scholarship match) — never hide a gate failure in a soft score.
- **Backend-only Stripe + service-role writes**, anon key + RLS on the frontend (existing rule).
- **Audit everything**: verify actions, employer searches, placement charges, pre-fills, and outcomes releases all write to `audit_logs`.
- **Background work on existing Redis** (`arq`/Celery or Railway cron): credential re-verify sweep, placement retention-clearing charge job, metric rollups, weekly-summary generation.
- **Consent + redaction** is the default for any cross-tenant exposure of people (workers, prospects).
- **LLMs narrate, deterministic code decides** — grounding-first for summaries; schema-validated, human-confirmed for application pre-fill.

---

## Sources

- Stripe — Implement advanced usage-based billing with pricing plans: https://docs.stripe.com/billing/subscriptions/usage-based/pricing-plans
- Stripe — How advanced usage-based billing works: https://docs.stripe.com/billing/subscriptions/usage-based/advanced/about
- Stripe — Usage-based billing (Meters): https://stripe.com/billing/usage-based-billing
- Stripe Metered Billing Guide for SaaS (2026): https://www.buildmvpfast.com/blog/stripe-metered-billing-implementation-guide-saas-2026
- Stripe — Accept a payment using separate charges and transfers: https://docs.stripe.com/connect/marketplace/tasks/accept-payment/separate-charges-and-transfers
- Stripe — Understand how charges work in a Connect integration: https://docs.stripe.com/connect/charges
- Stripe — Using manual payouts: https://docs.stripe.com/connect/manual-payouts
- Stripe — Place a hold on a payment method: https://docs.stripe.com/payments/place-a-hold-on-a-payment-method
- Stripe Connect for Marketplace Payments Explained (2026 Guide): https://greenmoov.app/articles/en/stripe-connect-for-marketplace-payments-explained-account-types-onboarding-and-pricing-2026-guide
- Cobalt Intelligence — Instant Contractor License Verification API: https://cobaltintelligence.com/blog/resources/contractor-license-api
- Cobalt Intelligence — Contractor Verification License API (2026): https://blog.cobaltintelligence.com/post/contractor-verification-license-api
- CheckLicensed — Contractor License Verification API (50 States, Real-Time): https://checklicensed.com/license
- Verified.fast — Contractor license verification in one API call: https://verified.fast/contractors
- SHRM — 2026 Recruiting Executives Benchmarking (data brief): https://www.shrm.org/in/topics-tools/research/recruiting-benchmarking/full-data-brief
- Pin — 8 Best Salary Benchmarking Tools for Recruiters (2026): https://www.pin.com/blog/salary-benchmarking-tools/
- AIHR — 23 Recruiting Metrics You Should Know: https://www.aihr.com/blog/recruiting-metrics/
- Treegarden — Average Time to Hire 2026 Benchmarks: https://treegarden.io/blog/average-time-to-hire-benchmarks-2026/
- US BLS — Occupational Employment and Wage Statistics (OEWS): https://www.bls.gov/oes/
- Programming Differential Privacy (Near & Abuah, 2026): https://programming-dp.com/book.pdf
- pyCANON — A Python library to check anonymity of a dataset (Scientific Data): https://www.nature.com/articles/s41597-022-01894-2
- IBM diffprivlib / Differential Privacy + Synthetic Data 2026 (Python tutorial): https://dev.to/pankaj_dhawan_fc4c5bf763a/differential-privacy-synthetic-data-in-2026-hands-on-python-tutorial-to-build-bulletproof-ai-57om
- Differential Privacy and k-Anonymity-Based Privacy Preserving Data Publishing (IEEE): https://ieeexplore.ieee.org/document/10275805/
- Grounding LLM Outputs with Structured Real-Time Data (APIClaw): https://apiclaw.io/en/blog/grounding-llm-outputs-with-structured-real-time-data
- Braintrust — Best hallucination detection tools for LLM applications (2026): https://www.braintrust.dev/articles/best-hallucination-detection-tools-2026
- DailyDoseOfDS — Build an automatic form-filling agent (instructor/Pydantic): https://blog.dailydoseofds.com/p/build-an-automatic-form-filling-agent
- Credential Engine — Credential Transparency Description Language (CTDL): https://credentialengine.org/credential-transparency/ctdl/
- O*NET OnLine (occupation taxonomy): https://www.onetonline.org/
