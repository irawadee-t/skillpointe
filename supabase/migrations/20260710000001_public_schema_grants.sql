-- Ensure Supabase API roles have privileges on the public schema.
--
-- Why this exists: on some Supabase CLI versions the default privileges that
-- normally grant SELECT/INSERT/UPDATE/DELETE to anon / authenticated /
-- service_role are not applied to tables created by migrations, leaving the
-- FastAPI backend (which talks to PostgREST as service_role) with
-- "permission denied for table ..." (SQLSTATE 42501). Row-level security still
-- governs which rows each role can see; these are table-level grants only.
--
-- Idempotent: safe to run on every `supabase db reset`.

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES    IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL ROUTINES  IN SCHEMA public TO anon, authenticated, service_role;

-- Apply to objects created later in the reset (e.g. by seed.sql).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES  TO anon, authenticated, service_role;
