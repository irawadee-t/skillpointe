-- Practical signals extracted from posting text. These answer questions real
-- applicants ask before applying: what shift is it, is it a paid
-- apprenticeship, do they welcome veterans.

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS shift text
        CHECK (shift IS NULL OR shift IN ('day','evening','night','weekend','rotating')),
    ADD COLUMN IF NOT EXISTS is_apprenticeship boolean,
    ADD COLUMN IF NOT EXISTS veteran_friendly boolean;

CREATE INDEX IF NOT EXISTS jobs_is_apprenticeship_idx
    ON public.jobs (is_apprenticeship) WHERE is_apprenticeship IS TRUE;
