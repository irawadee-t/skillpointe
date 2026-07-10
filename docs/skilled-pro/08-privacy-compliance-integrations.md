# Privacy, Compliance & Key Integrations — Production Architecture (2026)

> Synthesized from primary-source research into FERPA (34 CFR Part 99), CCPA/CPRA +
> the 2026 multi-state privacy landscape, AES-256/TLS-1.3/RBAC on Supabase/Postgres,
> KMS envelope encryption, tamper-evident 7-year audit logs, SOC 2 Type II tooling
> (Vanta/Drata), Kantara/ISO 27560 consent records, W3C Verifiable Credentials 2.0 /
> Open Badges 3.0, and unified-integration APIs (Merge.dev/Finch) vs. point connectors.

**Executive summary.** Architect for **two data regimes at once**: institutional student
records governed by **FERPA + a per-institution DPA** (school-official exception), and
direct-consumer data governed by **CCPA/CPRA and ~20 state privacy laws** — tag every PII
row with its governing regime and apply the stricter rule. The security baseline is
**AES-256 at rest + TLS 1.3 (verify-full) + RBAC enforced in the FastAPI backend** (Supabase
RLS protects only the anon path; the service-role key bypasses it), with **app-layer envelope
encryption via AWS KMS** for the most sensitive PII (enabling crypto-shred deletion),
**append-only hash-chained audit logs anchored off-box** to S3 Object Lock for 7 years, and
**SOC 2 Type II via Vanta in ~10 months**. For integrations the verdict splits by category:
**no unified API covers higher-ed SIS** (build direct on Ellucian Ethos first), but for **ATS
a unified API (Merge.dev) clearly beats four point integrations**; Stripe Checkout keeps you
at PCI **SAQ-A**, Cronofy/Nylas beat hand-rolled calendar OAuth, and the **SKILLED Nation**
sync should run on **Redis Streams + transactional outbox** since you control both sides.

---

# PART A — PRIVACY & COMPLIANCE

## 1. Encryption (AES-256 at rest), TLS 1.3, and RBAC

### 1.1 Encryption at rest

- **Baseline (always on, not configurable):** Supabase encrypts all data at rest with
  **AES-256** (AWS EBS volume-level: DB files, indexes, WAL, Storage, backups), keys managed
  by the cloud provider ([supabase.com/security](https://supabase.com/security)). This satisfies
  the "AES-256 at rest" checkbox but is **not a PII control** — a leaked DB credential, SQL
  injection, or stolen `service_role` key all yield plaintext. Disk encryption only defends a
  stolen physical disk.
- **Secrets in-DB → Supabase Vault.** Use Vault (AEAD authenticated encryption; the key is
  never stored alongside data, callers reference a Key ID) for Stripe/OpenAI/service keys
  ([Vault docs](https://supabase.com/docs/guides/database/vault)). **Do NOT use `pgcrypto`** for
  PII — it requires passing the raw key into SQL, which then leaks into logs/replication
  ([supabase blog](https://supabase.com/blog/supabase-vault)). **Do NOT adopt `pgsodium`** TCE —
  Supabase marks it pending-deprecation and recommends no new usage
  ([pgsodium docs](https://supabase.com/docs/guides/database/extensions/pgsodium)).
- **Sensitive PII → app-layer envelope encryption with an external KMS** (recommended). Encrypt
  SSNs, government-ID / license numbers, and precise geolocation **in FastAPI before they reach
  Postgres**, so the DB never sees plaintext. Pattern: KMS `GenerateDataKey` returns a plaintext
  DEK + a wrapped DEK; encrypt locally, discard the plaintext DEK, persist `ciphertext` +
  `wrapped_dek` columns ([AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html)).
  Use **one KEK per tenant + one DEK per record/per-user**. Rotating the KEK is cheap (re-wrap
  the small DEKs only); rotating a per-user DEK by **destroying it (crypto-shredding)** renders
  that user's PII — including in backups — unrecoverable, which is the clean answer to
  right-to-erasure (§3) vs. 7-year-retention (§5) tension.

| KMS | 2026 price | Notes |
|---|---|---|
| **AWS KMS** *(recommended)* | $1/key/mo + $0.03/10k req | FIPS 140-3 L3, auto annual rotation, BYOK import, trivial ops; mitigate per-req cost with DEK caching ([pricing](https://aws.amazon.com/kms/pricing/)) |
| GCP Cloud KMS | $0.06/key-version/mo (sw) | Per-*version* billing; frequent rotation multiplies cost ([pricing](https://cloud.google.com/kms/pricing)) |
| HashiCorp Vault Transit | OSS free + your ops | `/rewrap`, multi-cloud, no per-key fee; you own HA/unseal ([docs](https://developer.hashicorp.com/vault/docs/secrets/transit)) |

> **CMEK/BYOK on Supabase is not a confirmed self-serve managed feature** — confirm with
> Supabase Enterprise before relying on customer-managed keys; the documented path otherwise is
> self-hosting wired to your own KMS.

### 1.2 TLS 1.3 in transit

- **Postgres:** `sslmode=verify-full` (validates chain **and** hostname — `require` alone gives no
  MITM protection on a shared CA) + the Supabase CA cert + "Enforce SSL on incoming connections"
  ([ssl-enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)). In asyncpg build
  an `SSLContext` with `check_hostname=True`, `minimum_version=TLSv1_3`, and verify the negotiated
  version at runtime (Supabase does not publicly document a minimum TLS version).
- **Railway edge:** terminates TLS (1.2+ required, 1.3 negotiated), auto Let's Encrypt, HTTP→HTTPS
  301 ([public-networking](https://docs.railway.com/reference/public-networking)). Note edge→container
  is plaintext HTTP inside Railway's WireGuard-tunneled private network — document this residual.
- **Redis:** prefer `rediss://` + `ssl_min_version=TLSv1_3`. Railway's default Redis has no managed
  TLS endpoint — either self-manage TLS or accept reliance on the WireGuard tunnel; **decide and
  document** (this is also the most likely SOC-2 gap, §6).
- **Next.js:** HSTS `max-age=63072000; includeSubDomains; preload` via `next.config.js` headers.

### 1.3 RBAC (the load-bearing fact)

**`service_role` has Postgres `BYPASSRLS`. RLS does NOT protect any path through the FastAPI
backend** — it only guards the direct anon-key (frontend) path. Therefore:

- **The FastAPI backend is the sole authorization authority** for every backend-mediated query.
  A missing `WHERE employer_id = …` is an IDOR with no DB backstop. Keep the existing pattern:
  roles authoritative in `user_profiles`, centralized role guards (`require_admin`, etc.), every
  query scoped by the authenticated principal in code.
- **Keep RLS enabled and correct on every table anyway** (defense-in-depth + it protects the
  frontend path). Deny-by-default; `USING` vs `WITH CHECK`; index policy columns; wrap auth
  functions in subselects for performance
  ([RLS docs](https://supabase.com/docs/guides/database/postgres/row-level-security)).
- **Field-level access → Pydantic response models per role**, not column GRANTs (Supabase
  discourages column GRANTs — they break `SELECT *`). This is exactly how "admin views employer
  pages read-only, action UI omitted" should be enforced.

## 2. FERPA — institutional student records

**Framing:** FERPA binds the *institution*, not the vendor directly. SKILLED Pro inherits FERPA
obligations **contractually** when an institution shares education records and designates it a
"school official." If a student self-signs-up and no records come *from* an institution, FERPA may
not apply to that record — but state law does. **Most likely SKILLED Pro lives in both worlds.**

- **Education records** (34 CFR § 99.3): records directly related to a student **and maintained by
  a party acting for the institution** — the second prong pulls a SaaS vendor in. **PII** is broad:
  direct + indirect identifiers + *anything linkable to a specific student* — this catches
  quasi-identifiers and **derived embeddings/match features**. Don't assume **directory
  information** status; it's the institution's designation to make
  ([§ 99.3](https://www.law.cornell.edu/cfr/text/34/99.3)).
- **School-official exception** (§ 99.31(a)(1)) — the basis SKILLED Pro will rely on. A vendor
  qualifies only if it (1) performs an institutional function, (2) is under the institution's
  **direct control** re: use/maintenance of records, and (3) is bound by the use/redisclosure
  limits of § 99.33 — **PII used only for the authorized purpose; no secondary use; no using
  student PII to train models for other customers; no redisclosure**
  ([§ 99.31](https://www.law.cornell.edu/cfr/text/34/99.31),
  [PTAC vendor responsibilities](https://studentprivacy.ed.gov/resources/responsibilities-third-party-service-providers-under-ferpa)).
- **DPA contents** (no FERPA-mandated template, but procurement requires it — use the
  [PTAC Written Agreement Checklist](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Written_Agreement_Checklist.pdf)):
  data ownership stays with institution; purpose/scope/field inventory; use limitation (no
  marketing, no cross-customer model training); direct-control + correction/deletion on
  instruction; redisclosure restriction with **subprocessor flow-down** (Supabase, Railway,
  OpenAI, Stripe); a NIST-aligned security program; **contractual breach-notification timeline**;
  audit rights (SOC 2 Type II is the expected evidence); **data return/destruction on
  termination**; support for institutional access/amendment requests.
- **Related exceptions:** the **studies exception** (§ 99.31(a)(6)) *statutorily requires* a written
  agreement and PII destruction when done — the cleaner basis if you ever build/validate matching
  models *for* an institution; the **audit/evaluation exception** (§ 99.35) if reporting outcomes for
  a state workforce program.
- **Breach notification — the surprise:** FERPA imposes **no** breach-notice duty. But (a) all 50
  states' breach laws + state student-privacy laws do, (b) your DPA will, and (c) the real teeth is
  **§ 99.67's five-year ban** — a redisclosure/destruction violation can bar institutions from
  sharing records with the vendor for **≥5 years**, effectively a kill-switch (FERPA has no private
  right of action and no direct vendor fines, so this is the enforcement lever).
- **Rights flow through the institution**, not the consumer DSAR path — build admin tooling for
  institutional staff to export/inspect and correct a student's records.
- **2026 posture:** no recent Part 99 overhaul; the **March 28, 2025 Dear Colleague Letter** signals
  an enforcement stance favoring **broad parental access** (build tooling that can surface *all*
  student-related records on request)
  ([analysis](https://www.mcguirewoods.com/client-resources/alerts/2025/4/department-of-education-issues-guidance-on-student-privacy-and-parental-rights-imposes-reporting-requirements-for-state-educational-agencies/));
  amended **COPPA** (~April 2026 compliance) adds opt-in third-party sharing + biometric coverage if
  you ever serve under-13s.

## 3. CCPA/CPRA + the 2026 multi-state landscape

- **CCPA/CPRA rights** (enforced by the CPPA): access, delete, **correct**, **opt out of "sale" AND
  "sharing"** (sharing = cross-context behavioral advertising), **limit use of Sensitive PI (SPI)**,
  non-discrimination ([CA AG](https://oag.ca.gov/privacy/ccpa),
  [statute eff. 2026-01-01](https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf)).
  **SPI in scope for SKILLED Pro:** government IDs + financial/account data (credential
  verification, Stripe), precise geolocation (job matching), any health/protected-class data.
- **DSAR mechanics:** respond in **45 days** (+ one 45-day extension, *exceptional not routine*);
  tiered verification (≥2 data points for category-level; ≥3 + signed declaration for specific
  pieces). **GPC is mandatory** — you must honor a browser `Sec-GPC` signal as a valid opt-out of
  sale/sharing (the basis of the Sephora action); this is a **frontend + backend** requirement.
- **~20 states** have comprehensive laws in effect in 2026 (most "Virginia-style"). Common threads:
  same access/delete/correct/portability/opt-out rights, **45-day** SLA, **opt-IN for sensitive
  data** in most states (CCPA is the opt-out outlier — so design opt-in for SPI to cover the
  majority), and growing **universal-opt-out/GPC** mandates. Maryland (MODPA) is strictest
  (data-minimization caps + ban on selling sensitive data) — **design to the strictest common
  denominator**
  ([MultiState](https://www.multistate.us/insider/2026/2/4/all-of-the-comprehensive-privacy-laws-that-take-effect-in-2026),
  [Foley chart](https://www.foley.com/wp-content/uploads/2026/01/U.S.-State-Comprehensive-Consumer-Privacy-Law-Comparison-Chart_V16.pdf)).
- **FERPA × state law:** nearly all state laws carry a **data-level** FERPA carve-out (FERPA-governed
  records exempt; everything else covered) — **not** an entity-level exemption. You cannot claim
  "we're EdTech, state law doesn't apply." **Tag each record's governing regime.**
- **Minors:** trades cohorts skew 17–18 (protected-teen band). Capture DOB at signup, gate teen
  accounts, default minors to **no-sale / no-share / no-targeted-ads**; CCPA requires opt-in to
  sell/share under 16.

### 3.1 Concrete fit to FastAPI + Supabase/Postgres

- **Governance + consent columns** on PII tables: `governing_regime` (`ferpa` | `consumer` | `both`),
  source `institution_id`, plus a per-user prefs row (`opt_out_sale_share`, `gpc_applied`+ts+source,
  `spi_use_limited`, `minor` derived from DOB). Honor GPC from Next.js middleware reading `Sec-GPC`.
- **DSAR export/delete:** `POST /privacy/requests` → verify → Redis/RQ background job that assembles
  the export from a **central "where PII lives per user" registry** (Postgres tables, embeddings/vector
  store, Stripe, Storage) — partial responses are a top enforcement risk. **Delete = hybrid:**
  soft-delete tombstone (immediate disappearance from reads + SLA satisfied) → scheduled hard-delete
  / **crypto-shred** (~30 days) → for legally-retained data (Stripe tax records, FERPA records the
  institution still controls) **redact + record the retained-exception basis**. **Cascade** to
  embeddings (they're linkable PII), Stripe, OpenAI (zero-retention terms), and Storage.
- **Audit:** append-only `audit_logs` (§5) records every access to education-record PII, every
  disclosure (the § 99.32 record), every DSAR with its 45-day timer, and every consent/GPC change.
  **Because the backend uses the service-role key (bypasses RLS), deletion/access correctness must be
  enforced in app code + integration tests asserting full erasure** — RLS will not catch a missed
  table.

## 4. Granular consent + cryptographically verifiable consent records

- **Standards:** model consent records on the **Kantara Consent Receipt v1.1** (folded into ISO/IEC
  29184) → **ISO/IEC TS 27560:2023** consent-record information structure (PII principal, PII
  controller, purposes, data categories, recipients, jurisdiction, collection method, policy version,
  UUID-4 receipt ID, lifecycle events). GDPR Art. 7(1) requires you to *demonstrate* consent — the
  record is that proof; withdrawal must be as easy as granting
  ([ISO 27560](https://www.iso.org/standard/80392.html),
  [Kantara](https://kantarainitiative.org/download/consent-receipt-specification/),
  [implementation paper](https://arxiv.org/pdf/2405.04528)).
- **Build vs. buy (CMPs):** OneTrust ($10k annual minimum from Q2 2026; typical $50k–$300k+),
  Osano (free → $199/mo Plus), Ketch ($150–$333/mo), Usercentrics (session-based), Transcend/Ketch
  for DSAR/governance. **Most CMPs are cookie-consent-focused, not first-party data-sharing consent**
  — exactly what SKILLED Pro needs for sharing records with employers/SIS/ATS. **Recommendation:
  build a first-party consent ledger in Postgres** (CMPs don't fit the use case and cost is high);
  optionally add a lightweight CMP later for cookie/GPC banner compliance
  ([CMP buying guide](https://infotrust.com/articles/consent-management-platforms-buying-guide/)).
- **Making records cryptographically verifiable (layered, cheapest-first):**
  1. **Append-only + hash-chaining** — each row stores `prev_hash` and
     `row_hash = SHA-256(prev_hash || canonical_json(payload))`, computed server-side in the write
     transaction; tamper of any row breaks the chain.
  2. **Server-side digital signature** — sign the canonicalized consent payload with an
     Ed25519/KMS key so authenticity is provable independent of the DB.
  3. **RFC 3161 trusted timestamp** (or a Sigstore-Rekor-style transparency anchor) to prove
     *when* — anchor the chain head off-box periodically.
  4. **W3C Verifiable Credential consent receipt** — only if consent must be **portable across
     organizations** (see §B-cross). Standards-buildable but ahead of the market; defer.
- **Postgres data model + API enforcement:**
  ```
  consent_records(
    id uuid pk, subject_id, purpose, scope, recipient, legal_basis,
    terms_version, granted_at, expires_at, revoked_at,
    payload_json, prev_hash, row_hash, signature, rfc3161_token
  )  -- INSERT-only; REVOKE UPDATE/DELETE; revocation is a new row, not an edit
  ```
  **Enforce at the API layer:** every external integration push (employer share, SIS/ATS sync,
  scholarship sync) calls `assert_active_consent(subject_id, purpose, recipient)` **before** the
  outbound call — no valid, unexpired, unrevoked consent ⇒ the share is blocked. This is the
  technical realization of FERPA's "specific written consent" gate for employer sharing (which is
  generally *outside* the school-official exception).

## 5. Append-only, tamper-evident audit logs (7+ years)

The 2026 state of the art is **not** a single managed ledger — **AWS QLDB reached end-of-support
July 31, 2025** and AWS now recommends Postgres + build-your-own audit data
([InfoQ](https://www.infoq.com/news/2024/07/aws-kill-qldb/)). Build the layered pattern on the
Postgres + S3 you already have:

- **Layer A — append-only Postgres:** dedicated INSERT-only `audit_writer` role; REVOKE
  UPDATE/DELETE/TRUNCATE; a BEFORE-UPDATE/DELETE trigger that `RAISE EXCEPTION`s; `pgAudit` for
  statement-level who-ran-what ([supabase audit pattern](https://supabase.com/blog/postgres-audit)).
  Caveat: service-role is superuser-equivalent, so in-DB controls are **evidence, not prevention** —
  the off-box anchor is what makes tampering provable.
- **Layer B — hash chain in the FastAPI write path** (as §4) with `SELECT … FOR UPDATE` on a
  chain-head row to serialize concurrent inserts; **Merkle proofs** when you must show one record to
  a regulator/employer without exposing the whole log; run an independent verifier job that re-walks
  the chain and alerts on mismatch.
- **Layer C — WORM + the 7-year clock:** export aged partitions to compressed Parquet in **S3 with
  Object Lock in Compliance mode** (no one, including root, can delete before the retention date;
  Cohasset-assessed for SEC 17a-4/FINRA) → **S3 Lifecycle to Glacier Deep Archive** (~$0.00099/GB/mo,
  ~23× cheaper than Standard) → query via Athena with partition projection. **For ~5 GB/mo compressed,
  7-year storage costs on the order of low tens of dollars total** — the real cost is the pipeline +
  Glacier retrieval/Athena during audits (keep a thin warm tier).
- **Reconcile retention vs. erasure:** Object Lock Compliance is irreversible — with legal, set
  retention to the exact legal minimum and use **per-user crypto-shred (§1.1)** to satisfy
  right-to-erasure without rewriting immutable backups.

## 6. SOC 2 Type II within 18 months

- **What it is:** an AICPA *attestation* (only a licensed CPA firm issues it). Of the five Trust
  Services Criteria, **only Security (Common Criteria) is required**; scope v1 to **Security +
  Availability + Confidentiality** and add Privacy later. **Type II** tests design *and operating
  effectiveness* over a window (AICPA min 3 mo; 6 mo typical first time)
  ([Drata Type I vs II](https://drata.com/learn/soc-2/type-1-vs-type-2)). Note FERPA — not SOC 2 — is
  your primary *legal* obligation for student records; SOC 2 is the procurement/evidence gate.
- **Timeline (fits 18 mo with margin):** months 1–4 stand up controls (optionally land a Type I as a
  sales artifact) → 6-month observation window → ~6 weeks fieldwork → **Type II in ~8–10 months.**
- **Automation platform — Vanta (recommended):** Supabase itself runs SOC 2 on Vanta (near-exact
  reference), broadest auditor network, startup discounts (~$10–12k yr-1)
  ([vanta.com/customers/supabase](https://www.vanta.com/customers/supabase)). Alternatives: Drata
  ($7.5–15k + impl fee, custom/API-heavy stacks), Sprinto (lowest yr-1), Thoropass (bundles the
  audit). **Decisive caveat: none natively integrate Supabase or Railway** — budget custom-API
  evidence pushes regardless of vendor.
- **Auditor:** pick one **in your platform's network** for auto-mapped evidence — Johanson Group
  ($15–30k, fast) or Prescient ($10–75k, startup/AI-focused, bundles ISO 42001 for LLMs). A-LIGN is
  the enterprise-scale firm you graduate to later.
- **Realistic all-in year one: ~$28k–50k** = platform $5–15k + audit $12–30k + readiness $5–15k +
  **pen test $12–20k** (auditors expect it) + 100–200 staff hours
  ([Drata cost](https://drata.com/learn/soc-2/cost)).
- **Controls/evidence (CC1–CC9):** MFA everywhere, quarterly dated access reviews, same-day
  deprovisioning, encryption, PR-based change management traceable to commits (your `audit_logs`
  maps to CC8), vuln mgmt + annual pen test + tested IR plan, **BCP/DR tested annually**, and a
  **subprocessor inventory with each vendor's SOC 2 report + bridge letters + DPAs** (2026 CC9 now
  probes AI/LLM vendors — i.e. your OpenAI use). The recurring failure mode is "having a control vs.
  proving it operated continuously."
- **Stack notes:** all six vendors hold SOC 2 Type II *on the right tier* (Railway since Aug 2025,
  Supabase on Team/Enterprise, GitHub Enterprise, Stripe + PCI L1, OpenAI, managed Redis). You
  inherit infra security; you **solely own** RLS/RBAC config, secure vendor config, policies/IR/BCP,
  logging/retention, and the subprocessor program. **Flag:** Railway's ~8-hour outage (May 19, 2026)
  if you claim Availability; **self-hosted Redis is the most likely gap** — move to managed or secure
  + document it.

---

# PART B — KEY INTEGRATIONS

**Strategic verdict on unified APIs:** the build-vs-aggregator answer **splits by category**.
**No unified API covers higher-ed SIS** (Merge/Finch are corporate HRIS/payroll/ATS only; Clever/
Edlink are K-12 rostering) — so for SIS you build direct (Ellucian Ethos anchor) or buy the niche
iPaaS Lingk. **For ATS, a unified API (Merge.dev) clearly wins** over four point integrations.
Treat ATS credentials and OAuth refresh tokens as Tier-1 secrets in a real secret store (not Railway
plain env vars), per the student-PII posture.

## 7. Student Information Systems (SIS) — build direct; no aggregator exists

| SIS | Mechanism | Auth | Effort | Notes |
|---|---|---|---|---|
| **Ellucian Banner/Colleague** | **Ethos** REST/EEDM + change events | API key → short-lived JWT | Medium-High (EPN partner gating) | Anchor here — one normalized model covers both ERPs; subscribe to events, not polling |
| **Workday Student** | REST + SOAP/WWS + **RaaS** reports + WQL | OAuth 2.0 / ISU + WS-Security | High (per-tenant) | RaaS for reads, SOAP for writes; per-customer ISU + security-group provisioning |
| **PeopleSoft Campus Solutions** | Integration Broker REST/SOAP, ASF (8.59+), CIs | Institution-configured | High (least standardized) | Co-design service operations per institution |

- **Reality:** SIS integrations are heterogeneous, per-institution, slow, and gated by partner
  programs + institutional IT — **there is no "connect once" higher-ed SIS API.** The dominant cost
  is the per-institution onboarding motion, not the API code.
- **Recommendation:** **Ethos first** (broadest coverage per unit of effort), Workday Student second,
  PeopleSoft last. If per-institution burden becomes the bottleneck, evaluate **Lingk** (iPaaS that
  sits on Ethos and connects Banner/Colleague/Workday Student/PeopleSoft) as a managed-middleware buy.
- **Aggregators don't apply:** **Merge.dev** = HRIS/ATS/CRM/Accounting (no SIS); **Finch** =
  HRIS/payroll (no SIS, no ATS); **Edlink/Clever** = K-12 OneRoster (no higher-ed SIS).
  Sources: [Ellucian Ethos](https://www.ellucian.com/solutions/ellucian-ethos),
  [Workday API](https://community.workday.com/api),
  [PeopleSoft ASF REST](https://newpeoplesoft.wordpress.com/2025/08/06/building-modern-rest-apis-in-peoplesoft-with-application-services-framework/),
  [Merge unified API](https://www.merge.dev/unified-api), [Lingk](https://www.lingk.io/ellucian-banner).

## 8. Applicant Tracking Systems (ATS) — buy the unified API (Merge.dev)

| ATS | Auth | Access gate | Webhooks | Native effort |
|---|---|---|---|---|
| **Greenhouse** | HTTP Basic (API token) + mandatory `On-Behalf-Of`; Onboarding = GraphQL | Self-serve key | Yes (signed) | **Lowest (1–3 wks)** |
| **Lever** | API key (Basic) or OAuth 2.0 Auth Code; 50+ scoped perms; 1-hr tokens + rotating refresh | Self-serve key / OAuth | Yes (HMAC-SHA256) | Low–moderate (2–4 wks) |
| **iCIMS** | OAuth 2.0 **Client Credentials** + optional IP allowlist | Partner application + validation + sandbox | Limited | High (process-gated) |
| **Workday Recruiting** | OAuth (REST) + ISU (SOAP/RaaS), per-tenant | Customer admin / Innovation Partner cert | Limited | **Highest (8–14+ wks)** |

- **Recommendation: Merge.dev unified ATS API** — one integration via hosted OAuth (Merge Link) →
  normalized model + webhooks across 50+ ATSes (Greenhouse, Lever, Workday Recruiting, iCIMS, etc.).
  Pricing is **per Linked Account** (~$650/mo up to 10, +$65 each after) — cheap early, scales with
  connected employers. A pragmatic **hybrid**: build **Greenhouse + Lever native** (high-volume,
  low-effort, partner-friendly) and **proxy Workday + iCIMS through Merge** (partner-gated,
  high-effort, long-tail for trades).
- **Compliance:** Merge inserts a **subprocessor** into the PII flow → requires a Merge DPA, SOC 2
  confirmation, and inclusion in your subprocessor list + customer DPAs. Greenhouse's `On-Behalf-Of`
  gives per-actor attribution (good evidence); Lever's scopes give clean per-tenant least privilege.
- **Infra flags:** **iCIMS IP allowlisting vs Railway's dynamic egress** needs a static-egress/proxy
  solution; Lever's 2 req/s application-POST cap needs a Redis-backed throttle.
  Sources: [Greenhouse Harvest](https://developers.greenhouse.io/harvest.html),
  [Lever OAuth](https://hire.lever.co/developer/oauth),
  [iCIMS partner process](https://developer-community.icims.com/getting-started/partner-application-process),
  [Workday partners](https://www.workday.com/en-us/company/partners/innovation-partners.html),
  [Merge ATS](https://www.merge.dev/blog/guide-to-ats-api-integrations).

## 9. Glassdoor / Indeed verified-data licensing — mostly unavailable; use a tiered alternative

- **Indeed** (Recruit Holdings): offers **job-*posting* management** only (Job Sync GraphQL API,
  partner-gated OAuth; legacy XML feeds sunsetting through 2026) — **no salary/compensation data
  licensing**, and the old job-*search* read API is fully deprecated. Useful only if SKILLED Pro
  *posts* jobs to Indeed as an employer/ATS ([Job Sync](https://docs.indeed.com/job-sync-api/job-sync-api-guide)).
- **Glassdoor**: public/partner API is **dead** (enterprise-partnership-only, opaque pricing since
  2024). **Do not design around it**; scraping violates ToS / CFAA risk
  ([Glassdoor API 2026](https://zuplo.com/learning-center/what-is-glassdoor-api)).
- **Recommended tiered salary stack:** **(1) BLS OEWS** (free, public-domain, authoritative baseline
  by SOC × geo; annual ETL into Postgres) + **(2) Adzuna** (self-serve API-key, live posting-level
  salary distributions; **must license** before commercial use, ~£2.8–5k/mo) + **(3) optional
  premium** — **ADP Real Income** (real-payroll "verified" pay) or **Lightcast Compensation** (OAuth2,
  title/skill-level granularity), both enterprise contract-first.
  Sources: [BLS API](https://www.bls.gov/developers/home.htm),
  [Adzuna histogram](https://developer.adzuna.com/docs/histogram),
  [Lightcast Compensation](https://docs.lightcast.dev/apis/compensation).

## 10. Stripe (payments)

- **Architecture:** **Checkout Sessions in subscription mode + Customer Portal + Entitlements** —
  lowest-effort path that keeps you at PCI **SAQ-A** and gives subscription lifecycle + feature
  gating for free. Drive FastAPI role guards from `active_entitlements` (cached in Postgres/Redis,
  refreshed on the entitlement-summary webhook). Avoid raw Payment Intents (rebuilds tax/discount/
  subscription logic + PCI scope creep).
- **Webhooks (reuse Redis):** read **raw** `await request.body()` → verify HMAC-SHA256 signature with
  the SDK → **enqueue to Redis → return 200 fast** → worker reconciles by refetching from the API
  (delivery is at-least-once and **unordered**, retried up to 3 days). Idempotency: a Postgres UNIQUE
  `event.id` **inserted in the same transaction as the business mutation**. Handle
  `checkout.session.completed`, `customer.subscription.*`, `invoice.payment_succeeded/failed`,
  `charge.dispute.created`. Common pitfall: body-consuming middleware breaking signature verification.
- **PCI DSS 4.0.1:** load **Stripe.js from `js.stripe.com`** (never self-host — breaks SAQ-A); ship a
  strict CSP + Trusted Types; keep analytics/tag-manager scripts **off** any page hosting Elements;
  maintain a script inventory for the new SAQ-A eligibility attestation. Storing brand/last4/exp is
  out of scope — **don't push student PII into Stripe metadata.**
- **Connect:** **skip it** unless employers pay third parties through the platform; then **Express on
  Accounts v2** (offloads KYC).
- **SDK:** pin `stripe==15.3.x`; one `StripeClient` from `get_settings()` (never `os.environ.get()`);
  use `_async` methods in async routes; pin the webhook endpoint's API version deliberately. Radar is
  on by default — add adaptive 3DS for medium-risk.
  Sources: [Checkout vs PaymentIntents](https://docs.stripe.com/payments/checkout-sessions-and-payment-intents-comparison),
  [Entitlements](https://docs.stripe.com/billing/entitlements), [Webhooks](https://docs.stripe.com/webhooks),
  [PCI guide](https://stripe.com/guides/pci-compliance), [stripe-python](https://github.com/stripe/stripe-python).

## 11. Scheduling — Google Calendar + Microsoft Graph (use an aggregator)

- **Google Calendar:** all scopes are **sensitive** (verification + brand review, **no CASA** —
  CASA only applies to *restricted* Gmail/Drive scopes). Use least-privilege
  `calendar.events.freebusy` + `calendar.app.created`. Robust pattern: `events.watch` push →
  incremental `events.list` with stored `syncToken` → 410 GONE = full re-sync, **+ a safety-net poll**
  (push is lossy, channels don't auto-renew — needs a renewal cron).
- **Microsoft Graph:** Entra app, auth-code + PKCE via MSAL, `offline_access Calendars.ReadWrite.Shared`;
  `getSchedule` (≤20 entities) for free/busy, `findMeetingTimes` for smart slots, `POST /events` with
  `isOnlineMeeting` for Teams. Webhook validation handshake (respond to `validationToken` in 10s);
  **subscriptions cap at <7 days** (1 day for rich) → aggressive renewal cron; `calendarView/delta` as
  backstop. Admin-consent friction for app-only flows.
- **Recommendation: use an aggregator over hand-rolling both** — **Cronofy** is the strongest fit for
  interview scheduling: **Smart Invites** (invite candidates with **no recipient OAuth**), **Enterprise
  Connect** (employers connect org-wide once), EU data residency, and **compliance (SOC 2/ISO/HIPAA)
  held on standard plans**; floor ~$819/mo (1,000 accts). **Nylas** if you want email + calendar under
  one vendor (cheapest to prototype, $0 sandbox; but its CASA-skipping Shared GCP App is Enterprise-only).
  Direct OAuth only pays off at very high scale where per-account fees dominate and you can own three
  sync engines + compliance indefinitely.
  Sources: [Google Calendar push](https://developers.google.com/workspace/calendar/api/guides/push),
  [Graph getSchedule](https://learn.microsoft.com/graph/api/calendar-getschedule),
  [Cronofy pricing](https://www.cronofy.com/api-pricing), [Nylas pricing](https://www.nylas.com/pricing/).

## 12. Partner / user-data platforms + SKILLED Nation sync

- **SkillUp Coalition** — the **one external org with a real (partnership-gated) API** for embedding
  curated training/career content. Apply for partnership; integrate **read-only** to enrich the
  matching catalog; **keep student PII out of it** (stays inbound, so FERPA exposure stays low)
  ([SkillUp partners](https://skillup.org/partners)).
- **SkillsUSA** — **no public API**; member data lives in a dated registration portal with
  **CSV/XLSX export** only. Treat as a **batch import** through the existing `packages/etl/` pipeline +
  a data-sharing MOU. Highest FERPA exposure (student minors) → per-institution DPA, purpose-limited
  use ([skillsusa-register.org](https://www.skillsusa-register.org/)).
- **Path to Pro (Home Depot)** — **no developer API**; integration happens only as a negotiated
  corporate BD deal (the ServiceTitan model). Treat as **adjacent/competitor**, not an integration
  target ([Path to Pro Network](https://corporate.homedepot.com/news/trades-training-and-path-pro/home-depot-launches-path-pro-network-unique-jobseeker-platform)).
- **SKILLED Nation ⇄ SKILLED Pro bi-directional sync** (you control both sides — the one to invest in
  first): **NOT shared DB, NOT raw webhooks.** Recommended: **Redis Streams event log + transactional
  outbox + idempotent upsert consumers + nightly reconciliation** (Kafka semantics at a fraction of the
  ops cost, on infra you already run). Service-to-service auth via mTLS or OAuth2 client-credentials
  (reuse existing FastAPI JWT validation). Solve the four hard problems: **idempotency** (stable
  `event_id` + conditional `ON CONFLICT … WHERE excluded.updated_at > target.updated_at`),
  **conflict resolution** (per-field system-of-record + last-writer-wins within owner), **loop
  prevention** (origin-tag every event with `source`), and **drift** (nightly diff/checksum reconcile
  + dead-letter stream). FERPA governs the sync itself: **minimize the payload**, encrypt in transit,
  log every cross-product movement to `audit_logs`, and propagate deletes via a `student.deleted` event.
  Configure Redis persistence (AOF) so the log survives restarts.
  Sources: [events beat webhooks](https://www.stacksync.com/blog/events-beat-webhooks-reliable-data-sync),
  [bidirectional sync without loops](https://truto.one/blog/how-to-sync-customer-data-bidirectionally-between-your-app-and-hubspot/).

## 13. Verified credentials as W3C VCs / Open Badges 3.0 (and consent double-duty)

- **The credential side is production-viable today.** **W3C Verifiable Credentials Data Model 2.0**
  became a W3C Recommendation (May 2025), and **Open Badges 3.0 is literally a profile of W3C VC** —
  an `OpenBadgeCredential` *is* a VC, cryptographically self-verifiable and wallet-portable, with a
  live commercial issuer ecosystem (Credly, Accredible, Canvas Credentials, POK). The trades stack
  layers as **CTDL (description) → Open Badges 3.0 / W3C VC (issuance) → CLR/LER (aggregation) →
  Velocity Network / T3 (network + skills-based hiring)**
  ([VCDM 2.0](https://www.w3.org/TR/vc-data-model-2.0/),
  [Open Badges 3.0](https://www.1edtech.org/standards/open-badges),
  [Velocity Network](https://www.velocitynetwork.foundation/)).
- **Consent double-duty (defer):** "consent receipt as a VC" is buildable from standards (ISO 27560
  payload inside a VC) but **no ratified canonical standard exists and U.S. tradesperson wallet
  adoption is near zero** — it sits ahead of the market. **Recommendation:** model credentials in
  VC/Open Badges-3.0-compatible shapes now (export-ready, integrate an existing issuer rather than
  running key management yourself), build the **signed append-only consent log (§4) aligned to ISO
  27560 today**, and treat consent-as-portable-VC as future optionality gated on real cross-org demand
  — driven downstream by eIDAS 2.0 (EU wallets mandated by end of 2026).

---

## Recommended sequencing

1. **Security baseline first:** TLS `verify-full` everywhere, RBAC enforced in the backend with RLS
   as defense-in-depth, AES-256 confirmed, and **KMS app-layer envelope encryption** for SSNs/IDs/
   geolocation (enables crypto-shred erasure).
2. **Dual-regime data model:** tag every PII row's governing regime; build the DSAR export/delete
   pipeline (central PII registry, soft→crypto-shred), GPC handling, and the **append-only +
   hash-chained `audit_logs`** anchored to S3 Object Lock.
3. **Consent ledger (§4)** with API-layer `assert_active_consent()` gating *every* external share.
4. **SKILLED Nation sync** on Redis Streams + outbox — the one integration fully in your control.
5. **Integrations by ROI:** Stripe Checkout (SAQ-A); Cronofy for scheduling; Merge.dev for ATS;
   Ellucian Ethos for SIS; SkillUp read-only + SkillsUSA batch import; BLS+Adzuna for salary data.
6. **SOC 2 Type II via Vanta** — controls in months 1–4, 6-month window, Type II in ~10 months,
   budget ~$28–50k year one.

> **Caveats before relying on this doc:** (1) FERPA applicability hinges on your actual data flow —
> confirm whether records come *from institutions* (FERPA + DPA) vs. only direct signups; most likely
> both. (2) Confirm Supabase native CMEK/BYOK and the production Redis TLS/SOC-2 posture. (3) This is
> engineering/compliance research, not legal advice — have counsel review the DPA template and your
> FERPA-applicability determination before signing institutional contracts.

---

## Sources

**Encryption / TLS / RBAC**
- Supabase security & encryption at rest: https://supabase.com/security
- Supabase Vault: https://supabase.com/docs/guides/database/vault · pgsodium deprecation: https://supabase.com/docs/guides/database/extensions/pgsodium
- AWS KMS cryptography & pricing: https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html · https://aws.amazon.com/kms/pricing/
- GCP KMS pricing: https://cloud.google.com/kms/pricing · Vault Transit: https://developer.hashicorp.com/vault/docs/secrets/transit
- Supabase SSL enforcement: https://supabase.com/docs/guides/platform/ssl-enforcement · RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Railway public networking: https://docs.railway.com/reference/public-networking

**FERPA**
- 34 CFR § 99.3 / § 99.31: https://www.law.cornell.edu/cfr/text/34/99.3 · https://www.law.cornell.edu/cfr/text/34/99.31
- PTAC third-party responsibilities: https://studentprivacy.ed.gov/resources/responsibilities-third-party-service-providers-under-ferpa
- PTAC Written Agreement Checklist: https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Written_Agreement_Checklist.pdf
- 2025 Dear Colleague Letter analysis: https://www.mcguirewoods.com/client-resources/alerts/2025/4/department-of-education-issues-guidance-on-student-privacy-and-parental-rights-imposes-reporting-requirements-for-state-educational-agencies/

**CCPA / state privacy**
- CA AG CCPA: https://oag.ca.gov/privacy/ccpa · CCPA statute eff. 2026-01-01: https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf
- 2026 state-law landscape: https://www.multistate.us/insider/2026/2/4/all-of-the-comprehensive-privacy-laws-that-take-effect-in-2026
- Foley 50-state comparison (V16): https://www.foley.com/wp-content/uploads/2026/01/U.S.-State-Comprehensive-Consumer-Privacy-Law-Comparison-Chart_V16.pdf
- FERPA exemptions in state laws: https://publicinterestprivacy.org/ferpa-exemptions/

**Consent / verifiable credentials**
- ISO/IEC TS 27560:2023: https://www.iso.org/standard/80392.html · Kantara Consent Receipt: https://kantarainitiative.org/download/consent-receipt-specification/
- Implementing ISO 27560 (arXiv): https://arxiv.org/pdf/2405.04528 · CMP buying guide: https://infotrust.com/articles/consent-management-platforms-buying-guide/
- W3C VCDM 2.0: https://www.w3.org/TR/vc-data-model-2.0/ · Open Badges 3.0: https://www.1edtech.org/standards/open-badges · Velocity Network: https://www.velocitynetwork.foundation/

**Audit logs / SOC 2**
- AWS QLDB end-of-support: https://www.infoq.com/news/2024/07/aws-kill-qldb/ · Supabase audit pattern: https://supabase.com/blog/postgres-audit
- S3 Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html · S3 pricing: https://aws.amazon.com/s3/pricing/
- Vanta (Supabase case): https://www.vanta.com/customers/supabase · Drata cost: https://drata.com/learn/soc-2/cost · Type I vs II: https://drata.com/learn/soc-2/type-1-vs-type-2

**Integrations**
- Ellucian Ethos: https://www.ellucian.com/solutions/ellucian-ethos · Workday API: https://community.workday.com/api · Lingk: https://www.lingk.io/ellucian-banner
- Merge unified API: https://www.merge.dev/unified-api · Greenhouse Harvest: https://developers.greenhouse.io/harvest.html · Lever OAuth: https://hire.lever.co/developer/oauth · iCIMS partner: https://developer-community.icims.com/getting-started/partner-application-process
- Indeed Job Sync: https://docs.indeed.com/job-sync-api/job-sync-api-guide · Glassdoor API status: https://zuplo.com/learning-center/what-is-glassdoor-api · BLS API: https://www.bls.gov/developers/home.htm · Adzuna: https://developer.adzuna.com/docs/histogram · Lightcast: https://docs.lightcast.dev/apis/compensation
- Stripe Checkout vs PI: https://docs.stripe.com/payments/checkout-sessions-and-payment-intents-comparison · Entitlements: https://docs.stripe.com/billing/entitlements · Webhooks: https://docs.stripe.com/webhooks · PCI: https://stripe.com/guides/pci-compliance · stripe-python: https://github.com/stripe/stripe-python
- Google Calendar push: https://developers.google.com/workspace/calendar/api/guides/push · Graph getSchedule: https://learn.microsoft.com/graph/api/calendar-getschedule · Cronofy pricing: https://www.cronofy.com/api-pricing · Nylas pricing: https://www.nylas.com/pricing/
- SkillUp partners: https://skillup.org/partners · SkillsUSA register: https://www.skillsusa-register.org/ · Path to Pro Network: https://corporate.homedepot.com/news/trades-training-and-path-pro/home-depot-launches-path-pro-network-unique-jobseeker-platform
- Events vs webhooks: https://www.stacksync.com/blog/events-beat-webhooks-reliable-data-sync · Bidirectional sync without loops: https://truto.one/blog/how-to-sync-customer-data-bidirectionally-between-your-app-and-hubspot/
