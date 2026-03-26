-- =============================================================
-- Migration: conversations + direct_messages
-- Feature: DM system between applicants and employers
-- =============================================================

CREATE TABLE IF NOT EXISTS public.conversations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    applicant_id    UUID        NOT NULL REFERENCES public.applicants(id) ON DELETE CASCADE,
    employer_id     UUID        NOT NULL REFERENCES public.employers(id) ON DELETE CASCADE,
    job_id          UUID        REFERENCES public.jobs(id) ON DELETE SET NULL,
    match_id        UUID        REFERENCES public.matches(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    employer_unread INT         NOT NULL DEFAULT 0,
    applicant_unread INT        NOT NULL DEFAULT 0
);

-- One conversation per (applicant, employer, job) — NULLs handled with two partial indexes
CREATE UNIQUE INDEX IF NOT EXISTS conversations_with_job_idx
    ON public.conversations (applicant_id, employer_id, job_id)
    WHERE job_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS conversations_no_job_idx
    ON public.conversations (applicant_id, employer_id)
    WHERE job_id IS NULL;

CREATE INDEX IF NOT EXISTS conversations_applicant_idx ON public.conversations (applicant_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS conversations_employer_idx  ON public.conversations (employer_id, last_message_at DESC);

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;


CREATE TABLE IF NOT EXISTS public.direct_messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    sender_role     TEXT        NOT NULL CHECK (sender_role IN ('employer', 'applicant')),
    content         TEXT        NOT NULL CHECK (char_length(content) > 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS direct_messages_conv_idx ON public.direct_messages (conversation_id, created_at ASC);

ALTER TABLE public.direct_messages ENABLE ROW LEVEL SECURITY;
