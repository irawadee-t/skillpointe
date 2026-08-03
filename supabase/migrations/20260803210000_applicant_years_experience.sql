-- The matching engine's seniority gate reads applicant "years_experience", but
-- no column ever produced it: the value arrived as NULL, was coerced to 0, and
-- hard-failed every senior/management posting for every applicant.
--
-- experience_raw is free-text essay content and is not a substitute. This adds
-- the structured field the gate was already written against.

ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS years_experience smallint
        CHECK (years_experience IS NULL OR (years_experience >= 0 AND years_experience <= 60));

COMMENT ON COLUMN public.applicants.years_experience IS
    'Relevant trade experience in whole years. NULL means "not on file" and is '
    'treated as uncertainty by the seniority gate, not as zero experience.';

-- Partial index: the gate only cares about applicants who have a value.
CREATE INDEX IF NOT EXISTS applicants_years_experience_idx
    ON public.applicants (years_experience)
    WHERE years_experience IS NOT NULL;
