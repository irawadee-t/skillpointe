-- Geocode cache — feeds the commute / drive-time feature.
-- Free-form "city, state" (and zip) → lat/lng, memoized once.
CREATE TABLE IF NOT EXISTS geocode_cache (
  id           BIGSERIAL PRIMARY KEY,
  query        TEXT NOT NULL,        -- normalized lowercase "carrollton, ga" or "30117"
  lat          DOUBLE PRECISION NOT NULL,
  lng          DOUBLE PRECISION NOT NULL,
  display_name TEXT,
  provider     TEXT NOT NULL DEFAULT 'nominatim',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (query)
);
CREATE INDEX IF NOT EXISTS idx_geocode_query ON geocode_cache(query);
