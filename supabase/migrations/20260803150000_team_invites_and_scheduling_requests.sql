-- ---------------------------------------------------------------
-- Migration: employer team roles, email invites, delegated scheduling
--
-- 1. employer_contacts.role — org-level role (owner / admin / member).
--    Existing contacts backfill to 'owner' (they created/ran the account);
--    new rows default to 'member' and invites carry an explicit role.
-- 2. employer_invites — email invites to join an employer workspace.
--    The invite token is NEVER stored: only its SHA-256 hex digest
--    (token_hash). Tokens expire after 7 days and are single-use;
--    resending rotates the token (new hash, new expiry).
-- 3. scheduling_requests — "let them pick the times": the proposing
--    employer delegates slot-picking to a teammate. One pending request
--    per application (partial unique index). Fulfilled automatically
--    when the assignee proposes times; cancellable by the originator.
-- 4. New notification kinds for the flows above.
-- ---------------------------------------------------------------

-- 1. Org role on employer_contacts (additive)
ALTER TABLE public.employer_contacts
  ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'employer_contacts_role_check'
      AND conrelid = 'public.employer_contacts'::regclass
  ) THEN
    ALTER TABLE public.employer_contacts
      ADD CONSTRAINT employer_contacts_role_check
      CHECK (role IN ('owner', 'admin', 'member'));
  END IF;
END $$;

-- Backfill: everyone who existed before team invites was the account holder.
UPDATE public.employer_contacts SET role = 'owner' WHERE role = 'member';

-- 2. employer_invites
CREATE TABLE IF NOT EXISTS public.employer_invites (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id      UUID        NOT NULL
                               REFERENCES public.employers (id) ON DELETE CASCADE,
  email            TEXT        NOT NULL,
  role             TEXT        NOT NULL DEFAULT 'member'
                               CHECK (role IN ('owner', 'admin', 'member')),
  title            TEXT,

  -- SHA-256 hex digest of the URL token. The raw token exists only in the
  -- invite email. Rotated on resend.
  token_hash       TEXT        NOT NULL UNIQUE,

  invited_by       UUID        REFERENCES auth.users (id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at       TIMESTAMPTZ NOT NULL,

  accepted_at      TIMESTAMPTZ,
  accepted_user_id UUID        REFERENCES auth.users (id) ON DELETE SET NULL,
  revoked_at       TIMESTAMPTZ,
  revoked_by       UUID
);

-- One live (not yet accepted, not revoked) invite per email per employer.
CREATE UNIQUE INDEX IF NOT EXISTS employer_invites_active_email_uq
  ON public.employer_invites (employer_id, lower(email))
  WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS employer_invites_employer_id_idx
  ON public.employer_invites (employer_id);

-- Service-role/backend access only — no anon/authenticated policies.
ALTER TABLE public.employer_invites ENABLE ROW LEVEL SECURITY;

-- 3. scheduling_requests
CREATE TABLE IF NOT EXISTS public.scheduling_requests (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id      UUID        NOT NULL
                                  REFERENCES public.applications (id) ON DELETE CASCADE,
  employer_id         UUID        NOT NULL
                                  REFERENCES public.employers (id) ON DELETE CASCADE,
  requested_by        UUID        NOT NULL
                                  REFERENCES auth.users (id) ON DELETE CASCADE,
  assignee_contact_id UUID        NOT NULL
                                  REFERENCES public.employer_contacts (id) ON DELETE CASCADE,
  note                TEXT,
  status              TEXT        NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending', 'fulfilled', 'cancelled')),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  fulfilled_at        TIMESTAMPTZ,
  fulfilled_by        UUID,
  cancelled_at        TIMESTAMPTZ,
  cancelled_reason    TEXT
);

-- One pending request per application — a second "let them pick" must
-- replace/cancel the first, never stack.
CREATE UNIQUE INDEX IF NOT EXISTS scheduling_requests_one_pending_uq
  ON public.scheduling_requests (application_id)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS scheduling_requests_assignee_idx
  ON public.scheduling_requests (assignee_contact_id, status);

CREATE INDEX IF NOT EXISTS scheduling_requests_employer_idx
  ON public.scheduling_requests (employer_id);

ALTER TABLE public.scheduling_requests ENABLE ROW LEVEL SECURITY;

-- 4. Notification kinds
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'team_invite_accepted';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'scheduling_requested';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'scheduling_fulfilled';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'scheduling_cancelled';
