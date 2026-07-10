# SKILLED ID — B2B Credential-Verification API

> Architecture & implementation reference · 2026 · FastAPI (Python 3.11) · Supabase Postgres · Redis · Next.js 15 · Railway

**Executive summary.** SKILLED ID is the externally-monetized B2B surface of SKILLED Pro: a versioned REST API that lets authorized third parties (Glassdoor, Indeed, staffing agencies, and eventually unions/workforce boards/government) query the verified-credential status of a worker who has consented to share it. This document specifies the full production design — endpoint contract and versioning, partner authentication (OAuth2 client-credentials as the default, mTLS for regulated tiers, hashed API keys as the low-friction onramp), Redis-backed rate limiting and quotas, Stripe metered/usage-based billing across per-query and SaaS subscription tiers, consent-scoped data minimization, and a multi-tenancy path to white-label — each section grounded concretely in the FastAPI + Postgres + Redis + Railway stack with schemas, endpoints, and middleware. It is opinionated: where there is a defensible "boring" choice that survives real traffic and an audit, this doc names it and explains the tradeoff. The throughline is that **consent and verification provenance are first-class** — the API never returns a credential the subject has not authorized for that specific use, and every disclosure is logged.

---

## 0. Design principles (read first)

1. **The credential subject is the data owner, not the partner.** Every byte SKILLED ID returns about a person exists because that person granted a *scoped* consent. Partner authorization (who is calling) and subject consent (what they may see) are **two independent gates**, both required.
2. **Verification status is a claim, not a document.** SKILLED ID returns *attested status* ("Journeyman Electrician credential: VERIFIED, issuer X, verified 2026-03-01, expires 2028-03-01") — not the underlying PII document. This is the core of data minimization and the main commercial moat.
3. **Your database is the source of truth; Stripe is for billing.** Usage is metered to your Postgres first, then reconciled to Stripe asynchronously.
4. **Everything externally-facing is versioned, idempotent where it mutates, and cursor-paginated.** No surprises for partners.
5. **Defense in depth on tenant isolation.** Postgres RLS is a backstop, not the primary control. The application always scopes by `partner_id` / `tenant_id` explicitly.

---

## 1. REST API: endpoint design, versioning, OpenAPI, idempotency, pagination

### 1.1 State of the art (2026)
The settled public-API conventions — practiced by Stripe, GitHub, Google — are: **URL-path versioning** (`/v1/…`) as the visible default, **spec-first/API-first** development (the OpenAPI document is the artifact you design and review *before* code), **structured machine-readable errors**, **idempotency keys** on all unsafe (POST/mutation) operations, **opaque cursor pagination** for any frequently-changing collection, and **machine-readable deprecation** via `Sunset`/`Deprecation` headers. ([digitalapplied][da], [Fern][fern], [techinterview][ti])

### 1.2 Recommended approach (opinionated)
- **Versioning: URL path major version (`/v1`)** for the public contract — explicit, greppable in logs, obvious to integrators. Layer a date-pinned header (`SKILLED-Version: 2026-06-01`) on top, Stripe-style, so you can ship backward-compatible behavioral changes without a major bump. Bump the path version only for breaking changes; default un-pinned callers to the oldest still-supported date and warn via `Deprecation`/`Sunset` headers.
- **Spec-first.** Hand-author the OpenAPI 3.1 doc (or generate from Pydantic and treat the committed `openapi.json` as a reviewed artifact + contract test). FastAPI emits OpenAPI 3.1 natively from your Pydantic models — lean into it, but pin and snapshot-test the schema so partner-visible changes are intentional.
- **Idempotency** on every mutating endpoint (consent grants, bulk-verification job submission, webhook subscription creation). Client sends `Idempotency-Key: <uuidv4>`; you store the key + request fingerprint + response in Redis (24h TTL) and Postgres (durable), and replay the stored response on retry.
- **Cursor pagination** everywhere a list can change between calls (audit logs, bulk results, partner query history). Opaque base64 cursor encoding `(created_at, id)`; never offset/limit on changing data.
- **Structured errors** with a stable machine `code`, human `message`, and `request_id`.

### 1.3 Tools / libraries / tradeoffs / cost
| Concern | Pick | Why / tradeoff | Cost |
|---|---|---|---|
| Spec & validation | **FastAPI + Pydantic v2** (already in stack) | OpenAPI 3.1 for free; runtime validation; snapshot-test the spec | $0 |
| Contract testing | **schemathesis** (property-based against OpenAPI) | catches drift between spec and impl | $0 |
| SDKs for partners | **Fern** or **Speakeasy** (generate Python/TS/Go SDKs from OpenAPI) | partners adopt faster with typed SDKs; managed service cost | Fern OSS $0 / paid tiers; Speakeasy ~$250+/mo |
| Idempotency store | **Redis** (already in stack) + Postgres durable record | Redis fast path, PG durability | $0 incremental |

**Tradeoff note:** header-only (date) versioning is more elegant but less obvious to non-expert integrators (staffing agencies). Path version is the friendlier default for a B2B audience of mixed sophistication.

### 1.4 Security / compliance
- Every response carries `X-Request-Id` (tie to logs + audit row).
- `Idempotency-Key` reuse with a *different* request body → `409 idempotency_key_reuse` (never silently serve the wrong cached response).
- Spec is the gate for what fields can ever leave the system — fields not in the response schema cannot be accidentally serialized.

### 1.5 Concrete fit to this stack
A thin `app/routers/skilled_id/` package mirrors the existing FastAPI router layout. Idempotency is a dependency, not scattered logic:

```python
# apps/api/app/skilled_id/idempotency.py
from fastapi import Depends, Header, HTTPException
import hashlib, json

async def idempotent(idempotency_key: str = Header(..., alias="Idempotency-Key"),
                     request_body: dict | None = None, redis=Depends(get_redis)):
    if request_body is not None:
        fp = hashlib.sha256(json.dumps(request_body, sort_keys=True).encode()).hexdigest()
        stored = await redis.hgetall(f"idem:{idempotency_key}")
        if stored:
            if stored.get("fp") != fp:
                raise HTTPException(409, {"code": "idempotency_key_reuse"})
            return json.loads(stored["response"])  # replay
    return None  # proceed; caller stores result under key with 24h TTL
```

```sql
-- supabase/migrations: durable idempotency + request audit
create table idempotency_keys (
  partner_id   uuid not null references partners(id),
  key          text not null,
  request_fp   text not null,
  response     jsonb not null,
  status_code  int  not null,
  created_at   timestamptz not null default now(),
  primary key (partner_id, key)
);
```

### 1.6 Risks
- **Spec/impl drift** if FastAPI models change without snapshot test — mitigate with schemathesis in CI.
- **Idempotency key on the client side colliding** across partners — always namespace by `partner_id` (composite PK above).
- **Premature `/v2`** — resist; use date headers for additive change.

---

## 2. Partner authentication: API keys vs OAuth2 client-credentials vs mTLS

### 2.1 State of the art (2026)
The consensus for machine-to-machine B2B: **OAuth 2.0 client-credentials is the default** — `client_id` + `client_secret` (or a signed `client_assertion` private key) exchanged at `/token` for a short-lived (5–60 min) access token bearing **scopes** for least-privilege. **mTLS** is the highest-assurance option (both sides present X.509 certs) reserved for regulated/zero-trust counterparties — powerful but operationally heavy (PKI, rotation, CRL/OCSP, painful expiry debugging) and only "binary" trust without scopes. **API keys** still earn their place as a *simple identity + rate-limit handle* and a low-friction onramp, but should not be the sole auth for sensitive data. The mature pattern combines them: **mTLS for transport + OAuth for app-layer scopes** (the Open Banking / FAPI model). ([Scalekit OAuth-vs-mTLS][sk1], [Scalekit B2B][sk2], [Security Boulevard M2M][sb], [Elysiate gateway][el])

### 2.2 Recommended approach (opinionated)
**Tiered by partner sophistication and data sensitivity:**

1. **Hashed API keys** — the *onboarding* tier. A staffing agency gets a key in minutes, can hit read-only verification endpoints. Key format `skid_live_<random>`; **store only a hash** (see below). This is identity + a billing/rate handle, *not* a license to see PII beyond what consent allows.
2. **OAuth2 client-credentials — the standard tier and the strategic default.** Issue `client_id`/`client_secret`; partner exchanges for a short-lived JWT access token with scopes (`credential:read`, `bulk:submit`, `consent:read`). This is what Glassdoor/Indeed-scale partners use; it gives you rotation, revocation, introspection, and per-scope authorization.
3. **mTLS (+ OAuth) — the regulated/white-label tier.** Required for government/union/workforce-board tenants and any partner contractually demanding transport-mutual auth. Pin client certs per tenant; run OAuth on top for scopes.

**Secret handling (non-negotiable):**
- **Hash API keys and OAuth client secrets at rest** with a slow KDF — **Argon2id** (or scrypt). Never store plaintext; never log them. Show the secret exactly once at creation.
- Store a short **lookup prefix** (first 8 chars, indexed) so you can find the row without hashing every key on every request.
- **Rotation:** support *two live secrets per partner* with overlapping validity so partners rotate with zero downtime; expire the old one on a schedule. Surface `created_at` / `last_used_at` / `expires_at`.
- OAuth access tokens: **15-minute TTL**, signed (ES256), scope-bearing. Cache + de-dupe concurrent token refreshes on the partner side (document this in the SDK).

### 2.3 Tools / libraries / tradeoffs / cost
| Option | Library / service | Tradeoff | Cost |
|---|---|---|---|
| API keys (DIY) | `argon2-cffi`, `secrets` | full control, you own rotation UX | $0 |
| OAuth2 CC (DIY) | `python-jose`/`authlib` issuing ES256 JWTs; or reuse Supabase as IdP | most control, more code | $0 |
| OAuth2 CC (managed) | **Auth0**, **WorkOS**, **Scalekit**, **Stytch** | offloads token infra, org/scopes, rotation UI | Auth0 M2M ~$/active-token; WorkOS/Scalekit per-connection |
| mTLS termination | **Railway** lacks native mTLS client-cert termination → front with **Cloudflare** (mTLS to origin) or an Nginx/Envoy sidecar | infra complexity; Railway-specific gap | Cloudflare mTLS add-on |

**Opinion:** start DIY for API keys + OAuth client-credentials (you already have Supabase JWT plumbing in `app/auth/dependencies.py`), and only adopt a managed IdP (WorkOS/Scalekit) when partner count or SSO/SCIM demands justify it. **Railway has no built-in mTLS** — terminate client certs at Cloudflare in front of Railway for the regulated tier; do not block the MVP on it.

### 2.4 Security / compliance
- Argon2id hashing; constant-time compare; secrets shown once.
- Scope checks enforced server-side per endpoint (a dependency like the existing `require_*` guards).
- Revocation: a deny-list in Redis (`revoked:jti`) checked on token validation for instant kill.
- All auth events (issue, rotate, revoke, failed) → `audit_logs` (reuse existing table).

### 2.5 Concrete fit to this stack
```sql
-- supabase/migrations
create table partners (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  tier text not null default 'starter',          -- billing/quota tier
  auth_mode text not null default 'api_key',      -- api_key | oauth | mtls
  created_at timestamptz default now()
);

create table partner_api_keys (
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null references partners(id) on delete cascade,
  prefix text not null,                 -- 'skid_live_ab12cd34' lookup handle (indexed)
  key_hash text not null,               -- argon2id(secret)
  scopes text[] not null default '{credential:read}',
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz default now()
);
create index on partner_api_keys (prefix);

create table partner_oauth_clients (
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null references partners(id) on delete cascade,
  client_id text unique not null,
  client_secret_hash text not null,     -- argon2id
  client_secret_hash_next text,         -- overlapping rotation
  scopes text[] not null default '{credential:read}'
);
```

```python
# apps/api/app/skilled_id/auth.py  — FastAPI dependency
from argon2 import PasswordHasher
ph = PasswordHasher()

async def authenticate_partner(authorization: str = Header(...), conn=Depends(db)):
    scheme, _, cred = authorization.partition(" ")
    if scheme.lower() == "bearer" and cred.startswith("ey"):     # OAuth JWT
        claims = verify_es256(cred)                              # checks sig, exp, revocation
        return PartnerCtx(partner_id=claims["sub"], scopes=claims["scope"].split())
    if scheme.lower() == "bearer" and cred.startswith("skid_"):  # API key
        prefix = cred[:18]
        row = await conn.fetchrow("select * from partner_api_keys where prefix=$1 "
                                  "and revoked_at is null", prefix)
        if not row: raise HTTPException(401, {"code": "invalid_key"})
        ph.verify(row["key_hash"], cred)                         # raises on mismatch
        return PartnerCtx(partner_id=row["partner_id"], scopes=row["scopes"])
    raise HTTPException(401, {"code": "unauthenticated"})

def require_scope(scope: str):
    async def dep(p: PartnerCtx = Depends(authenticate_partner)):
        if scope not in p.scopes: raise HTTPException(403, {"code": "insufficient_scope"})
        return p
    return dep
```

### 2.6 Risks
- **Plaintext key leakage** in logs/error traces — scrub at the logging layer; never echo `Authorization`.
- **mTLS on Railway** is the real gap — if a government tenant mandates it before Cloudflare is in place, it blocks that deal. Plan the Cloudflare-front early.
- **DIY OAuth subtleties** (clock skew, key rotation for ES256 signing keys) — mitigate by reusing battle-tested `authlib`.

---

## 3. Rate limiting & quotas

### 3.1 State of the art (2026)
Distributed FastAPI rate limiting is Redis-backed. **Token bucket** smooths bursts (bucket of N tokens, refilled at rate R; empty → `429` + `Retry-After`). **Sliding-window counter** approximates a true window in O(1) with two counters and behaves predictably under bursts. `slowapi` is the standard decorator library for FastAPI/Starlette with Redis storage; `fastapi-limiter` is the async alternative. On limit: return **`429 Too Many Requests` with `Retry-After: <seconds>`** (seconds, not a date) plus `RateLimit-*` headers. ([freeCodeCamp token-bucket][fcc], [slowapi guide][slow], [Bryan Antonio Redis limiter][ba], [dev.to sliding window][dt])

### 3.2 Recommended approach (opinionated)
- **Two layers, both in Redis:**
  1. **Burst control — token bucket per API key** (e.g. 20 req/s, burst 40). Smooths spikes, protects origin.
  2. **Subscription quota — sliding-window monthly counter per partner** keyed to their plan (e.g. Starter 10k verifications/mo, Growth 250k, Scale 5M). This is the *billing* boundary; quota exhaustion → `429 quota_exceeded` with the upgrade path in the body (or soft-overage → metered billing, see §4).
- **Bulk access is a separate lane:** `bulk:submit` jobs don't burn per-second tokens; they consume quota by *result row* and run async with their own concurrency cap.
- **Always emit** `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, and on 429 `Retry-After`.

### 3.3 Tools / libraries / tradeoffs / cost
| Pick | Tradeoff | Cost |
|---|---|---|
| **slowapi** (decorator, Redis storage) | simplest; less control over custom token-bucket math | $0 |
| **Custom Lua script on Redis** (atomic token bucket / sliding window) | atomic, exact, no race; you maintain it | $0 |
| **fastapi-limiter** | async-native; smaller ecosystem | $0 |

**Opinion:** use **slowapi for per-key burst limits** (cheap, idiomatic) and a **small custom Redis Lua sliding-window for the monthly quota** (you need it tied to plan + exposed in billing, which slowapi doesn't model). One Lua script keeps the quota check atomic.

### 3.4 Security / compliance
- Quota/limit keys namespaced by `partner_id` so one tenant can't exhaust another.
- Reject anonymous traffic before the limiter (auth first, limit second — limit by partner, not IP, for B2B).
- Log 429s to detect abuse / undersized plans.

### 3.5 Concrete fit to this stack
```python
# apps/api/app/skilled_id/ratelimit.py
QUOTA_LUA = """
local used = redis.call('INCRBY', KEYS[1], ARGV[1])
if used == tonumber(ARGV[1]) then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return used
"""  # KEYS[1]=quota:{partner}:{yyyymm}; ARGV[1]=cost rows; ARGV[2]=seconds-to-month-end

async def check_quota(p: PartnerCtx, cost: int, redis, plan_limit: int):
    key = f"quota:{p.partner_id}:{utcnow():%Y%m}"
    used = await redis.eval(QUOTA_LUA, 1, key, cost, seconds_to_month_end())
    if used > plan_limit:
        raise HTTPException(429, {"code": "quota_exceeded", "limit": plan_limit,
                                  "upgrade": "https://skilled.pro/billing"},
                            headers={"Retry-After": str(seconds_to_month_end())})
    return plan_limit - used  # -> RateLimit-Remaining
```
```python
# per-key burst via slowapi
from slowapi import Limiter
limiter = Limiter(key_func=lambda req: req.state.partner_id,
                  storage_uri=settings.redis_url)
# @limiter.limit("20/second") on the verification route
```

### 3.6 Risks
- **Redis as a single point** — quota/limit fails open or closed? Decide explicitly (recommend **fail-open for burst limiter, fail-closed for quota** so you never give away unmetered usage on a Redis blip — but cap fail-closed with a short circuit-breaker to avoid total outage).
- **Month-boundary races** — Lua atomicity handles it; the `EXPIRE`-on-first-write pattern above is the safe idiom.
- **Clock drift** between app instances on `Retry-After` — compute from Redis-side TTL where possible.

---

## 4. Access models & metered billing (Stripe)

### 4.1 State of the art (2026)
Stripe's modern path is **Billing Meters + Meter Events** (the legacy usage-records API is deprecated since `2025-03-31.basil`; every metered price now requires a backing **Meter**). The canonical pattern: **write usage to your DB first, aggregate, then push meter events to Stripe asynchronously** — Stripe is for billing, your DB is the source of truth for real-time display, debugging, and audit. Meter events want a **unique idempotency-style identifier** (Stripe enforces uniqueness over a rolling 24h+ window), timestamps within ~35 days past / 5 min future, and Stripe waits ~1h after period end to finalize invoices for late events. Multiple prices (graduated/tiered) attach to a single meter. ([Stripe Meter Events][st-me], [Stripe Meters][st-m], [Prefab usage billing][pf], [buildmvpfast][bmf])

### 4.2 Recommended approach (opinionated)
**Hybrid commercial model:**
- **SaaS subscription tiers** (Starter / Growth / Scale) = a base fee + an included monthly verification allowance (the §3 quota). Most predictable revenue; easiest for partners to budget.
- **Metered overage** beyond the allowance, billed graduated (e.g. $0.05/verification first 50k over, $0.03 next, $0.01 above) — one Stripe Meter (`verifications`), multiple prices.
- **Pure per-query (PAYG)** tier for tiny partners with no commitment.
- **Bulk/enterprise** = custom contract, same meter, negotiated price.

**Implementation discipline:** record every billable verification in `usage_events` (Postgres) at request time; a scheduled Railway job rolls up hourly and emits Stripe `MeterEvent`s with a deterministic `identifier` (your `usage_event.id`) so retries are idempotent. Never call Stripe inline on the hot path.

### 4.3 Tools / libraries / tradeoffs / cost
| Pick | Tradeoff | Cost |
|---|---|---|
| **Stripe Billing Meters** (`stripe` Python SDK) | the standard; ~1h finalize grace; 24h idempotency window | Stripe Billing fee on revenue (typ. 0.5–0.7% on top of processing) |
| Scheduled rollup | **Railway cron** or APScheduler/Celery beat | $0 incremental |
| Alt: Orb / Metronome / Lago | richer usage-billing engines, entitlements | Lago OSS $0 / Orb-Metronome paid |

**Opinion:** Stripe Meters is the right call — you're already likely on Stripe and it covers graduated tiers natively. Reach for **Lago** only if entitlements/credits get complex.

### 4.4 Security / compliance
- Reconcile DB rollup vs Stripe meter summaries daily; alert on drift.
- Handle `v1.billing.meter.error_report_triggered` webhooks (`meter_event_customer_not_found`, `_invalid_value`).
- Usage events are an auditable financial record — append-only, never mutate.

### 4.5 Concrete fit to this stack
```sql
create table usage_events (
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null references partners(id),
  stripe_customer_id text not null,
  event_type text not null,             -- 'verification' | 'bulk_row'
  quantity int not null default 1,
  reported_to_stripe_at timestamptz,    -- null = not yet billed
  created_at timestamptz not null default now()
);
create index on usage_events (partner_id, created_at);
create index on usage_events (reported_to_stripe_at);  -- find unbilled
```
```python
# scheduled rollup (Railway cron)  apps/api/app/skilled_id/billing.py
async def push_usage_to_stripe(conn, stripe):
    rows = await conn.fetch("""
       select stripe_customer_id, sum(quantity) q, max(id) as cursor
       from usage_events where reported_to_stripe_at is null
       group by stripe_customer_id""")
    for r in rows:
        stripe.billing.MeterEvent.create(
            event_name="verifications",
            payload={"stripe_customer_id": r["stripe_customer_id"], "value": r["q"]},
            identifier=f"rollup-{r['cursor']}-{utcnow():%Y%m%d%H}")  # idempotent
        await conn.execute("update usage_events set reported_to_stripe_at=now() "
                           "where stripe_customer_id=$1 and reported_to_stripe_at is null",
                           r["stripe_customer_id"])
```

### 4.6 Risks
- **Double-billing** on retry — solved by the deterministic `identifier` + the `reported_to_stripe_at` flag.
- **Missing the ~1h finalize window** for late events — keep the rollup cadence ≤ hourly.
- **Quota (§3) and meter (§4) disagreeing** — derive both from the *same* `usage_events` table as source of truth.

---

## 5. Granular consent & data minimization

### 5.1 State of the art (2026)
Consent in 2026 is **granular, specific, purpose-bound, and traceable through the pipeline** — regulators (and patterns like Amazon's June-30-2026 CAPI consent-object requirement) push consent provenance into every API event payload. For credentials specifically, **verifiable-credential / micro-permission** patterns let a subject authorize a *single data point* ("age over 21: yes") without revealing the underlying value (birth date). API responses should **default to minimal** disclosure and require explicit, consent-backed requests for anything more; **consent-scope verification** keeps processing inside the granted boundary. ([didit micro-permissions][did], [Secure Privacy data minimization][sp], [ComplianceHub Amazon][ch], [ComplyDog GDPR API][cd])

### 5.2 Recommended approach (opinionated)
- **Consent is a first-class table** with three *independent* dimensions per credential per partner (or per partner-category): **display** (may show in partner UI), **internal_use** (may use for partner's own decisioning), **external_sharing** (may forward to a downstream). These are separate booleans/scopes — the prompt's core requirement — and the API response is filtered by the *intersection* of partner scope × subject consent.
- **Return attested status, not documents.** Default response = `{credential, status, issuer, verified_at, expires_at}`. The raw artifact is never an API field unless a distinct, higher consent + scope exists.
- **Purpose binding.** The partner declares a `purpose` on each query; consent records the purposes the subject allowed; mismatch → field omitted (not errored — minimize, don't leak the existence of a withheld field where avoidable).
- **Stamp consent provenance** (`consent_id`, `granted_at`) onto every disclosure row in the audit log.

### 5.3 Tools / libraries / tradeoffs / cost
| Concern | Pick | Tradeoff | Cost |
|---|---|---|---|
| Consent storage | Postgres table (below) | simple, queryable, auditable | $0 |
| Response shaping | Pydantic response models built per-request from consent | a bit of code; total control of what serializes | $0 |
| Future: selective disclosure | W3C Verifiable Credentials + BBS+ selective disclosure | strongest privacy; heavier to operate | OSS |

### 5.4 Security / compliance
- **Data minimization by construction:** the response model only includes fields the consent grants — withheld fields are never serialized, so they can't leak via logs.
- Subject can revoke any dimension; revocation is immediate (consent checked per request, not cached beyond seconds).
- DSAR/right-to-erasure: consent + disclosure tables make "who saw what, when, under which consent" answerable in one query.

### 5.5 Concrete fit to this stack
```sql
create table consents (
  id uuid primary key default gen_random_uuid(),
  applicant_id uuid not null references applicants(id),
  partner_id uuid references partners(id),      -- null = applies to a partner_category
  partner_category text,                         -- e.g. 'job_board','staffing'
  credential_type text not null,                 -- or '*'
  allow_display boolean not null default false,
  allow_internal_use boolean not null default false,
  allow_external_sharing boolean not null default false,
  purposes text[] not null default '{}',
  granted_at timestamptz not null default now(),
  revoked_at timestamptz
);

create table disclosure_log (             -- append-only: what left the system
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null,
  applicant_id uuid not null,
  consent_id uuid not null references consents(id),
  fields text[] not null,
  purpose text,
  created_at timestamptz not null default now()
);
```
```python
def shape_response(record, consent, requested_purpose) -> dict:
    if consent.revoked_at or requested_purpose not in consent.purposes:
        return {"status": "no_consent"}                  # minimal, no field existence leak
    out = {"credential": record.type, "status": record.status,
           "issuer": record.issuer, "verified_at": record.verified_at,
           "expires_at": record.expires_at}
    if not consent.allow_display:
        out.pop("issuer", None)                          # minimize per dimension
    return out
```

### 5.6 Risks
- **Consent caching staleness** → showing data after revocation. Check consent live; only cache for seconds.
- **Over-broad `partner_category` consents** — prefer per-partner where the subject expects it; document the default clearly at grant time.
- **Logging the withheld value by accident** — enforce that logs serialize the *response model*, never the raw record.

---

## 6. Multi-tenancy & future white-label (unions / workforce boards / government)

### 6.1 State of the art (2026)
The 2026 default for B2B SaaS is **shared schema + `tenant_id` + Postgres RLS as a defense-in-depth backstop** (scales to hundreds of thousands of tenants; RLS alone is *not* sufficient — the app must scope explicitly too). **Schema-per-tenant** suits hundreds–low-thousands of tenants needing more isolation; **database-per-tenant** is the right call for **regulated / white-label / data-residency** workloads (government, unions) where compliance demands hard isolation. Tenant identity must be resolved at the API boundary and carried through cache, jobs, audit, and analytics. ([dasroot patterns][dr], [ClickHouse PG multitenancy][ch2], [PlanetScale tenancy][ps], [Fritzsche RLS][rf])

### 6.2 Recommended approach (opinionated)
- **Now (Glassdoor/Indeed/staffing):** shared schema. `partner_id` already scopes everything; that *is* your tenant key. Add **RLS on the SKILLED ID tables** as a backstop with `app.current_partner` set per request, but keep explicit `where partner_id = $1` in queries (defense in depth — RLS is the safety net, not the seatbelt).
- **White-label tier (unions / workforce boards / government):** promote to **database-per-tenant** (or at minimum schema-per-tenant) for hard data-residency/isolation, plus the **mTLS** auth tier from §2. Drive tenant routing from a `tenants` registry that maps a tenant to its DB connection + branding + auth mode.
- **Branding/white-label** = config (logo, domain, sender identity) layered over the same API contract; the contract stays versioned and identical so SDKs work everywhere.

### 6.3 Tools / libraries / tradeoffs / cost
| Pattern | When | Tradeoff | Cost |
|---|---|---|---|
| Shared schema + RLS | default, many tenants | cheapest, easiest migrations; weakest isolation | $0 |
| Schema-per-tenant (dynamic `search_path`) | 100s–1000s, mid isolation | migration fan-out; moderate | $0 |
| DB-per-tenant | regulated / white-label / residency | strongest isolation & residency; ops + cost per tenant | 1 Postgres/Supabase project per gov tenant |

### 6.4 Security / compliance
- RLS policies as backstop on every tenant-scoped table.
- Per-request tenant context set in one middleware; never trust a `tenant_id` from the request body — derive it from the authenticated partner/cert.
- Audit, cache keys, background jobs, and usage events **all** carry tenant id (the "four isolation pillars": operational, data, compliance, analytical).

### 6.5 Concrete fit to this stack
```sql
-- RLS backstop on shared tables
alter table consents enable row level security;
create policy tenant_isolation on consents
  using (partner_id = current_setting('app.current_partner', true)::uuid);
```
```python
# middleware sets tenant context every request (Supabase service-role connection)
async def with_tenant(p: PartnerCtx, conn):
    await conn.execute("select set_config('app.current_partner', $1, true)",
                       str(p.partner_id))
# white-label routing
async def get_tenant_conn(tenant: Tenant):
    return pools[tenant.db_url] if tenant.isolation == "database" else shared_pool
```

### 6.6 Risks
- **Migration sprawl** if you jump to DB-per-tenant too early — stay shared until a regulated deal forces it.
- **RLS bypass via service-role key** — the API already uses the Supabase service-role (RLS-bypassing) key for writes; that means **RLS won't protect you unless you also set `app.current_partner` and keep explicit scoping** — treat the explicit `where partner_id` as the *primary* control, RLS as backup.
- **Cross-tenant cache leak** — namespace every Redis key by tenant/partner.

---

## 7. Concrete endpoint list (OpenAPI-style)

```
# --- Auth (OAuth2 client-credentials) ---
POST   /v1/oauth/token                      # client_credentials grant -> short-lived JWT

# --- Credential verification (core, monetized) ---
GET    /v1/credentials/{applicant_ref}      # consent-scoped verified status (single)
        scope: credential:read  ?purpose=hiring
POST   /v1/credentials:verify               # query by external identifiers (email/SSN-hash)
        scope: credential:read  Idempotency-Key
POST   /v1/bulk/verifications               # submit a bulk job (async)
        scope: bulk:submit      Idempotency-Key
GET    /v1/bulk/verifications/{job_id}       # job status
GET    /v1/bulk/verifications/{job_id}/results   # cursor-paginated results

# --- Consent (read-only to partners; subjects grant in SKILLED Pro UI) ---
GET    /v1/consents/{applicant_ref}         # what this partner is allowed to see
        scope: consent:read

# --- Account / usage / billing transparency ---
GET    /v1/usage                            # current period usage vs quota
GET    /v1/usage/events                      # cursor-paginated billable events
GET    /v1/account                           # plan, tier, limits

# --- Webhooks (partner-subscribed) ---
POST   /v1/webhooks                          # create subscription (Idempotency-Key)
GET    /v1/webhooks                          # list (cursor)
       events: credential.verified, credential.expired, consent.revoked

GET    /health
GET    /v1/openapi.json                      # the contract
```

### Sample request
```http
GET /v1/credentials/appl_8f2c?purpose=hiring HTTP/1.1
Host: id.skilled.pro
Authorization: Bearer eyJhbGciOiJFUzI1Ni␣...
SKILLED-Version: 2026-06-01
Idempotency-Key: 6f1c0b2e-...      # (on POST variants)
```

### Sample response — consent allows status, denies issuer/document
```http
HTTP/1.1 200 OK
X-Request-Id: req_a1b2c3
RateLimit-Limit: 250000
RateLimit-Remaining: 249831
RateLimit-Reset: 218400
SKILLED-Version: 2026-06-01

{
  "applicant_ref": "appl_8f2c",
  "purpose": "hiring",
  "credentials": [
    {
      "credential_type": "journeyman_electrician",
      "status": "VERIFIED",
      "verified_at": "2026-03-01T00:00:00Z",
      "expires_at": "2028-03-01T00:00:00Z",
      "consent": { "display": true, "internal_use": true, "external_sharing": false }
    },
    {
      "credential_type": "osha_30",
      "status": "no_consent"
    }
  ],
  "_meta": { "consent_id": "cns_44d9", "data_minimized": true }
}
```

### Sample error (quota exhausted)
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 218400
X-Request-Id: req_z9y8

{ "code": "quota_exceeded", "message": "Monthly verification allowance reached.",
  "limit": 250000, "upgrade_url": "https://skilled.pro/billing", "request_id": "req_z9y8" }
```

---

## 8. Build order (pragmatic)

1. `partners` + hashed **API keys** + `authenticate_partner` dependency + per-key slowapi burst limit. (Onboard first staffing partner.)
2. `consents` + `disclosure_log` + consent-shaped responses + `GET /v1/credentials/{ref}`. (The product.)
3. `usage_events` + Redis quota Lua + Stripe Meters rollup job. (Get paid.)
4. **OAuth2 client-credentials** tier + scopes + rotation UI. (Scale to Glassdoor/Indeed.)
5. Bulk job lane + webhooks + cursor pagination hardening.
6. White-label: `tenants` registry, DB-per-tenant routing, mTLS via Cloudflare front. (Government/union deals.)

---

## Sources

- digitalapplied — REST API Design in 2026: <https://www.digitalapplied.com/blog/rest-api-design-2026-engineering-reference-best-practices> [da]
- Fern — API design best practices guide (2026): <https://buildwithfern.com/post/api-design-best-practices-guide> [fern]
- techinterview — API Design Patterns (versioning/pagination/idempotency): <https://www.techinterview.org/post/3233474122/system-design-api-design-patterns-rest-graphql-grpc-versioning-pagination-rate-limiting-idempotency-hateoas/> [ti]
- Scalekit — OAuth client-credentials vs mTLS: <https://www.scalekit.com/blog/oauth-client-credentials-vs-mtls> [sk1]
- Scalekit — API authentication in B2B SaaS: <https://www.scalekit.com/blog/api-authentication-b2b-saas> [sk2]
- Security Boulevard — M2M Authentication / OAuth2 client credentials (2026): <https://securityboulevard.com/2026/05/machine-to-machine-m2m-authentication-complete-guide-with-oauth-2-0-client-credentials-flow/> [sb]
- Elysiate — API Gateway Authentication Patterns 2026: <https://www.elysiate.com/blog/api-gateway-authentication-patterns-jwt-oauth> [el]
- freeCodeCamp — Token Bucket Rate Limiting with FastAPI: <https://www.freecodecamp.org/news/token-bucket-rate-limiting-fastapi/> [fcc]
- Medium (Majumder) — Using SlowAPI in FastAPI: <https://shiladityamajumder.medium.com/using-slowapi-in-fastapi-mastering-rate-limiting-like-a-pro-19044cb6062b> [slow]
- Bryan Antonio — Rate Limiter with FastAPI and Redis: <https://bryananthonio.com/blog/implementing-rate-limiter-fastapi-redis/> [ba]
- DEV.to — Distributed Rate Limiter (sliding window): <https://dev.to/jpegcreate/building-a-distributed-rate-limiter-for-fastapi-with-redis-sliding-window-algorithm-5h10> [dt]
- Stripe — Meter Events API reference: <https://docs.stripe.com/api/billing/meter-event> [st-me]
- Stripe — Meters API reference: <https://docs.stripe.com/api/billing/meter> [st-m]
- Prefab — Usage-based billing with Stripe Meters: <https://prefab.cloud/blog/usage-based-billing-with-stripe-meters/> [pf]
- buildmvpfast — Stripe Metered Billing Guide for SaaS (2026): <https://www.buildmvpfast.com/blog/stripe-metered-billing-implementation-guide-saas-2026> [bmf]
- didit — Micro-Permissions & Granular Consent / Verifiable Credentials: <https://didit.me/blog/micro-permissions-granular-consent-verifiable-credentials/> [did]
- Secure Privacy — AI Data Minimization: <https://secureprivacy.ai/blog/ai-data-minimization> [sp]
- ComplianceHub — Amazon consent-signal API deadline (June 30 2026): <https://compliancehub.wiki/amazon-consent-signal-june-30-2026-gdpr-capi-events-api-deadline/> [ch]
- ComplyDog — GDPR API Security for Developers: <https://complydog.com/blog/gdpr-api-security-data-protection-developers> [cd]
- dasroot — Multi-Tenancy Database Patterns (2026): <https://dasroot.net/posts/2026/01/multi-tenancy-database-patterns-schema-database-row-level/> [dr]
- ClickHouse — Multi-tenant SaaS on Postgres: <https://clickhouse.com/resources/engineering/multi-tenant-saas-postgres-architecture> [ch2]
- PlanetScale — Approaches to tenancy in Postgres: <https://planetscale.com/blog/approaches-to-tenancy-in-postgres> [ps]
- Rico Fritzsche — Mastering PostgreSQL RLS for Multi-Tenancy: <https://ricofritzsche.me/mastering-postgresql-row-level-security-rls-for-rock-solid-multi-tenancy/> [rf]
