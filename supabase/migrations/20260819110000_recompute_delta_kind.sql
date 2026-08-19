-- 'delta' recompute runs: the 6h full sweep is replaced by a sweep that
-- enqueues only entities changed since the last sweep. Scoring compute
-- becomes proportional to change volume, not catalog size.
ALTER TABLE public.recompute_runs DROP CONSTRAINT IF EXISTS recompute_runs_kind_check;
ALTER TABLE public.recompute_runs ADD CONSTRAINT recompute_runs_kind_check
    CHECK (kind IN ('full', 'job', 'applicant', 'delta'));
