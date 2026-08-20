-- The live-update guarantee, moved INTO the schema. Previously "every write
-- path must remember to trigger matching" was a code convention, patrolled
-- by a 6h delta sweep. These triggers make it a database invariant: any
-- INSERT/UPDATE that changes match-relevant content on either side of the
-- marketplace enqueues the entity for the resident match worker — no matter
-- which endpoint, script, or future code performed the write. The sweep is
-- thereby demoted from safety net to drift DETECTOR (it should find nothing;
-- finding work means a bug).
--
-- Volume safety: content-change detection via to_jsonb comparison (a
-- timestamp-only touch does not fire); the queue's pending-unique index
-- absorbs duplicates; bulk maintenance can opt out per-transaction with
--   SET LOCAL skilled.skip_match_enqueue = 'on';

CREATE OR REPLACE FUNCTION public.enqueue_match_recompute()
RETURNS trigger AS $$
DECLARE
    v_type text := TG_ARGV[0];
    v_id   uuid;
BEGIN
    IF current_setting('skilled.skip_match_enqueue', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    IF v_type = 'job' THEN
        v_id := COALESCE(NEW.id, OLD.id);
    ELSIF v_type = 'applicant' THEN
        v_id := COALESCE(NEW.id, OLD.id);
    ELSE
        -- child tables (credentials, extracted signals) carry the owner id
        -- in the column named by TG_ARGV[1]
        EXECUTE format('SELECT ($1).%I::uuid', TG_ARGV[1])
           INTO v_id USING COALESCE(NEW, OLD);
        v_type := 'applicant';
    END IF;
    IF v_id IS NULL THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    INSERT INTO public.match_queue (entity_type, entity_id)
    VALUES (v_type, v_id)
    ON CONFLICT (entity_type, entity_id) WHERE processed_at IS NULL DO NOTHING;
    PERFORM pg_notify('match_queue', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Jobs: any content change (timestamp-only touches excluded), plus
-- activation flips (deactivation makes the worker clear the job's matches).
DROP TRIGGER IF EXISTS jobs_match_enqueue ON public.jobs;
DROP TRIGGER IF EXISTS jobs_match_enqueue_ins ON public.jobs;
CREATE TRIGGER jobs_match_enqueue_ins
    AFTER INSERT ON public.jobs
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_match_recompute('job');
DROP TRIGGER IF EXISTS jobs_match_enqueue_upd ON public.jobs;
CREATE TRIGGER jobs_match_enqueue_upd
    AFTER UPDATE ON public.jobs
    FOR EACH ROW
    WHEN ((to_jsonb(OLD) - 'updated_at') IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at'))
    EXECUTE FUNCTION public.enqueue_match_recompute('job');

DROP TRIGGER IF EXISTS applicants_match_enqueue_ins ON public.applicants;
CREATE TRIGGER applicants_match_enqueue_ins
    AFTER INSERT ON public.applicants
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_match_recompute('applicant');
DROP TRIGGER IF EXISTS applicants_match_enqueue_upd ON public.applicants;
CREATE TRIGGER applicants_match_enqueue_upd
    AFTER UPDATE ON public.applicants
    FOR EACH ROW
    WHEN ((to_jsonb(OLD) - 'updated_at' - 'profile_last_updated_at')
          IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at' - 'profile_last_updated_at'))
    EXECUTE FUNCTION public.enqueue_match_recompute('applicant');

-- Credential changes flip the credential gate -> re-match the applicant.
DROP TRIGGER IF EXISTS credentials_match_enqueue ON public.credentials;
CREATE TRIGGER credentials_match_enqueue
    AFTER INSERT OR UPDATE OR DELETE ON public.credentials
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_match_recompute('child', 'applicant_id');

-- LLM extraction results feed scoring directly.
DROP TRIGGER IF EXISTS app_signals_match_enqueue ON public.extracted_applicant_signals;
CREATE TRIGGER app_signals_match_enqueue
    AFTER INSERT OR UPDATE ON public.extracted_applicant_signals
    FOR EACH ROW EXECUTE FUNCTION public.enqueue_match_recompute('child', 'applicant_id');
