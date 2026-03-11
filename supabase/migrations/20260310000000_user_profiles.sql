-- =============================================================
-- Migration: user_profiles
-- Phase 2 — Auth + RBAC
--
-- This table is the authoritative source for app-level roles.
-- Supabase Auth handles identity; this table handles authorization.
--
-- Roles: admin | applicant | employer
-- Supabase Auth's built-in `role` column is NOT our app role.
-- =============================================================

CREATE TABLE IF NOT EXISTS public.user_profiles (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role                TEXT        NOT NULL CHECK (role IN ('admin', 'applicant', 'employer')),
  onboarding_complete BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT user_profiles_user_id_unique UNIQUE (user_id)
);

-- ---------------------------------------------------------------
-- auto-update updated_at
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER set_user_profiles_updated_at
  BEFORE UPDATE ON public.user_profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();

-- ---------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile row
CREATE POLICY "users_read_own_profile"
  ON public.user_profiles
  FOR SELECT
  USING (auth.uid() = user_id);

-- Users can update limited fields on their own profile.
-- Role changes must go through the service-role API (FastAPI).
-- This policy prevents self-escalation.
CREATE POLICY "users_update_own_onboarding"
  ON public.user_profiles
  FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (
    -- role must not change via client-side update
    role = (SELECT role FROM public.user_profiles WHERE user_id = auth.uid())
  );

-- INSERT and all admin-level access handled via service_role key in FastAPI.
-- Service role bypasses RLS automatically in Supabase.

-- ---------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS user_profiles_user_id_idx ON public.user_profiles (user_id);

-- ---------------------------------------------------------------
-- First admin — run this manually after migration to seed the first admin.
-- Replace the UUID with the user_id from auth.users after creating the account.
--
-- Example (run in Supabase Studio SQL editor after creating the auth user):
--
--   INSERT INTO public.user_profiles (user_id, role)
--   VALUES ('<paste-auth-user-uuid-here>', 'admin')
--   ON CONFLICT (user_id) DO UPDATE SET role = 'admin';
--
-- Or use: python scripts/seed_admin.py --email admin@example.com --password <secret>
-- ---------------------------------------------------------------
