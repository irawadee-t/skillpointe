# SKILLED Pro — Job Matching + Shared AI Services (2026)

> Production-grade, state-of-the-art architecture for the matching engine and shared AI services.

## Executive Summary

SKILLED Pro's matching layer should evolve the existing deterministic engine (hard gates + weighted dimensions + semantic similarity) into a **multi-stage retrieve-and-rerank pipeline**: pgvector/PostGIS for candidate generation, a LightGBM LambdaMART learning-to-rank (LTR) model for fine ordering, and a separately-stored policy layer — keeping the current "gates cap the score" and "base-fit vs policy" separation intact. Explanations stay trustworthy by computing feature attributions deterministically and using a small LLM only to *verbalize* pre-computed evidence (never to invent scores), with serving kept under 500 ms via HNSW ANN, precomputed match tables, and Redis caching. The shared AI services — OCR/document intelligence, LLM content generation, fraud/anomaly detection, and labor-market intelligence — are consolidated into one centralized FastAPI "AI service" with strict prompt versioning, eval harnesses, guardrails, and cost controls, choosing tiered 2026 models (small models for high-volume tasks, frontier models only where reasoning quality pays for itself).

---

## 0. Where This Plugs Into the Current Stack

The existing engine (`packages/matching/`: `gates.py`, `scorer.py`, `text_scorer.py`, `engine.py`) is a strong **Layer 1 (base fit)** that should be *kept*, not replaced. The 2026 upgrades slot in as:

| Existing | 2026 upgrade |
|---|---|
| `engine.py` formula `cap × (structured×0.75 + semantic×0.25)` | Becomes the **candidate generator + feature source**; an LTR reranker consumes its dimension scores as features |
| `text_scorer.py` cosine on OpenAI embeddings | Move embeddings into **pgvector HNSW**; add **hybrid BM25 + vector** retrieval |
| `config.py` / `SCORING_CONFIG.yaml` policy layer | Unchanged role — Layer 2 reranking stays separate as `policy_adjusted_score` |
| `match_dimension_scores` table | Becomes the **feature attribution store** that grounds LLM explanations |
| `extraction/` LLM pipeline | Folds into the **centralized AI service** with shared prompt mgmt + guardrails |

Guardrails from `CLAUDE.md` that constrain every recommendation below: no batch matching (continuous ranking only), hard-gate failures cap scores, LLMs are supporting not primary, geography is first-class, base-fit stays separate from policy, and extraction falls back to neutral defaults.

---

## 1. AI Matching Engine — Multi-Factor Model, Embeddings + Learning-to-Rank

### 1.1 State of the art (2026)

Production matching/recommendation is universally a **multi-stage funnel**: cheap **candidate generation** (ANN over embeddings + metadata filters) narrows millions to hundreds, then an expensive **reranker** orders the shortlist. The 2026 consensus:

- **Hybrid retrieval is no longer optional.** Dense vectors miss exact tokens (a specific OSHA cert, a NIMS code, "EPA 608 Type II"); lexical (BM25) misses paraphrase. The standard fix is to run both and merge with **Reciprocal Rank Fusion (RRF)**, scoring each doc `1/(k+rank)` with `k≈60`. RRF needs no weight tuning and is what Elasticsearch/OpenSearch use.
- **GBDT learning-to-rank (LambdaMART) remains the workhorse reranker**, not deep nets. A 2025 OTTO e-commerce study found a well-tuned **LightGBM LambdaMART** matched or beat deep-learning rankers at a fraction of the latency and ops cost. It optimizes ranking metrics (NDCG) directly via the `lambdarank` objective.
- **Two-tower neural retrieval** is used at hyperscale (Etsy, etc.) for candidate generation, but is overkill until you have large labeled interaction data; GBDT-on-features is the right first reranker for SKILLED Pro's data volume.

### 1.2 Recommended approach

Three-stage funnel that *reuses* the deterministic engine:

```
Stage 0 — Hard gates (existing gates.py): drop ineligible candidates entirely.
          Geography feasibility + required credentials are gates, not soft scores.

Stage 1 — Candidate generation (retrieval), target ~200 candidates:
            (a) PostGIS ST_DWithin radius filter (configurable radius)
            (b) pgvector HNSW ANN on profile/job embeddings
            (c) BM25 lexical (pg_textsearch / ParadeDB) on skills+titles
          Merge (b)+(c) with RRF inside one SQL function.

Stage 2 — Rerank the shortlist with LightGBM LambdaMART. Features =
          the 9 existing dimension scores + semantic sim + BM25 score +
          distance_km + wage_gap + availability_match + experience_delta +
          recency/engagement signals. Output = base_fit_score ranking.

Stage 3 — Policy rerank (existing config.py): boosts/visibility →
          policy_adjusted_score, stored separately. Unchanged.
```

Until enough labeled outcomes exist to train LambdaMART (interviews, hires, mutual interest from `engagement_events` / `hire_outcomes`), keep the current weighted formula as the Stage-2 scorer and **log features for every served match** so the LTR model can be trained later. This is a clean, low-risk migration path.

### 1.3 Tools / libraries / models + tradeoffs + cost

- **Vector store — use `pgvector` (Supabase) first.** Supabase benchmarks show pgvector HNSW matching/beating Qdrant at ~1M vectors on equal compute at 99% recall; you avoid a second datastore, keep ACID + joins to `applicants`/`jobs`/PostGIS in one query. **Cost: $0 extra** (already on Supabase Postgres).
  - **Migrate to Qdrant** only if you exceed ~5–10M vectors *and* need heavy filtered QPS; Qdrant wins in-graph filtering at scale. Self-host on Railway (~$20–60/mo) or Qdrant Cloud.
  - **Pinecone** = fastest time-to-prod, fully managed, but adds a vendor + sync pipeline + cost (~$70+/mo starter, scales with pods). Not worth it given you already run Postgres.
  - **Weaviate** wins built-in hybrid+rerank as one query, but again duplicates Postgres.
- **BM25 in Postgres:** `pg_textsearch` (open-sourced early 2026, v1.3 production-ready) or **ParadeDB** `pg_search` — both bring real BM25 ranking + RRF into Postgres, letting you "ship one database instead of two retrieval stacks."
- **Reranker:** **LightGBM** (`objective="lambdarank"`, `metric="ndcg"`) — tiny, CPU-fast (sub-ms per shortlist), trains in minutes. XGBoost `rank:ndcg` is an equivalent alternative. **Cost: negligible compute.**
- **Embeddings:** keep OpenAI `text-embedding-3-small` (1536-d, cheap at ~$0.02/M tokens). Consider `text-embedding-3-large` (3072-d) only for the skills-similarity field if recall is weak.

### 1.4 Latency / scaling / security

- HNSW ANN is the latency floor (10–50 ms at 1M scale in pgvector with tuned `ef_search`); PostGIS `ST_DWithin` on a GiST index prunes first so the ANN set is small. LightGBM rerank of ~200 rows is < 5 ms.
- **Security:** retrieval must respect employer data isolation (`CLAUDE.md`: employers only see candidates for their own jobs). Apply the employer/job filter *inside* the SQL candidate-gen query, never as a post-filter. Backend uses the service-role key; never expose raw embeddings or other employers' rows to the client.

### 1.5 Fit to this stack

Everything lives in the FastAPI + Supabase Postgres + Redis stack you already run. Add a `match_features` table (or columns on `matches`) to log per-match feature vectors for future LTR training. PostGIS + pgvector + pg_textsearch are all Postgres extensions — no new infra on Railway.

### 1.6 Risks

- **Cold-start LTR:** no labeled data initially → keep deterministic scorer; only switch to LambdaMART once you have ~thousands of labeled outcomes. Mitigate with implicit labels (interest_set, dm_sent, hire_reported).
- **pgvector ceiling:** revisit at ~5M vectors; the funnel design makes swapping the retrieval store a localized change.
- **Position/exposure bias** in implicit labels — debias with inverse-propensity weighting when training the ranker.

---

## 2. Explainable Match Scores — Feature Attribution + Grounded LLM Summaries

### 2.1 State of the art (2026)

The dominant, hallucination-safe pattern is **two-stage and decoupled**: (1) compute attributions deterministically (per-dimension contributions, or SHAP for the GBDT reranker); (2) feed those *numeric, structured* attributions into an LLM whose *only* job is to phrase them in plain language. 2026 research (joint-optimization explainable rec, llmSHAP, RobustExplain) is explicit: **separate the recommender from the explainer** and **ground the LLM in Shapley/feature evidence** so it can't invent reasons. The model never sees or produces the score — it narrates supplied facts.

### 2.2 Recommended approach

- Reuse `match_dimension_scores` as the attribution store. For the weighted scorer, contribution = `weight × dimension_score`; for the LambdaMART reranker, compute **SHAP values** (LightGBM has native TreeSHAP, microseconds per row) to get true per-feature attributions.
- Render `top_strengths` / `top_gaps` / `required_missing_items` deterministically from those contributions (you already store these fields).
- Pass the structured evidence to a **small LLM** (`gpt-5-mini` / `claude-haiku-4.5`) with a strict template: "Given these facts, write 2 sentences. Do not introduce facts not listed. Do not state a numeric score." Validate output against the input facts (entailment check) before display.
- **Template fallback:** if the LLM call fails or fails validation, render a deterministic template — no blank explanations.

### 2.3 Tools / cost

- LightGBM TreeSHAP (free, in-process). LLM verbalization at `gpt-5-mini` ($0.25/M in, $2/M out) ≈ fractions of a cent per explanation; cache by `match_id` since explanations only change when scores change.

### 2.4 Latency / security

- Attribution is sub-ms. Don't block the match list on LLM calls — precompute/caches explanations or render templates inline and hydrate the LLM version async. Never leak competing-candidate features into an explanation shown to one party.

### 2.5 Fit to this stack

Slots directly into `PROMPTS.md` (explanation template) and the existing `verifier.py` pattern. Store the grounded explanation on `matches` (e.g., `explanation_text`, `explanation_model`, `explanation_grounded_at`).

### 2.6 Risks

- LLM drift / persuasion bias (RobustExplain shows explainers can be nudged). Mitigate with the entailment/grounding check and fixed templates. Geography must always appear when it's a binding factor (`CLAUDE.md` guardrail).

---

## 3. Real-Time Inference < 500 ms — Serving, Caching, ANN, Precompute

### 3.1 State of the art (2026)

Latency budgets are spent across a multi-stage pipeline: HNSW ANN (10–300 ms depending on scale/recall), metadata filtering, record fetch, rerank. The leading levers are **precompute** (don't rank at request time when you can), **HNSW with tuned `ef_search`**, **in-session caching with stable cache keys**, and GPU ANN (CAGRA/cuVS) only at large scale. Serverless vector DBs add 100–500 ms cold-start — a reason to avoid them for an SLA path.

### 3.2 Recommended approach (hybrid precompute + on-demand)

- **Precompute the `matches` table** (you already do via recompute scripts + fire-and-forget on new jobs/applicants). The applicant/employer list views read precomputed `base_fit_score` / `policy_adjusted_score` — **this is already < 50 ms** (a DB read).
- **On-demand** only for: new entity before recompute finishes, ad-hoc filtered browse, and live re-ranking with fresh policy. Budget: PostGIS+ANN retrieval ≤ 80 ms → LightGBM rerank ≤ 10 ms → response.
- **Redis caching:** cache ranked shortlists keyed by `(viewer_id, filter_hash, page)` (mirrors your 5s DM polling cache discipline); cache embeddings and LLM explanations. Stable keys across pagination keep hit-rates high.
- Tune pgvector: `hnsw` index with `m=16`, `ef_construction=64`, request-time `ef_search` tuned to hit recall@k vs latency; `VACUUM`/`ANALYZE` after bulk recompute.

### 3.3 Tools / cost

- Redis (already in stack, Railway). pgvector HNSW (free). No GPU needed at SKILLED Pro scale — revisit cuVS/CAGRA only past tens of millions of vectors.

### 3.4 Security

- Cache keys must include the viewer identity/role so cached results never cross the employer-isolation boundary. Set TTLs and invalidate on recompute.

### 3.5 Fit to this stack

Continuous-ranking precompute is exactly the current `recompute_matches.py` + trigger model — keep it; add Redis read-through caching and the on-demand funnel for the live path.

### 3.6 Risks

- Stale precomputed scores between recomputes → show "updated X ago" and recompute on the events that matter (new job, profile edit, credential verified).

---

## 4. One-Click Apply, Geo-Targeted Recommendations (PostGIS), AI Interview Scheduling

### 4.1 One-click apply

- State of the art is a single idempotent action that snapshots the candidate's verified profile + credentials into an application record, logs an engagement event, and notifies the employer. Make it **idempotent** (unique constraint on `(applicant, job)`), and **synchronous-fast** (write + enqueue side-effects). Reuse your `engagement_events` (`apply_click`) and conversations system.

### 4.2 Geo-targeted recommendations (PostGIS, configurable radius)

- Use **`ST_DWithin(geog, point, radius_m)`** for radius filtering — it leverages the spatial index (GiST), unlike `ST_Distance`. Store location as `geography` for correct earth-distance, and add a parallel `geometry` column + index for hot-path speed if needed (the docs note a second `ST_DWithin` on indexed geometry can be ~3× faster). Radius is per-user configurable; "willing to relocate / remote" bypasses the gate.
- Geography stays first-class: it's a **hard gate** (feasibility), a **ranking feature** (`distance_km`), and an **explanation factor** — exactly the `CLAUDE.md` mandate.

### 4.3 AI-assisted interview scheduling

- 2026 leaders (Guide, Evie, Paradox Olivia, candidate.fyi) use an **LLM agent that parses natural-language requests** ("can we move to Thursday PM?"), checks availability, proposes slots, negotiates across parties, and confirms — resolving ~80% of sessions without a human.
- For SKILLED Pro: a tool-using agent (LLM + calendar tools: Google/Microsoft Graph, or hold-based internal calendar) that proposes slots inside the existing DM thread, with deterministic conflict-checking (the LLM proposes, code books). Keep money/identity actions out of the agent; humans confirm.

### 4.4 Cost / latency / risk

- PostGIS filtering is sub-ms with indexes. Scheduling agent uses a mid/small model per turn (cents/conversation). Risk: double-booking → make the booking step a transactional DB constraint, not LLM-trusted; always offer human override.

---

## 5. Centralized Matching / Shared AI Service Architecture

### 5.1 Recommended architecture

A single internal **FastAPI "AI service" module** (within `apps/api`, or a separate Railway service if you need independent scaling) that owns all model-touching logic and exposes clean internal endpoints:

```
ai-service/
  embeddings/      → embed(text) [OpenAI], batch + cache in Redis/pgvector
  retrieval/       → hybrid candidate gen (PostGIS + pgvector + BM25 + RRF)
  ranking/         → LightGBM LambdaMART load/score + SHAP attribution
  generation/      → LLM content (summaries, explanations, nudges, reports)
  documents/       → OCR + doc intelligence pipeline (§6)
  fraud/           → anomaly + document-fraud scoring (§7)
  intelligence/    → BLS/Lightcast demand + wage benchmarks (§8)
  prompts/         → versioned prompt registry (PROMPTS.md → code), evals
  guardrails/      → input/output validation, PII, injection, schema
```

- **Why centralize:** one place for prompt versioning, eval, cost tracking, guardrails, model routing, and caching — instead of LLM calls scattered across routers. Mirrors the 2026 "Document AI microservice" pattern (orchestrated reasoning loops behind one service boundary).
- **Model routing:** a thin router picks the model per task class (small model default, frontier only when justified) so you can swap models without touching call sites.

### 5.2 Fit / risk

- Keep pure logic (`packages/matching`, `packages/extraction`) free of I/O as today; the AI service is the I/O + orchestration shell around them. Risk: a single service becoming a bottleneck — mitigate by making it stateless behind Redis and scaling horizontally on Railway.

---

## 6. OCR & Document Intelligence Pipeline (Service Architecture)

> Cross-reference the credentials doc for verification policy; this section covers the **service architecture**.

### 6.1 State of the art (2026)

The pattern is an **agentic, multi-stage document microservice**: classify → route to the right parser → multimodal extraction to structured JSON → secondary validation (chain-of-thought self-check, self-healing reruns) → confidence-thresholded **human-in-the-loop**. Specialist OCR (AWS Textract, Google Document AI) for forms/tables; **vision LLMs** (Gemini 2.5/3 Pro, Claude, GPT vision) for whole-document understanding and adaptation to new credential formats without reprogramming.

### 6.2 Recommended approach

```
upload → virus/type scan → classify(doc_type)
      → route: forms/IDs → Textract; rich/varied creds → vision LLM → JSON
      → validate: schema + cross-ref against issuer/registry + self-check
      → confidence < threshold OR fraud signal → review_queue_items (you have this)
      → on pass: write verified credential + audit_logs entry
```

Use your existing `review_queue_items` and `audit_logs` tables (low-confidence → admin review; every decision auditable — a `CLAUDE.md` guardrail). Store extraction confidence so it can gate the matching hard-credential gate.

### 6.3 Tools / cost / latency / security

- **Google Document AI** or **AWS Textract** (~$1.50/1k pages) for structured docs; **vision LLM** (Gemini 3 Flash cheapest capable multimodal at $0.50/M in) for varied credentials. Async pipeline (queue) — OCR is not on the < 500 ms path. **Security:** PII at rest encrypted, signed URLs, never send full SSNs to LLMs, redact before logging.

### 6.4 Risk

- LLM extraction hallucination on fields → always schema-validate and cross-ref against an authoritative issuer/registry where one exists; flag, don't auto-trust.

---

## 7. LLM Content Generation — Prompts, Eval, Guardrails, Cost, Model Choice

### 7.1 Content types

Profile summaries, match explanations (§2), outcomes reports, and nudges/notifications.

### 7.2 State of the art + recommended practice (2026)

- **Prompt management:** versioned prompt registry (your `PROMPTS.md` → loaded as code with version IDs), A/B and regression eval per prompt/model pair (PromptLayer, Braintrust, LangSmith-style). Track every prompt-response pair.
- **Eval:** golden-set + LLM-as-judge for quality; **regression-test prompts** before model swaps. Small purpose-built eval models (e.g., Galileo Luna-2) catch hallucination/PII/injection at ~98% lower cost than a frontier judge.
- **Guardrails:** input guards (prompt-injection, PII) *before* the expensive call (saves cost + latency), output guards (schema, toxicity, grounding/entailment for explanations). Runtime, millisecond enforcement.
- **Cost control:** model routing (small default), aggressive caching (explanations, summaries keyed by content hash), max-token caps, prompt caching for shared system prompts, batch where non-interactive.

### 7.3 Model choice (June 2026) + tradeoffs

| Task | Model | Why | Approx cost (in/out per M) |
|---|---|---|---|
| Nudges, short summaries, explanation verbalization | **gpt-5-mini** or **claude-haiku-4.5** | high volume, cheap, fast | $0.25/$2 ; $1/$5 |
| Match explanations needing nuance | **gemini-3-flash** / **claude-haiku-4.5** | strong quality/cost | $0.50/$3 |
| Outcomes reports, complex reasoning, doc self-check | **claude-sonnet-4.6** / **gemini-3.1-pro** | reasoning quality | $3/$15 ; $2/$12 |
| Vision OCR / varied credentials | **gemini-3-flash** (cheap) / **gemini-3.1-pro** (hard cases) | multimodal | $0.50/$3 ; $2/$12 |
| Frontier (rare, hardest) | **claude-opus-4.8** / **gpt-5.5** | top reasoning | $5/$25 ; $5/$30 |

Default to small models; reserve frontier for tasks where quality measurably moves outcomes. The platform's current `LLM_MODEL`/`LLM_EXTRACTION_MODEL` env split already encodes this two-tier idea — extend it to per-task routing.

### 7.4 Fit / risk

- Lives in the AI service `generation/` + `prompts/` modules. Risk: cost creep and silent quality regressions on model swaps → enforce eval gates in CI and per-feature cost dashboards.

---

## 8. Fraud & Anomaly Detection — Credential Uploads + Platform Activity

### 8.1 State of the art (2026)

Identity fraud is now **AI/deepfake-driven** (thousands of monthly liveness-bypass attempts industry-wide); 30% of enterprises no longer trust standalone document verification. The shift is to **risk-adaptive, multi-signal** detection: don't trust a document alone — fuse device fingerprint, session behavior, identity-reuse, and liveness, and **escalate checks in response to live risk**.

### 8.2 Recommended approach

- **Document fraud:** metadata/EXIF analysis, copy-move/clone detection, font/template consistency, and a vision-LLM tamper check; cross-ref issuer registry; reused-document detection (perceptual hash dedupe across uploads).
- **Platform anomaly:** unsupervised **Isolation Forest** (scikit-learn) on behavioral features (signup velocity, device sharing across "different" accounts, impossible travel, bulk-apply patterns, message spam). Feed scores into a risk tier that gates auto-trust and routes to `review_queue_items`.
- **Device fingerprint + identity-reuse** signals as first-class features. Adaptive step-up: high risk → require additional verification.

### 8.3 Tools / cost / latency / fit

- scikit-learn IsolationForest (free, ms inference) for behavioral anomaly; optional vendor liveness (Persona/Onfido-class) for biometric. Vision-LLM tamper check reuses §6 pipeline. Runs async; risk score stored on the credential/account and written to `audit_logs`.

### 8.4 Risk

- Label scarcity → semi-supervised/unsupervised first, add supervised once confirmed-fraud labels accrue. False positives harm real tradespeople → always allow human appeal via the review queue; never hard-auto-reject.

---

## 9. Labor Market Intelligence — BLS + Job-Posting Data → Demand & Wage Benchmarks

### 9.1 State of the art (2026)

Two complementary sources: **BLS** (authoritative, free, but lagged — OES wages, employment projections, OEWS by SOC + MSA) and **Lightcast** (2.5B+ postings, daily refresh, 165+ countries, Talent Benchmark wages, **Hiring Demand Rating** = YoY 90-day posting-volume momentum). Postings data is the leading indicator; BLS is the ground truth.

### 9.2 Recommended approach

- **Wage benchmarks:** BLS OEWS by SOC occupation × MSA as the free baseline; layer Lightcast Talent Benchmark for current, granular, trade-specific wages where budget allows. Surface as "this job pays at the Nth percentile for [trade] in [metro]" — drives the `wage_gap` ranking feature and applicant guidance.
- **Demand signals:** ingest Lightcast Hiring Demand Rating (or compute your own YoY posting momentum from scraped + partner postings) per trade × region to prioritize recommendations and inform employers.
- **Pipeline:** scheduled ETL (your existing `etl/` + scripts pattern) → normalized `labor_market_stats` table keyed by `(soc_code, region, period)` → joined into matching features and shown in outcomes reports.

### 9.3 Tools / cost / latency / fit

- **BLS Public Data API** — free, registration raises rate limits; map trades → SOC codes once. **Lightcast API** — paid (enterprise contract), strong ROI for wage/demand depth. Batch/nightly ETL — not on the request path; cache aggregates. Fits the existing ETL + normalization scripts cleanly.

### 9.4 Risk

- BLS lag (months) and SOC↔trade mapping ambiguity; Lightcast posting data overcounts duplicate/aggregator postings. Mitigate by triangulating both sources and labeling freshness/source on every figure.

---

## Recommended Build Order (lowest risk first)

1. Move embeddings → pgvector HNSW; add PostGIS `ST_DWithin` radius gating. (Reuses engine; immediate latency + geo wins.)
2. Add hybrid BM25 + RRF retrieval in Postgres (`pg_textsearch`/ParadeDB).
3. Stand up the centralized AI service shell + prompt registry + guardrails + cost tracking.
4. Grounded explanations (deterministic attribution → small-LLM verbalization + entailment check).
5. Log per-match features; train LightGBM LambdaMART once labels accrue; swap in as Stage-2 scorer.
6. Document-intelligence pipeline + fraud/anomaly scoring into `review_queue_items` / `audit_logs`.
7. Labor-market ETL (BLS first, Lightcast when funded) feeding wage/demand features.
8. AI interview-scheduling agent in the DM thread (LLM proposes, code books).

---

## Sources

- [Pinecone vs Weaviate vs Qdrant vs pgvector: Which Vector DB Wins in 2026? — Second Talent](https://www.secondtalent.com/resources/pinecone-vs-weaviate-vs-qdrant-vs-pgvector/)
- [pgvector vs Pinecone vs Qdrant vs Weaviate (2026): Which We Actually Use in Production — Kalvium Labs](https://www.kalviumlabs.ai/blog/vector-databases-compared-pgvector-pinecone-qdrant-weaviate/)
- [pgvector vs Pinecone vs Qdrant: 2026 Benchmarks — Vecstore](https://vecstore.app/blog/vector-database-performance-compared)
- [Best Vector Databases in 2026: A Complete Comparison Guide — Firecrawl](https://www.firecrawl.dev/blog/best-vector-databases)
- [pg_trgm + pgvector Hybrid Retrieval: Build Better RAG in Postgres (2026) — CallSphere](https://callsphere.ai/blog/vw7h-pg-trgm-pgvector-hybrid-retrieval-2026)
- [Hybrid Search in 100 Lines: BM25 + pgvector with RRF Merge — DEV](https://dev.to/gabrielanhaia/hybrid-search-in-100-lines-bm25-pgvector-with-rrf-merge-58cn)
- [Elasticsearch's Hybrid Search, Now in Postgres (BM25 + Vector + RRF) — Tiger Data](https://www.tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres-bm25-vector-rrf)
- [Hybrid Search in PostgreSQL: The Missing Manual — ParadeDB](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
- [BM25 Search in PostgreSQL: The Missing Piece for Hybrid Search — Pedro Alonso](https://www.pedroalonso.net/blog/postgres-bm25-search/)
- [LambdaMART Explained: The Workhorse of Learning-to-Rank — Shaped](https://www.shaped.ai/blog/lambdamart-explained-the-workhorse-of-learning-to-rank)
- [Industry Insights from Comparing Deep Learning and GBDT Models for E-Commerce Learning-to-Rank — arXiv](https://arxiv.org/pdf/2507.20753)
- [Learning to Rank — XGBoost docs](https://xgboost.readthedocs.io/en/latest/tutorials/learning_to_rank.html)
- [Unified Embedding Based Personalized Retrieval in Etsy Search — arXiv](https://arxiv.org/pdf/2306.04833)
- [Sub-100ms Discovery: Why Retrieval Speed is the Agent Bottleneck — Shaped](https://www.shaped.ai/blog/sub-100ms-discovery-why-retrieval-speed-is-the-agent-bottleneck)
- [Enhancing GPU-Accelerated Vector Search in Faiss with NVIDIA cuVS — NVIDIA](https://developer.nvidia.com/blog/enhancing-gpu-accelerated-vector-search-in-faiss-with-nvidia-cuvs/)
- [Can Explanations Improve Recommendations? A Joint Optimization with LLM Reasoning — arXiv](https://arxiv.org/pdf/2502.16759)
- [RobustExplain: Evaluating Robustness of LLM-Based Explanation Agents for Recommendation — arXiv](https://arxiv.org/pdf/2601.19120)
- [llmSHAP: A Principled Approach to LLM Explainability — arXiv](https://arxiv.org/pdf/2511.01311)
- [A hybrid explainability framework for recommender systems — IJIRSS](https://ijirss.com/index.php/ijirss/article/download/9669/2189/16512)
- [ST_DWithin — PostGIS docs](https://postgis.net/docs/ST_DWithin.html)
- [Use ST_DWithin for radius queries — PostGIS](https://postgis.net/documentation/tips/st-dwithin/)
- [Spatial Indexing — Introduction to PostGIS](http://postgis.net/workshops/postgis-intro/indexing.html)
- [PostGIS Performance Showdown: Geometry vs. Geography — Medium](https://medium.com/coord/postgis-performance-showdown-geometry-vs-geography-ec99967da4f0)
- [Operationalizing Document AI: A Microservice Architecture for OCR and LLM Pipelines — arXiv](https://arxiv.org/html/2605.18818v1)
- [Leveraging Document AI for LLM Data Ingestion Beyond OCR in 2026 — Data Science Society](https://www.datasciencesociety.net/leveraging-document-ai-for-llm-data-ingestion-beyond-ocr-capabilities-in-2026-agentic-ai/)
- [Document Intelligence with LLMs: Extracting Structure from Unstructured Data [2026] — Virtido](https://virtido.com/blog/document-intelligence-llm-extraction-guide)
- [Mastering LLM Guardrails: Complete 2026 Guide — Orq.ai](https://orq.ai/blog/llm-guardrails)
- [Best tools for tracking LLM costs in production (2026) — Braintrust](https://www.braintrust.dev/articles/best-tools-tracking-llm-costs-2026)
- [5 Best AI Guardrails Platforms Compared in 2026 — Galileo](https://galileo.ai/blog/best-ai-guardrails-platforms)
- [AI API Pricing Comparison (June 2026): 50+ Models Side-by-Side — DevTk.AI](https://devtk.ai/en/blog/ai-api-pricing-comparison-2026/)
- [LLM API Pricing Comparison 2026 — BenchLM.ai](https://benchlm.ai/llm-pricing)
- [How AI and deepfakes are reshaping identity fraud in 2026 — Fintech Global](https://fintech.global/2026/03/20/how-ai-and-deepfakes-are-reshaping-identity-fraud-in-2026/)
- [The Fraud Files: Stolen Credentials, Fake Biometrics, and the Synthetic Identity Wave (June 2026) — Proof](https://www.proof.com/blog/the-fraud-files-stolen-credentials-fake-biometrics-and-the-synthetic-identity-wave-june-2026)
- [AI Deepfake Threats in 2026: Detection & Protection Guide — Adaptive Security](https://www.adaptivesecurity.com/blog/ai-deepfake-in-2026-a-detection-and-protection-guide-for-security-teams)
- [Lightcast Talent Benchmark — Lightcast docs](https://docs.lightcast.io/lightcast-api/docs/talent-benchmark)
- [Bureau of Labor Statistics (BLS) — Lightcast Knowledge Base](https://kb.lightcast.io/en/articles/7932528-bureau-of-labor-statistics-bls)
- [Can Job Postings Data Track AI Demand? — Lightcast](https://lightcast.io/resources/blog/can-job-postings-data-track-ai-demand)
- [Employment Projections — U.S. Bureau of Labor Statistics](https://www.bls.gov/emp/)
- [Automated Interview Scheduling in 2026: The Complete Guide — candidate.fyi](https://candidate.fyi/post/automated-interview-scheduling-2026-guide)
- [Evie — Your AI recruiting coordinator](https://www.evie.ai/)
- [Conversational Scheduling — Paradox](https://www.paradox.ai/products/conversational-scheduling)
