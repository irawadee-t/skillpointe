# FERPA + US State Privacy — Compliance Deep Dive (2026)

> Companion to `08-privacy-compliance-integrations.md`. Production compliance research
> for SKILLED Pro (FastAPI / Supabase / Redis / OpenAI / Stripe / Next.js / Railway).
> **Engineering/compliance research, not legal advice — have counsel review the DPA
> template and the FERPA-applicability determination before signing institutional contracts.**

**Critical framing:** whether FERPA applies depends on data flow. FERPA binds the
*institution*, not the vendor directly; you inherit it *contractually* when an institution
shares student education records and designates you a "school official." If students sign
up directly and you never receive records *from* an institution, FERPA may not apply at all
— but state privacy law (CCPA et al.) will. SKILLED Pro most likely lives in **both** worlds
(institutional-channel = FERPA-governed; direct-consumer = state-law-governed). Architect for both.

---

## PART 1 — FERPA for an EdTech vendor

### 1.1 What FERPA requires (34 CFR Part 99)
Rights for parents / "eligible students" (18+ or postsecondary): **inspect & review**,
**request amendment**, **control disclosure** of PII (consent required unless an exception applies).
- "**Education records**" (§99.3): records (i) directly related to a student and (ii) maintained
  by the institution *or a party acting for it* — the prong that pulls a SaaS vendor in.
- "**PII**" is broad: direct + indirect identifiers **plus** anything "linked or linkable…
  that would allow a reasonable person in the school community… to identify the student with
  reasonable certainty." This catches quasi-identifiers and **embeddings/derived data**.
- "**Directory information**" (name, email, dates of attendance, degrees…) may be disclosed
  without consent *only if* the institution gave notice + opt-out and the student didn't opt out.
  **Never assume directory status** — it's the institution's designation.
- **De-identification** (§99.31(b)): release without consent only after a *reasonable
  determination* that re-identification isn't possible "through single or multiple releases…
  taking into account other reasonably available information." A judgment standard, not a fixed k.

### 1.2 The "School Official" exception (§99.31(a)(1)) — how a vendor qualifies
A vendor is a school official only if it meets **all three**: (1) performs an institutional
service the school would otherwise use employees for; (2) is under the institution's **direct
control** re: use/maintenance of records; (3) is bound by the **§99.33 use/redisclosure limits**
(use only for authorized purposes, no redisclosure). Plus: the institution must define
**legitimate educational interest** in its annual notice, and use **reasonable access-control
methods** — delegated to you technically as least-privilege/scoped access.
- **Use limitation:** PII used **only** for the institution's authorized purposes. **No secondary
  use** — no using student PII to train models for other customers, no advertising, no monetizing.
- **Redisclosure (§99.33):** subprocessors (OpenAI, Supabase/Postgres, Railway, Stripe) that touch
  education-record PII must be bound to the same limits — the legal hook for your subprocessor DPAs.

### 1.3 The institution↔vendor DPA
No FERPA-mandated template for the school-official exception, **but districts/colleges won't buy
without a DPA** — a weak DPA is the top procurement rejection. PTAC's **Written Agreement Checklist**
+ **Vendor FAQ** are what buyers cite. A defensible DPA includes: data ownership (institution/student),
purpose/scope/field-level data inventory, use limitation (**no marketing, no cross-customer model
training**), direct control, redisclosure restriction + subprocessor flow-down, security program
(NIST 800-53/CSF or CIS; encryption in transit + at rest), **contractual breach notice** (FERPA
itself imposes none), audit rights (SOC 2 Type II is the expected evidence), data return/destruction
on termination, and support for institution-fielded access/amendment requests.
- **Studies exception (§99.31(a)(6))** *statutorily requires* a written agreement (purpose/scope/
  duration, use limit, anti-re-identification, destruction when done) — the cleaner basis if you
  build/validate matching models *as a service to the institution*.
- **Audit/evaluation exception (§99.35)** for state authorities; also requires an agreement + destruction.

### 1.4 Technical handling, breach, rights
- **FERPA requires NO breach notification** — its only post-incident mechanic is recordkeeping. But
  state breach laws (all 50), state privacy laws, and your DPA do require notice. The real teeth:
  **§99.67 five-year ban** — ED can bar an institution from sharing records with a vendor that
  improperly rediscloses or fails to destroy PII for ≥5 years (business-ending). FERPA has **no
  private right of action** (*Gonzaga v. Doe*) and no direct vendor fines — the ban is the stick.
- **Security:** "reasonable methods" → tie to NIST/CIS; SOC 2 + NIST-aligned program as baseline.
- **Rights flow through the institution**, not you — but build admin tooling so institutional staff can
  export/inspect and correct/amend a student's records.
- **Load-bearing technical controls:** least-privilege, **per-institution tenant isolation**, audit
  logging of every access to education-record PII, encryption in transit + at rest, minimization.

### 1.5 2026 developments
No recent FERPA rule overhaul (last major: 2011). **March 28, 2025 Dear Colleague Letter** (SPPO)
pressed an enforcement posture favoring **broad parental access** to "all information directly related
to a student" → institutions will demand vendor tooling that surfaces all student-related records on
request. The 2026 pressure is from **states**, not federal FERPA rulemaking; plus amended **COPPA**
(~April 2026 compliance: opt-in for third-party sharing, biometric coverage) if you serve under-13s.

---

## PART 2 — CCPA/CPRA + US state privacy (2026)

- **Rights:** access/know, delete, correct, portability, **opt out of sale AND "sharing"**
  (cross-context behavioral advertising), **limit use of Sensitive PI**, non-discrimination.
- **SPI in scope for SKILLED Pro:** government IDs + financial/account data (credential verification,
  Stripe), precise geolocation (location matching), any health/protected-class data.
- **DSAR:** ≥2 submission methods (online-only direct-relationship businesses may use one);
  **respond in 45 days + one 45-day extension** (notify within first 45); CPPA treats routine
  extensions as non-compliance. Verification tiers: category ≥2 data points; specific pieces ≥3 +
  signed declaration; scale delete verification to risk.
- **GPC is mandatory** — must treat the browser `Sec-GPC` signal as a valid opt-out of sale/sharing
  (basis of the Sephora action). Frontend (Next.js middleware reads `Sec-GPC`) + backend persistence.
- **DELETE Act / DROP** (CA): launched Jan 1 2026; data-broker enforcement Aug 1 2026 — applies only
  if you meet the **data-broker** definition (selling/sharing PI of people with **no direct
  relationship**). A platform serving its own registered users generally is **not** a data broker.
- **~20 states** have comprehensive laws in 2026 (mostly "Virginia-style"): 45-day DSAR SLA,
  **opt-IN for sensitive data** in most (CCPA is the opt-out outlier → design opt-in for SPI to cover
  the majority), growing **UOOM/GPC** mandates, Maryland MODPA stricter (minimization + ban on
  selling sensitive data → design to the strictest common denominator).
- **FERPA interplay:** nearly all state laws have a **data-level** FERPA carve-out (the FERPA-governed
  *records* are exempt; your other data is still covered) — a commercial EdTech vendor does **not** get
  an **entity-level** exemption. **Tag each record with its governing regime.**
- **Minors:** COPPA <13; CCPA opt-in to sell/share <16; many states opt-in for targeted ads/sale 13–17
  + minimization/no-profiling for known minors. Trades cohorts skew 17–18 → **capture DOB, gate teen
  accounts, default minors to no-sale/no-share/no-targeted-ads.**

---

## PART 3 — Fit to the FastAPI + Supabase/Postgres stack
- **Tag governance per record:** add `governing_regime` (`institutional_ferpa` / `direct_consumer` /
  both) + `source_institution_id` to PII tables. Per-user consent table: `opt_out_sale_share`,
  `gpc_applied` (+ ts/source), `spi_use_limited`, `minor` (from DOB), `consent_records` jsonb.
- **DSAR:** `POST /privacy/requests` → background job assembles export from a **central "where PII
  lives per user" registry** (Postgres tables + embeddings/vector store + Stripe + Storage) — partial
  responses are a top enforcement risk. Bind verification to the Supabase Auth session. Route FERPA
  institutional records through institution-admin tooling, not the consumer DSAR path.
- **Delete (hybrid):** (1) soft-delete/tombstone immediately (meets consumer "deleted" expectation +
  rollback window); (2) scheduled hard-delete/crypto-shred (~30 days); (3) **crypto-shredding** for
  Storage + backups (per-user key, destroy key); (4) **cascade** to Postgres, **embeddings/vectors**
  (they're linkable PII), Stripe, OpenAI (zero-retention, no training), Storage. **RLS caveat:** the
  backend uses the service-role key which **bypasses RLS**, so deletion/access correctness must be in
  app code + DB constraints + integration tests, not assumed from RLS.
- **Audit:** append-only `audit_logs` (no UPDATE/DELETE grants) recording every access to education-
  record PII (who/when/which/purpose), disclosures (§99.32), DSAR lifecycle with 45-day timers,
  consent/opt-out/GPC changes, admin overrides.
- **Subprocessors:** DPAs with Supabase/Railway/OpenAI/Stripe flowing down FERPA + state-processor
  obligations; OpenAI = no training/zero-retention + minimize raw PII in prompts; public subprocessor list.

---

## PART 4 — Top risks (prioritized)
1. **FERPA §99.67 five-year ban** — redisclosure / failure-to-destroy = kill-switch for the
   institutional business (highest severity).
2. **Secondary use of student data (esp. LLM training)** — violates school-official use limit + state
   purpose limits. Hard-wire "no cross-customer use, no training on student PII."
3. **Service-role key bypasses RLS** — deletion/access bugs won't be caught by RLS; missed table in a
   DSAR delete = enforcement-grade gap. Central PII registry + erasure integration tests.
4. **GPC not honored** — direct CPRA violation (Sephora); cheap to fix early.
5. **Embeddings/derived data treated as "not PII"** — they're linkable PII; in scope for access + delete.
6. **Minors (17–18) mishandled** — capture DOB, gate, default-protect.
7. **Misclassifying the FERPA carve-out as entity-level** — only the records are carved out; tag per record.
8. **Breach-response gap** — FERPA's no-notice rule lulls; DPAs + 50 state laws require it. Have a runbook.
9. **DSAR completeness/timeliness** — partial exports / routine extensions are themselves violations.

---

## Sources (authoritative first)
- 34 CFR §99.3: https://www.law.cornell.edu/cfr/text/34/99.3 · §99.31: https://www.law.cornell.edu/cfr/text/34/99.31 · Part 99 Subpart D: https://www.ecfr.gov/current/title-34/subtitle-A/part-99/subpart-D
- PTAC Vendor FAQ: https://studentprivacy.ed.gov/resources/responsibilities-third-party-service-providers-under-ferpa · Written Agreement Checklist: https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Written_Agreement_Checklist.pdf · EdTech vendor hub: https://studentprivacy.ed.gov/audience/education-technology-vendors
- FERPA breach (no-notice): https://databreaches.net/ferpa-does-not-require-data-breach-disclosure/ · Studies exception: https://studentprivacycompass.org/ferpa-exceptions-a-study-in-studies/ · FERPA exemptions in state laws: https://publicinterestprivacy.org/ferpa-exemptions/
- 2025 Dear Colleague analysis: https://www.mcguirewoods.com/client-resources/alerts/2025/4/department-of-education-issues-guidance-on-student-privacy-and-parental-rights-imposes-reporting-requirements-for-state-educational-agencies/
- CA AG CCPA: https://oag.ca.gov/privacy/ccpa · CPPA FAQ: https://cppa.ca.gov/faq.html · 2026 statute: https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf
- GPC/Do-Not-Sell-or-Share: https://www.onetrust.com/blog/navigating-the-cpras-do-not-sell-or-share-requirement/ · DSAR mechanics: https://termly.io/resources/guides/ccpa-dsar-requirements/
- 2026 state landscape: https://www.multistate.us/insider/2026/2/4/all-of-the-comprehensive-privacy-laws-that-take-effect-in-2026 · Foley 50-state chart: https://www.foley.com/wp-content/uploads/2026/01/U.S.-State-Comprehensive-Consumer-Privacy-Law-Comparison-Chart_V16.pdf
- Minors/teens 2026: https://natlawreview.com/article/kids-watch-modifications-state-comprehensive-laws · EdTech FERPA/COPPA/SOC2: https://www.thesoc2.com/post/edtech-compliance-2026-ferpa-coppa-and-soc2-requirements-explained
