-- The job-import approval flow (app/routers/job_imports.py approve_batch)
-- publishes rows with an employment_type value, but public.jobs never had the
-- column — publishing any import batch failed with UndefinedColumnError.
-- Additive fix: mirror job_import_rows.employment_type onto jobs.

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS employment_type TEXT;
