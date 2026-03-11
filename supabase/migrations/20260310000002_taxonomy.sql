-- =============================================================
-- Migration: taxonomy reference tables
-- Phase 3 — Core Data Model
--
-- canonical_job_families: normalisation target for program/job names.
-- canonical_career_pathways: training programs / pathways within a family.
-- geography_regions: US regional groupings for geography-aware ranking.
--
-- These tables are read-only for applicants and employers.
-- Only admins (via service-role API) can mutate them.
-- Seed data is loaded by supabase/seed.sql.
-- =============================================================


-- ---------------------------------------------------------------
-- canonical_job_families
-- Top-level job/trade family taxonomy.
-- Used to normalise applicant programs and job titles into a
-- common vocabulary for hard-gate and scoring comparisons.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.canonical_job_families (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  code        TEXT        NOT NULL UNIQUE,   -- short machine key, e.g. 'electrical'
  name        TEXT        NOT NULL,           -- display name, e.g. 'Electrical'
  description TEXT,
  parent_id   UUID        REFERENCES public.canonical_job_families (id),
  aliases     TEXT[]      NOT NULL DEFAULT '{}',  -- alternative names for fuzzy matching
  is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_canonical_job_families_updated_at
  BEFORE UPDATE ON public.canonical_job_families
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- public read, service-role write
ALTER TABLE public.canonical_job_families ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_job_families"
  ON public.canonical_job_families FOR SELECT
  USING (TRUE);

CREATE INDEX IF NOT EXISTS canonical_job_families_code_idx
  ON public.canonical_job_families (code);

CREATE INDEX IF NOT EXISTS canonical_job_families_parent_id_idx
  ON public.canonical_job_families (parent_id)
  WHERE parent_id IS NOT NULL;


-- ---------------------------------------------------------------
-- canonical_career_pathways
-- Training programmes / career pathways within a job family.
-- An applicant's programme maps to one of these to establish
-- job-family alignment.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.canonical_career_pathways (
  id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  code                    TEXT        NOT NULL UNIQUE,
  name                    TEXT        NOT NULL,
  description             TEXT,
  job_family_id           UUID        REFERENCES public.canonical_job_families (id),
  typical_duration_months INTEGER,                    -- typical programme length
  aliases                 TEXT[]      NOT NULL DEFAULT '{}',
  is_active               BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_canonical_career_pathways_updated_at
  BEFORE UPDATE ON public.canonical_career_pathways
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.canonical_career_pathways ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_career_pathways"
  ON public.canonical_career_pathways FOR SELECT
  USING (TRUE);

CREATE INDEX IF NOT EXISTS canonical_career_pathways_code_idx
  ON public.canonical_career_pathways (code);

CREATE INDEX IF NOT EXISTS canonical_career_pathways_job_family_id_idx
  ON public.canonical_career_pathways (job_family_id)
  WHERE job_family_id IS NOT NULL;


-- ---------------------------------------------------------------
-- geography_regions
-- US regional groupings used for geography-aware ranking.
-- e.g. 'northeast' → ['NY', 'NJ', 'CT', 'MA', 'RI', 'VT', 'NH', 'ME']
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.geography_regions (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  code        TEXT        NOT NULL UNIQUE,   -- e.g. 'northeast'
  name        TEXT        NOT NULL,           -- e.g. 'Northeast'
  states      TEXT[]      NOT NULL DEFAULT '{}',  -- 2-letter state codes
  description TEXT,
  is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.geography_regions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_geography_regions"
  ON public.geography_regions FOR SELECT
  USING (TRUE);

CREATE INDEX IF NOT EXISTS geography_regions_code_idx
  ON public.geography_regions (code);
