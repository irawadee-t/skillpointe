-- =============================================================
-- Migration: taxonomy industries + scholarship-import support
--
-- 1. canonical_job_families.industries — first-class industry grouping
--    (healthcare / construction / transportation / energy / manufacturing).
--    A family belongs to ONE canonical slug; titles that appear in two
--    industries (Machinist, Pipefitter/Steamfitter, Field Service Technician)
--    keep a single family whose industries[] lists both.
-- 2. applicants.scholarship_review_status — the 'Folder - Name' column of
--    SPF scholarship exports holds a REVIEW STATUS ('Internal Review',
--    'Accepted Award - Pending Payment', 'Selected - Pending Acceptance'),
--    never a person's name.  Dedicated queryable field.
-- 3. 15 new canonical job families covering the definitive SPF job-type
--    list (Healthcare, Construction, Transportation, Energy, Manufacturing).
-- 4. Alias extensions + industries[] for existing families.
--    Aliases are MERGED (array union), never overwritten, so demo-data /
--    admin-added aliases survive.
-- 5. canonical_career_pathways umbrella rows for the CSV 'Career Path'
--    values (Building, Transportation, Healthcare, Industrial, Energy,
--    Manufacturing, Emerging Technologies, Other Skilled Trade Career
--    Pathway) so every CSV value has a taxonomy landing spot.
--
-- Safe to re-run (IF NOT EXISTS / ON CONFLICT upserts).
-- =============================================================

-- -------------------------------------------------------
-- 1. Industry grouping on job families
-- -------------------------------------------------------
ALTER TABLE public.canonical_job_families
  ADD COLUMN IF NOT EXISTS industries TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN public.canonical_job_families.industries IS
  'Industry grouping(s): healthcare, construction, transportation, energy, manufacturing. Multi-valued for cross-industry trades (machinist, pipefitter, field service).';

-- -------------------------------------------------------
-- 2. Scholarship review status on applicants
-- -------------------------------------------------------
ALTER TABLE public.applicants
  ADD COLUMN IF NOT EXISTS scholarship_review_status TEXT;

COMMENT ON COLUMN public.applicants.scholarship_review_status IS
  'Review status from SPF scholarship export (''Folder - Name'' column): Internal Review / Accepted Award - Pending Payment / Selected - Pending Acceptance.';

-- -------------------------------------------------------
-- 3 + 4. Job family upserts (aliases merged, never clobbered)
-- -------------------------------------------------------
INSERT INTO public.canonical_job_families (code, name, description, aliases, industries) VALUES
  -- ---- NEW: Healthcare ----
  ('pharmacy', 'Pharmacy', 'Pharmacy technician and pharmacy support roles',
   ARRAY['pharmacy technician','pharmacy tech','pharm tech','pharmacy assistant'],
   ARRAY['healthcare']),
  ('surgical_tech', 'Surgical Technology', 'Surgical technologist and operating room support',
   ARRAY['surgical technologist','surgical tech','surg tech','operating room technician','scrub tech'],
   ARRAY['healthcare']),
  ('veterinary', 'Veterinary Support', 'Veterinary technician and assistant roles',
   ARRAY['veterinary tech','veterinary technician','vet tech','veterinary assistant','veterinary technologist'],
   ARRAY['healthcare']),
  ('lab_sciences', 'Laboratory Sciences', 'Medical and clinical laboratory technician roles',
   ARRAY['laboratory technician','lab technician','lab tech','medical laboratory technician','mlt','laboratory assistant'],
   ARRAY['healthcare']),
  ('health_information', 'Health Information', 'Medical records and health information technology',
   ARRAY['medical records','health information technician','health information technology','medical records technician','medical coder','medical billing'],
   ARRAY['healthcare']),
  ('dietetics', 'Dietetics & Nutrition', 'Registered dietitian and nutrition support roles',
   ARRAY['registered dietitian','dietitian','dietetic technician','nutritionist'],
   ARRAY['healthcare']),
  -- ---- NEW: Construction ----
  ('civil_survey', 'Civil & Survey Technology', 'Civil engineering, surveying, and mapping technicians',
   ARRAY['civil engineering technician','surveying and mapping tech','surveying technician','survey technician','mapping technician','land surveying'],
   ARRAY['construction']),
  -- ---- NEW: Construction + Energy (multi-industry) ----
  ('field_service', 'Field Service', 'Field service technicians across construction and energy (multi-industry)',
   ARRAY['field service technician','field service tech','field technician'],
   ARRAY['construction','energy']),
  -- ---- NEW: Transportation ----
  ('rail_transit', 'Rail & Transit Technology', 'Locomotive, rail, bridge, and structure technicians',
   ARRAY['locomotive diesel technician','locomotive technician','bridge rail structure technician','rail technician','railcar technician','track technician','signal maintainer','railroad'],
   ARRAY['transportation']),
  ('marine', 'Marine Technology', 'Marine engine and vessel service technicians',
   ARRAY['marine technician','marine mechanic','boat technician','outboard technician','marine service technician'],
   ARRAY['transportation']),
  -- ---- NEW: Energy ----
  ('power_plant', 'Power Generation', 'Power plant, nuclear, and turbine operations',
   ARRAY['power plant operator','nuclear technician','turbine technician','power plant technician','reactor operator','nuclear power technician','generation technician'],
   ARRAY['energy']),
  ('building_automation', 'Building Automation & Energy Management', 'Building automation, controls, and energy management technicians',
   ARRAY['building automation technician','building automation','bas technician','building energy management','energy management technician','building controls technician'],
   ARRAY['energy']),
  ('data_center', 'Data Center Operations', 'Data center and critical facilities specialists',
   ARRAY['data center specialist','data center technician','data center operations','critical facilities technician'],
   ARRAY['energy']),
  -- ---- NEW: Manufacturing ----
  ('industrial_maintenance', 'Industrial Maintenance', 'Industrial machinery mechanics and maintenance',
   ARRAY['industrial machinery mechanic','industrial maintenance','millwright','industrial machinery technician','maintenance mechanic','machinery maintenance'],
   ARRAY['manufacturing']),
  ('electronics', 'Electronics & Electro-Mechanical', 'Electrical/electronics engineering and electro-mechanical technicians',
   ARRAY['electrical and electronics engineering technician','electronics engineering technician','electronics technician','electro mechanical technician','electro-mechanical technician','electromechanical technician'],
   ARRAY['manufacturing']),
  -- ---- EXTEND: existing families (aliases merged below, industries set) ----
  ('electrical', 'Electrical', 'Electrical installation, maintenance, and repair',
   ARRAY['electrical engineering'],
   ARRAY['construction']),
  ('plumbing', 'Plumbing', 'Plumbing installation and pipefitting (construction + manufacturing)',
   ARRAY['pipefitter/steamfitter','pipe fitter'],
   ARRAY['construction','manufacturing']),
  ('hvac', 'HVAC/R', 'Heating, ventilation, air conditioning, and refrigeration',
   ARRAY['hvac technician'],
   ARRAY['construction']),
  ('construction', 'General Construction', 'Carpentry, framing, masonry, and general construction trades',
   ARRAY['carpentry','building construction','construction technology'],
   ARRAY['construction']),
  ('welding', 'Welding & Metal Fabrication', 'Welding, cutting, metal fabrication, and shipbuilding (construction + manufacturing)',
   ARRAY['shipbuilder','shipfitter','shipbuilding'],
   ARRAY['construction','manufacturing']),
  ('automotive', 'Automotive & Diesel', 'Automotive service and heavy diesel equipment',
   ARRAY['automotive technician','diesel technician'],
   ARRAY['transportation']),
  ('manufacturing', 'Manufacturing & Production', 'CNC, machining, assembly, and production operations (machinist also serves transportation)',
   ARRAY['advanced manufacturing technician','industrial engineering technician'],
   ARRAY['manufacturing','transportation']),
  ('logistics', 'Logistics & Supply Chain', 'Warehousing, distribution, and commercial driving',
   ARRAY['commercial truck driver','truck driver','cdl driver','commercial driver'],
   ARRAY['transportation']),
  ('heavy_equipment', 'Heavy Equipment', 'Heavy equipment operation and maintenance',
   ARRAY['heavy equipment mechanic','construction equipment operator'],
   ARRAY['construction']),
  ('security', 'Security & Protective Services', 'Security officer, alarm installation, and protective services',
   ARRAY['security alarm technician','security alarm tech','alarm installer','alarm technician','fire alarm technician'],
   ARRAY['construction']),
  ('drafting', 'Architectural Drafting', 'Architectural and technical drafting',
   ARRAY['architectural drafter'],
   ARRAY['construction']),
  ('aviation', 'Aviation Maintenance', 'Aircraft maintenance and repair',
   ARRAY['aviation maintenance technician'],
   ARRAY['transportation']),
  ('auto_body', 'Auto Body / Collision', 'Automotive body repair and painting',
   ARRAY['auto body technician'],
   ARRAY['transportation']),
  ('energy_lineman', 'Electrical Lineman', 'Power line installation and maintenance',
   ARRAY['electrical lineman'],
   ARRAY['energy']),
  ('solar_energy', 'Solar Energy', 'Solar panel installation and photovoltaic systems',
   ARRAY['solar energy technician'],
   ARRAY['energy']),
  ('wind_energy', 'Wind Turbine', 'Wind turbine installation and maintenance',
   ARRAY['wind turbine technician'],
   ARRAY['energy']),
  ('robotics', 'Robotics & Automation', 'Robotics, mechatronics, and automation technology',
   ARRAY['automation technology'],
   ARRAY['manufacturing']),
  ('construction_mgmt', 'Construction Management', 'Construction project management and supervision',
   ARRAY['construction management'],
   ARRAY['construction']),
  ('healthcare_support', 'Healthcare Support', 'Medical assistant, phlebotomy, patient care, and allied health support',
   ARRAY['certified nursing assistant'],
   ARRAY['healthcare']),
  ('dental', 'Dental', 'Dental assisting and hygiene',
   ARRAY['dental hygienist','dental assistant'],
   ARRAY['healthcare']),
  ('nursing', 'Nursing / LPN', 'Licensed practical and vocational nursing',
   ARRAY['nurse lpn','nurse lvn'],
   ARRAY['healthcare']),
  ('radiology', 'Radiology & Medical Imaging', 'Radiology, MRI, sonography, and cardiovascular imaging',
   ARRAY['mri technician','mri tech','cardiovascular technician','cardiovascular technologist','ekg technician','medical sonographer'],
   ARRAY['healthcare']),
  ('respiratory', 'Respiratory Therapy', 'Respiratory therapy and support',
   ARRAY['respiratory therapist'],
   ARRAY['healthcare']),
  ('physical_therapy', 'Physical/Occupational Therapy Support', 'PT and OT assistant roles',
   ARRAY['occupational therapy assistant','physical therapy assistant'],
   ARRAY['healthcare'])
ON CONFLICT (code) DO UPDATE SET
  name        = EXCLUDED.name,
  description = EXCLUDED.description,
  -- MERGE aliases: keep existing + add new (deduplicated)
  aliases     = (
    SELECT COALESCE(array_agg(DISTINCT a), '{}')
    FROM unnest(public.canonical_job_families.aliases || EXCLUDED.aliases) AS a
  ),
  industries  = EXCLUDED.industries;

-- -------------------------------------------------------
-- 5. Career-path umbrella rows (CSV 'Career Path' values)
--    job_family_id stays NULL — these are industry umbrellas, not
--    single-family programmes.  Aliases hold the exact CSV literals.
-- -------------------------------------------------------
INSERT INTO public.canonical_career_pathways (code, name, description, job_family_id, aliases) VALUES
  ('path_building',           'Building',
   'CSV Career Path umbrella; maps to the construction industry', NULL, ARRAY['building']),
  ('path_transportation',     'Transportation',
   'CSV Career Path umbrella; maps to the transportation industry', NULL, ARRAY['transportation']),
  ('path_healthcare',         'Healthcare',
   'CSV Career Path umbrella; maps to the healthcare industry', NULL, ARRAY['healthcare']),
  ('path_industrial',         'Industrial',
   'CSV Career Path umbrella; maps to the manufacturing industry (closest grouping — there is no dedicated industrial industry)', NULL, ARRAY['industrial']),
  ('path_energy',             'Energy',
   'CSV Career Path umbrella; maps to the energy industry', NULL, ARRAY['energy']),
  ('path_manufacturing',      'Manufacturing',
   'CSV Career Path umbrella; maps to the manufacturing industry', NULL, ARRAY['manufacturing']),
  ('path_emerging_tech',      'Emerging Technologies',
   'CSV Career Path umbrella; no industry equivalent — family resolved from program field per row', NULL, ARRAY['emerging technologies']),
  ('path_other_skilled_trade', 'Other Skilled Trade Career Pathway',
   'CSV Career Path umbrella; catch-all — family resolved from program field per row', NULL, ARRAY['other skilled trade career pathway'])
ON CONFLICT (code) DO UPDATE SET
  name        = EXCLUDED.name,
  description = EXCLUDED.description,
  aliases     = EXCLUDED.aliases;
