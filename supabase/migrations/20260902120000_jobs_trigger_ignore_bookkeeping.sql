-- The jobs UPDATE enqueue-trigger compared every column except updated_at,
-- so a routine re-pull or link check that only bumps bookkeeping fields
-- (last_verified_at, apply_link_checked_at, ...) enqueued a full recompute
-- for EVERY job it touched. Overnight 2026-09-02 that flooded match_queue
-- with thousands of no-op job recomputes and saturated the database.
--
-- Matching reads none of these columns; changes to them cannot change a
-- match. Note apply_link_status is bookkeeping here too: when a dead link
-- retires a job, is_active flips, and is_active IS still compared.

DROP TRIGGER IF EXISTS jobs_match_enqueue_upd ON public.jobs;
CREATE TRIGGER jobs_match_enqueue_upd
    AFTER UPDATE ON public.jobs
    FOR EACH ROW
    WHEN ((to_jsonb(OLD) - 'updated_at' - 'last_verified_at'
                         - 'apply_link_status' - 'apply_link_checked_at'
                         - 'search_tsv' - 'status_changed_at' - 'posted_date')
          IS DISTINCT FROM
          (to_jsonb(NEW) - 'updated_at' - 'last_verified_at'
                         - 'apply_link_status' - 'apply_link_checked_at'
                         - 'search_tsv' - 'status_changed_at' - 'posted_date'))
    EXECUTE FUNCTION public.enqueue_match_recompute('job');
