-- Kill the last "asterisk": scoring-config and taxonomy changes alter match
-- results without touching job/applicant rows, so row triggers can't see
-- them. These table-level triggers enqueue EVERY active job when the rules
-- of the game change — the resident worker rescores the catalog in minutes,
-- live, instead of waiting for the weekly full pass.

CREATE OR REPLACE FUNCTION public.enqueue_all_jobs_recompute()
RETURNS trigger AS $$
BEGIN
    IF current_setting('skilled.skip_match_enqueue', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    INSERT INTO public.match_queue (entity_type, entity_id)
    SELECT 'job', id FROM public.jobs WHERE is_active
    ON CONFLICT (entity_type, entity_id) WHERE processed_at IS NULL DO NOTHING;
    PERFORM pg_notify('match_queue', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS policy_configs_match_enqueue ON public.policy_configs;
CREATE TRIGGER policy_configs_match_enqueue
    AFTER INSERT OR UPDATE ON public.policy_configs
    FOR EACH ROW
    WHEN (pg_trigger_depth() = 0)
    EXECUTE FUNCTION public.enqueue_all_jobs_recompute();

DROP TRIGGER IF EXISTS taxonomy_match_enqueue ON public.canonical_job_families;
CREATE TRIGGER taxonomy_match_enqueue
    AFTER INSERT OR UPDATE ON public.canonical_job_families
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_all_jobs_recompute();

-- Refinement: only rescore the catalog when the config CONTENT or active
-- flag changes — an updated_at touch or description edit is not a rules
-- change.
DROP TRIGGER IF EXISTS policy_configs_match_enqueue ON public.policy_configs;
CREATE TRIGGER policy_configs_match_enqueue_ins
    AFTER INSERT ON public.policy_configs
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_all_jobs_recompute();
CREATE TRIGGER policy_configs_match_enqueue_upd
    AFTER UPDATE ON public.policy_configs
    FOR EACH ROW
    WHEN (OLD.config IS DISTINCT FROM NEW.config
          OR OLD.is_active IS DISTINCT FROM NEW.is_active)
    EXECUTE FUNCTION public.enqueue_all_jobs_recompute();
