-- =============================================================
-- Migration: ops tables — import_runs, import_rows, audit_logs,
--            policy_configs, review_queue_items
-- Phase 3 — Core Data Model
--
-- These tables are primarily service-role (admin / backend) owned.
-- No direct client-side RLS policies; FastAPI enforces access via RBAC.
-- Audit log is append-only by design (no UPDATE policy for non-service-role).
-- Policy config rows are versioned and only one may be active at a time.
-- =============================================================


-- ---------------------------------------------------------------
-- import_runs
-- Tracks each bulk import batch (applicants, jobs, employers).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.import_runs (
  id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  import_type     TEXT    NOT NULL,   -- 'applicants', 'jobs', 'employers'
  source_file     TEXT,               -- original uploaded filename
  row_count       INTEGER,
  success_count   INTEGER NOT NULL DEFAULT 0,
  error_count     INTEGER NOT NULL DEFAULT 0,
  warning_count   INTEGER NOT NULL DEFAULT 0,
  status          public.import_status_enum NOT NULL DEFAULT 'pending',
  error_summary   JSONB,              -- high-level error summary
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  initiated_by    UUID        REFERENCES auth.users (id),

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_import_runs_updated_at
  BEFORE UPDATE ON public.import_runs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Service-role only; no direct client access
ALTER TABLE public.import_runs ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS import_runs_import_type_idx
  ON public.import_runs (import_type);

CREATE INDEX IF NOT EXISTS import_runs_status_idx
  ON public.import_runs (status);


-- ---------------------------------------------------------------
-- import_rows
-- One row per row in an import batch.  Raw data preserved.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.import_rows (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  import_run_id UUID    NOT NULL REFERENCES public.import_runs (id) ON DELETE CASCADE,
  row_number    INTEGER,
  raw_data      JSONB   NOT NULL,   -- original row as key-value map
  status        TEXT    NOT NULL DEFAULT 'pending',
    -- 'pending', 'success', 'error', 'warning', 'skipped'
  error_message   TEXT,
  warning_message TEXT,
  entity_id       UUID,             -- ID of created/updated entity if successful
  entity_type     TEXT,             -- 'applicant', 'job', 'employer'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.import_rows ENABLE ROW LEVEL SECURITY;
-- Service-role only

CREATE INDEX IF NOT EXISTS import_rows_import_run_id_idx
  ON public.import_rows (import_run_id);

CREATE INDEX IF NOT EXISTS import_rows_status_idx
  ON public.import_rows (status);


-- ---------------------------------------------------------------
-- audit_logs
-- Append-only audit trail.  All significant admin and system
-- actions must write a row here.  No UPDATE or DELETE policy.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id    UUID    REFERENCES auth.users (id),  -- null = system/background job
  actor_role  TEXT,   -- 'admin', 'applicant', 'employer', 'system'
  action      TEXT    NOT NULL,
    -- e.g. 'create_job', 'override_match', 'update_policy_config',
    --      'resolve_review_item', 'import_applicants', 'recompute_matches'
  entity_type TEXT,   -- 'applicant', 'job', 'match', 'policy_config', ...
  entity_id   UUID,
  before_state JSONB, -- snapshot before change (null for creates)
  after_state  JSONB, -- snapshot after change (null for deletes)
  metadata     JSONB, -- any extra context (e.g. policy version, run ID)
  ip_address   TEXT,  -- optional, from request context

  -- Immutable timestamp — no updated_at, no trigger
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
-- Service-role only; admins read via FastAPI (not direct Supabase client)

CREATE INDEX IF NOT EXISTS audit_logs_actor_id_idx
  ON public.audit_logs (actor_id)
  WHERE actor_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS audit_logs_entity_type_entity_id_idx
  ON public.audit_logs (entity_type, entity_id)
  WHERE entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS audit_logs_action_idx
  ON public.audit_logs (action);

CREATE INDEX IF NOT EXISTS audit_logs_created_at_idx
  ON public.audit_logs (created_at DESC);


-- ---------------------------------------------------------------
-- policy_configs
-- Versioned scoring/policy config.  Exactly one row should have
-- is_active = TRUE at any time.  Managed by admin via FastAPI.
-- All changes must be written to audit_logs.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.policy_configs (
  id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  version     TEXT    NOT NULL UNIQUE,  -- e.g. 'v1', 'v1.1', 'v2'
  is_active   BOOLEAN NOT NULL DEFAULT FALSE,
  config      JSONB   NOT NULL,
    -- Full config blob mirroring SCORING_CONFIG.yaml structure.
    -- Matching engine reads from this table at runtime.
  description TEXT,
  created_by    UUID    REFERENCES auth.users (id),
  activated_by  UUID    REFERENCES auth.users (id),
  activated_at  TIMESTAMPTZ,
  deactivated_at TIMESTAMPTZ,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_policy_configs_updated_at
  BEFORE UPDATE ON public.policy_configs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.policy_configs ENABLE ROW LEVEL SECURITY;
-- Service-role only

-- Only one active config at a time (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS policy_configs_one_active_idx
  ON public.policy_configs (is_active)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS policy_configs_version_idx
  ON public.policy_configs (version);


-- ---------------------------------------------------------------
-- review_queue_items
-- Items flagged for admin human-in-the-loop review.
-- Created automatically by extraction pipeline or scoring engine
-- when confidence is low or signals conflict.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.review_queue_items (
  id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  item_type   public.review_queue_item_type_enum NOT NULL,

  -- What is being reviewed
  entity_type TEXT    NOT NULL,
    -- 'extracted_applicant_signals', 'extracted_job_signals', 'match', 'import_row'
  entity_id   UUID    NOT NULL,

  -- Context
  description     TEXT,       -- human-readable description of the issue
  flags           JSONB,      -- [{flag_type, detail}]
  confidence_level public.confidence_level_enum,
  priority        INTEGER NOT NULL DEFAULT 5,
    -- 1 = urgent/blocking, 10 = low-priority cosmetic

  -- Resolution
  status          public.review_status_enum NOT NULL DEFAULT 'pending',
  resolved_by     UUID    REFERENCES auth.users (id),
  resolved_at     TIMESTAMPTZ,
  resolution_action TEXT,    -- 'approved', 'overridden', 'dismissed'
  resolution_notes  TEXT,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_review_queue_items_updated_at
  BEFORE UPDATE ON public.review_queue_items
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.review_queue_items ENABLE ROW LEVEL SECURITY;
-- Service-role only; admin reads via FastAPI

CREATE INDEX IF NOT EXISTS review_queue_items_status_idx
  ON public.review_queue_items (status);

CREATE INDEX IF NOT EXISTS review_queue_items_item_type_idx
  ON public.review_queue_items (item_type);

CREATE INDEX IF NOT EXISTS review_queue_items_entity_type_entity_id_idx
  ON public.review_queue_items (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS review_queue_items_priority_idx
  ON public.review_queue_items (priority, created_at ASC)
  WHERE status = 'pending';
