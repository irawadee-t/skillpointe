-- =============================================================
-- Employer self-serve careers-page pipeline.
--
-- An employer connects their careers-page URL once; every "pull"
-- re-scrapes that URL, filters to skilled-trades roles, dedupes
-- against the source's rolling import batch, validates apply
-- links, and records a history row so counts stay auditable.
-- =============================================================

-- 'stale' — a row whose source_url vanished from the careers site on a
-- re-pull. (The resync code already writes this value; the enum was missing
-- it, so resync's stale-marking failed silently. This fixes that too.)
ALTER TYPE public.job_import_row_status_enum ADD VALUE IF NOT EXISTS 'stale';

-- Review-queue reason for the periodic apply-link recheck.
ALTER TYPE public.review_queue_item_type_enum ADD VALUE IF NOT EXISTS 'broken_apply_link';

-- ---------------------------------------------------------------
-- employer_career_sources
-- One row per connected careers-page URL. Supports multiple URLs
-- per employer (plants on different ATSs, brand sub-sites).
-- Each source owns ONE rolling import batch that re-pulls sync into.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.employer_career_sources (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id     UUID        NOT NULL REFERENCES public.employers(id) ON DELETE CASCADE,
  url             TEXT        NOT NULL,
  platform        TEXT,                 -- workday | greenhouse | lever | generic | ...
  batch_id        UUID        REFERENCES public.job_import_batches(id) ON DELETE SET NULL,
  created_by      UUID        REFERENCES auth.users(id),

  last_pulled_at  TIMESTAMPTZ,
  last_status     TEXT,                 -- ok | error | blocked | no_jobs
  last_error      TEXT,
  jobs_found      INTEGER     NOT NULL DEFAULT 0,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (employer_id, url)
);

CREATE INDEX IF NOT EXISTS employer_career_sources_employer_idx
  ON public.employer_career_sources (employer_id, created_at DESC);

CREATE TRIGGER set_employer_career_sources_updated_at
  BEFORE UPDATE ON public.employer_career_sources
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.employer_career_sources ENABLE ROW LEVEL SECURITY;
-- Service-role only; access mediated by FastAPI.

-- ---------------------------------------------------------------
-- career_source_pulls
-- One row per pull run (manual "Refresh from site" or scheduled).
-- The counters back the employer-facing pull history.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.career_source_pulls (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       UUID        NOT NULL REFERENCES public.employer_career_sources(id) ON DELETE CASCADE,
  batch_id        UUID        REFERENCES public.job_import_batches(id) ON DELETE SET NULL,
  triggered_by    UUID        REFERENCES auth.users(id),

  status          TEXT        NOT NULL DEFAULT 'ok',  -- ok | error | blocked | no_jobs
  platform        TEXT,
  error           TEXT,

  jobs_found      INTEGER     NOT NULL DEFAULT 0,  -- total scraped from the site
  jobs_new        INTEGER     NOT NULL DEFAULT 0,  -- rows created this pull
  jobs_updated    INTEGER     NOT NULL DEFAULT 0,  -- rows refreshed in place
  jobs_removed    INTEGER     NOT NULL DEFAULT 0,  -- rows marked stale (gone from site)
  jobs_rejected   INTEGER     NOT NULL DEFAULT 0,  -- non-skilled-trades roles filtered out
  links_broken    INTEGER     NOT NULL DEFAULT 0,  -- apply links that failed validation

  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS career_source_pulls_source_idx
  ON public.career_source_pulls (source_id, created_at DESC);

ALTER TABLE public.career_source_pulls ENABLE ROW LEVEL SECURITY;
-- Service-role only; access mediated by FastAPI.

-- ---------------------------------------------------------------
-- Apply-link validation state
-- ---------------------------------------------------------------
ALTER TABLE public.job_import_rows
  ADD COLUMN IF NOT EXISTS link_status     TEXT,          -- ok | broken | blocked
  ADD COLUMN IF NOT EXISTS link_checked_at TIMESTAMPTZ;

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS apply_link_status     TEXT,    -- ok | broken | blocked
  ADD COLUMN IF NOT EXISTS apply_link_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS jobs_apply_link_check_idx
  ON public.jobs (apply_link_checked_at)
  WHERE is_active = TRUE AND source_url IS NOT NULL;
