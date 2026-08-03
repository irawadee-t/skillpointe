-- Job lifecycle statuses + career-source freshness robustness. All additive.
--
-- 1. jobs.status — employer-facing lifecycle: active | paused | filled | closed.
--    Backfilled from is_active (TRUE -> active, FALSE -> closed). A trigger
--    keeps status and is_active mutually consistent BOTH ways so every
--    existing consumer of is_active (browse, matching recompute, career-source
--    sync writers) keeps working unchanged:
--      * writer sets status        -> is_active := (status = 'active')
--      * writer flips is_active    -> status follows (TRUE -> active;
--        FALSE -> closed, unless already filled/closed which are preserved)
--    jobs.previous_status powers the real-undo revert endpoint (same pattern
--    as applications.previous_status).
--
-- 2. career_source_jobs.consecutive_misses — flap protection: a posting must
--    be absent from TWO consecutive listing syncs before it is marked
--    vanished/stale, so one scrape hiccup can't unpublish live jobs.
--
-- 3. employer_career_sources adaptive cadence state: when the last N syncs
--    found zero changes the effective interval backs off (x2, capped at 24h);
--    any observed change snaps back to the employer-set base interval.

-- 1. Job lifecycle ----------------------------------------------------------

ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'filled', 'closed')),
    ADD COLUMN IF NOT EXISTS previous_status text
        CHECK (previous_status IS NULL OR previous_status IN ('active', 'paused', 'filled', 'closed')),
    ADD COLUMN IF NOT EXISTS status_changed_at timestamptz;

UPDATE public.jobs SET status = 'closed' WHERE is_active = FALSE AND status = 'active';

CREATE OR REPLACE FUNCTION public.jobs_sync_status_is_active()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- Derive whichever side the writer didn't set.
        IF NEW.status IS DISTINCT FROM 'active' THEN
            NEW.is_active := FALSE;
        ELSIF NEW.is_active = FALSE THEN
            NEW.status := 'closed';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        -- Lifecycle write wins: is_active follows the status.
        NEW.is_active := (NEW.status = 'active');
        NEW.status_changed_at := now();
    ELSIF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
        -- Legacy writer (career-source sync, admin tooling) flipped is_active:
        -- status follows. Terminal employer decisions (filled/closed) are
        -- preserved on deactivate; reactivation always reads as active.
        IF NEW.is_active THEN
            NEW.status := 'active';
        ELSIF OLD.status IN ('filled', 'closed') THEN
            NEW.status := OLD.status;
        ELSE
            NEW.status := 'closed';
        END IF;
        NEW.status_changed_at := now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_sync_status_is_active ON public.jobs;
CREATE TRIGGER jobs_sync_status_is_active
    BEFORE INSERT OR UPDATE ON public.jobs
    FOR EACH ROW EXECUTE FUNCTION public.jobs_sync_status_is_active();

CREATE INDEX IF NOT EXISTS jobs_status_idx ON public.jobs (status) WHERE status <> 'active';

-- 2. Flap protection --------------------------------------------------------

ALTER TABLE public.career_source_jobs
    ADD COLUMN IF NOT EXISTS consecutive_misses integer NOT NULL DEFAULT 0;

-- 3. Adaptive cadence -------------------------------------------------------

ALTER TABLE public.employer_career_sources
    ADD COLUMN IF NOT EXISTS no_change_streak integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS adaptive_interval_hours integer;

COMMENT ON COLUMN public.employer_career_sources.adaptive_interval_hours IS
    'Effective auto-sync interval after churn-based backoff. NULL = use the '
    'employer-set base (auto_sync_interval_hours). Never below the base, '
    'capped at max(24h, base).';
