-- =============================================================
-- Migration: hire_outcomes
-- Feature: Employer hire reporting and placement tracking
-- =============================================================

CREATE TABLE IF NOT EXISTS public.hire_outcomes (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id  UUID    NOT NULL REFERENCES public.applicants (id) ON DELETE CASCADE,
  job_id        UUID    NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  employer_id   UUID    NOT NULL REFERENCES public.employers (id) ON DELETE CASCADE,
  match_id      UUID    REFERENCES public.matches (id) ON DELETE SET NULL,

  -- One outcome per (applicant, job) pair
  CONSTRAINT hire_outcomes_unique UNIQUE (applicant_id, job_id),

  outcome_type  TEXT    NOT NULL DEFAULT 'hired',
    -- 'hired', 'declined', 'withdrew'

  hire_date     DATE,
  start_date    DATE,
  reported_by   UUID    REFERENCES auth.users (id),
  notes         TEXT,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_hire_outcomes_updated_at
  BEFORE UPDATE ON public.hire_outcomes
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.hire_outcomes ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS hire_outcomes_employer_idx
  ON public.hire_outcomes (employer_id);

CREATE INDEX IF NOT EXISTS hire_outcomes_applicant_idx
  ON public.hire_outcomes (applicant_id);

CREATE INDEX IF NOT EXISTS hire_outcomes_created_at_idx
  ON public.hire_outcomes (created_at DESC);
