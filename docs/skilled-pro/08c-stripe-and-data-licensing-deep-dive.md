# Stripe Billing + Salary-Data Licensing — Deep Dive (2026)

> Companion to `05-employer-training.md` (monetization) and `08`. Stripe verified against
> docs.stripe.com; data-licensing verified against BLS/Lightcast/Adzuna/Indeed/Glassdoor
> primary sources. Research, not implementation.

## A. Stripe (employer subscriptions + "Pay When They Stay")

**Net recommendation:**
1. **Checkout Sessions (subscription mode) + Customer Portal + Entitlements** — covers the
   whole subscription product with minimal code and keeps you at **PCI SAQ-A**. Avoid raw
   Payment Intents (rebuilds tax/discount/subscription logic, more PCI scope).
2. **Entitlements API** to gate tier features: attach Features to Products; read
   `active_entitlements`, cache in Postgres/Redis keyed by `stripe_customer_id`, refresh on
   the `entitlements.active_entitlement_summary.updated` webhook, check in FastAPI role
   guards. (Eventually consistent — refetch via API for security-critical gates.)
3. **Webhooks the right way (fits existing Redis):** read **raw** `await request.body()` →
   verify signature with the SDK → **enqueue to Redis** → return 200 fast → worker reconciles
   by refetching from the API. Idempotency: persist `event.id` with a UNIQUE constraint **in
   the same DB transaction as the business mutation**. Handle out-of-order delivery (no
   ordering guarantee; retries up to 3 days). Core events: `checkout.session.completed`,
   `customer.subscription.created/updated/deleted`, `invoice.paid|payment_failed`,
   `customer.subscription.trial_will_end`, `entitlements.*`, `charge.dispute.created`.
   **FastAPI pitfall:** body-parsing middleware that consumes the stream before verification
   breaks signatures — use the raw body.
4. **"Pay When They Stay" deferred placement fee:** charge-at-milestone (retention window
   elapses → create charge) + Stripe **Meters** for any usage-billed metric. If money ever
   flows to third parties (paying instructors/applicants), add **Connect Express on Accounts
   v2** (Dec 2025) — but **skip Connect** for plain employer-subscriptions.
5. **PCI SAQ-A (DSS 4.0.1):** load **Stripe.js from `js.stripe.com`** (never self-host/bundle
   — voids SAQ-A), strict **CSP + Trusted Types**, keep analytics/tag-manager scripts **off**
   any page hosting Elements, keep a script inventory (new 4.0.1 eligibility attestation).
   Prefer hosted Checkout to minimize your scripts on the payment surface.
6. **Radar** on by default + **adaptive 3DS** step-up for medium risk; add Radar for Fraud
   Teams at scale.
7. **SDK:** pin `stripe==15.3.x` in `requirements.txt`; one **`StripeClient`** built from
   `get_settings()` (never `os.environ.get()` per CLAUDE.md); use **`_async`** methods in
   async routes; deliberately pin the webhook endpoint's API version (schema stability).

Sources: Checkout vs PaymentIntents https://docs.stripe.com/payments/checkout-sessions-and-payment-intents-comparison ·
Entitlements https://docs.stripe.com/billing/entitlements · Webhooks https://docs.stripe.com/webhooks ·
Connect accounts https://docs.stripe.com/connect/accounts · PCI guide https://stripe.com/guides/pci-compliance ·
PCI 4.0.1 scripts https://www.humansecurity.com/learn/blog/pci-dss-4-0-1-updates-to-browser-script-requirements/ ·
stripe-python https://pypi.org/project/stripe/

## B. Salary / labor-market data licensing

**Bottom line:** the brand names you'd expect — **Indeed and Glassdoor — do NOT sell a
verified-salary API** in 2026. Build the wage layer from **BLS (free) + a commercial
benchmark vendor + an aggregator for posting-level pay.**

| Source | What it gives | Access / cost | Verdict |
|---|---|---|---|
| **BLS OEWS** (api.bls.gov) | Authoritative wages by SOC × geo (mean + percentiles), annual | **Free** (v2 free key) | ✅ **Foundation** — defensible "verified" floor; annual ETL into Postgres |
| **Adzuna** | Posting-level **salary distribution/trends/histogram**, 12+ countries | Self-serve `app_id`+`app_key`; **must license for commercial use** (~£2.8–5k/mo) | ✅ **Live market layer** (lowest-effort commercial; posting-derived, not verified-paid) |
| **Lightcast Compensation/Market Salary** | Title/skill/region pay + postings, 160k+ sources | OAuth2 client-creds; **sales-gated, 5-figure+** | 🟡 Premium enrichment (granular) |
| **ADP DataCloud / Real Income** | Benchmarks off **42M+ real payroll records** | Enterprise license | 🟡 Strongest "**verified actual-pay**" claim |
| **Payscale** | Large comp dataset + HCM integrations | Enterprise | 🟡 Alternative premium |
| **Indeed** | **Job Sync/Apply APIs (posting only, no salary)**; XML feeds deprecating 2026 | Partner-gated OAuth2 | ⚠️ Only if posting jobs as an ATS |
| **Glassdoor** | — | **Closed** (enterprise-only, opaque); scraping = ToS/CFAA risk | ❌ Avoid as a source |
| Scraped vendors (Bright Data, Coresignal, TheirStack…) | Breadth of postings, some salary | $59–$1.5k+/mo | ⚠️ Salary is scraped/posting-derived; get redistribution-rights reps |

**Recommended tiered stack:** **BLS OEWS (free baseline)** → **Adzuna (live posting pay,
licensed before launch)** → **ADP Real Income *or* Lightcast (premium, when funded)**.
Do **not** architect around Indeed/Glassdoor branded salary feeds — not realistically
obtainable via API in 2026. Map the trades taxonomy → SOC for BLS; cache all of it (data is
not real-time) via the existing ETL pattern (`scripts/import_bls_oews.py`). **Attribution +
license terms matter** — confirm display vs. redistribution rights per vendor before showing
raw figures to end-users.

Sources: BLS https://www.bls.gov/developers/home.htm · OEWS https://www.bls.gov/oes/tables.htm ·
Adzuna https://developer.adzuna.com/overview , terms https://developer.adzuna.com/docs/terms_of_service ·
Lightcast Compensation https://docs.lightcast.dev/apis/compensation · ADP DataCloud
https://www.adp.com/what-we-offer/products/adp-datacloud.aspx · Indeed Job Sync
https://docs.indeed.com/job-sync-api/job-sync-api-guide · Glassdoor API status
https://zuplo.com/learning-center/what-is-glassdoor-api
