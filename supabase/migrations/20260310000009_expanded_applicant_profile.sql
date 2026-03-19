-- =============================================================
-- Expanded applicant profile fields
-- Sources: SkillPointe Foundation Skilled Trades Scholarship data
--
-- Adds:
--   - Education details (enrollment, school, degree, program taxonomy)
--   - Richer travel/relocation preferences (enum + state list)
--   - Demographics (age range, gender, military)
--   - Financial context (wages, household income, remaining costs)
--   - Internship and essay text for extraction
--   - Activities/extracurriculars, honor societies, GPA
--   - Program start date
-- =============================================================

-- -------------------------------------------------------
-- Enums for new categorical fields
-- -------------------------------------------------------
DO $$ BEGIN
  CREATE TYPE enrollment_status AS ENUM (
    'high_school',
    'dual_enrollment',
    'community_college',
    'vocational_certificate',
    'apprenticeship',
    'bachelors_plus',
    'not_enrolled',
    'other'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE degree_type AS ENUM (
    'associates',
    'bachelors',
    'skilled_trades_certificate',
    'apprenticeship',
    'dual_enrollment',
    'other'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE travel_willingness AS ENUM (
    'no_travel',
    'within_metro',
    'within_state',
    'within_region',
    'anywhere'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE relocation_willingness AS ENUM (
    'stay_current',
    'within_state',
    'specific_states',
    'anywhere'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- -------------------------------------------------------
-- Add columns to applicants table
-- -------------------------------------------------------
ALTER TABLE public.applicants
  -- Education
  ADD COLUMN IF NOT EXISTS enrollment_status    enrollment_status,
  ADD COLUMN IF NOT EXISTS degree_type          degree_type,
  ADD COLUMN IF NOT EXISTS school_name          text,
  ADD COLUMN IF NOT EXISTS school_campus        text,
  ADD COLUMN IF NOT EXISTS school_city          text,
  ADD COLUMN IF NOT EXISTS school_state         text,
  ADD COLUMN IF NOT EXISTS career_path          text,
  ADD COLUMN IF NOT EXISTS program_field        text,
  ADD COLUMN IF NOT EXISTS specific_career      text,
  ADD COLUMN IF NOT EXISTS program_start_date   date,
  ADD COLUMN IF NOT EXISTS gpa                  numeric(4,2),

  -- Richer travel/relocation (replaces booleans)
  ADD COLUMN IF NOT EXISTS travel_preference    travel_willingness DEFAULT 'within_state',
  ADD COLUMN IF NOT EXISTS relocation_preference relocation_willingness DEFAULT 'stay_current',
  ADD COLUMN IF NOT EXISTS relocation_states    text[] DEFAULT '{}',

  -- Demographics
  ADD COLUMN IF NOT EXISTS age_range            text,
  ADD COLUMN IF NOT EXISTS gender               text,
  ADD COLUMN IF NOT EXISTS military_status      boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS military_dependent   boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS household_income     text,
  ADD COLUMN IF NOT EXISTS current_wages        text,

  -- Internship
  ADD COLUMN IF NOT EXISTS has_internship       boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS internship_details   text,

  -- Essays and text for extraction
  ADD COLUMN IF NOT EXISTS essay_background     text,
  ADD COLUMN IF NOT EXISTS essay_impact         text,

  -- Activities / Honor societies
  ADD COLUMN IF NOT EXISTS activities           text,
  ADD COLUMN IF NOT EXISTS honor_societies      text[],

  -- Financial
  ADD COLUMN IF NOT EXISTS remaining_program_costs text;

-- -------------------------------------------------------
-- Expand canonical_job_families with CSV-derived programs
-- These cover SPF's actual taxonomy from the scholarship data
-- -------------------------------------------------------
INSERT INTO public.canonical_job_families (code, name, description, aliases) VALUES
  ('energy_lineman', 'Electrical Lineman', 'Power line installation and maintenance',
   ARRAY['lineman','lineworker','electrical lineman','power line','line technician']),
  ('solar_energy', 'Solar Energy', 'Solar panel installation and photovoltaic systems',
   ARRAY['solar','solar tech','solar installer','photovoltaic','solar energy technician']),
  ('wind_energy', 'Wind Turbine', 'Wind turbine installation and maintenance',
   ARRAY['wind turbine','wind tech','wind energy','wind turbine technician']),
  ('dental', 'Dental', 'Dental assisting and hygiene',
   ARRAY['dental assistant','dental hygienist','dental tech']),
  ('nursing', 'Nursing / LPN', 'Licensed practical and vocational nursing',
   ARRAY['lpn','lvn','nurse','nursing','licensed practical nurse']),
  ('radiology', 'Radiology', 'Radiology and medical imaging',
   ARRAY['radiology tech','radiology','x-ray tech','medical sonographer','ultrasound tech']),
  ('respiratory', 'Respiratory Therapy', 'Respiratory therapy and support',
   ARRAY['respiratory therapist','respiratory','breathing therapy']),
  ('physical_therapy', 'Physical/Occupational Therapy Support', 'PT and OT assistant roles',
   ARRAY['physical therapy assistant','occupational therapy assistant','pta','ota','pt assistant']),
  ('aviation', 'Aviation Maintenance', 'Aircraft maintenance and repair',
   ARRAY['aircraft','aircraft technician','aircraft mechanic','airframe','a&p','powerplant']),
  ('auto_body', 'Auto Body / Collision', 'Automotive body repair and painting',
   ARRAY['auto body','collision repair','body shop','auto body technician']),
  ('robotics', 'Robotics & Automation', 'Robotics, mechatronics, and automation technology',
   ARRAY['robotics','mechatronics','automation','automation technology','robot tech']),
  ('construction_mgmt', 'Construction Management', 'Construction project management and supervision',
   ARRAY['construction management','project management construction','building management']),
  ('drafting', 'Architectural Drafting', 'Architectural and technical drafting',
   ARRAY['architectural drafter','drafting','cad drafter','architectural drafting','cad technician']),
  ('heavy_equipment', 'Heavy Equipment', 'Heavy equipment operation and maintenance',
   ARRAY['heavy equipment','equipment operator','heavy equipment technician','bulldozer','excavator','crane'])
ON CONFLICT (code) DO UPDATE SET
  name        = EXCLUDED.name,
  description = EXCLUDED.description,
  aliases     = EXCLUDED.aliases;
