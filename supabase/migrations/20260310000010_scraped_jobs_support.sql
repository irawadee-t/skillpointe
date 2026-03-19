-- =============================================================
-- Migration: scraped jobs support
-- Adds source tracking fields to jobs table and a scrape_runs
-- audit table for tracking scraping pipeline runs.
-- =============================================================

-- Add scraping-specific columns to jobs
ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS source_url    TEXT,
  ADD COLUMN IF NOT EXISTS source_site   TEXT,
  ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS jobs_source_idx
  ON public.jobs (source) WHERE source IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_source_url_idx
  ON public.jobs (source_url) WHERE source_url IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_url_unique
  ON public.jobs (source_url) WHERE source_url IS NOT NULL;

-- Scrape runs tracking table
CREATE TABLE IF NOT EXISTS public.scrape_runs (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_site   TEXT        NOT NULL,
  status        TEXT        NOT NULL DEFAULT 'running',
  started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMPTZ,
  jobs_found    INTEGER     NOT NULL DEFAULT 0,
  jobs_created  INTEGER     NOT NULL DEFAULT 0,
  jobs_updated  INTEGER     NOT NULL DEFAULT 0,
  jobs_deactivated INTEGER  NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS scrape_runs_source_site_idx
  ON public.scrape_runs (source_site);
