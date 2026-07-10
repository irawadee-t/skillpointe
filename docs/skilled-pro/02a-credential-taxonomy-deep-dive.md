# Credential Taxonomy & Standards — Deep Dive + Postgres Design (2026)

> Companion to `02-credentials-verification.md`. The authoritative, schema-level reference
> for the credential/occupation/skill taxonomy. Synthesized from verified research into
> Credential Engine/CTDL, O*NET/SOC/CareerOneStop, Lightcast Open Skills, W3C VC 2.0 /
> Open Badges 3.0 / CLR 2.0, and the major skilled-trades credentialing bodies.

**Four functional layers — use one anchor from each (keep the ID namespaces in separate columns; never overload one):**

| Layer | Job in your system | Recommended standard | Key column |
|---|---|---|---|
| Credential identity / catalog | "what is this credential" | **Credential Engine CTID (CTDL)** | `ctid` |
| Occupation anchor | "what job is this" | **O*NET-SOC 2019** (+ 2018 SOC rollup) | `onet_soc_code` |
| Skills / demand | skill normalization, resume/JD parsing | **Lightcast Open Skills** (`KS…`) | `lightcast_skill_id` |
| Verification wrapper | provable "this person holds it" | **W3C VC 2.0 + Open Badges 3.0 / CLR 2.0** | `vc_jsonb` |

---

## 1. Credential Engine / CTDL / Registry — credential anchor
- **CTDL** = RDF/JSON-LD vocabulary (CC BY 4.0; May 2025 schema); **Credential Registry** = linked-open-data store. `ceterms:Credential` umbrella with trade subclasses: `Certification`, `License`, `ApprenticeshipCertificate`/`JourneymanCertificate`/`MasterCertificate`. `ConditionProfile` (`requires`, `requiresCompetency`, prior creds, experience, jurisdiction) drives "to qualify you need X". Competencies in CTDL-ASN.
- **CTID** = `ce-` + UUIDv4 (39 chars), **decentrally minted** (any UUIDv4 lib). Resolvable: `GET https://credentialengineregistry.org/resources/{CTID}` (JSON-LD) and `/graph/{CTID}`.
- **API (REST/JSON-LD):** record retrieval (no key) as above; Search API `POST https://apps.credentialengine.org/assistant/search/ctdl` (Bearer key; `Skip`/`Take` ≤100); Registry Assistant for publish/validate; bulk "Offline Storage" ZIP. Reference importer is **SQL Server — re-implement for Postgres**.
- **Trades coverage (verified):** NCCER, AWS (17 creds), ASE, OSHA 30 present; EPA 608/NATE/state licenses partial; **NCCCO not found**. Coverage is uneven — measure via Search API.
- ⚠️ **Biggest open item: commercial-use licensing** of Registry *data* isn't clearly declared (free tier stated for non-commercial). Confirm a commercial agreement before launch.

## 2. O*NET + SOC + CareerOneStop — occupation anchor
- **O*NET 30.3** (May 2026; parameterize version). **2018 SOC** (`XX-XXXX`, BLS-owned) → **O*NET-SOC 2019** (`XX-XXXX.XX`, 1,016 occs). No "2019 SOC". **Canonical key = `XX-XXXX.XX`**; `soc_code = left(code,7)`.
- Trades: Electricians `47-2111.00`, HVAC `49-9021.00`, Plumbers `47-2152.00`, Welders `51-4121.00`, Auto `49-3023.00`.
- **Critical:** O*NET DB has **no cert/license records** — those live in **CareerOneStop**: Certification Finder (~5,700 certs, each `Id`) + License Finder (state licenses, each carrying its O*NET code). CareerOneStop Web API is **free** (register → `userId` + Bearer; key expires 36 mo); license bulk download available.
- **Crosswalks (free):** O*NET-SOC↔SOC, **CIP↔O*NET-SOC** (program→occupation), **RAPIDS↔O*NET-SOC** (apprenticeships). Chain: `CIP → O*NET-SOC → {skills/tools/job-zones} + {SOC→BLS wages} + {CareerOneStop licenses by state} + {certs}`.
- O*NET + Credential Engine data are **CC BY 4.0 → attribution mandatory** (bake credit lines in now).

## 3. Lightcast Open Skills — skills/demand layer
- ~34–35k skills; **`KS`+~18 chars** stable IDs. **Certifications exist as a skill type** with their own `KS…` IDs. OAuth2 client-creds (`https://auth.emsicloud.com/connect/token`, scope `emsi_open`); `/skills/.../extract` parses resumes/JDs.
- ⚠️ "Open" to view but **not an open-source data license**; **commercial use needs a contract**, and self-serve API access may be tightening. No official bulk download / data repo. **No Lightcast↔Credential Engine crosswalk exists** — build credential→skill via CTDL competency links → `KS…`.

## 4. Verification wrapper — W3C VC 2.0 + Open Badges 3.0 / CLR 2.0
- **VC Data Model 2.0** = W3C REC (15 May 2025); base context `https://www.w3.org/ns/credentials/v2`; Data Integrity (`eddsa-rdfc-2022`; `bbs-2023` selective disclosure) or VC-JOSE (SD-JWT); `did:web` pragmatic. Issuer signs → holder presents → verifier checks **offline**.
- **Open Badges 3.0** (Final May 2024, *is* a VC); **CLR 2.0** (Oct 2025) embeds OB3 credentials. The matcher glue is **`Achievement.alignment[]`** with CTDL `targetType` values (`ceterms:Credential`, `ceasn:Competency`, `CTDL`) → badge → Registry credential → competencies → (indirect) O*NET occupation.

## 5. Skilled-trades bodies — verifiability tiers (no clean public REST APIs)
- **Strong ID-keyed lookup:** NCCCO (verifycco.org), AWS (QuikCheck + Credly badge), NATE, ASE, **NCCER (Automated National Registry + BuilderFax QR digital wallet)** — most automatable: NCCER + AWS Credly.
- **QR/decentralized:** OSHA 10/30 (serial + trainer ID, no central DB), EPA 608 (not centrally issued; per-issuer, ESCO dominant).
- **Per-state fragmented:** electrical/plumbing licenses → ~50 portals, inconsistent/no APIs; use CareerOneStop License Finder as directory; budget per-state connectors or an aggregator. (Mandatory-vs-voluntary ≠ license-vs-cert: EPA 608 is a federal *mandatory cert*.)

---

## Recommended Postgres design

```sql
CREATE TABLE credentials (
  internal_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ctid               text UNIQUE CHECK (ctid ~ '^ce-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  credential_type    text NOT NULL,            -- Certification | License | ApprenticeshipCertificate ...
  name               text NOT NULL,
  issuing_org        text,
  jurisdiction_state text,
  registry_raw       jsonb,                     -- full CTDL JSON-LD (GIN index)
  refreshed_at       timestamptz DEFAULT now()
);
CREATE TABLE credential_source_xref (           -- one canonical credential <- many source IDs
  internal_id      uuid REFERENCES credentials(internal_id),
  source           text NOT NULL,               -- credential_engine|careeronestop_cert|careeronestop_license|lightcast|issuer_native
  source_id        text NOT NULL,
  match_confidence numeric,
  PRIMARY KEY (source, source_id)
);
CREATE TABLE occupations (
  onet_soc_code text PRIMARY KEY,                -- XX-XXXX.XX
  soc_code      text GENERATED ALWAYS AS (left(onet_soc_code,7)) STORED,
  title text, description text
);
CREATE TABLE credential_occupation (
  internal_id uuid REFERENCES credentials(internal_id),
  onet_soc_code text REFERENCES occupations(onet_soc_code),
  PRIMARY KEY (internal_id, onet_soc_code)
);
CREATE TABLE skills (
  lightcast_skill_id text PRIMARY KEY,           -- KS…
  name text, skill_type text, taxonomy_version text
);
CREATE TABLE held_credentials (
  applicant_id uuid,
  internal_id  uuid REFERENCES credentials(internal_id),
  vc_jsonb     jsonb,                            -- store signed VC VERBATIM; never re-serialize (breaks proof)
  issuer_did   text, verified_at timestamptz, valid_until timestamptz, revoked boolean DEFAULT false
);
```

**Ingestion / matching flow:** seed catalog from CareerOneStop (cert API + license bulk, keyed to O*NET-SOC) → enrich with Credential Engine CTIDs via Search API → attach Lightcast `KS…` for demand signal. Normalize incoming cert names with Lightcast `/extract` + fuzzy match against `credential_source_xref` (fallback name+org dedup). Hard-gate the matcher on `credential_occupation` using CTID as the deterministic key (extends the existing `gates.py` required-credentials gate); feed CTDL `ConditionProfile`/competency links into the `credential_readiness` dimension. Wrap issued credentials as VC 2.0 + OB 3.0 with `alignment[].targetType = ceterms:Credential` → CTID; store the signed VC verbatim; verify offline.

> Note: the repo's current `app/skilled_pro/taxonomy.py` is the curated **seed** of this model — this doc is the target architecture it grows into.

## Open questions before committing
1. **Credential Engine commercial-use licensing** of Registry data (biggest unknown).
2. **Lightcast commercial contract** + whether free self-serve API access still exists.
3. Per-issuer/per-state **verification** has no clean APIs — plan connectors (NCCER BuilderFax + AWS Credly most automatable).
4. **Attribution mandatory** (CC BY 4.0) for O*NET + Credential Engine.

## Sources
Credential Engine: https://credreg.net/ctdl/ctid · https://credreg.net/registry/searchapi · https://credentialengine.org/develop-solutions/apis/ ·
O*NET: https://www.onetcenter.org/database.html · crosswalks https://www.onetcenter.org/crosswalks.html · BLS SOC https://www.bls.gov/soc/2018/ ·
CareerOneStop: https://www.careeronestop.org/Developers/WebAPI/web-api.aspx · licenses bulk https://www.careeronestop.org/Developers/Data/occupational-licenses.aspx ·
Lightcast: https://docs.lightcast.dev/apis/skills · access https://lightcast.io/open-skills/access ·
W3C VC 2.0 https://www.w3.org/TR/vc-data-model-2.0/ · Open Badges 3.0 https://www.imsglobal.org/spec/ob/v3p0 · CLR 2.0 https://www.imsglobal.org/spec/clr/v2p0 ·
NCCER registry https://www.nccer.org/ · AWS QuikCheck https://cloudweb2.aws.org/certifications/ · NCCCO https://www.verifycco.org/
