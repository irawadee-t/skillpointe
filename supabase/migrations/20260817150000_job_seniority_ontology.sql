-- Seniority ontology evidence on jobs. experience_level stays the display
-- value; these columns record HOW it was decided so every label is auditable
-- ("asks for 7+ years", "posting says 'we will train'"), per the O*NET-style
-- preparation-level classifier in packages/matching/seniority.py.

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS years_experience_required smallint
        CHECK (years_experience_required IS NULL OR years_experience_required BETWEEN 0 AND 40),
    ADD COLUMN IF NOT EXISTS entry_friendly boolean,
    ADD COLUMN IF NOT EXISTS seniority_evidence jsonb;

COMMENT ON COLUMN public.jobs.entry_friendly IS
    'Posting explicitly welcomes untrained applicants ("no experience necessary", '
    '"we will train"). NULL = not yet classified.';

CREATE INDEX IF NOT EXISTS jobs_entry_friendly_idx
    ON public.jobs (entry_friendly) WHERE entry_friendly IS TRUE;
