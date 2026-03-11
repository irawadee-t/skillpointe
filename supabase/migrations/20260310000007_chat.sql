-- =============================================================
-- Migration: chat_sessions, chat_messages
-- Phase 3 — Core Data Model
--
-- Applicant planning chat (Phase 8).
-- Tables are created now so the schema is complete; they will
-- remain empty until Phase 8 adds the chat backend.
--
-- Design principles:
--   - context_snapshot captures the applicant's match state at
--     session creation time so the chat is grounded in data
--   - raw LLM responses are stored for audit (context_used,
--     raw_llm_response on assistant messages)
--   - no autonomous actions; chat is read-only w.r.t. matches
-- =============================================================


-- ---------------------------------------------------------------
-- chat_sessions
-- One per planning conversation started by an applicant.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id  UUID    NOT NULL REFERENCES public.applicants (id) ON DELETE CASCADE,

  title         TEXT,   -- optional session title (auto-generated or user-set)

  -- Context snapshot at session start (for explainability + audit)
  context_snapshot JSONB,
    -- {top_matches: [...], top_gaps: [...], geography: {...}, ...}
    -- Captured when session opens; does not change during the session.

  is_active   BOOLEAN NOT NULL DEFAULT TRUE,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_chat_sessions_updated_at
  BEFORE UPDATE ON public.chat_sessions
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

-- Applicants can manage their own chat sessions
CREATE POLICY "applicants_manage_own_chat_sessions"
  ON public.chat_sessions
  USING (
    EXISTS (
      SELECT 1 FROM public.applicants a
      WHERE a.id = applicant_id AND a.user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS chat_sessions_applicant_id_idx
  ON public.chat_sessions (applicant_id);

CREATE INDEX IF NOT EXISTS chat_sessions_created_at_idx
  ON public.chat_sessions (applicant_id, created_at DESC);


-- ---------------------------------------------------------------
-- chat_messages
-- Individual turns within a chat session.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chat_messages (
  id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  UUID    NOT NULL REFERENCES public.chat_sessions (id) ON DELETE CASCADE,

  role        public.chat_role_enum NOT NULL,
    -- 'user', 'assistant', 'system'
  content     TEXT    NOT NULL,

  -- LLM metadata (assistant messages only; null for user/system)
  llm_model       TEXT,
  prompt_version  TEXT,
  context_used    JSONB,    -- which context items grounded this response
  raw_llm_response JSONB,   -- full LLM API response for audit

  -- Immutable timestamp (messages are never edited)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Applicants can read their own chat messages
CREATE POLICY "applicants_read_own_chat_messages"
  ON public.chat_messages FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.chat_sessions cs
      JOIN public.applicants a ON a.id = cs.applicant_id
      WHERE cs.id = session_id AND a.user_id = auth.uid()
    )
  );

-- Service-role handles all writes (backend sends and stores messages)

CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx
  ON public.chat_messages (session_id);

CREATE INDEX IF NOT EXISTS chat_messages_session_role_idx
  ON public.chat_messages (session_id, role);

CREATE INDEX IF NOT EXISTS chat_messages_created_at_idx
  ON public.chat_messages (session_id, created_at ASC);
