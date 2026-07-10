# 06 — Mission Dashboard + Perks Marketplace

> Area owner doc for **SKILLED Pro** (nonprofit "SKILLED Nation"). Stack: FastAPI (Python 3.11), Supabase Postgres, Redis, OpenAI, Stripe; Next.js 15; Railway.

**Executive summary.** This document specifies two distinct subsystems that share one verified-identity backbone: a **Mission Dashboard** that turns scholarship → employment → wage-growth records into board/donor-grade impact analytics, and a **Perks Marketplace** that monetizes the verified-trades audience through identity-gated brand offers and commission-tracked redemptions. The mission side is fundamentally a *longitudinal/event-sourced analytics* problem solved with append-only event tables + Postgres materialized views now, graduating to dbt + a warehouse only when outcome data volume and report cadence justify it. The perks side is fundamentally an *eligibility-verification + attribution* problem solved with GovX/SheerID-style gating, signed redemption tokens, and webhook-driven commission ledgers, with PII minimization enforced because the same person is both a donor-reported scholarship outcome and a commercial shopper.

---

# PART A — MISSION DASHBOARD (Nonprofit Impact Analytics)

## A1. Cohort-level outcomes tracking (employment rate, wages, credential attainment, time-to-hire)

### (1) 2026 state of the art
Workforce-outcome reporting has standardized hard around the federal **WIOA primary indicators**: employment rate Q2 and Q4 after exit, median earnings Q2 after exit, credential attainment rate, and measurable skill gains. In August 2025 the U.S. DOL launched a public WIOA performance dashboard aggregating PY2023 data from 550+ local boards, which makes these the *lingua franca* metrics any funder or corporate partner now expects to see. The defining 2025/26 practice is **objective wage verification** — linking participant records to UI wage records / employer payroll / tax data rather than relying solely on self-report — with follow-up surveys as a supplement, not the source of truth.

### (2) Recommended approach
Adopt the WIOA indicator set verbatim as your canonical metric definitions (it makes your impact reports instantly legible to government and corporate funders), but compute them from your own event stream so you are not blocked on external data feeds. Define a **cohort** as a cohort_key = (program, scholarship_round, geography, trade_vertical, entry_quarter). Compute, per cohort:
- `employment_rate_q2`, `employment_rate_q4` (employed at quarter offset N after exit)
- `median_earnings_q2` (median of verified wage events at offset)
- `credential_attainment_rate` (% with a verified credential within the WIOA window)
- `time_to_hire` (days from exit/credential to first verified employment event)
- `wage_growth` (entry wage → latest wage, p50/p90)

Treat self-reported vs. verified as a first-class quality dimension on every metric (`source ∈ {self_report, employer_attested, payroll_linked, ui_wage_match}`) so reports can footnote confidence.

### (3) Tools / libraries + tradeoffs + cost
- **Compute layer:** plain SQL in Postgres + Pandas/Polars in FastAPI for cohort rollups. Cost: $0 incremental. Tradeoff: must be careful with timezone/quarter boundary math (write it once, test it hard).
- **Wage verification source:** UI-wage linkage requires state-by-state data-sharing agreements (slow, high friction). Pragmatic 2026 path: employer-attested + applicant-confirmed wage events now; pursue payroll integrations (Argyle/Pinwheel-style income verification) later if a funder demands payroll-grade rigor.
- **Don't** hand-roll a stats engine; lean on `numpy`/`pandas` quantiles.

### (4) Privacy / compliance
Cohort metrics must be reported as **aggregates only**, with **small-cell suppression** (suppress or bucket any cell with n < 10) — this is the single most common way nonprofits accidentally re-identify a participant in a "wage by trade by county" table. Wage data is sensitive; store raw wage events row-level-secured, expose only aggregates to the dashboard role.

### (5) Fit to THIS stack
- **Data model (new tables):**
  - `scholarship_awards (id, applicant_id, program, round, amount, geography, trade_vertical, awarded_at)`
  - `outcome_events (id, applicant_id, event_type, occurred_at, source, payload jsonb, recorded_at)` — append-only (see A2)
  - `cohort_metrics_mv` (materialized view; see A2/A3)
- **Endpoints (admin-gated, extends existing `/admin/analytics/*`):**
  - `GET /admin/analytics/impact/cohorts?program=&trade=&from=&to=`
  - `GET /admin/analytics/impact/cohort/{cohort_key}`
  - `GET /admin/analytics/impact/funnel` (awarded → enrolled → credentialed → hired → wage-growth)
- Reuses existing `engagement_events` pattern and `require_admin` guard; this is additive, not a rewrite.

### (6) Risks
- **Survivorship/attrition bias:** non-responders skew employment rate up. Mitigation: report denominator and response rate alongside every rate.
- **Definition drift:** if your "employed" definition differs from WIOA, funders will challenge the numbers. Lock definitions in a `metric_definitions` doc/table and version them.
- **Garbage-in:** self-reported wages are noisy; flag confidence explicitly.

---

## A2. Longitudinal tracking: scholarship award → employment history → wage growth

### (1) 2026 state of the art
For records that must reconstruct "what was true at any point in time" (a regulatory/donor-audit requirement), the dominant pattern is **event sourcing**: changes are captured as immutable, append-only events in an event store, and read models ("projections" / materialized views) are derived from the stream. Postgres is a fully legitimate event store in 2026 — append-only event table + projections — and you only reach for dedicated event stores (KurrentDB/EventStoreDB, Marten on Postgres) when you need stream-per-aggregate concurrency guarantees you don't have here. The key benefit for a nonprofit is the **complete audit trail**: every wage and employment fact is reproducible, which is exactly what board/donor audits demand.

### (2) Recommended approach
Use a **lightweight event-sourcing-lite** model, not full CQRS framework adoption:
- One append-only `outcome_events` table keyed by `applicant_id` (the longitudinal subject).
- Event types: `scholarship_awarded`, `program_enrolled`, `program_exited`, `credential_earned`, `employment_started`, `employment_ended`, `wage_reported`, `wage_verified`.
- Each row is immutable; corrections are new compensating events (`wage_corrected`), never UPDATEs. This gives you longitudinal truth + audit trail for free.
- Derive current state and time-series via **projections** (materialized views or incremental tables), not by querying raw events on every dashboard load.

This is "event-sourced records, relational projections" — pragmatic, debuggable, and native to Postgres.

### (3) Tools / libraries + tradeoffs + cost
- **Postgres append-only table + materialized views:** $0, already in your stack, easiest to reason about. Tradeoff: `REFRESH MATERIALIZED VIEW` is whole-view recompute unless you do incremental tables.
- **Marten (if you were .NET) / sqlalchemy + custom projections (Python):** you're Python, so use SQLAlchemy/psycopg + a small projector module in `packages/` (mirrors your existing `packages/matching` pure-logic convention). Tradeoff: you own the projection code.
- **Avoid Kafka/Debezium/RisingWave** at this stage — massive operational overhead for a dataset measured in thousands of participants. Note them only as a future option if you ever do true streaming.

### (4) Privacy / compliance
- The event log is the **system of record for a person's life outcomes** — treat it as your highest-sensitivity store. Restrict raw access to a single service-role path; never expose `outcome_events` to the frontend.
- **Right-to-erasure tension:** event sourcing is append-only, but donors fund people who retain privacy rights. Resolve via **crypto-shredding** (store PII-bearing payload encrypted per-applicant; delete the key to "forget" while preserving the aggregate-safe event shape) rather than deleting events.
- Separate **identity** (who) from **facts** (what happened) so anonymized cohort analytics never need to join to PII.

### (5) Fit to THIS stack
- `outcome_events` lives in Supabase Postgres with RLS denying all client access (service-role writes only — matches your "backend uses service-role key" architecture).
- A `packages/impact/` module (pure Python, no DB I/O, mirroring `packages/matching`) holds projection logic; scripts/ gets `rebuild_projections.py` to recompute from the event log (the event-sourcing superpower: you can always rebuild read models).
- Wage growth time series = projection grouped by `applicant_id` ordered by `occurred_at`.

### (6) Risks
- **Projection drift / bugs:** a buggy projection silently corrupts the dashboard. Mitigation: projections are deterministic + rebuildable from events; add a `verify_projections.py` reconciliation check (mirrors your existing `verify_schema.py`).
- **Schema-on-read sprawl:** `payload jsonb` is flexible but easy to abuse. Define a typed event schema (Pydantic models per event type) and validate on write.
- **Over-engineering:** resist adopting a full CQRS framework; the lite model is sufficient until you have multiple writers contending on one stream.

---

## A3. Warehousing — when to add a warehouse / dbt / materialized views

### (1) 2026 state of the art
The 2026 consensus is a **staged maturity curve**, not "warehouse from day one":
1. **Materialized views in your OLTP db** (Postgres) — for modest data + periodic refresh. dbt's own guidance now treats warehouse-native materialized views / dynamic tables as the near-real-time default rather than always-incremental.
2. **dbt + the same Postgres** (or a read replica) — when transformation logic grows enough that you want version-controlled, tested, lineage-tracked SQL models.
3. **Dedicated warehouse (BigQuery / Snowflake / DuckDB-MotherDuck / Postgres-on-bigger-iron)** — only when analytical queries start hurting transactional performance, or data volume / join complexity exceeds OLTP comfort.

### (2) Recommended approach — explicit triggers for THIS product
Start at **stage 1 (Postgres materialized views), refreshed on a schedule via Redis-backed worker.** Graduate stages on concrete signals:
- **Add dbt when:** you have >~15 derived models, multiple people editing transformation SQL, or you need tested/documented lineage for funder audits. dbt-postgres runs against your existing db — no warehouse required to start. This is the cheap, high-value step.
- **Add a warehouse when ALL of:** impact queries measurably slow the app db (look at p95 on `/admin/analytics/*`), OR you exceed ~tens of millions of event rows, OR you need to blend external datasets (BLS wage benchmarks, state UI data) at scale. For a nonprofit with thousands of participants, this is likely **years away** — say so to stakeholders to avoid premature spend.

Practical refresh strategy: incremental projection tables updated by an event-driven worker on each new `outcome_event`, plus a nightly full `REFRESH MATERIALIZED VIEW CONCURRENTLY` as a safety net.

### (3) Tools + tradeoffs + cost
- **Postgres MVs:** $0, in-stack. Tradeoff: refresh cost grows with data; `CONCURRENTLY` needs a unique index.
- **dbt-core (OSS) on Postgres:** free, runs in CI; dbt Cloud ~$100/dev/mo if you want hosted scheduling/lineage UI. High ROI for testability + audit lineage.
- **DuckDB / MotherDuck:** excellent cheap "analytical sidecar" — embed DuckDB in the FastAPI worker to crunch heavy aggregates over Parquet exports without standing up Snowflake. Great middle option for a nonprofit budget.
- **BigQuery/Snowflake:** powerful but introduces $ + ops + a second data home + PII-replication compliance surface. Defer.

### (4) Privacy / compliance
- Every warehouse you add is **another copy of sensitive outcome data** → another DPA, another breach surface, another erasure target. The compliance cost of a warehouse is a real reason to stay in Postgres longer.
- If/when you export to DuckDB/Parquet for analytics, export **pre-anonymized, cell-suppressed** datasets where possible so the analytical store never holds raw PII.

### (5) Fit to THIS stack
- Refresh worker: reuse your existing Redis + fire-and-forget worker pattern (already used for match recompute) to refresh projections.
- dbt project lives at repo root (`/dbt`) pointing at the Supabase Postgres connection; models = the cohort_metrics / funnel / wage-growth projections, with `dbt test` enforcing not-null / accepted-values on metric definitions.
- `scripts/` gets `refresh_impact_views.py` (callable from cron/Railway scheduled job).

### (6) Risks
- **Premature warehouse spend** — biggest risk; gate it on the explicit triggers above.
- **MV refresh storms** — refreshing on every event at scale can thrash; debounce via Redis (coalesce refreshes within a window).
- **Two sources of truth** — if dbt models and ad-hoc API SQL both compute "employment rate" differently, numbers diverge. Mitigation: API reads *from* the projections/dbt models, never recomputes independently.

---

## A4. AI-generated impact reports for board / donors / corporate partners

### (1) 2026 state of the art
2026 reporting has moved from "text generation" to **artifact generation**: LLMs run sandboxed Python (matplotlib/reportlab) and return real PDF/DOCX/PPTX files. The dominant safe pattern is **deterministic numbers + LLM narrative**: the analytics engine computes the figures and renders charts; the LLM only writes the prose *around* verified numbers and never invents them. "Data storytelling" (charts embedded in branded narrative templates) is the expected output format for board/donor decks.

### (2) Recommended approach
Pipeline: **query projections → render charts (deterministic) → LLM writes narrative grounded in a structured facts blob → assemble templated PDF/PPTX → schedule + export.**
- The LLM input is a JSON of *already-computed* metrics ("Q4 employment rate: 78%, n=142, +6pp YoY"); the prompt forbids numeric invention and requires every claim to cite a field from the blob (extends your existing `PROMPTS.md` convention).
- Three audience templates: **Board** (governance/efficiency), **Donor** (per-dollar impact, individual story highlights with consent), **Corporate partner** (talent-pipeline ROI, trade/geo breakdowns).
- Each report is reproducible: store the facts blob + template version so a report can be regenerated/audited.

### (3) Tools + tradeoffs + cost
- **Charts:** `matplotlib`/`plotly` for static PNG, or **QuickChart** (OSS, can self-host) if you want a stateless chart-image service. Tradeoff: matplotlib = in-process, no extra service.
- **PDF assembly:** `reportlab` (programmatic, precise) or `WeasyPrint` (HTML+CSS → PDF, easiest for branded layouts — reuse your Next.js/Tailwind design tokens as HTML). **WeasyPrint recommended** for brand consistency.
- **PPTX:** `python-pptx` for partner decks.
- **Narrative:** your existing OpenAI integration (`LLM_MODEL=gpt-4o`); cost is a few cents per report — trivial.
- **Scheduling:** Railway cron / scheduled job → FastAPI export endpoint → store to Supabase Storage → email link.

### (4) Privacy / compliance
- **Consent gating for individual stories:** donor reports love named success stories — require an explicit, revocable `story_consent` flag per applicant; default off. Never let the LLM pull a named individual without the flag.
- **Aggregate suppression in generated charts** (n<10) must be enforced *before* the LLM/chart step, not after.
- **No PII in LLM context** beyond consented stories — feed aggregates, not row-level wage data.
- Watermark/version every exported report for auditability; log generation to `audit_logs` (your existing table).

### (5) Fit to THIS stack
- `packages/reporting/` (pure logic: facts-blob builder + chart renderers, no DB).
- Endpoints: `POST /admin/reports/generate` (audience, period, format), `GET /admin/reports/{id}`, `GET /admin/reports` (history). Stored in `report_runs (id, audience, period, template_version, facts_blob jsonb, file_url, generated_by, generated_at)`.
- Scheduled exports via Railway cron hitting an internal generate endpoint; files to Supabase Storage; notify via existing email path.

### (6) Risks
- **Hallucinated numbers** — the cardinal sin in donor reporting. Mitigation: deterministic numbers only; LLM gets a closed facts blob + a validator that rejects any number in the output not present in the blob.
- **Over-claiming causation** — "scholarship caused 78% employment" without a comparison/counterfactual is misleading and erodes funder trust. Use careful framing ("among participants…") and consider a matched comparison cohort later.
- **Stale templates / brand drift** — version templates.

---

# PART B — PERKS MARKETPLACE (Identity-Gated Commerce)

## B1. Identity-gated perks for verified users (GovX / SheerID-inspired gating)

### (1) 2026 state of the art
Gated-offer commerce is mature and consolidated around two players. **SheerID** verifies eligibility against 200,000+ authoritative data sources (2.5B+ people), gates offers to defined "audience segments" (students, teachers, military, essential workers), and in 2025 added a Marketing Hub + DataConnectors into 400+ martech tools. **GovX ID** focuses on military/first-responder gating, uses OAuth 2.0 + JWT, and ships a Shopify app. The model: user proves membership in an eligible group → receives a **single-use, time-bound token/code** redeemable at the brand. For SKILLED Pro the "eligible group" is *verified skilled-trades professional* (and sub-segments by trade/credential) — a novel but structurally identical gate.

### (2) Recommended approach
You **already own the verification asset** (verified credentials are your core product), so you are your own SheerID for the "verified tradesperson" segment — don't pay a third party to re-verify what you've verified. Architecture:
- A **perk eligibility resolver**: given a user, compute their eligible segments from verified credentials (trade vertical, credential level, experience tier, geography).
- Gating issues a **signed, single-use, short-TTL redemption token** (JWT-style, your existing HS256/ES256 infra) carrying segment claims but minimal PII.
- For segments you *can't* verify yourself (e.g., a brand wants "veteran" gating you don't track), integrate SheerID/GovX as a pluggable verifier behind the same resolver interface.

### (3) Tools + tradeoffs + cost
- **Self-verification (recommended primary):** $0 marginal, reuses your credential graph + JWT infra. Tradeoff: you carry fraud risk for your own segments.
- **SheerID:** quote-based, priced on verification volume + number of segments + contract; custom/white-label integrations add ~$5k–$25k+ one-time. Best when you need segments outside your data or want their fraud-mitigation/anti-abuse muscle. Strong GDPR/CCPA posture, consent-based.
- **GovX ID:** simpler, military/first-responder focused, OAuth2+JWT, Shopify-native — good if those specific segments matter and you sell via Shopify.
- Tradeoff summary: build for *your* segment, buy for *adjacent* segments.

### (4) Privacy / compliance
- **Minimal-claim tokens:** the redemption token a brand sees should assert "eligible: HVAC-journeyman, region: TX" — **not** the user's name, scholarship status, or wage. Decouple commercial identity from mission/donor data entirely.
- **Consent + purpose limitation:** verifying for a perk is a different purpose than scholarship reporting; capture separate consent and don't reuse mission data for commerce without it (FTC/state-privacy expectation).
- Honor data-usage transparency à la GovX's "data usage FAQ" — publish what brands receive.

### (5) Fit to THIS stack
- **Data model:**
  - `perk_segments (id, key, definition jsonb)` (e.g., trade=HVAC & credential>=journeyman)
  - `user_perk_eligibility` = computed view from verified credentials (don't store stale copies; derive)
  - `perks (id, brand_id, title, segment_filters jsonb, discount_terms, geo, experience_level, active)`
- **Endpoints:** `GET /perks` (auto-filtered to caller's eligible segments — gating happens server-side, never trust client), `POST /perks/{id}/redeem` (issues signed token / unique code), reusing `apps/api/app/auth/dependencies.py` for identity.
- Eligibility resolver is a pure module (`packages/perks/`), testable like `packages/matching`.

### (6) Risks
- **Leaky gating:** if the frontend filters perks, a savvy user hits the API directly. Mitigation: enforce eligibility server-side on both list and redeem.
- **Credential ≠ entitlement freshness:** revoked/expired credentials must immediately revoke perk eligibility (compute live, short token TTL).
- **Conflating donor data with commerce** — keep a hard wall; mixing them is a privacy and reputational landmine for a nonprofit.

---

## B2. Brand-partner listings targeted by trade vertical, geography, experience level

### (1) 2026 state of the art
Gated marketplaces target offers along the same axes SheerID/GovX expose as "segments" — affiliation, plus increasingly geography and life-stage. The 2026 norm is **server-side, rules-based targeting** (declarative segment filters) with the eligibility evaluated at request time so a single perk catalog serves personalized, compliant views.

### (2) Recommended approach
Model targeting as **declarative predicates** on the perk, evaluated by the same eligibility resolver from B1:
- `segment_filters`: `{ trade_verticals: [...], min_experience: "journeyman", geos: ["TX","OK"], credentials_required: [...] }`.
- Perk is visible iff resolver(user) ⊇ perk.segment_filters. This is the same gate-evaluation primitive — reuse it, don't fork it.
- Give brands a self-serve portal (admin-approved) to define targeting; admin reviews/approves before listings go live (mirrors your existing admin-review philosophy).

### (3) Tools + tradeoffs + cost
- **In-Postgres predicate evaluation** (jsonb filters + your resolver): $0, simplest, plenty fast for a curated catalog. Tradeoff: complex boolean targeting in jsonb gets unwieldy — keep filters flat.
- **Feature-flag / targeting engines (LaunchDarkly, GrowthBook OSS):** overkill for perk targeting; only consider if targeting logic explodes.
- Geo: store ISO state codes; if you ever need radius targeting, PostGIS (already viable in Supabase).

### (4) Privacy / compliance
- Targeting must run on **eligibility attributes, not raw PII** — a brand defines "HVAC journeymen in TX," never sees the list of individuals unless a user redeems.
- **No discriminatory targeting:** ensure targeting axes (trade/geo/experience) don't proxy for protected classes; document the allowed targeting dimensions.

### (5) Fit to THIS stack
- Reuses `perks.segment_filters` + `packages/perks/` resolver from B1.
- **Endpoints:** brand portal CRUD `POST/PATCH /brand/me/perks` (brand-role guard, new role analogous to employer), admin approval `POST /admin/perks/{id}/approve` (writes `audit_logs`).
- New role `brand_partner` in `user_profiles` (extends your existing 3-role RBAC pattern).

### (6) Risks
- **Catalog sparsity per segment:** narrow trades may see an empty marketplace — seed with broadly-eligible national offers.
- **Brand-portal abuse:** require admin approval before listings go live; rate-limit.
- **Stale geo/experience data** degrades targeting quality — recompute eligibility live.

---

## B3. Daily Deals with sponsored placement slots

### (1) 2026 state of the art
"Daily Deals" + **sponsored placement** is standard marketplace monetization: a small number of paid, clearly-labeled premium slots above organic, rotated by time window, with FTC-mandated **"Sponsored"/"Ad" disclosure**. Modern implementations decouple *slot inventory* (positions) from *campaigns* (who's booked which slot when).

### (2) Recommended approach
- A `featured_slots` model with `(slot_position, date/window, perk_id, sponsorship_tier, price)`; a scheduler assigns the day's slots.
- **Organic Daily Deals** = highest-value eligible perks for the user (rank by discount depth + freshness + your commission), **clearly separated** from sponsored slots which are labeled.
- Cache the daily computed deal list in **Redis** (you already run it) with a daily TTL — deals change once/day, so don't recompute per request.

### (3) Tools + tradeoffs + cost
- **Redis** (in-stack) for the cached daily deal set + slot assignments: $0 marginal.
- **Railway cron** to roll the daily window at midnight (per relevant timezone).
- Avoid a full ad-server (Kevel/GAM) — far too heavy for a nonprofit perks page; a simple slot table suffices until you have real ad demand.

### (4) Privacy / compliance
- **Disclosure is a legal requirement, not a nicety:** sponsored slots must be visibly labeled "Sponsored" (FTC). Bake the label into the component, not the data.
- As a **nonprofit**, sponsored placement revenue may be **UBIT (unrelated business income tax)**-relevant — flag for finance/legal; structure as qualified sponsorship where possible. (Engineering note: tag revenue type per slot so accounting can classify it.)

### (5) Fit to THIS stack
- `featured_slots` table + `daily_deals` Redis cache; selection logic in `packages/perks/`.
- **Endpoints:** `GET /perks/daily` (returns eligible organic deals + labeled sponsored slots), `POST /admin/perks/slots` (book/price a slot, admin or brand-portal), all eligibility-filtered server-side.
- Reuses your Redis worker + Railway scheduling already used elsewhere.

### (6) Risks
- **User trust erosion** if sponsored ≈ organic visually — over-disclose.
- **Empty slots** when unsold — fall back to organic deals so the page never looks broken.
- **Tax misclassification** — coordinate slot-revenue tagging with finance early.

---

## B4. Transaction commission tracking (10–18%): attribution, redemption, payouts

### (1) 2026 state of the art
SaaS/marketplace affiliate tracking in 2026 standardizes on **webhook-driven, multi-method attribution with fallbacks**: unique per-affiliate/per-perk **coupon or promotion codes** as the primary signal (robust, fraud-resistant), unique referral links as secondary, and **Stripe webhooks** as the real-time source of truth that triggers commission calculation. Coupon-code attribution is specifically favored because it survives ad-blockers/cookie loss and assigns clean per-source codes for fraud monitoring (anomaly detection on redemption patterns). Tools like Rewardful/Tolt/PartnerStack handle the messy parts (refunds, upgrades, multi-currency).

### (2) Recommended approach
For SKILLED Pro you are the *publisher* taking a **10–18% commission** on transactions you drive to brands — slightly different from classic affiliate-payout-to-affiliates, but the same machinery in reverse:
- **Attribution:** issue a unique, traceable redemption artifact per (user, perk) — either a brand-honored unique code or a tracked redemption link. Store the `redemption` at issuance.
- **Confirmation:** receive conversion via (a) brand postback/webhook, (b) Stripe webhook if the transaction settles through your Stripe (preferred — real-time + authoritative), or (c) periodic brand reconciliation file.
- **Commission ledger:** an append-only ledger computes commission = rate × order_value, with state `pending → confirmed → reversed (on refund) → paid`. Refunds/chargebacks emit reversal entries (never mutate).
- **Payout:** since *brands* pay *you*, generate per-brand commission invoices/statements (monthly) — Stripe Invoicing or Stripe Connect if you intermediate funds.

### (3) Tools + tradeoffs + cost
- **Stripe (in-stack):** webhooks for real-time conversion, Stripe Invoicing for billing brands, Stripe Connect *only* if you take custody of funds (adds KYC/compliance — avoid unless necessary). Cost: standard Stripe fees.
- **Build vs. buy:** Rewardful (~$49–$149+/mo) / Tolt / Trackier are built for paying-out-to-affiliates; your model (collecting commission from brands) is partially inverted, so a **lightweight in-house ledger** is likely cleaner than bending an affiliate SaaS. Tradeoff: you own refund/edge-case logic.
- **Anomaly detection:** simple SQL rules first (redemption velocity, dup codes), ML later.

### (4) Privacy / compliance
- **PCI:** never touch raw card data — Stripe-hosted only.
- **Attribution without surveillance:** prefer coupon-code attribution over heavy cross-site tracking (privacy-friendly + ad-blocker-proof).
- **Nonprofit accounting:** commission income is almost certainly **UBI** — must be cleanly ledgered and reportable to the board/auditors and IRS (Form 990-T). Keep the commission ledger audit-grade and segregated from donation revenue.
- **Financial-action guardrail:** automate *calculation*; keep *money movement* (paying out, issuing refunds) human-approved.

### (5) Fit to THIS stack
- **Data model:**
  - `redemptions (id, user_id, perk_id, brand_id, code, issued_at, status, expires_at)`
  - `commission_ledger (id, redemption_id, brand_id, order_value, rate, commission_amount, currency, state, source, occurred_at)` — append-only
  - `brand_payouts (id, brand_id, period, total_commission, invoice_id, status)`
- **Endpoints:** `POST /perks/{id}/redeem` (issues redemption — B1), `POST /webhooks/stripe` (conversion → ledger entry), `POST /webhooks/brand/{brand_id}` (brand postback), `GET /admin/perks/commissions` (finance view), `GET /brand/me/statements`.
- Logs every conversion to `engagement_events` (extends your existing event taxonomy: add `perk_redeemed`, `perk_converted`).
- Ledger logic in `packages/perks/` (pure), webhook handlers in `apps/api/app/routers/`.

### (6) Risks
- **Attribution leakage / disputes:** brand says the sale wasn't yours. Mitigation: unique codes + signed redemption tokens + timestamped ledger as evidence; reconcile monthly.
- **Refund/chargeback clawbacks:** must reverse commission cleanly — append-only reversal entries; never pay out `pending`, only `confirmed` past a clawback window.
- **Fraud:** code sharing / self-dealing — anomaly rules + single-use tokens + per-user redemption caps.
- **Tax/UBIT exposure** — get this classified by finance *before* launch, not after the first 990.

---

## Cross-cutting: the hard wall between Mission and Commerce

The single most important architectural decision spanning both halves: **mission/donor data and commercial/perks data must not casually join.** The same person is a *scholarship outcome* (highest-sensitivity, donor-reportable, consent-gated, erasure-bound) and a *shopper* (commercial, commission-tracked). Keep them in separate schemas with separate access roles; perks gating reads only `verified_credential` attributes (the minimal eligibility surface), never wage/scholarship rows. This protects donors, satisfies purpose-limitation, and keeps your nonprofit commercial activity (UBI) cleanly separable for tax and audit.

---

## Sources

- [U.S. DOL launches WIOA workforce transparency dashboard (Aug 2025)](https://www.dol.gov/newsroom/releases/eta/eta20250813)
- [WIOA Performance Indicators and Measures — U.S. DOL](https://www.dol.gov/agencies/eta/performance/performance-indicators)
- [DOL Launches Dashboard Detailing Effectiveness of WIOA Programs — SWACCA](https://swacca.org/dol-launches-dashboard-detailing-effectiveness-of-wioa-programs/)
- [ETA Workforce Data Hub — U.S. DOL](https://www.dol.gov/agencies/eta/datahub)
- [9 Key Metrics That Drive Workforce Development Program Success — PlanStreet](https://www.planstreet.com/9-metrics-that-drive-better-workforce-development-program-outcomes)
- [Innovation and Impact Report 2025 — Foundation for California Community Colleges](https://impactreport.foundationccc.org/workforce-development/)
- [Comprehensive Guide to Event Sourcing Database Architecture — RisingWave](https://risingwave.com/blog/comprehensive-guide-to-event-sourcing-database-architecture/)
- [Comparing EventStoreDB/KurrentDB and PostgreSQL — Kurrent](https://www.kurrent.io/blog/comparing-eventstoredb-and-postgresql/)
- [Understanding Event Sourcing with Marten](https://martendb.io/events/learning)
- [dbt — Warehouse-native features for real-time data](https://docs.getdbt.com/best-practices/how-we-handle-real-time-data/3-warehouse-native-features)
- [dbt — Materializations](https://docs.getdbt.com/docs/build/materializations)
- [How to Build an AI Analytics and Reporting Platform with Python, FastAPI, and LLMs — Codersarts](https://www.codersarts.com/post/how-to-build-an-ai-analytics-and-reporting-platform-with-python-fastapi-and-llms)
- [QuickChart — Python chart example](https://quickchart.io/documentation/python-chart-example/)
- [reportAI — Generate PDF reports using LLMs (GitHub)](https://github.com/AdirthaBorgohain/reportAI)
- [Your LLM can write files now — DEV Community](https://dev.to/imaginex/your-llm-can-write-files-now-4c6e)
- [SheerID Expands Identity Verification Platform with Marketing Hub and DataConnectors](https://www.sheerid.com/press-release/sheerid-expands-identity-verification-platform-with-marketing-hub-and-dataconnectors-to-400-martech-solutions/)
- [SheerID Pricing](https://www.sheerid.com/pricing/)
- [SheerID Software Pricing & Plans 2026 — Vendr](https://www.vendr.com/buyer-guides/sheerid)
- [GOVX ID Exclusive Discounts — Shopify App Store](https://apps.shopify.com/govx-id)
- [GOVX ID Verification Technology Now Available on Shopify — GovX](https://www.govx.com/blog/636/govx-id-verification-technology-is-now-available-on-shopify-)
- [GOVX ID Data Usage FAQ — GovX](https://support.govxinc.com/hc/en-us/articles/360044801411-GOVX-ID-Data-Usage-FAQ)
- [How to Track Affiliate Commissions with Stripe — Referral Factory](https://referral-factory.com/learn/how-to-track-affiliate-commissions-with-stripe-without-writing-code)
- [How to Create a Stripe Affiliate Program — Refgrow](https://refgrow.com/stripe-affiliate-program)
- [Best Affiliate Coupon Tracking Tools for SaaS — Rewardful](https://www.rewardful.com/articles/best-affiliate-coupon-trackers)
- [SaaS Affiliate Marketing Commission Rates and Structures — Post Affiliate Pro](https://www.postaffiliatepro.com/blog/saas-affiliate-commission-rates/)
- [Affiliate Marketing Tracking Software 2026 — Fintel Connect](https://www.fintelconnect.com/blog/affiliate-marketing-tracking-software-2026/)
- [Coupon Affiliate Marketing Programs 2025 — Trackier](https://trackier.com/tracking-coupon-affiliate-marketing-programs/)
