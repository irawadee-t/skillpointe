# Consent Architecture — Deep Dive + Target Schema (2026)

> Companion to `consent` implementation (`app/skilled_pro/consent.py`, `app/routers/consent.py`)
> and `08`/`08a`. This is the **target architecture** the implemented MVP grows into — an
> ISO/IEC TS 27560-aligned, append-only, cryptographically verifiable consent ledger with a
> single API enforcement chokepoint. Scope: **first-party data sharing with external
> recipients** (SIS, ATS, scholarship platforms, employers) — NOT cookie/marketing consent.

## Principles (2026)
- **Granular = per-purpose AND per-recipient.** The unit of record is a tuple
  `(subject, purpose, recipient, data_scope)`, never a global user flag. Bundled "I agree"
  is invalid under GDPR; each purpose separably opt-in/refusable.
- **Consent receipt** = human- + machine-readable record returned at consent time (who,
  what data, purpose, recipients, legal basis, policy version) — transparency + interop +
  GDPR Art. 7(1) demonstrability.
- **Anchor the schema to ISO/IEC TS 27560:2023** (supersedes Kantara v1.1; pairs with ISO
  29184 notices). Record (controller's authoritative) + receipt (subject's copy); header +
  `pii_processing[]` entries (purposes, pii_categories, recipients, retention, status). Maps
  cleanly to Postgres JSONB. Best practical reference: arXiv 2405.04528.
- **GDPR↔record mapping:** Art.4(11) → store purpose/recipient/terms_version/collection_method;
  Art.7(1) → tamper-evident record; Art.7(3) → first-class revoke + easy withdrawal;
  Art.7(4) → separable purposes. **CCPA/CPRA** = opt-out + GPC (run one GDPR-grade opt-in
  model; treat US opt-out as a subset). **FERPA** = "signed & dated" → argues for signature +
  timestamp + (ideally) WebAuthn user-signing.

## Build vs. buy: **build the ledger, don't buy a CMP**
Almost every CMP (OneTrust, Osano, Usercentrics…) is a **cookie/marketing-tag** product — not
first-party API-boundary consent. Your need is a narrow high-stakes primitive (~2 tables + a
middleware gate) that must live inside your trust boundary anyway (can't outsource the hot-path
"is this share allowed now" check). Conform to ISO 27560 for interop instead of buying.
**If** DSAR automation / RoPA / a preference-center UI become burdens later, the right-shaped
vendors are **Transcend or Ketch** (developer/API-first, purpose-based) — not the cookie-led ones.

| Vendor | Really is | First-party sharing consent? |
|---|---|---|
| OneTrust | enterprise GRC suite ($10k/yr min Q2 2026) | yes (heavyweight) |
| Transcend | developer-first privacy infra | **closest fit** |
| Ketch | programmatic data-permissions | **yes** |
| Osano | cookie-led + DSAR (free tier) | partial |
| Usercentrics | cookie CMP (Cookiebot) | weak |

## Target Postgres schema (append-only ledger + current-state view)
```sql
CREATE TABLE consent_events (
  id BIGSERIAL PRIMARY KEY,                       -- monotonic chain order
  event_id UUID NOT NULL DEFAULT gen_random_uuid(),
  subject_id UUID NOT NULL,                        -- PII principal
  event_type TEXT NOT NULL CHECK (event_type IN ('grant','revoke')),
  purpose TEXT NOT NULL,                           -- e.g. share_for_scholarship_matching
  recipient TEXT NOT NULL,                         -- employer:acme | sis:banner | scholarship:xyz
  data_scope JSONB NOT NULL,                       -- minimized pii_categories shared
  legal_basis TEXT NOT NULL, terms_version TEXT NOT NULL,
  jurisdiction TEXT, collection_method TEXT NOT NULL,  -- web_form_v3 | webauthn ...
  receipt JSONB NOT NULL,                          -- full ISO 27560 receipt (hash source)
  payload_canonical BYTEA NOT NULL,               -- RFC 8785 canonical bytes
  prev_hash BYTEA, record_hash BYTEA NOT NULL,    -- H(payload || prev_hash) chain
  server_signature BYTEA NOT NULL, signing_key_id TEXT NOT NULL,
  user_assertion JSONB, tsa_token BYTEA,          -- optional WebAuthn / RFC 3161
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE RULE consent_no_update AS ON UPDATE TO consent_events DO INSTEAD NOTHING;
CREATE RULE consent_no_delete AS ON DELETE TO consent_events DO INSTEAD NOTHING;

CREATE VIEW consent_current AS                     -- latest event wins per tuple
SELECT DISTINCT ON (subject_id, purpose, recipient)
  subject_id, purpose, recipient, event_type, data_scope, terms_version, created_at
FROM consent_events
ORDER BY subject_id, purpose, recipient, id DESC;
```
Revocation = a later `revoke` row (preserves immutable demonstrable history); the view collapses
to a live answer. **This is a richer model than the implemented `consent_settings` table — adopt
it when wiring real external sharing.**

## The load-bearing rule: one API chokepoint, fail-closed
No external share executes without a fresh consent check; every share is audited.
```python
async def assert_active_consent(conn, *, subject_id, purpose, recipient, required_scope: set[str]):
    row = await conn.fetchrow("""SELECT event_type, data_scope FROM consent_current
        WHERE subject_id=$1 AND purpose=$2 AND recipient=$3""", subject_id, purpose, recipient)
    if row is None or row["event_type"] != "grant":
        raise ConsentError("no active consent")
    if not required_scope <= set(row["data_scope"]):     # scope must cover fields leaving
        raise ConsentError("scope not consented")

async def push_to_external(conn, *, subject_id, purpose, recipient, payload, fields):
    await assert_active_consent(conn, subject_id=subject_id, purpose=purpose,
                                recipient=recipient, required_scope=fields)
    resp = await integration_client(recipient).send(payload)
    await log_engagement_event(conn, "external_share", subject_id=subject_id,
                               recipient=recipient, purpose=purpose, fields=list(fields))
    return resp
```
Rules: **single chokepoint** (wrap HTTP clients so a raw external call is impossible; enforce via
lint/CI); **scope-tight** (consented scope ⊇ fields → data minimization, not a boolean);
**fail closed**; **audit both** consent changes and actual shares; **real-time revocation** (checks
read `consent_current`). The implemented SKILLED ID verify endpoint already does a consent gate —
this generalizes it to every outbound integration.

## Cryptographic verifiability — layered (cheapest first)
1. **Canonicalize** (RFC 8785 JCS) → stable hashes/signatures.
2. **Ed25519 server signature** over canonical payload → integrity + origin (`PyNaCl`/`cryptography`). ✅ implemented.
3. **Postgres hash-chain** (`prev_hash`/`record_hash`) + append-only rules → tamper-evidence. ✅ implemented (per-subject).
4. **WebAuthn user assertion** on high-stakes consent → subject non-repudiation; satisfies FERPA "signed". 📋
5. **Periodic external anchoring** — RFC 3161 timestamp (freeTSA/DigiCert) or Sigstore Rekor of the
   chain head → defeats **backdating + collusive rewrite** that 1–4 alone don't. 📋
   (AWS QLDB is EOL Jul 31 2025 — don't use; do the chain in Postgres. Libs: `rfc3161-client`, `py_webauthn`.)

## Convergence with verified credentials
Same crypto stack serves both: issue trade credentials AND (optionally) consent receipts as
**W3C VC 2.0 + Open Badges 3.0** (Data Integrity `eddsa`, `bbs` for selective disclosure). Patterns:
(A) *presentation is consent* (established, selective-disclosure minimization); (B) *consent receipt
as its own VC* (forward-looking; Kantara ANCR heading there, no ratified standard yet → keep schema
ISO-27560-aligned so the VC form is a thin wrapper). Don't make MVP compliance depend on wallets
(US tradesperson adoption ~0 today) — design for VC optionality.

## Sources
ISO/IEC TS 27560:2023 https://www.iso.org/standard/80392.html · impl paper https://arxiv.org/pdf/2405.04528 ·
Kantara Consent Receipt https://kantarainitiative.org/download/consent-receipt-specification/ + ANCR WG ·
GDPR Art.7 https://gdpr-info.eu/art-7-gdpr/ · FERPA §99.30 https://www.ecfr.gov/current/title-34/subtitle-A/part-99 ·
RFC 3161 https://www.rfc-editor.org/rfc/rfc3161 · RFC 8785 JCS https://datatracker.ietf.org/doc/html/rfc8785 ·
Sigstore Rekor https://docs.sigstore.dev/logging/overview/ · QLDB EOL https://www.infoq.com/news/2024/07/aws-kill-qldb/ ·
W3C VC 2.0 https://www.w3.org/TR/vc-data-model-2.0/ · Transcend https://transcend.io · Ketch https://www.ketch.com
