-- SKILLED Nation <-> Pro event sync (transactional outbox + idempotent inbox).
--
-- Pattern: domain mutations write an event row to event_outbox in the SAME
-- transaction as the state change (no dual-write / lost-event race). A relay
-- publishes unpublished rows to a Redis Stream; a consumer group on the peer
-- (SKILLED Nation) applies them idempotently into sync_inbox. event_id carries
-- end-to-end idempotency; `source` carries the origin tag to prevent echo loops.

CREATE TABLE IF NOT EXISTS public.event_outbox (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id       text NOT NULL UNIQUE,
    aggregate_type text NOT NULL,
    aggregate_id   uuid,
    event_type     text NOT NULL,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    source         text NOT NULL DEFAULT 'skilled_pro',
    occurred_at    timestamptz NOT NULL DEFAULT now(),
    published_at   timestamptz
);

-- Relay scans for unpublished rows in occurrence order.
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON public.event_outbox (occurred_at)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS public.sync_inbox (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id       text NOT NULL UNIQUE,          -- idempotency key
    aggregate_type text NOT NULL,
    aggregate_id   uuid,
    event_type     text NOT NULL,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    source         text NOT NULL,
    received_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inbox_aggregate
    ON public.sync_inbox (aggregate_type, aggregate_id);
