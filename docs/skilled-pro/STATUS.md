# SKILLED Pro — Capability Status Map

What was done in the autonomous overnight session, mapped to **every bullet** of the
Core Platform Capabilities brief. Read this first.

### Honest framing
The brief describes a **multi-quarter, multi-team enterprise program**. Several bullets
have hard external dependencies that cannot be completed by a coding session — vendor
contracts/credentials (Workday/Ellucian SIS, Glassdoor/Indeed licensing, Stripe, AWS),
native app-store accounts, and a **SOC 2 Type II audit / FERPA legal review** (audits and
legal processes, not code). For those, this session delivers **production-grade designs +
scaffolding**, not a false "done."

### Legend
- ✅ **Implemented + tested** — working code in this repo, unit-tested / smoke-tested.
- 🟡 **Scaffolded** — interface/adapter or partial implementation in repo; finish per dossier.
- 📋 **Designed** — full production architecture researched + documented in `docs/skilled-pro/`; build pending.
- 🔒 **External-blocked** — needs a credential, contract, audit, or app-store account first.

### Phase 9 + 10 — Verified Credentials section + Employer Portal section completed (latest session)
Completed every remaining buildable bullet in two capability sections (subscription tiers excluded — Stripe-blocked). Honest boundary: real SIS (Banner/Workday) + AWS Textract need vendor creds, so those ship as working lanes + a functional default/mock provider (real connector = adapter swap), not a fake "done."
- **AI/OCR document verification** (P9a): `HeuristicOCRProvider` (cloud-free, default) + Textract production swap; pure `doc_verify.assess` (name/issuer/authenticity → decision). `POST /applicant/me/credentials/{id}/verify-document` raises a confirmed doc to Institution-Verified (signed record), routes borderline to review, leaves failures Self-Reported. Credentials-page UI. e2e: a matching authentic doc → **Institution-Verified** (score 0.78). 5 tests.
- **Ingestion lanes** (P9b): SIS adapter (`MockSISProvider` default, `EllucianEthosSISProvider` stub) + SFTP/file-drop CSV parser (`file_lane`), both feeding the existing audited pipeline via `POST /admin/credentials/ingest/sis` + `/file`. Admin "Pull from SIS" button. e2e: SIS pull created 2 / unmatched 1. 5 tests.
- **Institution partner portal** (P9c): new `institution` role + `institutions`/`institution_contacts` (migration `..._019`); `/institution/me` self-serve upload + roster + import history, scoped to the signed-in institution. Seeded `institution@test.local` → West Georgia Technical College. e2e: upload created 1, roster shows Institution-Verified credentials.
- **Verified-worker hybrid ranking** (P10a): pure `ranking.relevance_score` (credentials + recency + free-text query) + `q` search param; directory ranks by relevance and shows a "% match". e2e: `q=forklift` → relevance 0.91.
- **Employer analytics** (P10b): `GET /employer/me/analytics/insights` — median time-to-fill, median wage vs **platform benchmark**, avg candidate fit + strong-match count, and an AI narrative (template fallback). "Hiring intelligence" section on the analytics page. e2e: 212 placements, 90d time-to-fill, 33% avg fit. **271 tests pass.**

### Phase 8 — SKILLED Foundation impact & outcomes analytics (earlier session)
- **WIOA-style outcomes** across all learners served: employment (placement) rate, median reported wage, credential attainment rate, median time-to-hire — overall + by cohort (program / region / cohort year). Migration `..._018` adds `hire_outcomes.reported_wage_annual` + an `applicant_outcomes` fact view.
- **k-anonymity** publish-safe feed: any cohort with n < k (default 10) is suppressed (metrics nulled, count still disclosed so totals reconcile). Pure logic in `app/skilled_pro/outcomes.py` (metrics + aggregation + suppression).
- **AI impact report** (`POST /admin/foundation/impact-report`) — numbers computed deterministically; only the board/donor narrative is AI (grounded on the exact figures, never invents), with template fallback. Extends `ai.py`.
- Admin router `foundation.py` (summary / outcomes / feed / impact-report). UI `/admin/foundation` (headline cards, cohort table w/ employment bars + dimension toggle + publish-safe switch, impact-report generator). "Impact" in admin nav. 6 unit tests.
- **Idempotent demo seed** (`scripts/seed_outcomes_demo.sql`, deterministic via `hashtext`, markered for teardown) → 212 placements + 202 program credentials. **Verified e2e:** summary 337 served / 63% employment / $52k median / 60% attainment / 121d; feed at k=10 correctly suppressed all sub-10 cohorts (Electrician/Carpentry/Plumbing/Diesel); impact narrative grounded.

### Phase 7 — SKILLED Nation ⇄ Pro event sync (earlier session)
- **Transactional outbox → Redis Stream → idempotent peer inbox.** Domain mutations (credential / consent records) write an `event_outbox` row on the same connection as the state change. A relay (`publish`) XADDs unpublished rows to the `skilled.events` stream; a consumer group (`skilled_nation`) applies them into `sync_inbox`.
- **Idempotent** (consumer group won't redeliver ACKed + `sync_inbox.event_id` UNIQUE) and **echo-guarded** (consumer skips events whose `source` == its own origin). **Reconciliation** diffs published-peer-applicable vs applied → drift report.
- Pure `app/skilled_pro/events.py` (envelope, canonical JSON, echo guard, drift diff; 7 tests). `outbox.py`, `stream.py`, admin router `sync.py` (status/publish/consume/reconcile/emit). Migration `..._017_event_sync.sql`. Admin UI `/admin/sync` (pipeline view + operate controls + event log).
- **Two bugs caught & fixed in live e2e:** (1) echo-guard polarity — the consumer is the *peer*, so it must skip `skilled_nation`-origin events, not `skilled_pro`; (2) reconciliation counted echoes as drift — now only peer-applicable (`source <> peer`) events count. After fix: emit 2 `skilled_pro` + 1 echo → publish 3 → **consume: applied 2, skipped 1**; re-consume → all 0 (idempotent); **reconcile: in_sync, 0 drift**. Transactional emission verified via a real credential add (`credential.created` appeared in outbox).

### Phase 6 — AI profile summaries + PDF résumé (latest session)
- **Grounded AI summary** (`POST /applicant/me/summary`) — prompt contains only the worker's real facts + verified credentials, instructed not to invent; **graceful degradation** to a deterministic factual template when no OpenAI key / on error (so it always works). Editable + saved (`PUT`). `app/skilled_pro/ai.py`.
- **Server-side PDF résumé** (`GET /applicant/me/resume.pdf`) — `fpdf2` (pure-Python, no system deps), one page, credentials marked with their SKILLED verification tier. `app/skilled_pro/resume.py`.
- UI `/applicant/resume` (generate/edit/save + download) + "Résumé" in applicant nav + cross-link from Credentials. `lib/api/resume.ts`. 10 unit tests.
- **Verified e2e:** Jordan → generate (fell back to `template` since this env has no live key — correct) → factual 2-verified-credential summary, persisted; PDF valid (`%PDF-`, correct filename/content-type, renders cleanly with green Institution-Verified badges).

### Phase 5 — SKILLED ID Partner Console (earlier session)
- **Admin console** (`/admin/skilled-id`) operationalizes the B2B API: issue / rotate / revoke partner keys, manage tier + requester category, per-partner **usage analytics** (30-day daily chart, totals, by-endpoint, recent), and a **live in-console verify tester**. Raw keys shown once (SHA-256 stored); every lifecycle action → `audit_logs`.
- Backend `app/routers/skilled_id_admin.py` (6 routes); pure `usage.py` zero-fill series (4 tests). Reuses `apikeys`, `keyring`, and `skilled_id._verify_subject`.
- **Verified end-to-end against the LIVE API:** issued a key in the UI → used it on `GET /skilled-id/v1/verify` → 200 + consented + Institution-Verified creds; a `background_check` partner (not in the worker's sharing) → `consented:false` (per-requester gating); **rotated key → old key 401**; bad key → 401. Metering (`api_request_logs`) + audit confirmed in DB. **237 tests pass** (33 pre-existing matching failures unrelated).

### Phase 4 — employer SKILLED Verify + Verified-Worker Directory (earlier session)
- **Consent-gated verified-worker search** (`GET /employer/me/verified-workers`, employer/admin) — paginated, faceted (trade/credential/state); surfaces a worker **only if** they granted `external_sharing[employer]` on `certifications` AND hold ≥1 Institution-Verified credential. **Data-minimized** (identity + trade + verified credentials; never contact info).
- **SKILLED Verify** (`GET /employer/me/verified-workers/{id}`) — consent-gated per-candidate verified-credential view; logs a `candidate_verified` engagement event (employer-attributed; admins view read-only, unlogged). 403 for non-consenting workers.
- Pure invariants in `app/skilled_pro/discovery.py` (5 tests); GIN index migration on `consent_settings.external_sharing`.
- **Employer UI** `/employer/verified-workers` — filters, worker cards, green SKILLED Verify modal. `lib/api/verifiedWorkers.ts`; "Verified workers" in employer nav.
- **Verified e2e incl. the privacy negative case:** a verified-but-non-consenting worker (job-board-only) was correctly **excluded** from search and the gate held; consented worker appeared with Institution-Verified credentials; audit event logged. **52 backend tests pass.** This closes the loop — verified credentials become discoverable employer value, consent-first.

### Phase 3 — credential ingestion (earlier session)
- **Bulk ingestion API** (`POST /admin/credentials/ingest`, admin) — match applicant by email → normalize → **upsert at Institution-Verified** → signed hash-chained `verified` record → `import_runs` tracking. Dry-run preview + commit. Pure planner unit-tested (6 tests).
- **Admin ingestion console** (`/admin/credentials`) — institution + CSV paste/upload, preview table, commit, summary (created/upgraded/unmatched/errors). Added to admin nav. CSV parser in `lib/api/ingest.ts`.
- Shared `app/skilled_pro/records.py` (DRY signed-record writers; credentials + consent + ingest all use it).
- **Verified end-to-end via real browser + DB:** EPA 608 upgraded Self-Reported → **Institution-Verified**; Forklift created Institution-Verified; unmatched row → warning; `import_runs` status `partial`. **This makes the verification tiers real** — only the trusted ingestion lane raises a tier; self-service stays Self-Reported.

### Phase 2 — frontend (earlier session)
- **Credentials UI** (`/applicant/credentials`) — add/list/remove credentials, live taxonomy-match feedback, tiered verification badges, verification summary. Added to applicant nav.
- **Consent Center** (`/applicant/consent`) — per-category Display / Platform-use / External-sharing (per requester category) with auto-save + signed records.
- `lib/api/credentials.ts` + `consent.ts`; isomorphic `apiSend`/`API_BASE` in `client.ts`.
- **Verified end-to-end via real browser** (login → add 3 credentials → toggle consent): taxonomy normalization, Ed25519 hash-chained `credential_records` + `consent_records`, and correct array persistence all confirmed in the DB.
- **Bug caught + fixed during verification:** consent `external_sharing` was double-encoded (pre-`json.dumps` + `::jsonb` cast collided with the asyncpg JSONB codec) → stored as a JSON string; now stores as a proper array.

### What shipped (overnight session) — code
- `apps/api/app/skilled_pro/` — taxonomy, Ed25519 signing + hash chain, verification badges, consent eval, API keys, rate limiter (**41 unit tests, all passing**).
- `apps/api/app/routers/` — `credentials.py`, `consent.py`, `skilled_id.py` (wired into `main.py`; smoke-tested: 401/403 auth gates, OpenAPI routes live).
- `supabase/migrations/20260627000015_skilled_pro_core.sql` — applied (credentials, credential_records, consent_settings, consent_records, api_clients, api_request_logs; employer tier; applicant identity/summary).
- `apps/api/app/integrations/ocr.py` — adapter pattern reference (Null + Textract stub).
- `docs/skilled-pro/01–08` — production architecture dossier for every area (with sources).
- **Deep dives** (extra verified research): `02a` credential taxonomy + Postgres schema design; `08a` FERPA + US state privacy; `08b` ATS integrations + partner platforms + SKILLED Nation⇄Pro sync architecture; `08c` Stripe billing + salary-data licensing; `08d` consent architecture (ISO-27560 append-only ledger + API chokepoint — the target the implemented MVP grows into).

---

## User Profiles
| Bullet | Status | Notes |
|---|---|---|
| Auto-generated profiles seeded from SKILLED Nation data (with consent) | 📋 / 🟡 | ETL `import_runs`/`import_rows` exist; consent gate ✅ built. Bi-di sync designed (01, 08). |
| Editable trade specialty, certs, employment history, portfolio media, availability | 🟡 | Profile + **credentials CRUD ✅**; portfolio media (Supabase Storage + Mux video) designed (01). |
| Tiered verification badges (Self-Reported → Institution → SKILLED Verified) | ✅ | `verification.py` derives tier from evidence; never client-settable. Tested. |
| AI profile summaries + exportable resumes | ✅ | **Built** (Phase 6): grounded AI summary w/ template fallback (`ai.py`), PDF résumé via fpdf2 (`resume.py`), UI `/applicant/resume`. 10 tests + e2e. |
| Visual career ladder | 📋 | Postgres skills/credential graph + React Flow designed (01); taxonomy ✅ underpins it. |

## Verified Credentials
| Bullet | Status | Notes |
|---|---|---|
| Partner portal for colleges/programs | ✅ | **Self-serve institution portal ✅** (Phase 9c): `institution` role, `/institution/me` upload + roster + import history. Admin console also remains. SSO/SCIM is the enterprise upgrade (08). |
| Ingestion via API, SFTP, SIS (Banner/Colleague, Workday, PeopleSoft) | ✅ / 🔒 | **API + CSV + SFTP file-drop + SIS lanes ✅** (Phase 9b) all feeding the audited pipeline. Real SIS connector (Ellucian Ethos) is an adapter swap — needs creds. |
| AI/OCR document verification | ✅ / 🔒 | **Pipeline built ✅** (Phase 9a): cloud-free `HeuristicOCRProvider` + `doc_verify` → raises matching authentic docs to Institution-Verified. Textract is a production provider swap (needs AWS creds). |
| Credential taxonomy normalization | ✅ | `taxonomy.py` (curated CTDL/O*NET/CareerOneStop seed) + confidence + review routing. Tested. Full registry sync designed (02 §4). |
| Cryptographically signed, immutable records + audit | ✅ | Ed25519 + canonical JSON + per-subject hash chain (`signing.py`, `credential_records`). Tested incl. tamper detection. KMS key + RFC 3161 timestamp = next (02 §5). |

## SKILLED ID (B2B API)
| Bullet | Status | Notes |
|---|---|---|
| REST API for third parties to query verified status | ✅ | `/skilled-id/v1/verify` + `/verify/bulk`; verified-only, consent-gated. Smoke-tested. |
| Per-query + SaaS access, rate-limited bulk | ✅ | API-key auth (hashed), Redis sliding-window rate limiter w/ tiers, 429. Per-query metering. **Admin Partner Console ✅** (Phase 5): issue/rotate/revoke keys, tiers, usage analytics, live tester. Stripe Meters billing (charge on metered usage) designed (03). |
| Granular consent (display/internal/external independently) | ✅ | `consent.py` + `consent_settings` + signed `consent_records`; SKILLED ID filters by requester category. Tested. |
| White-label for unions/workforce boards/gov | 📋 | Shared-schema→DB-per-tenant path designed (03). |

## Job Matching
| Bullet | Status | Notes |
|---|---|---|
| AI multi-factor matching engine | 🟡 | Deterministic engine exists (`packages/matching`); evolve to retrieve-and-rerank (pgvector HNSW + PostGIS + LambdaMART) designed (04). |
| Explainable match scores | ✅ (exists) | Engine already emits strengths/gaps/labels; grounded-LLM explanations designed (04). |
| One-click apply | 🟡 | Interest/apply signals exist; one-click apply via stored profile designed. |
| Geo recommendations + AI interview scheduling | 📋 / 🔒 | PostGIS radius designed (04); scheduling needs Google/Outlook OAuth (08). |

## Employer Portal
| Bullet | Status | Notes |
|---|---|---|
| Org profiles, structured postings, verified-worker search | ✅ | Portal + jobs exist; **consent-gated verified-worker directory ✅** (Phase 4) with **hybrid relevance ranking ✅** (Phase 10a: credentials + recency + free-text `q`, "% match"). pgvector semantic rerank is the next upgrade (05). |
| SKILLED Verify instant checks | ✅ | **Built end-to-end** (Phase 4): `GET /employer/me/verified-workers/{id}`, consent-gated, audit-logged, employer UI modal. |
| Subscription tiers + "Pay When They Stay" | 🟡 / 🔒 | `employers.subscription_tier` column added; Stripe Billing/Meters + Connect escrow designed (05). Needs Stripe account. |
| Analytics (time-to-fill, quality, wage benchmarking, AI summaries) | ✅ | **Built** (Phase 10b): `/employer/me/analytics/insights` — time-to-fill, match quality, platform wage benchmark, AI narrative. BLS as an external benchmark feed is the upgrade (05). |

## Training Programs
| Bullet | Status | Notes |
|---|---|---|
| Program profiles mapped to taxonomy | 📋 | Taxonomy ✅; program model + CTDL/CIP mapping designed (05). |
| AI student pipeline (pre-qualified, filterable) | 📋 | Gate-based pipeline designed (05). |
| Automated scholarship matching + AI pre-filled apps | 📋 | Designed (05); human-confirm guardrail. |
| Outcomes feed (anonymized) | ✅ | **Built** (Phase 8): k-anonymity suppression (n<k) on `/admin/foundation/feed`. Differential-privacy noise still designed (06). |

## SN Mission Dashboard
| Bullet | Status | Notes |
|---|---|---|
| Cohort outcomes (employment, wages, attainment, time-to-hire) | ✅ | **Built** (Phase 8): `applicant_outcomes` view + `outcomes.py` cohort metrics + `/admin/foundation`. Materialized-views→dbt is the scale path (06). |
| Longitudinal scholarship→employment→wage tracking | 📋 | Event-sourced longitudinal model designed (06). |
| AI impact reports (board/donors/partners) | ✅ | **Built** (Phase 8): deterministic numbers + grounded LLM narrative (template fallback), `/admin/foundation/impact-report`. |

## Perks Marketplace
| Bullet | Status | Notes |
|---|---|---|
| Identity-gated perks (GovX model) | 📋 | Self-owned eligibility gating (vs SheerID) designed (06). |
| Brand listings targeted by trade/geo/experience | 📋 | Declarative targeting designed (06). |
| Daily Deals + sponsored slots | 📋 | Redis-cached, disclosed sponsorship designed (06). |
| Commission tracking (10–18%) | 📋 | Webhook-driven append-only commission ledger designed (06). |

## Notifications & Mobile
| Bullet | Status | Notes |
|---|---|---|
| Native iOS/Android, feature parity | 📋 / 🔒 | **React Native + Expo (EAS)** recommended (07); needs Apple/Google dev accounts. |
| Push / in-app / email | 📋 | Expo Push→Knock/Courier + Resend/Postmark; `device_tokens` table designed (07). |
| AI-optimized timing | 📋 | Heuristic→ML send-time, driven by `engagement_events` (07). |
| Geo-targeted alerts / shift dispatch | 📋 | Server-side proximity + opt-in background geo designed (07). |

## Privacy & Compliance
| Bullet | Status | Notes |
|---|---|---|
| AES-256 at rest, TLS 1.3, RBAC | 🟡 | Provider AES-256 + TLS; RLS/RBAC exist; KMS column-encryption for sensitive fields designed (08). |
| FERPA compliance | 📋 / 🔒 | Technical controls designed; needs DPAs + legal review (08). |
| CCPA + state privacy | 📋 | DSAR/opt-out/GPC designed (08). |
| Granular consent + verifiable records | ✅ | Implemented (Kantara/ISO 27560-aligned signed records); add policy-version + receipt next (08). |
| 7-year append-only audit logs | 🟡 | `audit_logs` + hash-chained signed credential/consent logs ✅; Glacier retention + RFC 3161 anchoring designed (08). |
| SOC 2 Type II (≤18 mo) | 🔒 | Vanta/Drata path + control list designed (08). Audit process, not code. |

## AI Services (Shared)
| Bullet | Status | Notes |
|---|---|---|
| Centralized matching service (<500ms) | 📋 | pgvector HNSW + rerank architecture designed (04). |
| OCR/document intelligence pipeline | 🟡 | Adapter ✅; Textract pipeline designed (02, 04). |
| LLM content generation | 🟡 / exists | Chat + extraction exist; summaries/explanations/reports designed (04). |
| Fraud & anomaly detection | 📋 | Designed (04). |
| Labor-market intelligence (BLS) | 📋 | BLS + Lightcast feeds designed (04, 05). |

## Key Integrations
| Integration | Status | Notes |
|---|---|---|
| SKILLED Nation sync | ✅ | **Built** (Phase 7): transactional outbox → Redis Stream → idempotent, echo-guarded peer inbox + reconciliation. `events.py`/`outbox.py`/`stream.py`, `/admin/sync`. 7 tests + live e2e. |
| SIS (Ellucian/Workday/PeopleSoft) | 🔒 | Ethos-first design (02, 08); contracts/creds. |
| ATS (Workday/Greenhouse/iCIMS/Lever) | 📋 | **Merge.dev unified API** recommended (08). |
| Glassdoor/Indeed licensing | 🔒 | Commercial contract. |
| Stripe / Google-Outlook scheduling | 🟡 / 🔒 | Designs ready (05, 08); need accounts. |
| SkillsUSA / SkillUp / Path to Pro | 📋 | Import via taxonomy (08). |

---

## Recommended next build order (no external deps first)
1. Frontend **Consent Center** + **Credentials** profile UI on the ✅ backend.
2. SKILLED Nation sync + CSV/SFTP ingestion lane (reuse `import_runs`).
3. Wire **Textract** OCR (needs AWS creds + opt-out SCP) → raises Institution/SKILLED tiers.
4. Move signing key to **KMS** + add **RFC 3161** timestamp to the chain.
5. Adopt **Merge.dev** for ATS; **Stripe Billing** for employer tiers.
6. Start **Vanta/Drata** for the SOC 2 runway; engage counsel for FERPA DPAs.
