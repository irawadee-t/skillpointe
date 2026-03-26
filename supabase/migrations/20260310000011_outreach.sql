-- =============================================================
-- Migration: employer_outreach
-- Feature: Employer reach-out messaging to matched candidates
-- =============================================================

CREATE TABLE IF NOT EXISTS public.employer_outreach (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id   UUID    NOT NULL REFERENCES public.employers (id) ON DELETE CASCADE,
  job_id        UUID    NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  applicant_id  UUID    NOT NULL REFERENCES public.applicants (id) ON DELETE CASCADE,
  match_id      UUID    REFERENCES public.matches (id) ON DELETE SET NULL,

  subject       TEXT,
  body          TEXT    NOT NULL,
  ai_generated  BOOLEAN NOT NULL DEFAULT FALSE,

  -- Status lifecycle: draft → sent
  status        TEXT    NOT NULL DEFAULT 'draft',
    -- 'draft', 'sent'
  sent_at       TIMESTAMPTZ,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_employer_outreach_updated_at
  BEFORE UPDATE ON public.employer_outreach
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.employer_outreach ENABLE ROW LEVEL SECURITY;

-- Employers manage their own outreach records via service role
-- (all writes go through the API with service role)

CREATE INDEX IF NOT EXISTS employer_outreach_employer_idx
  ON public.employer_outreach (employer_id);

CREATE INDEX IF NOT EXISTS employer_outreach_applicant_idx
  ON public.employer_outreach (applicant_id);

CREATE INDEX IF NOT EXISTS employer_outreach_job_idx
  ON public.employer_outreach (job_id);
