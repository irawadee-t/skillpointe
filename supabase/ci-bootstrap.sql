-- CI bootstrap: recreate the minimal Supabase-provided environment that the
-- migrations assume, so they can be applied on a plain Postgres in CI.
--
-- Locally, `supabase start` provisions the `auth` schema, `auth.uid()`,
-- pgvector in the `extensions` schema, etc. CI uses a bare Postgres image
-- (with pgvector — use the pgvector/pgvector:pg17 image), so we stand those
-- prerequisites up here BEFORE running supabase/migrations/*.sql.

-- Roles the migrations GRANT to (Supabase provides these).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION IF NOT EXISTS pgcrypto;               -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;  -- pgvector (embeddings)

-- Minimal auth.users so FK references (user_profiles, audit_logs, …) resolve.
CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text,
  phone text,
  raw_user_meta_data jsonb,
  created_at timestamptz DEFAULT now()
);

-- RLS helper referenced by policies. In CI there is no request context, so it
-- returns NULL — enough for the policies to be CREATEable.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
  LANGUAGE sql STABLE
AS $$ SELECT NULL::uuid $$;

CREATE OR REPLACE FUNCTION auth.role() RETURNS text
  LANGUAGE sql STABLE
AS $$ SELECT NULL::text $$;

-- Supabase Storage. Only `storage.buckets` is touched by the migrations
-- (20260721000004 registers the private `documents` bucket for credential
-- uploads), so that is all we stand up. Columns mirror the ones Supabase
-- defines that our migration writes to, plus the primary key it conflicts on.
CREATE SCHEMA IF NOT EXISTS storage;

CREATE TABLE IF NOT EXISTS storage.buckets (
  id         text PRIMARY KEY,
  name       text NOT NULL,
  public     boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Realtime publication. Supabase ships an empty `supabase_realtime`
-- publication and migrations enrol tables into it (20260803090000 adds
-- notifications + direct_messages). Recreated here with the same shape
-- Supabase uses (all DML events, not FOR ALL TABLES).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    CREATE PUBLICATION supabase_realtime;
  END IF;
END $$;
