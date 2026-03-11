-- =============================================================
-- Migration: applicant import support
-- Phase 4 — Imports + ETL
--
-- Imported applicants do not have Supabase Auth accounts yet.
-- They sign up later; the /auth/complete-signup endpoint links
-- the auth user to the existing applicant row by email.
--
-- Changes:
--   1. user_id → nullable (was NOT NULL)
--   2. email column added for pre-signup matching
--   3. Unique index on email (partial — only when email is set)
-- =============================================================

ALTER TABLE public.applicants
  ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE public.applicants
  ADD COLUMN IF NOT EXISTS email TEXT;

-- Unique index so two applicants cannot share an email
CREATE UNIQUE INDEX IF NOT EXISTS applicants_email_unique_idx
  ON public.applicants (email)
  WHERE email IS NOT NULL;

-- Index for the signup-linking lookup (email → user_id update)
CREATE INDEX IF NOT EXISTS applicants_email_idx
  ON public.applicants (email)
  WHERE email IS NOT NULL;

-- Comment: when an applicant signs up via /auth/complete-signup, the endpoint
-- should check for an existing applicant row with matching email and set
-- user_id on that row rather than creating a new row.  This linking step
-- will be implemented in Phase 5/6 when the applicant profile views are built.
