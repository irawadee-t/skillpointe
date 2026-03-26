-- =============================================================
-- Migration: engagement_events
-- Feature: Track applicant and employer engagement actions
-- =============================================================

CREATE TABLE IF NOT EXISTS public.engagement_events (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Who performed the action (all optional — some events are system-generated)
  applicant_id  UUID    REFERENCES public.applicants (id) ON DELETE SET NULL,
  employer_id   UUID    REFERENCES public.employers (id) ON DELETE SET NULL,

  -- What was acted on
  job_id        UUID    REFERENCES public.jobs (id) ON DELETE SET NULL,
  match_id      UUID    REFERENCES public.matches (id) ON DELETE SET NULL,

  -- Event type taxonomy
  event_type    TEXT    NOT NULL,
    -- applicant: 'interest_set', 'apply_click', 'match_view', 'chat_started'
    -- employer:  'outreach_sent', 'candidate_viewed', 'hire_reported'

  -- Flexible payload for event-specific data
  event_data    JSONB,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.engagement_events ENABLE ROW LEVEL SECURITY;
-- All writes via service role (no RLS rules needed for reads in MVP)

CREATE INDEX IF NOT EXISTS engagement_events_applicant_idx
  ON public.engagement_events (applicant_id);

CREATE INDEX IF NOT EXISTS engagement_events_employer_idx
  ON public.engagement_events (employer_id);

CREATE INDEX IF NOT EXISTS engagement_events_type_idx
  ON public.engagement_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS engagement_events_created_at_idx
  ON public.engagement_events (created_at DESC);
