-- Ranked-impression log: every time a ranked list is served, record what was
-- shown, at which position, with the exact scoring state used at serve time.
-- This is the feedback-loop foundation: joined with engagement_events
-- (interest_set / apply_click / hire_reported) it makes offline evaluation
-- and any future learned ranker possible. Without positions logged at serve
-- time, click data is unusable (position bias is unrecoverable after the fact).
CREATE TABLE IF NOT EXISTS public.match_impressions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    applicant_id    uuid NOT NULL REFERENCES public.applicants(id) ON DELETE CASCADE,
    job_id          uuid NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    match_id        uuid,
    context         text NOT NULL,           -- 'applicant_matches' | 'employer_candidates'
    position        integer NOT NULL,        -- 1-based rank as displayed
    tier            text,
    score           numeric(6,2),
    n_gaps          integer,
    evidence_pct    numeric(5,1),
    scoring_run_id  uuid,                    -- keys to the full dimension breakdown
    surfaced_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS match_impressions_applicant_idx
    ON public.match_impressions (applicant_id, surfaced_at DESC);
CREATE INDEX IF NOT EXISTS match_impressions_job_idx
    ON public.match_impressions (job_id, surfaced_at DESC);
ALTER TABLE public.match_impressions ENABLE ROW LEVEL SECURITY;
-- Service-role writes only; no client policies (analytics surface, not user data).
