-- Internal-apply configuration — employers opt jobs into "Apply on SKILLED
-- Nation" and declare what they need from applicants.
--
--   • employers.accepts_internal_applications_default — company-wide default
--     for jobs that don't set their own flag (scraped/imported jobs included).
--   • jobs.accepts_internal_applications — per-job override (NULL = inherit
--     the company default).
--   • jobs.required_profile_fields — which profile-sourced groups the employer
--     requires at apply time. Allowed keys:
--       contact | location | program | availability | credentials | resume
--   • applications.reapply_count — a withdrawn application may be re-submitted
--     exactly once (the row is reactivated in place; count enforces the limit).
--   • applications.shared_fields — consent record: the profile groups that
--     were shared at submit time (snapshot lives in resume_snapshot; this is
--     the list the applicant reviewed and agreed to share).
--
-- Additive only.

BEGIN;

ALTER TABLE public.employers
  ADD COLUMN IF NOT EXISTS accepts_internal_applications_default BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS accepts_internal_applications BOOLEAN,
  ADD COLUMN IF NOT EXISTS required_profile_fields TEXT[] NOT NULL DEFAULT '{contact,location,program}'::text[];

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'jobs_required_profile_fields_valid'
  ) THEN
    ALTER TABLE public.jobs
      ADD CONSTRAINT jobs_required_profile_fields_valid
      CHECK (required_profile_fields <@ ARRAY['contact','location','program','availability','credentials','resume']::text[]);
  END IF;
END $$;

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS reapply_count SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS shared_fields TEXT[] NOT NULL DEFAULT '{}'::text[];

-- Fast lookup for the effective-internal-apply flag on browse.
CREATE INDEX IF NOT EXISTS jobs_internal_apply_idx
  ON public.jobs (accepts_internal_applications)
  WHERE accepts_internal_applications IS NOT NULL;

COMMIT;
