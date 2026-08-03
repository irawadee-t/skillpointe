-- =============================================================
-- Career-source learned profiles + instant incremental sync.
--
-- After the first successful pull, the pipeline stores what it
-- learned about the site (platform API params, job-link URL
-- patterns, JSON-LD availability, HTTP cache validators) so every
-- re-sync can skip discovery: fetch ONLY the listing (a 304
-- short-circuits to "no changes"), diff per-job fingerprints, and
-- fetch detail pages only for new/changed postings.
--
-- Additive only. Three pieces:
--   1. employer_career_sources — profile JSONB + auto-sync cadence
--   2. career_source_jobs      — per-URL fingerprint memory
--   3. career_source_pulls     — timing/fetch counters + a human-
--      readable event payload (added/removed job titles etc.)
-- =============================================================

-- ---------------------------------------------------------------
-- 1. Learned extraction profile + auto-sync scheduling state.
-- ---------------------------------------------------------------
ALTER TABLE public.employer_career_sources
  ADD COLUMN IF NOT EXISTS extraction_profile       JSONB,
  ADD COLUMN IF NOT EXISTS auto_sync_enabled        BOOLEAN     NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS auto_sync_interval_hours INTEGER     NOT NULL DEFAULT 6,
  ADD COLUMN IF NOT EXISTS next_auto_sync_at        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS consecutive_failures     INTEGER     NOT NULL DEFAULT 0;

-- Scheduler scan: "which sources are due?"
CREATE INDEX IF NOT EXISTS employer_career_sources_auto_sync_idx
  ON public.employer_career_sources (next_auto_sync_at ASC NULLS FIRST)
  WHERE auto_sync_enabled;

-- ---------------------------------------------------------------
-- 2. Per-job fingerprint memory, keyed by canonical posting URL.
--
-- A dedicated table (not a JSONB blob on the source) because the
-- diff runs per URL on every sync: it needs an indexed lookup,
-- per-row first/last-seen + last-changed timestamps, and it must
-- not rewrite one ever-growing document per pull. Rows persist
-- when a posting vanishes (vanished_at set) so a reappearing job
-- keeps its first-seen history.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.career_source_jobs (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           UUID        NOT NULL REFERENCES public.employer_career_sources(id) ON DELETE CASCADE,
  source_url          TEXT        NOT NULL,
  title               TEXT,
  fingerprint         TEXT,          -- sha256 of the full extracted row (set once detail is fetched)
  listing_fingerprint TEXT,          -- cheap hash of listing-level signal (anchor text / API summary)

  first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_changed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  vanished_at         TIMESTAMPTZ,   -- NULL while the posting is live on the site

  UNIQUE (source_id, source_url)
);

CREATE INDEX IF NOT EXISTS career_source_jobs_live_idx
  ON public.career_source_jobs (source_id)
  WHERE vanished_at IS NULL;

ALTER TABLE public.career_source_jobs ENABLE ROW LEVEL SECURITY;
-- Service-role only; access mediated by FastAPI.

-- ---------------------------------------------------------------
-- 3. Pull history → sync activity log.
--    details carries the human-readable event payload:
--    {"added":[{"title","url"}], "updated":[...], "removed":[...],
--     "held":[...], "unchanged": 14, "relearned": false}
-- ---------------------------------------------------------------
ALTER TABLE public.career_source_pulls
  ADD COLUMN IF NOT EXISTS sync_mode   TEXT    NOT NULL DEFAULT 'full',
                                       -- full | incremental | not_modified | relearned
  ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
  ADD COLUMN IF NOT EXISTS fetch_count INTEGER,
  ADD COLUMN IF NOT EXISTS details     JSONB   NOT NULL DEFAULT '{}'::jsonb;
