-- Scale-readiness indexing: full-text/fuzzy search + hot-path composites.
--
-- PRODUCTION NOTE: on an already-large `jobs`/`employers` table these index
-- builds take a write lock, and the generated `search_tsv` column forces a full
-- table rewrite under ACCESS EXCLUSIVE. On a live database at volume, either run
-- during a maintenance window, OR build the indexes with CREATE INDEX
-- CONCURRENTLY (which cannot run inside a transaction — apply those statements
-- outside the migration runner's transaction wrapper) and add the tsvector
-- column NOT NULL-free first, backfilling in batches. At the current data size
-- this migration is instantaneous; this note is for when it isn't.
--
-- Motivation (see the concurrency audit):
--   * job/employer search is ILIKE '%…%' → sequential scans. Trigram GIN
--     indexes make leading-wildcard ILIKE index-backed and add typo tolerance.
--   * the matches ranking queries filter eligibility_status alongside the
--     score — fold it into the visibility-partial composites so it's resolved
--     by the index instead of post-filtered.
--   * /jobs/browse orders active rows by posted_date — no supporting index.
--   * the browse state filter uses UPPER(state) — needs a functional index.

-- ---------------------------------------------------------------------------
-- 1. Fuzzy / substring search — pg_trgm trigram GIN
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS jobs_title_trgm_idx
  ON public.jobs USING gin (title_raw gin_trgm_ops);
CREATE INDEX IF NOT EXISTS jobs_desc_trgm_idx
  ON public.jobs USING gin (description_raw gin_trgm_ops);
CREATE INDEX IF NOT EXISTS employers_name_trgm_idx
  ON public.employers USING gin (name gin_trgm_ops);

-- Optional relevance-ranked keyword search for the jobs bar. A generated
-- tsvector kept in sync automatically; query with websearch_to_tsquery and
-- ORDER BY ts_rank when you want ranked results instead of raw ILIKE.
ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS search_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english',
      coalesce(title_raw, '') || ' ' || coalesce(description_raw, ''))
  ) STORED;
CREATE INDEX IF NOT EXISTS jobs_search_tsv_idx
  ON public.jobs USING gin (search_tsv);

-- ---------------------------------------------------------------------------
-- 2. matches ranking — add eligibility_status to the visibility composites so
--    "WHERE eligibility_status IN (...) ORDER BY policy_adjusted_score" is one
--    index range scan.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS matches_applicant_elig_score_idx
  ON public.matches (applicant_id, eligibility_status, policy_adjusted_score DESC NULLS LAST)
  WHERE is_visible_to_applicant = TRUE;
CREATE INDEX IF NOT EXISTS matches_job_elig_score_idx
  ON public.matches (job_id, eligibility_status, policy_adjusted_score DESC NULLS LAST)
  WHERE is_visible_to_employer = TRUE;

-- ---------------------------------------------------------------------------
-- 3. /jobs/browse — active-rows ordering + case-insensitive state filter
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS jobs_active_posted_idx
  ON public.jobs (posted_date DESC NULLS LAST, created_at DESC)
  WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS jobs_upper_state_idx
  ON public.jobs (UPPER(state))
  WHERE is_active = TRUE;
