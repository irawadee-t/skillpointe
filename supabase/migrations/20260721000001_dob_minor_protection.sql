-- Date of birth + minor protection.
--
-- Serving a nonprofit's scholars means some applicants are under 18 (FERPA /
-- COPPA / CCPA-minor). We capture DOB so under-18 applicants can be default-
-- excluded from employer-facing discovery. DOB is nullable (legacy rows and
-- adults who decline to share age simply aren't gated, and are treated as
-- adults). A guardian-consent override for intentional minor discoverability is
-- a follow-on; the safe default here is: minors are not proactively surfaced to
-- employers.

ALTER TABLE public.applicants
  ADD COLUMN IF NOT EXISTS date_of_birth date;

-- Partial index to make the "is a minor" discovery filter cheap.
CREATE INDEX IF NOT EXISTS applicants_dob_idx
  ON public.applicants (date_of_birth)
  WHERE date_of_birth IS NOT NULL;

COMMENT ON COLUMN public.applicants.date_of_birth IS
  'Optional. When set and under 18, the applicant is excluded from employer-facing discovery by default (minor protection).';
