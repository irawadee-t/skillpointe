-- Robustness pack: resume uploads, SMS, i18n, drive-time, training pathways.
--
-- Additive only — no data destroyed, no existing behavior changed.

-- =====================================================================
-- 1. Resume upload artifacts
-- =====================================================================
CREATE TABLE IF NOT EXISTS applicant_resume_uploads (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id  UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
  filename      TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  size_bytes    INTEGER NOT NULL,
  raw_text      TEXT,               -- extracted text (nullable if extraction failed)
  parsed_json   JSONB,              -- structured signals from LLM
  applied_at    TIMESTAMPTZ,        -- when applicant confirmed and merged into profile
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_resume_uploads_applicant
  ON applicant_resume_uploads(applicant_id, created_at DESC);


-- =====================================================================
-- 2. SMS notifications — mirror email stub pattern
-- =====================================================================
ALTER TABLE notifications
  ADD COLUMN IF NOT EXISTS sms_pending  BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS sms_sent_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS phone        TEXT;    -- captured at send time, so recipient can move

-- Per-user notification prefs (extends user_profiles rather than a new table).
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS sms_opt_in         BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS email_opt_in       BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS preferred_locale   TEXT NOT NULL DEFAULT 'en';   -- 'en' | 'es'


-- =====================================================================
-- 3. i18n — cache of translated job content
-- =====================================================================
CREATE TABLE IF NOT EXISTS translated_content (
  id           BIGSERIAL PRIMARY KEY,
  entity_type  TEXT NOT NULL,       -- 'job' | 'match_explanation' | ...
  entity_id    UUID NOT NULL,
  field        TEXT NOT NULL,       -- e.g. 'description', 'requirements', 'top_strengths'
  locale       TEXT NOT NULL,       -- 'es'
  text         TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id, field, locale)
);
CREATE INDEX IF NOT EXISTS idx_translated_lookup
  ON translated_content(entity_type, entity_id, locale);


-- =====================================================================
-- 4. Commute / drive-time cache
-- =====================================================================
CREATE TABLE IF NOT EXISTS commute_cache (
  id              BIGSERIAL PRIMARY KEY,
  origin_lat      DOUBLE PRECISION NOT NULL,
  origin_lng      DOUBLE PRECISION NOT NULL,
  dest_lat        DOUBLE PRECISION NOT NULL,
  dest_lng        DOUBLE PRECISION NOT NULL,
  drive_minutes   INTEGER NOT NULL,
  distance_meters INTEGER,
  provider        TEXT NOT NULL DEFAULT 'google',   -- 'google' | 'mapbox' | 'haversine'
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Coarse index — snap lat/lng to 3 decimals (~110m) so nearby-origin pairs share cache.
CREATE INDEX IF NOT EXISTS idx_commute_cache_lookup
  ON commute_cache (
    ROUND(origin_lat::numeric, 3),
    ROUND(origin_lng::numeric, 3),
    ROUND(dest_lat::numeric, 3),
    ROUND(dest_lng::numeric, 3)
  );

-- Attach drive-time to matches so downstream consumers can show it without
-- calling the API every render. Nullable — populated lazily.
ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS drive_minutes  INTEGER,
  ADD COLUMN IF NOT EXISTS drive_provider TEXT;


-- =====================================================================
-- 5. Training-pathway recommendations
-- =====================================================================
CREATE TABLE IF NOT EXISTS training_providers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  website_url   TEXT,
  city          TEXT,
  state         CHAR(2),
  country       TEXT DEFAULT 'US',
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS training_programs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id       UUID NOT NULL REFERENCES training_providers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  credential_key    TEXT NOT NULL,           -- e.g. 'osha_30', 'cdl_a', 'welding_aws_d1_1', 'nccer_electrical'
  duration_weeks    INTEGER,
  cost_range        TEXT,                    -- 'Free', '$500-$1,500', 'Financial aid available'
  format            TEXT,                    -- 'in_person' | 'online' | 'hybrid'
  city              TEXT,
  state             CHAR(2),
  url               TEXT,
  description       TEXT,
  active            BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_programs_by_credential
  ON training_programs(credential_key) WHERE active;
CREATE INDEX IF NOT EXISTS idx_programs_by_region
  ON training_programs(state) WHERE active;


-- Seed real partner-college programs near the current employer footprint (GA/AL/TN).
INSERT INTO training_providers (name, website_url, city, state, notes) VALUES
  ('Southern Union State Community College', 'https://www.suscc.edu',       'Opelika',       'AL', 'Serves East Alabama / West Georgia trades corridor'),
  ('Chattahoochee Technical College',        'https://www.chattahoocheetech.edu', 'Marietta','GA', 'Largest technical college in Georgia'),
  ('Wallace State Community College',        'https://www.wallacestate.edu', 'Hanceville',   'AL', 'Diesel, welding, HVAC programs'),
  ('West Georgia Technical College',         'https://www.westgatech.edu',   'Waco',         'GA', 'Serves Carrollton / Southwire region'),
  ('Athens Technical College',               'https://www.athenstech.edu',   'Athens',       'GA', 'HVAC, industrial systems, welding'),
  ('Motlow State Community College',         'https://www.mscc.edu',         'Tullahoma',    'TN', 'Mechatronics + industrial maintenance')
ON CONFLICT (name) DO NOTHING;

-- Programs — credential_key values must match SCORING_CONFIG credential taxonomy.
INSERT INTO training_programs (provider_id, name, credential_key, duration_weeks, cost_range, format, city, state, url, description)
SELECT p.id, prg.name, prg.credential_key, prg.duration_weeks, prg.cost_range, prg.format, prg.city, prg.state, prg.url, prg.description
FROM training_providers p
JOIN (VALUES
  ('West Georgia Technical College',         'Industrial Electrician',       'nccer_electrical', 40, 'Financial aid available', 'in_person', 'Waco', 'GA',      'https://www.westgatech.edu/programs/industrial-systems-technology/', 'Two-semester certificate covering NCCER Electrical Levels 1–2.'),
  ('West Georgia Technical College',         'AWS D1.1 Welding',             'welding_aws_d1_1', 32, '$1,200-$2,000',           'in_person', 'Waco', 'GA',      'https://www.westgatech.edu/programs/welding/', 'Prepares for AWS D1.1 structural steel qualification.'),
  ('Chattahoochee Technical College',        'OSHA 30 - General Industry',   'osha_30',           1, '$300-$500',               'hybrid',    'Marietta', 'GA',  'https://www.chattahoocheetech.edu', 'OSHA-authorized 30-hour general industry training.'),
  ('Chattahoochee Technical College',        'CDL Class A',                  'cdl_a',             8, '$4,000-$6,000',           'in_person', 'Marietta', 'GA',  'https://www.chattahoocheetech.edu/programs/cdl/', 'Full CDL Class A licensure with pre-trip inspection lab.'),
  ('Wallace State Community College',        'Diesel Technology',            'diesel_tech',      36, 'Financial aid available', 'in_person', 'Hanceville', 'AL','https://www.wallacestate.edu/programs/diesel', 'Diesel truck and heavy-equipment mechanics.'),
  ('Wallace State Community College',        'AWS D1.1 Welding',             'welding_aws_d1_1', 32, '$1,500-$2,500',           'in_person', 'Hanceville', 'AL','https://www.wallacestate.edu/programs/welding', 'Structural welding — MIG, TIG, stick.'),
  ('Wallace State Community College',        'HVAC Fundamentals + EPA 608',  'epa_608',          12, '$800-$1,500',             'in_person', 'Hanceville', 'AL','https://www.wallacestate.edu/programs/hvac',   'EPA 608 refrigerant handling certification.'),
  ('Athens Technical College',               'HVAC Fundamentals + EPA 608',  'epa_608',          14, '$900-$1,600',             'hybrid',    'Athens', 'GA',    'https://www.athenstech.edu', 'HVAC-R foundation + EPA 608 exam prep.'),
  ('Southern Union State Community College', 'Industrial Maintenance',       'industrial_maint', 40, 'Financial aid available', 'in_person', 'Opelika', 'AL',   'https://www.suscc.edu', 'Multi-craft maintenance program.'),
  ('Motlow State Community College',         'Mechatronics AAS',             'mechatronics',     72, 'Financial aid available', 'in_person', 'Tullahoma', 'TN', 'https://www.mscc.edu/mechatronics', 'Two-year mechatronics associate degree.')
) prg(provider_name, name, credential_key, duration_weeks, cost_range, format, city, state, url, description)
ON prg.provider_name = p.name
ON CONFLICT DO NOTHING;
