# Integrations Deep Dive — ATS, Partner Platforms & SKILLED Nation Sync (2026)

> Companion to `08-privacy-compliance-integrations.md`. Verified against official
> developer docs (Greenhouse, Lever, iCIMS) + reputable secondary sources (Workday).
> Every integration is server-to-server from FastAPI; treat all ATS/partner credentials
> as Tier-1 secrets in a managed secret store (not Railway plain env), with rotation
> documented for SOC 2.

## ATS integrations — summary

| ATS | Auth | Access gate | Rate limit | Webhooks | Native effort |
|---|---|---|---|---|---|
| **Greenhouse** | HTTP Basic (API token) + mandatory `On-Behalf-Of` header on writes; Onboarding = GraphQL | Self-serve key; partner for Marketplace | ~50 req/10s, 429 + `X-RateLimit-*` | Yes (signed) | **Lowest (1–3 wks)** |
| **Lever** | API key (Basic) **or** OAuth2 Auth-Code + `offline_access`; 50+ `resource:action:admin` scopes; 1-hr tokens, rotating refresh | Self-serve key; OAuth for partner apps | 10/s (burst 20); **app POSTs 2/s** | Yes (HMAC-SHA256) | **Low–moderate (2–4 wks)** |
| **iCIMS** | **OAuth2 Client-Credentials** + optional **IP allowlist** | Partner application + validation + sandbox | not public | Limited | High (process-gated) |
| **Workday** | OAuth2 (REST) + ISU (SOAP/RaaS), per-tenant; RaaS for bulk, SOAP for writes | Customer admin / Innovation Partner cert | tenant-config | Limited | **Highest (8–14+ wks)** |

**Recommendation:** Build **Greenhouse + Lever native first** (high ROI, partner-friendly,
clean docs, webhooks). Proxy **Workday + iCIMS through Merge.dev** (both partner-gated,
high-effort, likely long-tail for trades) until you have committed enterprise employers on
them. Direction-scope to least privilege: **read** requisitions/postings for matching;
**write** candidate/application records only when pushing verified candidates.

**Two infra blockers to solve early:**
1. **iCIMS IP allowlisting vs Railway dynamic egress** — needs static-egress/NAT/proxy.
2. **Secrets management** — long-lived Greenhouse/Lever keys + rotating OAuth refresh tokens
   belong in a real secret store given student-PII scope.

**Compliance:** Greenhouse `On-Behalf-Of` + Audit Log API give per-actor attribution;
Lever OAuth scopes give per-tenant least privilege + clean revocation. A unified API
(Merge.dev) inserts a **sub-processor** into the PII flow → Merge DPA + SOC 2 + subprocessor-
list inclusion required.

Sources: Greenhouse Harvest https://developers.greenhouse.io/harvest.html · Lever
https://hire.lever.co/developer/documentation , OAuth https://hire.lever.co/developer/oauth ·
iCIMS https://developer-community.icims.com/getting-started/integrating-icims · Workday
https://www.workday.com/en-us/company/partners/innovation-partners.html · Merge ATS
https://www.merge.dev/blog/guide-to-ats-api-integrations

---

## Partner / user-data platforms

**Bottom line:** of the three external orgs, **only SkillUp has a real (partner-gated) API.**

- **SkillsUSA** — no public API/SSO/bulk-export; member data in a dated registration portal
  (`skillsusa-register.org`, "Hivelocity 2020") with CSV/XLSX upload only. Treat as a
  **batch/manual import** via the existing `packages/etl/` pipeline + a data-sharing MOU.
  **Highest FERPA exposure** (student minors). No API to design around.
- **SkillUp Coalition** — the one with a real **partnership-gated API** (consumers: Willow,
  Kuder, ASA, Overgrad) for embedding curated training/opportunity content. **Read-only,
  inbound** — pull pathways/opportunities into matching as an enrichment signal; **keep
  student PII out of it** (avoids FERPA outbound). Apply via their partnership process.
- **Path to Pro (Home Depot)** — closed Home Depot-operated marketplace; **no developer API**.
  Integration only via an enterprise BD deal (the ServiceTitan model). Treat as an
  **adjacent/competitor** marketplace, not an integration target.

Sources: SkillsUSA register https://www.skillsusa-register.org/ · SkillUp partners
https://skillup.org/partners · Path to Pro Network
https://corporate.homedepot.com/news/trades-training-and-path-pro/home-depot-launches-path-pro-network-unique-jobseeker-platform

---

## SKILLED Nation ⇄ SKILLED Pro bi-directional sync (you own both sides — build this first)

**Recommended pattern: Redis Streams event log + transactional outbox + idempotent upsert
consumers + nightly reconciliation.** Kafka-like semantics on infra you already run; avoids
shared-DB coupling and the drop/duplicate problems of raw webhooks.

| Pattern | Verdict |
|---|---|
| Shared database | ❌ couples schemas, no PII ownership boundary |
| REST + webhooks only | ⚠️ fast path only; drops/dupes without queue+DLQ+reconciliation |
| Full Kafka | ⚠️ correct shape, operationally heavy for two services |
| CDC (Debezium) | ⚠️ leaks raw schema as contract; internal feeder at best |
| **Redis Streams** | ✅ durable, ordered, replayable consumer groups on existing infra |

**Topology:** `Postgres write → transactional outbox (atomic) → Redis Stream → consumer
group on the other service → idempotent upsert → ack`. Service-to-service auth via mTLS or
OAuth2 client-credentials (reuse existing FastAPI JWT validation).

**The four hard problems:**
1. **Idempotency** — every event has a stable `event_id` (UUID) + entity `version`/`updated_at`;
   consumers do conditional upserts (`ON CONFLICT … DO UPDATE … WHERE excluded.updated_at >
   target.updated_at`); track processed ids / use consumer-group acks.
2. **Conflict resolution** — **per-field system-of-record** (Nation owns scholarship/eligibility;
   Pro owns job-match/profile), last-writer-wins only within an owning system; audit trail.
3. **Loop prevention** — **origin tagging** (`source: "skilled_pro"`); skip re-emitting events
   you originated.
4. **Drift** — streams are the fast path; pair with a **nightly reconciliation** (checksum /
   `updated_at` watermark diff) + a **dead-letter stream** with replay.

**FERPA (governs the sync itself, both sides handle student records):** minimize payload (sync
only needed fields, not full education records), encrypt in transit + at rest, log every
cross-product movement to `audit_logs` (disclosure accounting), propagate deletes
(`student.deleted` event) for right-to-delete/amend. Configure Redis persistence (AOF/replication)
or the event log silently loses data on restart.

**Effort:** ~a few weeks for a solid v1 on existing Redis + Postgres + FastAPI; reuse
`packages/types` as the shared versioned event-schema package.

Sources: Events beat webhooks https://www.stacksync.com/blog/events-beat-webhooks-reliable-data-sync ·
Bidirectional sync without loops https://truto.one/blog/how-to-sync-customer-data-bidirectionally-between-your-app-and-hubspot/ ·
Supabase CDC options https://www.stacksync.com/blog/supabase-cdc-options-triggers-webhooks-realtime-compared ·
FERPA vendor FAQ https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Vendor%20FAQ.pdf
