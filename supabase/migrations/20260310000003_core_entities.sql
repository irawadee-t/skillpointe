-- =============================================================
-- Migration: core entities — applicants, employers, employer_contacts, jobs
-- Phase 3 — Core Data Model
--
-- Key design principles:
--   - raw imported / self-entered values preserved alongside normalised values
--   - geography is first-class (city, state, region, travel/relocation prefs)
--   - FK to auth.users kept tight; business data lives in these tables
--   - no batch-matching columns; this is a continuous ranking system
-- =============================================================


-- ---------------------------------------------------------------
-- applicants
-- One row per applicant user.  Created automatically on signup
-- via POST /auth/complete-signup (or admin import).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.applicants (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL UNIQUE
                                REFERENCES auth.users (id) ON DELETE CASCADE,

  -- Identity
  first_name        TEXT,
  last_name         TEXT,
  preferred_name    TEXT,
  phone             TEXT,

  -- Raw imported / self-entered values (always preserved)
  program_name_raw  TEXT,    -- program name exactly as entered / imported
  career_goals_raw  TEXT,    -- free-text career goals
  experience_raw    TEXT,    -- free-text experience / resume text
  bio_raw           TEXT,    -- essay / personal statement

  -- Normalised location  (geography first-class per CLAUDE.md)
  city              TEXT,
  state             TEXT,    -- 2-letter state code
  region            TEXT,    -- normalised US region code (FK-quality, no hard FK to allow nulls)
  zip_code          TEXT,
  country           TEXT        NOT NULL DEFAULT 'US',

  -- Geography preferences (hard-gate inputs)
  willing_to_relocate          BOOLEAN     NOT NULL DEFAULT FALSE,
  willing_to_travel            BOOLEAN     NOT NULL DEFAULT FALSE,
  commute_radius_miles         INTEGER,
  relocation_willingness_notes TEXT,
  travel_willingness_notes     TEXT,

  -- Normalised programme / career path (soft FK — nullable until normalised)
  canonical_job_family_id      UUID        REFERENCES public.canonical_job_families (id),
  canonical_career_pathway_id  UUID        REFERENCES public.canonical_career_pathways (id),

  -- Availability / timing (hard-gate inputs)
  expected_completion_date DATE,
  available_from_date      DATE,
  timing_notes             TEXT,

  -- Profile state
  onboarding_complete BOOLEAN     NOT NULL DEFAULT FALSE,
  profile_last_updated_at TIMESTAMPTZ,

  -- Source tracking
  source          TEXT,                   -- 'import', 'self_signup'
  import_run_id   UUID,                   -- set if row was created via import

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_applicants_updated_at
  BEFORE UPDATE ON public.applicants
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.applicants ENABLE ROW LEVEL SECURITY;

-- Applicants can read and update their own row
CREATE POLICY "applicants_read_own"
  ON public.applicants FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "applicants_update_own"
  ON public.applicants FOR UPDATE
  USING (auth.uid() = user_id);

-- Service-role (FastAPI) handles INSERT and all cross-applicant access

CREATE INDEX IF NOT EXISTS applicants_user_id_idx
  ON public.applicants (user_id);

CREATE INDEX IF NOT EXISTS applicants_canonical_job_family_id_idx
  ON public.applicants (canonical_job_family_id)
  WHERE canonical_job_family_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS applicants_state_idx
  ON public.applicants (state)
  WHERE state IS NOT NULL;


-- ---------------------------------------------------------------
-- employers
-- One row per employer company (not per user).
-- Multiple contacts (users) may belong to one employer.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.employers (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Company info
  name        TEXT        NOT NULL,
  industry    TEXT,
  description TEXT,
  website     TEXT,

  -- Location
  city        TEXT,
  state       TEXT,
  region      TEXT,
  zip_code    TEXT,
  country     TEXT        NOT NULL DEFAULT 'US',

  -- Policy flags
  is_partner  BOOLEAN     NOT NULL DEFAULT FALSE,
  partner_since DATE,

  -- Source tracking
  source         TEXT,
  import_run_id  UUID,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_employers_updated_at
  BEFORE UPDATE ON public.employers
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.employers ENABLE ROW LEVEL SECURITY;
-- NOTE: the SELECT policy for employers is added AFTER employer_contacts is created below.

CREATE INDEX IF NOT EXISTS employers_name_idx
  ON public.employers (name);

CREATE INDEX IF NOT EXISTS employers_is_partner_idx
  ON public.employers (is_partner);


-- ---------------------------------------------------------------
-- employer_contacts
-- Links a Supabase Auth user to an employer company.
-- One user → one employer for MVP (UNIQUE on user_id).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.employer_contacts (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL UNIQUE
                          REFERENCES auth.users (id) ON DELETE CASCADE,
  employer_id UUID        NOT NULL
                          REFERENCES public.employers (id) ON DELETE CASCADE,
  is_primary  BOOLEAN     NOT NULL DEFAULT FALSE,
  title       TEXT,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_employer_contacts_updated_at
  BEFORE UPDATE ON public.employer_contacts
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.employer_contacts ENABLE ROW LEVEL SECURITY;

-- Contacts can read their own link row
CREATE POLICY "employer_contacts_read_own"
  ON public.employer_contacts FOR SELECT
  USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS employer_contacts_user_id_idx
  ON public.employer_contacts (user_id);

CREATE INDEX IF NOT EXISTS employer_contacts_employer_id_idx
  ON public.employer_contacts (employer_id);


-- ---------------------------------------------------------------
-- jobs
-- One row per job posting.  Raw source text is always preserved
-- alongside normalised fields.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.jobs (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id UUID        NOT NULL
                          REFERENCES public.employers (id) ON DELETE CASCADE,

  -- Raw source values (always preserved)
  title_raw                    TEXT        NOT NULL,
  description_raw              TEXT,
  requirements_raw             TEXT,
  preferred_qualifications_raw TEXT,
  responsibilities_raw         TEXT,

  -- Normalised fields
  title_normalized             TEXT,
  canonical_job_family_id      UUID        REFERENCES public.canonical_job_families (id),

  -- Location (geography first-class)
  city            TEXT,
  state           TEXT,
  region          TEXT,
  zip_code        TEXT,
  country         TEXT        NOT NULL DEFAULT 'US',
  work_setting    public.work_setting_enum,
  travel_requirement TEXT,     -- 'none', 'light', 'moderate', 'frequent'

  -- Compensation (raw + normalised)
  pay_min         NUMERIC(12,2),
  pay_max         NUMERIC(12,2),
  pay_type        TEXT,         -- 'hourly', 'annual', 'contract'
  pay_raw         TEXT,         -- original string e.g. "$25–$35/hr"

  -- Requirements
  required_credentials  TEXT[]  NOT NULL DEFAULT '{}',   -- explicit required creds/licences
  preferred_credentials TEXT[]  NOT NULL DEFAULT '{}',
  required_experience_years INTEGER,
  experience_level      TEXT,   -- 'entry', 'mid', 'senior'

  -- Physical / compliance
  physical_requirements TEXT,
  background_check_required BOOLEAN NOT NULL DEFAULT FALSE,
  drug_test_required        BOOLEAN NOT NULL DEFAULT FALSE,

  -- Status
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  posted_date   DATE,

  -- Source tracking
  source         TEXT,
  import_run_id  UUID,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_jobs_updated_at
  BEFORE UPDATE ON public.jobs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Applicants can read active jobs (for ranked-match display)
CREATE POLICY "applicants_read_active_jobs"
  ON public.jobs FOR SELECT
  USING (is_active = TRUE);

-- Employer contacts can read/write their own employer's jobs
CREATE POLICY "employer_contacts_read_own_jobs"
  ON public.jobs FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.employer_contacts ec
      WHERE ec.employer_id = jobs.employer_id
        AND ec.user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS jobs_employer_id_idx
  ON public.jobs (employer_id);

CREATE INDEX IF NOT EXISTS jobs_canonical_job_family_id_idx
  ON public.jobs (canonical_job_family_id)
  WHERE canonical_job_family_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_state_idx
  ON public.jobs (state)
  WHERE state IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_is_active_idx
  ON public.jobs (is_active);


-- ---------------------------------------------------------------
-- Deferred RLS: employers SELECT policy
-- employer_contacts must exist before this policy can be created.
-- ---------------------------------------------------------------
CREATE POLICY "employer_contacts_read_own_employer"
  ON public.employers FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.employer_contacts ec
      WHERE ec.employer_id = public.employers.id
        AND ec.user_id = auth.uid()
    )
  );
