-- Applicant work-radius matching: pre-resolved coordinates.
--
-- Jobs on the platform are posted against a city; the applicant sets a
-- commute radius (applicants.commute_radius_miles, added in core_entities).
-- A job is in range iff the geodesic distance between the applicant's home
-- coords and the job's city coords is <= the radius. The matching engine
-- (packages/matching — pure, no DB/network) consumes these pre-resolved
-- coords from its input structs; they are populated at profile-save / job
-- import time via geocode_cache (Nominatim, memoized) and backfilled by
-- scripts/recompute_matches.py.
--
-- Additive only.

ALTER TABLE public.applicants
  ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;

COMMENT ON COLUMN public.applicants.lat IS
  'Home latitude, resolved from city/state/zip via geocode_cache at profile save or recompute backfill.';
COMMENT ON COLUMN public.applicants.lng IS
  'Home longitude — see applicants.lat.';
COMMENT ON COLUMN public.jobs.lat IS
  'Job-city latitude, resolved from city/state via geocode_cache at import or recompute backfill.';
COMMENT ON COLUMN public.jobs.lng IS
  'Job-city longitude — see jobs.lat.';
