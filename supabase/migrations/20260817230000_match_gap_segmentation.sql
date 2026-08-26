-- The backfill below walks every existing match row doing JSONB parsing —
-- on hosted nano compute that exceeds the migration role's statement
-- timeout (observed live on the 2026-08 prod push). Lift it for this
-- session only; the setting dies with the migration connection. The
-- backfill itself is belt-and-braces: any full recompute rewrites every
-- row with engine-computed values anyway.
SET statement_timeout = 0;

-- Gap-based segmentation: what stands between this applicant and this job,
-- as data. n_gaps = how many gates are near-fit (0 for eligible);
-- primary_gap = the most structural one, for the card's one-sentence story.
-- A one-gap match at score 55 is a better lead than a three-gap match at 58,
-- and the ranked ORDER BY now says so.

ALTER TABLE public.matches
    ADD COLUMN IF NOT EXISTS n_gaps smallint,
    ADD COLUMN IF NOT EXISTS primary_gap text;

-- Backfill from the stored gate rationale (no recompute needed).
UPDATE public.matches SET
    n_gaps = (SELECT count(*) FROM jsonb_each(hard_gate_rationale::jsonb) je
               WHERE je.value->>'result' = 'near_fit'),
    primary_gap = (
        SELECT key FROM jsonb_each(hard_gate_rationale::jsonb) je
         WHERE je.value->>'result' = 'near_fit'
         ORDER BY CASE key
             WHEN 'job_family_compatibility' THEN 0   -- structural first
             WHEN 'seniority_compatibility' THEN 1
             WHEN 'geography_feasibility' THEN 2
             WHEN 'readiness_timing_compatibility' THEN 3
             WHEN 'required_credential_compatibility' THEN 4  -- paperwork last
             ELSE 5 END
         LIMIT 1)
    WHERE n_gaps IS NULL;

-- Ranked reads: same-status list ordered by gap count then score.
CREATE INDEX IF NOT EXISTS matches_applicant_gap_rank_idx
    ON public.matches (applicant_id, eligibility_status, n_gaps, policy_adjusted_score DESC);
CREATE INDEX IF NOT EXISTS matches_job_gap_rank_idx
    ON public.matches (job_id, eligibility_status, n_gaps, policy_adjusted_score DESC);
