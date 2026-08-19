-- Work queue for the resident match worker. Replaces per-event recompute
-- subprocesses (each paid ~25s of data loading; concurrent triggers could
-- stampede — observed: 77 parallel processes exhausting connection slots).
-- The partial unique index IS the debounce: re-enqueueing a pending target
-- is a no-op, no Redis required. NOTIFY 'match_queue' wakes the worker.
CREATE TABLE IF NOT EXISTS public.match_queue (
    id           bigserial PRIMARY KEY,
    entity_type  text NOT NULL CHECK (entity_type IN ('job', 'applicant')),
    entity_id    uuid NOT NULL,
    enqueued_at  timestamptz NOT NULL DEFAULT now(),
    claimed_at   timestamptz,
    processed_at timestamptz,
    error        text
);
CREATE UNIQUE INDEX IF NOT EXISTS match_queue_pending_uidx
    ON public.match_queue (entity_type, entity_id)
    WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS match_queue_drain_idx
    ON public.match_queue (enqueued_at) WHERE processed_at IS NULL;
