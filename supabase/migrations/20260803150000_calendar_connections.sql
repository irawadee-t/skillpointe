-- =====================================================================
-- Calendar connections (OAuth read tier)  — additive only
--
-- 1. calendar_connections — one row per (user, provider, account) OAuth
--    calendar connection used to overlay the user's OWN busy times on the
--    interview slot picker. Tokens are stored app-layer encrypted
--    (app/util/crypto.py Fernet envelope — same discipline as screening
--    answers); the plaintext never touches the database.
--      provider: 'google' (freeBusy, scope calendar.freebusy),
--                'microsoft' (Graph getSchedule, scope Calendars.Read),
--                'demo' (local-only deterministic fake — the row exists so
--                the whole storage/fetch/overlay pipeline is exercised, but
--                the flag that allows creating it is refused in production).
--
-- 2. calendar_oauth_states — short-lived, single-use rows carrying the
--    OAuth state nonce + PKCE code_verifier between /calendar/connect/{p}
--    and /calendar/callback/{p}. Rows expire after 10 minutes and are
--    deleted on first use; a periodic opportunistic sweep happens on insert.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.calendar_connections (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                   UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  provider                  TEXT NOT NULL CHECK (provider IN ('google', 'microsoft', 'demo')),
  account_email             TEXT NOT NULL DEFAULT '',
  -- App-layer encrypted (Fernet, "v1:" prefixed) — see app/util/crypto.py.
  access_token_ciphertext   TEXT,
  refresh_token_ciphertext  TEXT,
  access_token_expires_at   TIMESTAMPTZ,
  connected_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at              TIMESTAMPTZ,
  UNIQUE (user_id, provider, account_email)
);

CREATE INDEX IF NOT EXISTS calendar_connections_user_idx
  ON public.calendar_connections (user_id);

COMMENT ON TABLE public.calendar_connections IS
  'OAuth calendar connections (read/free-busy tier). Tokens are app-layer encrypted; service-role access only.';

CREATE TABLE IF NOT EXISTS public.calendar_oauth_states (
  state          TEXT PRIMARY KEY,
  user_id        UUID NOT NULL,
  provider       TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
  code_verifier  TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backend talks to Postgres directly (service role); nothing here is meant
-- for the anon PostgREST surface.
ALTER TABLE public.calendar_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calendar_oauth_states ENABLE ROW LEVEL SECURITY;
