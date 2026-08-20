-- Close the write-time-enqueue gaps the "live and 100%" audit found:
-- 1. extracted_job_signals feeds scoring (job side) but had no trigger.
-- 2. employers rows feed the employer_soft_pref dimension; an employer
--    profile change must rescore that employer's jobs.

CREATE OR REPLACE FUNCTION public.enqueue_match_recompute_job_child()
RETURNS trigger AS $$
BEGIN
    IF current_setting('skilled.skip_match_enqueue', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    INSERT INTO public.match_queue (entity_type, entity_id)
    VALUES ('job', COALESCE(NEW.job_id, OLD.job_id))
    ON CONFLICT (entity_type, entity_id) WHERE processed_at IS NULL DO NOTHING;
    PERFORM pg_notify('match_queue', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS job_signals_match_enqueue ON public.extracted_job_signals;
CREATE TRIGGER job_signals_match_enqueue
    AFTER INSERT OR UPDATE ON public.extracted_job_signals
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_match_recompute_job_child();

CREATE OR REPLACE FUNCTION public.enqueue_match_recompute_employer()
RETURNS trigger AS $$
BEGIN
    IF current_setting('skilled.skip_match_enqueue', true) = 'on' THEN
        RETURN NEW;
    END IF;
    INSERT INTO public.match_queue (entity_type, entity_id)
    SELECT 'job', j.id FROM public.jobs j
     WHERE j.employer_id = NEW.id AND j.is_active
    ON CONFLICT (entity_type, entity_id) WHERE processed_at IS NULL DO NOTHING;
    PERFORM pg_notify('match_queue', '');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS employers_match_enqueue ON public.employers;
CREATE TRIGGER employers_match_enqueue
    AFTER UPDATE ON public.employers
    FOR EACH ROW
    WHEN ((to_jsonb(OLD) - 'updated_at') IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at'))
    EXECUTE FUNCTION public.enqueue_match_recompute_employer();
