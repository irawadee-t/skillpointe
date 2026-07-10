-- Recompute recovery table + GDPR deletion column.
-- Idempotent: uses IF NOT EXISTS everywhere.

-- ---------------------------------------------------------------------------
-- recompute_runs: telemetry + recovery state for match-recompute jobs.
-- On API startup any in_progress row older than 15 min is marked failed with
-- error = 'server restart'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recompute_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          TEXT NOT NULL CHECK (kind IN ('full', 'job', 'applicant')),
    target_id     UUID,
    status        TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'in_progress', 'complete', 'failed')),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recompute_runs_status_idx
    ON public.recompute_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS recompute_runs_kind_target_idx
    ON public.recompute_runs (kind, target_id);


-- ---------------------------------------------------------------------------
-- GDPR/CCPA deletion: pending_deletion_at on user_profiles.
-- Cleared on cancel; hard-deletion sweep runs weekly.
-- ---------------------------------------------------------------------------
ALTER TABLE public.user_profiles
    ADD COLUMN IF NOT EXISTS pending_deletion_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS user_profiles_pending_deletion_idx
    ON public.user_profiles (pending_deletion_at)
    WHERE pending_deletion_at IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Screening answers encryption marker.
-- We encrypt at the application layer (see app.util.crypto). The column
-- ciphertext_v records the key/version the row was encrypted with so key
-- rotation stays possible without a schema change.
-- ---------------------------------------------------------------------------
ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS screening_answers_ciphertext_v SMALLINT DEFAULT 0;

COMMENT ON COLUMN public.applications.screening_answers_ciphertext_v IS
    '0 = plaintext (legacy). 1+ = Fernet ciphertext, version selects the key. '
    'Application layer chooses the key by version; see app.util.crypto.';
