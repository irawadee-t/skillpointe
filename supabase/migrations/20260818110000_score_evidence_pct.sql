-- Evidence share behind each match score: % of structured-score weight that
-- came from real applicant/job data rather than null-handling defaults.
-- Drives the UI information gate (low-evidence scores render as labels, not
-- confident numbers). Written by the matching pipeline on every recompute.
ALTER TABLE public.matches
    ADD COLUMN IF NOT EXISTS score_evidence_pct numeric(5,1);
COMMENT ON COLUMN public.matches.score_evidence_pct IS
    'Share (0-100) of structured-score weight backed by evidence rather than defaults. Below ~40 the UI shows a label instead of a number.';
