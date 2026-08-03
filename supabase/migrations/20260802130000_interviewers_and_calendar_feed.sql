-- =====================================================================
-- Interview assignees + calendar feed secrets  (additive only)
--
-- 1. interview_slots gains "who is running this interview" fields.
--    The assignment is information routing, not access control:
--      - interviewer_contact_id — set when the interviewer is a teammate in
--        employer_contacts (nullable; ON DELETE SET NULL so removing a
--        contact never breaks scheduled interviews — the denormalized
--        name/email below keep rendering).
--      - interviewer_name / interviewer_email / interviewer_title — always
--        denormalized onto the slot so the applicant-facing "You'll meet:
--        Marcus Lee, Production Supervisor" line and the .ics exports work
--        even for free-form (not-in-the-system) interviewers.
--
-- 2. calendar_feed_secrets — one long-lived random secret per user that
--    keys the HMAC on their personal ICS feed token
--    (GET /calendar/feed.ics?token=...). Rotating the secret revokes every
--    previously issued feed URL for that user.
-- =====================================================================

ALTER TABLE public.interview_slots
  ADD COLUMN IF NOT EXISTS interviewer_contact_id UUID
    REFERENCES public.employer_contacts(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS interviewer_name  TEXT,
  ADD COLUMN IF NOT EXISTS interviewer_email TEXT,
  ADD COLUMN IF NOT EXISTS interviewer_title TEXT;

COMMENT ON COLUMN public.interview_slots.interviewer_name IS
  'Denormalized display name of whoever runs the interview (may be a non-user).';

CREATE TABLE IF NOT EXISTS public.calendar_feed_secrets (
  user_id    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  secret     TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  rotated_at TIMESTAMPTZ
);

-- Backend talks to Postgres directly (service role); nothing here is meant
-- for the anon PostgREST surface.
ALTER TABLE public.calendar_feed_secrets ENABLE ROW LEVEL SECURITY;
