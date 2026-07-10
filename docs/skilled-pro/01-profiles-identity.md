# SKILLED Pro — User Profiles & Identity (Production Architecture, 2026)

**Executive summary.** This document specifies a production-grade design for the User Profiles & Identity capability of SKILLED Pro — covering consent-gated profile seeding from external application data, editable trade/cert/employment/portfolio records with secure media uploads, tiered verification badges grounded in the W3C Verifiable Credentials / Open Badges 3.0 standards, AI-generated summaries with server-side PDF resume export, and a visual career-ladder built on a Postgres-resident skills/credential graph. Every recommendation is tailored to the existing stack: **Next.js 15 (React 19) + FastAPI (Python 3.11) + Supabase (Postgres/Auth/Storage) + Redis + OpenAI, deployed on Railway.** The opinionated through-line is *stay in your existing primitives wherever the standards allow* — Supabase Storage + a transform/scan layer for media, Postgres (no graph DB) for the credential graph, WeasyPrint for PDFs — and only reach outside (Mux for video, a VC issuance library) where the bar is genuinely higher.

---

## 1. Auto-Generated Profiles from External Application Data (Consent-Gated)

### 1.1 State of the art (2026)

The mature pattern for seeding profiles from a partner/source system is a **three-stage pipeline**: (1) land raw external records in a staging table untouched, (2) transform/normalize into canonical shape, (3) idempotent upsert into live tables keyed by a stable natural key — all **gated behind an explicit consent state** that is enforced at *every* downstream data flow, not just collected once at import. The 2026 regulatory reality (CPRA's ADMT rules effective Jan 1 2026, and the shift CMPs describe from "consent collected" to "consent enforced everywhere") means consent is now a first-class column that travels with the record and is checked on read, not a one-time checkbox. For a platform that makes automated recommendations and matches, this matters directly: profile data used for automated decision-making sits squarely inside the new ADMT/opt-out obligations.

### 1.2 Recommended approach (opinionated)

1. **Land then transform.** Import raw partner rows into `profile_import_staging` verbatim (jsonb payload + provenance). Never write external data straight into `applicants`/profile tables. This makes re-runs safe, gives you an audit trail, and decouples partner schema drift from your live schema. You already have this muscle (`import_runs` / `import_rows`) — reuse it.
2. **Consent gate before activation, not before import.** Importing into staging is fine (you're a processor with a contract/consent basis from the partner). What requires consent is **activating** the profile into a live, recommendable, employer-visible entity. Model a `profile_status` lifecycle: `seeded` → (consent captured) → `active`. A `seeded` profile is invisible to employers and excluded from matching until the worker claims it and consents.
3. **Idempotent upsert keyed by a stable natural key.** Use `INSERT ... ON CONFLICT (source_system, source_external_id) DO UPDATE` so a re-import never duplicates and never silently clobbers worker edits. Critically: **never overwrite worker-edited fields with stale source data.** Track per-field provenance/dirty flags so the upsert only refreshes fields the worker hasn't touched.
4. **Consent enforced on read.** Matching, employer surfacing, and AI summary generation all check `consent_status = 'granted'` and `profile_status = 'active'`. Keep a `consent_events` append-only log (granted/withdrawn, scope, timestamp, IP, version of terms) — this is your proof-of-consent record that 2026 enforcement expects.

### 1.3 Data model sketch

```sql
-- Raw landing (reuses your import_runs pattern)
create table profile_import_staging (
  id              uuid primary key default gen_random_uuid(),
  import_run_id   uuid references import_runs(id),
  source_system   text not null,            -- 'partner_ats_x'
  source_external_id text not null,         -- stable id in source
  raw_payload     jsonb not null,
  processed_at    timestamptz,
  unique (source_system, source_external_id, import_run_id)
);

-- Provenance + consent on the live profile (extend applicants)
alter table applicants
  add column source_system        text,
  add column source_external_id   text,
  add column profile_status        text not null default 'active', -- seeded|active|suspended
  add column consent_status        text not null default 'none',   -- none|granted|withdrawn
  add column consent_version       text,
  add column field_provenance      jsonb default '{}'::jsonb;       -- {"trade":"worker","phone":"source"}
create unique index on applicants (source_system, source_external_id)
  where source_system is not null;

create table consent_events (
  id            uuid primary key default gen_random_uuid(),
  applicant_id  uuid references applicants(id),
  event         text not null,          -- granted|withdrawn
  scope         text[] not null,        -- ['matching','employer_visibility','ai_summary']
  terms_version text not null,
  actor         text not null,          -- 'worker'|'admin'|'system'
  ip            inet,
  created_at    timestamptz not null default now()
);
```

### 1.4 Endpoints / services

- `POST /admin/imports/profiles` — kick off a staged import run (admin only; writes staging).
- Worker **claim flow**: `POST /applicant/me/claim` (matches a `seeded` row by verification token sent to the worker), then `POST /applicant/me/consent` records a `consent_events` row and flips `consent_status='granted'`, `profile_status='active'`.
- `POST /applicant/me/consent/withdraw` — writes a `withdrawn` event, removes from matching/employer visibility, and (per CPRA) triggers deletion/anonymization workflow if scope requires.
- Service: an idempotent `upsert_profile_from_staging()` that respects `field_provenance` and never touches worker-dirty fields.

### 1.5 Security / privacy / compliance

- **Lawful basis to import vs. to activate are different** — keep them separate in code and in your DPA with the partner. Document the basis per scope.
- **Withdrawal must propagate** — consent is enforced on read everywhere, and withdrawal triggers the deletion/opt-out path (CPRA 2026 wants real-time enforcement, not just a stored flag).
- **Sensitive data minimization** — do not import fields you won't use; trade/license data can proxy protected attributes.
- **Audit everything** — your existing `audit_logs` guardrail applies to every admin import/override.

### 1.6 Risks / gotchas

- **Clobbering worker edits on re-import** is the classic failure — the `field_provenance` map is non-optional.
- **Orphaned `seeded` profiles** that are never claimed accumulate PII you have no consent to keep; set a TTL purge.
- **Identity collision on claim** (two people, same name/phone) — require a token-based claim, never fuzzy auto-merge.

---

## 2. Editable Profile + Portfolio Media (Image / Video / Doc)

### 2.1 State of the art (2026)

The settled best practice is **direct, signed client-to-storage uploads** (the backend signs the upload; bytes never transit your API server), with **CDN edge delivery** and **a security layer between upload and "ready"** (virus scan + metadata strip + transcode). The clear 2026 fork is image/doc vs. **video**: object storage like Supabase Storage handles images and documents well (it now has an image-transformation layer and CDN), but it does **not transcode video or do adaptive streaming** — for video you want a purpose-built service. Mux's chunked/resumable upload + just-in-time HLS transcode is the reference design for worker-recorded portfolio video.

### 2.2 Recommended approach (opinionated)

- **Images + documents (resume PDFs, cert scans, photos): Supabase Storage.** Private buckets, RLS-scoped, signed-URL upload, built-in image transformation + CDN. Zero new vendor; consistent with your auth model.
- **Video: Mux.** Use Mux Direct Uploads (resumable, survives flaky job-site connectivity) → Mux returns an `asset_id` + `playback_id`; store those, stream HLS via Mux's CDN. Do not try to make Supabase Storage stream adaptive video.
- **Scan-before-publish for everything.** New uploads land in a quarantine/`pending` state; an async worker scans (ClamAV) and strips metadata (ExifTool) before flipping to `ready`. Run ClamAV as a small REST sidecar service on Railway (e.g. `clamav-rest-api`) so you scan in-house and never ship user bytes to a third party. Refresh signatures on a schedule.
- **Why not Cloudinary?** Cloudinary is excellent and could replace *both* image and video, but it's a heavier, credit-metered platform; for this stack the Supabase-(images) + Mux-(video) split is cheaper at low volume and keeps images inside your existing RLS/auth perimeter. Revisit Cloudinary only if you need heavy on-the-fly image AI (background removal, content-aware crop) at scale.

### 2.3 Tools / cost (rough, 2026)

| Concern | Choice | Rough cost | Tradeoff |
|---|---|---|---|
| Images/docs | **Supabase Storage + transform + CDN** | Included in Supabase plan; storage/egress metered | No video transcode; transform is image-only |
| Video | **Mux** | ~**$0.07/min encode + $0.025/min delivery + storage/min/mo** (resolution-tiered) | Best-in-class streaming; per-minute adds up at scale |
| Video (alt, all-in-one) | **Cloudinary** | From ~$89–99/mo; credit-based (1 credit = 1GB storage *or* 1GB bandwidth *or* 250 HD video processing seconds) | One vendor for image+video; credit model gets pricey |
| Virus scan | **ClamAV REST sidecar** (self-host on Railway) | ~single-digit $/mo container | You operate it + signature updates; but no data leaves |
| Virus scan (alt) | Cloud scan API / GCS+ClamAV-on-Cloud-Run pattern | Per-scan or per-event | Managed, but ships bytes out / cross-cloud |

### 2.4 Data model + endpoints

```sql
create table portfolio_items (
  id            uuid primary key default gen_random_uuid(),
  applicant_id  uuid references applicants(id),
  kind          text not null,            -- image|document|video
  status        text not null default 'pending', -- pending|scanning|ready|rejected
  -- images/docs:
  storage_path  text,                     -- supabase bucket path (private)
  -- video:
  mux_asset_id  text,
  mux_playback_id text,
  mime_type     text,
  size_bytes    bigint,
  scan_result   text,                     -- clean|infected|error
  created_at    timestamptz default now()
);
```

- `POST /applicant/me/portfolio/upload-url` — returns a signed Supabase upload URL (image/doc) **or** a Mux direct-upload URL (video). Backend signs; bytes go direct.
- Webhook/worker `POST /internal/portfolio/{id}/finalize` — triggered after upload (Supabase Storage event / Mux webhook): enqueue scan, strip metadata, set `ready` or `rejected`.
- `GET /applicant/me/portfolio` / `DELETE /applicant/me/portfolio/{id}`.
- Reads serve **short-TTL signed URLs** for private images/docs and Mux signed playback tokens for video.

### 2.5 Security / privacy / compliance

- **Private buckets + short-lived signed URLs** (minutes). CDN-cache gotcha: a leaked signed token on a cached object is a backdoor until eviction — keep TTL short, don't edge-cache private objects.
- **Scan before public/employer exposure** — never let a `pending`/unscanned item be served.
- **Strip EXIF/metadata** (geolocation in job-site photos is a real privacy leak).
- **Validate MIME server-side**, cap sizes, reject by content-sniff not extension.

### 2.6 Risks / gotchas

- **Direct uploads bypass your API** — you *must* sign narrowly (path, content-type, size, expiry) or you've opened your storage account.
- **Mux webhook reliability** — reconcile with a poll fallback so assets don't get stuck `pending`.
- **ClamAV memory + signature freshness** — under-provisioned ClamAV silently fails; monitor signature age.
- **Orphaned blobs** — deleting a `portfolio_items` row must also delete the Supabase object / Mux asset (transactional cleanup or a sweeper).

---

## 3. Tiered Verification Badges (Self-Reported → Institution-Verified → SKILLED Verified)

### 3.1 State of the art (2026)

The credentialing world has converged on **W3C Verifiable Credentials Data Model 2.0** (W3C Recommendation, May 2025) and **Open Badges 3.0** (final 1EdTech standard, June 2024), which is built *on* W3C VC. These give you cryptographically signed, tamper-evident, holder-portable credentials with standardized securing (JOSE/COSE) and selective disclosure. Major issuers — Accredible (added OB 3.0 + W3C VC + ACE extension, Jan 2026), Credly/Pearson, Canvas Credentials — now issue and *ingest* OB 3.0 / VC while preserving signatures. For skilled trades specifically, **NCCER's Digital Wallet (BuilderFax-powered)** is the live verified-credential rail with QR/secure-link sharing.

### 3.2 Recommended approach (opinionated)

Model trust as an **explicit tier on each credential claim, derived from verifiable provenance — never self-asserted into a higher tier:**

- **Tier 1 — Self-Reported:** worker-entered. No cryptographic proof. Display clearly as unverified.
- **Tier 2 — Institution-Verified:** backed by an external verifiable source — an NCCER Digital Wallet record, a state license lookup, or an inbound **Open Badges 3.0 / W3C VC** whose signature you validated. Store the issuer DID/identity + the proof.
- **Tier 3 — SKILLED Verified:** your platform performed (or attests to) verification, and **you issue your own Open Badges 3.0 / W3C VC** asserting it. This is the only tier where SKILLED is the cryptographic issuer.

**Build, don't roll your own crypto.** Implement issuance/verification with established OB 3.0 / VC tooling and standard securing (JOSE). For volume issuance and recipient wallets, integrating **Accredible or Credly** as the issuance backend is the fast path (per-recipient pricing, ~$1.5k setup at Accredible, sales-quoted). If you want to own issuance, use VC libraries to sign with a platform DID and publish OB 3.0 — interoperable with the ecosystem, no migration.

**Hard rule (fraud surface):** an LLM or worker edit can never promote a claim's tier. Tier is a function of stored, validated provenance only.

### 3.3 Data model + endpoints

```sql
create table credential_claims (
  id              uuid primary key default gen_random_uuid(),
  applicant_id    uuid references applicants(id),
  credential_id   uuid references credentials(id),   -- canonical credential (see §5)
  trust_tier      text not null default 'self_reported', -- self_reported|institution_verified|skilled_verified
  verified_via    text,            -- nccer_wallet|state_license|ob3_import|skilled_issued
  issuer_identity text,            -- DID / issuer URI for tier 2/3
  proof           jsonb,           -- the VC proof / signature blob, validated
  vc_document     jsonb,           -- full OB3/VC if issued or imported
  verified_at     timestamptz,
  expires_at      date,
  created_at      timestamptz default now()
);
```

- `POST /applicant/me/credentials` — add a self-reported claim (tier 1).
- `POST /applicant/me/credentials/{id}/verify` — submit/import an OB3/VC or trigger NCCER/state lookup; backend validates signature/source → sets tier 2.
- `POST /admin/credentials/{id}/issue` — SKILLED issues a signed OB 3.0 / W3C VC → tier 3 (writes `audit_logs`).
- `GET /credentials/{id}/verify` — public verification endpoint (resolves proof; supports inbound shared VCs).
- Display: a badge component keyed on `trust_tier` with distinct visual treatment + a "verify" affordance.

### 3.4 Security / privacy / compliance

- **Provenance is the security boundary** — store and re-validatable proof for tiers 2/3; never trust a tier flag without it.
- **Selective disclosure / minimal exposure** — OB 3.0 supports not publicly hosting sensitive data; share only what an employer needs.
- **Key management** — if you issue (tier 3), protect the platform signing key (KMS/HSM); key compromise forges trust.
- **Expiry + revocation** — model `expires_at` and support VC status/revocation lists; a lapsed license must drop tier.

### 3.5 Risks / gotchas

- **Tier inflation / spoofed proofs** — validate signatures and issuer identity server-side, every time.
- **Standard version skew** — accept OB 2.0/3.0 + VC 1.1/2.0 on ingest; emit OB 3.0/VC 2.0. Platforms auto-convert; mirror that leniency.
- **NCCER/state lookups have no clean APIs** — expect QR/secure-link + curation; plan human-in-the-loop.

---

## 4. AI-Generated Summaries + Exportable PDF Resumes

### 4.1 State of the art (2026)

For server-side PDF the field has split: **HTML/CSS → PDF via a pure-Python engine (WeasyPrint)** for static documents, vs **headless-Chromium services (Gotenberg)** for browser-grade fidelity. `wkhtmltopdf` is deprecated (dead WebKit, SSRF history) — avoid. Client-side (`@react-pdf/renderer`, html2canvas) is the wrong tool for a real CV (separate styling system / rasterized non-selectable text / client-side PII). For the AI summary, the 2026 default is **`gpt-4o-mini` with Structured Outputs (strict mode)** driven from a Pydantic schema, with anti-fabrication prompting and app-level caching.

### 4.2 Recommended approach (opinionated)

- **Generate the PDF in FastAPI with WeasyPrint 69+**, rendering a Jinja2 HTML/CSS template. It's lightweight (tens of MB), deterministic, has excellent print/`@page` CSS, runs no JS (kills script-based SSRF), and deploys cleanly on Railway. Wrap the synchronous call: `pdf = await asyncio.to_thread(HTML(string=html).write_pdf)`. **Do not** put Chromium/`@react-pdf` in the path. Keep **Gotenberg (`gotenberg:8-chromium`, isolated Railway service)** as the documented escalation only if you later need browser-grade fidelity or Office→PDF.
- **AI summary: `gpt-4o-mini` + Structured Outputs (strict).** Define the schema in Pydantic; return *structured fields* (`headline`, `summary_paragraph`, `key_strengths[]`, `cert_highlights[]`) not a blob, so the PDF template controls layout. **Anti-hallucination is the real risk** (it's a real person's resume): system prompt forbids inventing employers/dates/certs; validate output fields against source data before persisting.
- **Cache the summary on the profile**, keyed by a hash of input fields; regenerate only on profile change or explicit "regenerate." PDF export then reads cached text → instant, deterministic, near-zero marginal cost.

### 4.3 Tools / cost (rough)

| Concern | Choice | Cost | Note |
|---|---|---|---|
| PDF engine | **WeasyPrint** (in FastAPI) | ~$0 marginal | Best fit; no extra service |
| PDF escalation | **Gotenberg** (separate Railway svc) | low single-digit $/mo | Only if fidelity demands |
| Hosted PDF (alt) | DocRaptor (PrinceXML) / api2pdf | ~$0.12/doc / ~$0.001/doc | Zero-infra; per-doc billing |
| AI summary | **gpt-4o-mini + Structured Outputs** | ~**$0.0002/summary** (~$0.15/1M in, $0.60/1M out) | Negligible; cache anyway |

### 4.4 Endpoints / services

- `POST /applicant/me/profile/summary/regenerate` — gpt-4o-mini + strict Structured Outputs → validate against source → cache on profile row.
- `POST /applicant/me/profile/export-pdf` — render Jinja2 template (bundled `@font-face` fonts, inline SVG icons, `break-inside: avoid`) → WeasyPrint with a **restrictive `url_fetcher`** (only local trusted assets) → upload to private Supabase bucket → return short-TTL signed URL.
- Next.js just calls the endpoint and redirects to the signed URL (Route Handler if proxying bytes).

### 4.5 Security / privacy / compliance

- **SSRF is the headline PDF risk** — WeasyPrint runs no JS; additionally disable remote fetching via custom `url_fetcher`. If on Gotenberg, network-isolate Chromium (no metadata endpoint) and keep it patched (active Chromium RCE classes affect headless PDF).
- **Template injection** — Jinja2 autoescaping on; profile fields are data, never template code.
- **PII PDFs** → private bucket + short-TTL signed URL only.
- **No fabrication** — validate LLM output against source before it touches the document.

### 4.6 Risks / gotchas

- **Fonts** — bundle brand + Noto fallback fonts in the container (Railway images are font-sparse) and reference via `@font-face`; WeasyPrint embeds used fonts.
- **Emoji** — flaky in WeasyPrint; use inline SVG icons instead.
- **Page breaks** — `break-inside: avoid` on entries so jobs don't split across pages.
- **Don't block the event loop** — always `asyncio.to_thread` the render.
- **Railway native deps** — use a custom Dockerfile (`apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 ...`) rather than auto-builders.

---

## 5. Visual Career-Ladder (Skills/Credential Graph + Recommendation)

### 5.1 State of the art (2026)

The reference taxonomy stack pairs **O*NET** (free, CC BY 4.0, US occupation + base-skill spine, REST API) with **CTDL / Credential Engine Registry** (the only standard that natively models *credential → competency → pathway*, free to consume non-commercially) and optionally **Lightcast Open Skills** for skill-label granularity and demand signal (the free download is fine; the live API is now licensed/paid). RSD has folded into CTDL. For trade ladders specifically there is **no clean API** — you curate from DOL RAPIDS (apprenticeable occupations), NCCER's 4-level craft curricula (a ready-made ladder skeleton), and per-state journeyman/master licensing rules. For storage and recommendation, the 2026 consensus for a graph of this size (thousands of nodes, shallow paths) is **Postgres, not a graph DB**, with hybrid graph-traversal + embeddings + LLM recommendation. For visualization, **React Flow (@xyflow/react)** is the right tool for an authored, interactive ladder of rich custom nodes.

### 5.2 Recommended approach (opinionated)

- **Storage: stay in Postgres.** A normalized polymorphic **edge table + recursive CTEs**, `ltree` for the strict hierarchies (trade→craft→level; SOC major→minor→detailed), and `pgvector` (you already use 1536-dim embeddings) for adjacency. **No Neo4j. No Apache AGE** — AGE is not supported on managed Supabase (Nix-built, no runtime C-extension compilation), and a separate graph DB isn't justified at this scale. Reassess only at millions of nodes with deep variable-length traversals.
- **Recommendation: hybrid, mirroring your existing 3-layer matching engine.** (1) Deterministic graph traversal over `PREREQ_OF`/`UNLOCKS`/`PART_OF_LADDER` edges = the *gates* (you can't skip journeyman hours). (2) `pgvector` cosine similarity = transferable/adjacent credentials (your `text_scorer` analog). (3) Market-demand re-rank = your `policy_adjusted_score` layer (keep base graph fit separate from policy). (4) `gpt-4o`/`mini` writes the 1-sentence "why this next" and final ordering — it *explains and nudges, never invents prerequisites.* Skip GNNs at MVP; keep the clean edge table so one can be trained later.
- **Visualization: React Flow** for the worker ladder (custom nodes = credential cards with `earned / in-progress / unlocked / locked` states, `dagre`/`elkjs` auto-layout, animated "next step"). Render in a `"use client"` component fed by a FastAPI traversal endpoint returning `{nodes, edges}`; cache positions in Redis. Reserve Sigma.js + graphology for an optional admin whole-graph explorer.

### 5.3 Data model sketch

```sql
skills (id uuid pk, label text, onet_element_id text, lightcast_id text,
        ctdl_uri text, embedding vector(1536));
credentials (id uuid pk, name text, type text,   -- license|apprenticeship|nccer_level|certification|degree
        issuer text, ctdl_uri text, jurisdiction text, trade text, ladder_rank int);
occupations (id uuid pk, soc_code text, title text, trade text, path ltree);

graph_edges (                                    -- the graph lives here
  id uuid pk, src_type text, src_id uuid, dst_type text, dst_id uuid,
  relation text,    -- REQUIRES|PREREQ_OF|UNLOCKS|TEACHES|PART_OF_LADDER|TRANSFERS_TO|LEADS_TO_ROLE
  weight numeric default 1.0, source text, confidence numeric,
  unique (src_type, src_id, dst_type, dst_id, relation));
create index on graph_edges (src_type, src_id, relation);
create index on graph_edges (dst_type, dst_id, relation);
-- worker_credentials = credential_claims from §3 (status: earned|in_progress|expired)
```

Traversal ("given what the worker has, what's unlocked toward target role, bounded depth"):

```sql
WITH RECURSIVE reachable AS (
  SELECT e.dst_type, e.dst_id, e.relation, e.weight, 1 AS depth
  FROM graph_edges e
  WHERE e.src_type='credential'
    AND e.src_id IN (SELECT credential_id FROM credential_claims
                     WHERE applicant_id=:wid AND trust_tier<>'self_reported')
    AND e.relation IN ('UNLOCKS','PREREQ_OF','PART_OF_LADDER')
  UNION ALL
  SELECT e.dst_type, e.dst_id, e.relation, e.weight, r.depth+1
  FROM graph_edges e JOIN reachable r
       ON e.src_type='credential' AND e.src_id=r.dst_id
  WHERE r.depth < 5)
SELECT * FROM reachable;
```

### 5.4 Endpoints / services

- `GET /applicant/me/career-ladder?target_occupation=...` — runs the CTE + pgvector adjacency + policy re-rank, returns `{nodes, edges}` with per-node state for React Flow.
- `GET /applicant/me/recommendations/next-credentials` — top-N next credentials with LLM "why" strings.
- `GET /credentials/graph` (admin) — full taxonomy for the Sigma.js explorer.

### 5.5 Security / privacy / compliance

- **Explainability** — your deterministic-first design is a compliance asset under skills-based-hiring / EEOC scrutiny: you can say *why* a recommendation/match was made. Don't bury it in opaque scores.
- **RLS** — skills/credentials/edges are world-readable reference data; `credential_claims` and recommendation outputs stay behind strict RLS / service-role writes (consistent with employer-isolation guardrails).
- **Licensing** — O*NET requires attribution; CTDL/ESCO open; **Lightcast API is licensed — don't redistribute beyond terms.**

### 5.6 Risks / gotchas

- **Curation is the real cost** — trade ladders + 50-state licensing rules are human-curated; treat it as a moat, not a one-time import.
- **Recursive-CTE depth** — bound it (`depth < N`) or a cyclic edge will run away; enforce a DAG on prerequisite edges.
- **React Flow scale** — fine to low-thousands of nodes; paginate/cluster if the worker view ever exceeds that.

---

## Sources

- [Supabase Storage docs](https://supabase.com/docs/guides/storage) · [Storage scaling/optimizations](https://supabase.com/docs/guides/storage/production/scaling) · [Serving downloads / signed URLs](https://supabase.com/docs/guides/storage/serving/downloads) · [createSignedUrl (Python)](https://supabase.com/docs/reference/python/storage-from-createsignedurl)
- [Supabase vs Cloudinary (2026)](https://www.buildmvpfast.com/compare/supabase-vs-cloudinary) · [Mux vs Cloudinary deep dive](https://medium.com/@vignarajj/beyond-the-loading-spinner-a-strategic-deep-dive-into-modern-video-infrastructure-mux-vs-99c067691ed1)
- [Mux pricing](https://www.mux.com/pricing) · [Mux video pricing docs](https://www.mux.com/docs/pricing/video) · [Cloudinary pricing](https://cloudinary.com/pricing) · [Video streaming pricing comparison (2026)](https://www.buildmvpfast.com/api-costs/video)
- [ClamAV docs](https://docs.clamav.net/) · [clamav-rest-api](https://github.com/benzino77/clamav-rest-api) · [GCS + ClamAV malware scanning (Google Cloud)](https://cloud.google.com/architecture/automate-malware-scanning-for-documents-uploaded-to-cloud-storage) · [Securing file uploads with ClamAV + ExifTool](https://devkamal.medium.com/securing-file-uploads-in-nestjs-a-complete-guide-to-implementing-clamav-for-virus-scanning-and-a152a6f021d6)
- [CCPA 2026 updates: consent, consumer rights, AI](https://pandectes.io/blog/ccpa-2026-updates-consent-consumer-rights-and-ai-impact/) · [CCPA compliance playbook 2026 (consent enforced)](https://www.privado.ai/post/ccpa-compliance-playbook-for-2026) · [GDPR vs CCPA 2026](https://www.recordinglaw.com/world-laws/world-data-privacy-laws/gdpr-vs-ccpa/) · [Consent management platforms 2026](https://www.ketch.com/blog/posts/consent-management-platforms)
- [W3C VC Data Model 2.0](https://www.w3.org/TR/vc-data-model-2.0/) · [Open Badges 3.0 (1EdTech)](https://www.imsglobal.org/spec/ob/v3p0/cert) · [Explaining VCs and Open Badges 3.0 (DCC)](https://blog.dcconsortium.org/explaining-verifiable-credentials-and-open-badges-3-0-5bf2f482b383) · [Accredible OB 3.0 + W3C VC launch](https://www.accredible.com/newsroom/accredible-launches-support-for-open-badge-3-0-and-w3c-verifiable-credentials) · [Accredible pricing](https://www.accredible.com/pricing) · [Digital credentials pricing comparison 2026 (POK)](https://www.pok.tech/blog/posts/credly-accredible-accreditta-vs-pok-digital-credentials-pricing-2026)
- [NCCER credentials/certifications](https://www.nccer.org/credentials-certifications/)
- [WeasyPrint](https://weasyprint.org/) · [WeasyPrint 69 changelog](https://doc.courtbouillon.org/weasyprint/stable/changelog.html) · [Gotenberg](https://gotenberg.dev/) · [Deploy Gotenberg on Railway](https://railway.com/deploy/gotenberg-1) · [HTML-to-PDF benchmark 2026 (pdf4.dev)](https://pdf4.dev/blog/html-to-pdf-benchmark-2026) · [Playwright vs WeasyPrint (pdf4.dev)](https://pdf4.dev/blog/playwright-vs-weasyprint) · [@react-pdf/renderer (npm)](https://www.npmjs.com/package/@react-pdf/renderer)
- [Exploiting PDF generators: SSRF (Intigriti)](https://www.intigriti.com/researchers/blog/hacking-tools/exploiting-pdf-generators-a-complete-guide-to-finding-ssrf-vulnerabilities-in-pdf-generators) · [Hunting SSRF in PDF generators (Black Hills)](https://www.blackhillsinfosec.com/hunting-for-ssrf-bugs-in-pdf-generators/)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) · [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) · [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [O*NET database](https://www.onetcenter.org/database.html) · [O*NET Web Services](https://services.onetcenter.org/about) · [Credential Engine / CTDL](https://credentialengine.org/credential-transparency/ctdl/) · [Credential Registry Search API](https://credreg.net/registry/searchapi) · [Lightcast Open Skills](https://lightcast.io/open-skills) · [Lightcast Open Skills API access](https://lightcast.io/open-skills/access) · [DOL RAPIDS / apprenticeship data](https://www.apprenticeship.gov/data-and-statistics)
- [Apache AGE](https://age.apache.org/) · [Supabase + AGE not supported (discussion)](https://github.com/orgs/supabase/discussions/40285) · [Postgres as a graph DB / CTE benchmarks](https://www.klioba.com/postgresql-as-a-graph-database) · [Snowflake: graph queries in Postgres + AGE](https://www.snowflake.com/en/blog/engineering/graph-queries-postgres-apache-age/)
- [React graph visualization libraries](https://cambridge-intelligence.com/blog/react-graph-visualization-library/) · [Cytoscape vs vis-network vs Sigma (2026)](https://www.pkgpulse.com/guides/cytoscape-vs-vis-network-vs-sigma-graph-visualization-2026) · [Skill-based career path modeling (UMass)](https://people.umass.edu/~andrewlan/papers/20bigdata-mnss.pdf)
