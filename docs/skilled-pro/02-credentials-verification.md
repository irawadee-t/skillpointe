# Verified Credentials — Production Architecture (2026)

> Synthesized from primary-source research into Credential Engine/CTDL, 1EdTech
> Open Badges 3.0 / CLR 2.0, W3C Verifiable Credentials 2.0, O*NET / CareerOneStop,
> Lightcast Open Skills, AWS Textract, and tamper-evident-logging literature.

**Executive summary.** Model every credential as a **W3C Verifiable Credential 2.0**
(the cryptographic wrapper) carrying an **Open Badges 3.0 / CLR 2.0** payload (the
education meaning), with `Achievement.alignment[]` pointing at **CTDL / Credential
Engine** entities so a worker's badge links machine-readably to a recognized
credential → competencies → (via CTDL) O*NET-SOC occupations — the exact join key
for matching. Normalize free text against a **CTDL + O*NET-SOC + CareerOneStop**
taxonomy (our `taxonomy.py` is the curated seed of this). Verify uploaded documents
with **AWS Textract `AnalyzeDocument` QUERIES**, and make records tamper-evident with
**canonicalized JSON → Ed25519 signature (KMS key) → Postgres hash chain → RFC 3161
timestamp**, anchoring periodically for anti-collusion.

---

## 1. Partner portal for institutions (community colleges / trade programs)

**State of the art.** Multi-tenant B2B portal where each institution is a tenant
with least-privilege RBAC. Two institutional roles: **Institutional Admin** (members,
settings, API keys, billing) vs **Registrar** (uploads + verifies records, no member/
billing access) — a separation-of-duties control appropriate for FERPA-adjacent data.

**Recommended approach.**
- Check **permissions, not roles** (`records:upload`, `records:verify`,
  `members:invite`, `api_keys:manage`), bundled into roles. Every check tenant-scoped
  ("is admin **in this tenant**").
- Strict SoD: Registrar gets `records:*` (minus `bulk_delete`) and **zero** `members:*`,
  `billing:*`, `api_keys:*`, `integrations:*`.
- Invites: token **hashed at rest**, 7-day expiry, single-use, **role bound to the
  invite record** (invitee never self-selects). Block public/disposable domains for any
  domain auto-join; default to **approval mode**.
- Enterprise SSO: support **SAML** (Shibboleth/InCommon is the higher-ed gold standard)
  and OIDC via a broker; prefer **SP-initiated**; map **IdP groups → app roles** with a
  least-privilege default. Add **SCIM** (`active=false` soft-deprovision) when a tenant
  requires lifecycle management — JIT cannot deprovision.

**Fit to stack.** Add an `institutions` tenant table + `institution_members`
(institution_id, user_id, role); reuse existing `audit_logs`. Extend the existing
`/auth/invite-employer` pattern for institution invites. Buy SSO/SCIM via WorkOS/Clerk
rather than hand-rolling SAML XML-signature validation.

**Risks.** Domain-auto-join → org-takeover via DNS; never auto-assign admin by domain.
SAML cert rotation; per-IdP attribute-name variance (mapping must be per-connection).

---

## 2. Ingestion: REST API, SFTP batch, and direct SIS integration

**State of the art / real mechanisms.**
- **Ellucian** — the modern path is the **Ellucian Ethos** integration platform + Ethos
  APIs (REST/JSON, OAuth) which front both **Banner** and **Colleague**. Avoid direct
  Banner Oracle / Colleague access; integrate at Ethos.
- **Workday Student** — SOAP web services + **RaaS** (Report-as-a-Service) custom
  reports exposed as REST/JSON; OAuth2. Enterprise contracting + ISU credentials needed.
- **PeopleSoft Campus Solutions** — Integration Broker (SOAP/REST services) or warehouse
  extracts; oldest/most bespoke.
- **Lowest common denominator that always works:** signed **CSV/SFTP batch** + a REST
  push API. Most community colleges can produce a nightly CSV far sooner than they can
  stand up SIS web services.

**Recommended approach.** Ship **three ingestion lanes** behind one normalization
pipeline: (a) Partner-portal REST push + CSV upload (build first), (b) SFTP batch drop
(PGP-encrypted) polled by a worker, (c) SIS connectors (Ethos first — best ROI; Workday/
PeopleSoft per-customer). Strongly consider a **unified-API aggregator** (Merge.dev HRIS/
ATS; no single vendor covers SIS well) to collapse connector maintenance. Every inbound
record is **idempotent upsert** keyed on `(institution_id, external_student_id,
credential_code)`, with **field-level provenance** stamped (source, received_at, batch_id).

**Fit to stack.** `import_runs`/`import_rows` already exist — reuse them. A
`credential_ingest` worker normalizes each row via `taxonomy.normalize()`, sets
`source='sis'|'partner_portal'`, derives `INSTITUTION_VERIFIED`, and writes a signed
`credential_records` row.

**Risks.** SIS projects are multi-month and contract-gated; FERPA "school official"
agreements required; schema drift across institutions → keep a per-institution field map.

---

## 3. AI/OCR document verification (diplomas, transcripts, union/trade cards)

**State of the art.** **AWS Textract**, **Google Document AI**, **Azure Document
Intelligence** are the three production OCR/IDP engines. For structured field extraction
(GPA, institution, dates, degree, cert number) **Textract `AnalyzeDocument` with the
`QUERIES` FeatureType** is the best fit — ask natural-language questions ("What is the
degree awarded?") and get typed answers. `SIGNATURES` detects sign-off blocks.
- **Not** `AnalyzeID` (US DL/passport only — useless for union/trade cards; use
  `AnalyzeDocument`). **Not** `AnalyzeExpense` (receipts).
- **Pricing (US, mid-2026, per page, additive):** DetectText $0.0015, Queries $0.015,
  Tables $0.015, Forms $0.05, Signatures $0.0035, Layout free-with-Tables. 3-month free
  tier. Multipage transcripts (PDF) **must** use the **async** API + S3.
- **Compliance caveat:** Textract is HIPAA-eligible + FedRAMP High/Moderate, **but AWS
  may store content for service improvement by default** — set an **Organizations AI
  opt-out SCP** before processing FERPA transcripts. English-only for handwriting/queries.

**Recommended approach.** Pipeline: upload → S3 (private, SSE-KMS) → ClamAV scan →
Textract async `AnalyzeDocument [QUERIES, SIGNATURES]` → LLM (gpt-4o-mini) reconciles
extracted fields against the worker's claim + the taxonomy issuer list → **forgery
heuristics** (font/AKAZE tamper checks, metadata, issuer allowlist) → if issuer matched
+ authentic ⇒ `INSTITUTION_VERIFIED`, else queue for human review. Never trust OCR alone.

**Fit to stack.** New `app/integrations/ocr/` adapter (Protocol + Textract impl + a
`NullOCR` dev stub) behind a feature flag; results feed `verification.derive_level`.

**Risks.** Forgery detection is probabilistic — keep a human-in-the-loop review queue
(`review_queue_items` exists). Cost scales per page; cache by document hash.

---

## 4. Credential taxonomy (normalizing all U.S. trade certs/licenses/degrees)

**Authoritative sources to reconcile against (all free / CC-BY):**
- **Credential Engine / CTDL** (`ceterms:Credential`, `ceasn:Competency`) — the registry
  of recognized credentials; the alignment target for Open Badges. CTID identifiers.
- **O*NET-SOC 2019** (`XX-XXXX.XX`, 1,016 occupations; CC-BY 4.0) — occupation anchor;
  rolls up to **2018 SOC** (`left(code,7)`) for BLS wage/projection joins. Crosswalks:
  CIP (program→occupation), RAPIDS (apprenticeship→occupation).
- **CareerOneStop** (free API, Bearer token) — **Certification Finder** (5,700+ national
  certs, voluntary) + **License Finder** (state-issued licenses, mandatory, carry O*NET
  codes). This is where cert/license records actually live — the O*NET DB has none.
  Prefer the **bulk occupational-licenses download** for seeding.
- **Lightcast Open Skills** (open, contract-gated API) — skill IDs for skill-level matching.

**Recommended approach.** Canonical key = **O*NET-SOC 2019 code** for occupations;
credentials keyed by CareerOneStop cert `Id` / license id+state. `taxonomy.normalize()`
(implemented) handles free-text → canonical with confidence + review routing; back it
with a periodic CTDL/CareerOneStop sync that expands the curated seed. Model **one
occupation → many state licenses** (electrician license differs per state). Note EPA 608
is a *federal mandatory* credential catalogued as a *certification* — "mandatory" ≠
"license".

**Fit to stack.** `credentials.canonical_code` already stores the taxonomy code; add
`occupations`, `occupation_credentials`, `occupation_aliases` reference tables loaded from
O*NET + CareerOneStop. **Attribution is mandatory** (O*NET CC-BY, CareerOneStop license) —
add the credit line to the footer.

---

## 5. Cryptographically signed, immutable credential records + audit trail

**State of the art.** Three-layer stack: **W3C VC Data Model 2.0** (REC, May 2025) wrapper
→ **Open Badges 3.0** (Final, May 2024; an OB3 badge *is* a VC) / **CLR 2.0** (Final, Oct
2025) payload → **CTDL alignment**. Secure with **Data Integrity proofs**
(`eddsa-rdfc-2022`, Ed25519) or **VC-JOSE (SD-JWT)** for selective disclosure. Issuer
identity via **`did:web`** (pragmatic for an institutional issuer).

**Tamper-evidence (layered — each defends a distinct threat):**
- Edits/deletes → **Ed25519 signature (KMS/HSM key)** + **Postgres hash chain**
  (`entry_hash = SHA256(content_hash || prev_hash)`; revoke UPDATE/DELETE from app role).
- Backdating → **RFC 3161 trusted timestamp** (freeTSA/DigiCert) of each entry / batch root.
- User repudiation → optional **WebAuthn user-signing** for high-stakes consent.
- Silent full-history rewrite → periodic **external anchoring** of the chain root to a
  transparency log (Sigstore Rekor pattern).

**Recommended pragmatic baseline (implemented now):** canonicalized JSON (sorted keys, →
migrate to RFC 8785 JCS) → **Ed25519** signature → per-applicant **hash chain**
(`credential_records` / `consent_records`). **Next:** move the private key to a KMS, add a
daily RFC 3161 timestamp of the chain head, then Rekor anchoring. Libraries: `PyNaCl` or
`cryptography` (used), `rfc3161-client` (Trail of Bits), a JCS impl.

**Fit to stack.** Implemented in `app/skilled_pro/signing.py` + `credential_records`
table. Migration path to full W3C VC issuance: store the signed VC verbatim as `jsonb`
(preserve canonical bytes — re-serializing breaks Data Integrity proofs) and denormalize
alignment codes into indexed columns for matching.

**Risks.** AWS **QLDB is EOL** (July 31 2025) — do not use; the Aurora migration path
drops built-in verifiability (build it in app code, as we have). Point-release context
URLs (OB `3.0.3`, CLR `2.0.1`) drift — resolve live `purl.imsglobal.org` at build time.

---

## Sources
- Credential Engine / CTDL ↔ Open Badges: https://credentialengine.org/2024/06/18/enhanced-integration-of-ctdl-in-new-open-badges-standard-boosts-credential-clarity/
- Open Badges 3.0: https://www.imsglobal.org/spec/ob/v3p0 · CLR 2.0: https://www.imsglobal.org/spec/clr/v2p0
- W3C VC Data Model 2.0: https://www.w3.org/TR/vc-data-model-2.0/ · Data Integrity: https://www.w3.org/TR/vc-data-integrity/
- O*NET DB (CC-BY): https://www.onetcenter.org/database.html · crosswalks: https://www.onetcenter.org/crosswalks.html
- BLS SOC 2018: https://www.bls.gov/soc/2018/
- CareerOneStop API: https://www.careeronestop.org/Developers/WebAPI/web-api.aspx · license bulk: https://www.careeronestop.org/Developers/Data/occupational-licenses.aspx
- Lightcast Open Skills: https://docs.lightcast.dev/apis/skills
- AWS Textract AnalyzeDocument/Queries: https://docs.aws.amazon.com/textract/latest/dg/API_AnalyzeDocument.html · pricing: https://aws.amazon.com/textract/pricing/
- Ellucian Ethos: https://www.ellucian.com/solutions/ellucian-ethos · Workday Student/RaaS, PeopleSoft IB (vendor docs)
- Merge.dev unified API: https://www.merge.dev/
- RFC 3161: https://www.rfc-editor.org/rfc/rfc3161.html · RFC 8785 JCS: https://datatracker.ietf.org/doc/html/rfc8785 · Sigstore Rekor: https://docs.sigstore.dev/logging/overview/ · immudb: https://docs.immudb.io
- AWS QLDB EOL: https://www.infoq.com/news/2024/07/aws-kill-qldb/
