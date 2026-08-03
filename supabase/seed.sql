-- =============================================================
-- SkillPointe Match — Baseline Seed Data
-- Phase 3 — Step 3.2: Seed baseline taxonomy/config
--
-- Run automatically by `supabase db reset`.
-- Safe to re-run (ON CONFLICT DO NOTHING / DO UPDATE).
--
-- Contents:
--   1. geography_regions         — US regional groupings
--   2. canonical_job_families    — trades/skilled-labour taxonomy
--   3. canonical_career_pathways — programme → job family mappings
--   4. policy_configs v1         — default scoring config from SCORING_CONFIG.yaml
-- =============================================================


-- ============================================================
-- 1. Geography Regions
-- ============================================================
INSERT INTO public.geography_regions (code, name, states, description) VALUES
  ('northeast',   'Northeast',     ARRAY['CT','ME','MA','NH','RI','VT','NY','NJ','PA'],
   'New England + Mid-Atlantic states'),
  ('southeast',   'Southeast',     ARRAY['DE','FL','GA','MD','NC','SC','VA','WV','AL','KY','MS','TN','AR','LA'],
   'South Atlantic + East South Central + lower Mid-Atlantic'),
  ('midwest',     'Midwest',       ARRAY['IL','IN','MI','OH','WI','IA','KS','MN','MO','NE','ND','SD'],
   'East and West North Central'),
  ('southwest',   'Southwest',     ARRAY['AZ','NM','OK','TX'],
   'West South Central + Mountain Southwest'),
  ('west',        'West',          ARRAY['CO','ID','MT','NV','UT','WY','AK','CA','HI','OR','WA'],
   'Mountain + Pacific'),
  ('mid_atlantic', 'Mid-Atlantic',  ARRAY['DC','DE','MD','NJ','NY','PA','VA'],
   'DC metro region and surrounding states')
ON CONFLICT (code) DO UPDATE SET
  name        = EXCLUDED.name,
  states      = EXCLUDED.states,
  description = EXCLUDED.description;


-- ============================================================
-- 2. Canonical Job Families
-- SkillPointe serves skilled-trade and workforce-development
-- placements.  Seed with the most common trades + adjacent
-- roles.  Admins can add more via the admin console.
-- ============================================================
INSERT INTO public.canonical_job_families (code, name, description, aliases) VALUES
  -- Core skilled trades
  ('electrical',       'Electrical',       'Electrical installation, maintenance, and repair',
   ARRAY['electrician','electrical tech','electrical technician','wireman','lineman']),
  ('plumbing',         'Plumbing',         'Plumbing installation and pipefitting',
   ARRAY['plumber','pipefitter','steamfitter','gasfitter']),
  ('hvac',             'HVAC/R',           'Heating, ventilation, air conditioning, and refrigeration',
   ARRAY['hvac','hvacr','heating and cooling','refrigeration tech','chiller tech']),
  ('construction',     'General Construction', 'Carpentry, framing, masonry, and general construction trades',
   ARRAY['carpenter','framer','mason','bricklayer','construction worker','laborer']),
  ('welding',          'Welding & Metal Fabrication', 'Welding, cutting, and metal fabrication',
   ARRAY['welder','fitter','metal fabricator','boilermaker','pipeweld']),
  ('automotive',       'Automotive & Diesel', 'Automotive service and heavy diesel equipment',
   ARRAY['auto tech','automotive technician','mechanic','diesel tech','diesel mechanic','auto mechanic']),
  ('manufacturing',    'Manufacturing & Production', 'CNC, machining, assembly, and production operations',
   ARRAY['machinist','cnc operator','cnc tech','machine operator','production operator','assembler']),
  ('logistics',        'Logistics & Supply Chain', 'Warehousing, distribution, and transportation operations',
   ARRAY['warehouse','forklift operator','logistics coordinator','supply chain','distribution']),
  ('healthcare_support','Healthcare Support', 'Medical assistant, phlebotomy, patient care, and allied health support',
   ARRAY['cna','medical assistant','ma','phlebotomist','patient care tech','pct','home health aide']),
  ('it_support',       'IT & Technology Support', 'Help desk, network support, and technology operations',
   ARRAY['help desk','it support','computer tech','network technician','it technician']),
  ('culinary',         'Culinary & Food Service', 'Professional cooking, baking, and food service',
   ARRAY['cook','chef','baker','food service worker','line cook']),
  ('childcare_education','Childcare & Education', 'Childcare, early education, and paraprofessional education roles',
   ARRAY['childcare worker','daycare','paraprofessional','teacher aide','early childhood']),
  ('cosmetology',      'Cosmetology & Aesthetics', 'Hair, skin, and nail services',
   ARRAY['cosmetologist','barber','esthetician','nail tech','stylist']),
  ('security',         'Security & Protective Services', 'Security officer, loss prevention, and emergency dispatch',
   ARRAY['security officer','security guard','loss prevention','dispatcher','armed security']),
  ('administrative',   'Administrative & Office Support', 'Office administration, customer service, and clerical roles',
   ARRAY['admin','administrative assistant','office assistant','receptionist','data entry','customer service'])
ON CONFLICT (code) DO UPDATE SET
  name        = EXCLUDED.name,
  description = EXCLUDED.description,
  aliases     = EXCLUDED.aliases;


-- ============================================================
-- 3. Canonical Career Pathways
-- Seed a representative set linked to the job families above.
-- ============================================================
INSERT INTO public.canonical_career_pathways
  (code, name, description, job_family_id, typical_duration_months, aliases)
SELECT
  cp.code, cp.name, cp.description,
  jf.id AS job_family_id,
  cp.typical_duration_months,
  cp.aliases
FROM (VALUES
  -- Electrical
  ('electrical_apprenticeship', 'Electrical Apprenticeship',
   '4–5 year IBEW or non-union electrical apprenticeship', 'electrical', 48,
   ARRAY['ibew apprenticeship','jatc electrical','electrical apprentice']),
  ('electrical_pre_apprenticeship', 'Electrical Pre-Apprenticeship',
   'Entry-level pre-apprenticeship programme preparing for full apprenticeship', 'electrical', 6,
   ARRAY['pre-apprenticeship electrical','electrical prep']),
  -- Plumbing
  ('plumbing_apprenticeship', 'Plumbing Apprenticeship',
   '4–5 year UA or non-union plumbing apprenticeship', 'plumbing', 48,
   ARRAY['ua apprenticeship','plumbing apprentice']),
  -- HVAC
  ('hvac_certificate', 'HVAC/R Certificate Program',
   'Vocational certificate in HVAC installation and service', 'hvac', 12,
   ARRAY['hvac cert','hvacr certificate','hvac program']),
  ('hvac_apprenticeship', 'HVAC Apprenticeship',
   'Apprenticeship in heating, ventilation, and air conditioning', 'hvac', 36,
   ARRAY['hvac apprentice']),
  -- Construction
  ('carpentry_apprenticeship', 'Carpentry Apprenticeship',
   'UBC or non-union carpentry apprenticeship', 'construction', 48,
   ARRAY['carpenter apprenticeship','uca apprenticeship']),
  ('construction_pre_apprenticeship', 'Construction Pre-Apprenticeship',
   'Pre-apprenticeship preparing for trades entry', 'construction', 6,
   ARRAY['pre-apprenticeship construction','trades prep']),
  -- Welding
  ('welding_certificate', 'Welding Certificate Program',
   'Vocational certificate covering SMAW, GMAW, FCAW, and TIG', 'welding', 12,
   ARRAY['welding cert','welding program','weld school']),
  -- Automotive
  ('automotive_certificate', 'Automotive Service Technology Certificate',
   'ASE-aligned automotive service programme', 'automotive', 12,
   ARRAY['auto tech program','automotive cert','ase prep']),
  -- Manufacturing
  ('manufacturing_certificate', 'Manufacturing/CNC Certificate',
   'Certificate in CNC operation, machining, and manufacturing basics', 'manufacturing', 9,
   ARRAY['cnc certificate','machining program','manufacturing cert']),
  -- Healthcare Support
  ('cna_program', 'Certified Nursing Assistant (CNA) Program',
   'State-approved CNA training and certification', 'healthcare_support', 3,
   ARRAY['cna training','cna course','nursing assistant program']),
  ('medical_assistant_program', 'Medical Assistant Program',
   'Diploma or certificate in clinical and administrative medical assisting', 'healthcare_support', 12,
   ARRAY['ma program','medical assistant cert','clinical assistant']),
  -- IT Support
  ('it_support_certificate', 'IT Support / CompTIA A+ Certificate',
   'Certificate programme aligned with CompTIA A+ and help-desk skills', 'it_support', 9,
   ARRAY['comptia a+','it certificate','helpdesk training']),
  -- Culinary
  ('culinary_certificate', 'Culinary Arts Certificate',
   'Vocational culinary certificate covering kitchen operations and food safety', 'culinary', 12,
   ARRAY['culinary program','cooking school','culinary arts cert']),
  -- Cosmetology
  ('cosmetology_license', 'Cosmetology License Program',
   'State-required cosmetology hours and licensing programme', 'cosmetology', 12,
   ARRAY['cosmetology school','barber school','esthetics program'])
) AS cp (code, name, description, job_family_code, typical_duration_months, aliases)
JOIN public.canonical_job_families jf ON jf.code = cp.job_family_code
ON CONFLICT (code) DO UPDATE SET
  name                    = EXCLUDED.name,
  description             = EXCLUDED.description,
  job_family_id           = EXCLUDED.job_family_id,
  typical_duration_months = EXCLUDED.typical_duration_months,
  aliases                 = EXCLUDED.aliases;


-- ============================================================
-- 4. Default Policy Config — v1
-- Mirrors SCORING_CONFIG.yaml exactly.
-- The matching engine reads the active row at runtime.
-- Only one row may have is_active = TRUE (enforced by partial
-- unique index in migration 6).
-- ============================================================
INSERT INTO public.policy_configs (version, is_active, description, config) VALUES (
  'v1',
  TRUE,
  'Default scoring and policy config — SkillPointe Match MVP (from SCORING_CONFIG.yaml v1)',
  '{
    "version": "v1",
    "mvp_scope": {
      "batch_matching_enabled": false,
      "deferred_acceptance_enabled": false,
      "centralized_clearing_enabled": false,
      "autonomous_agents_enabled": false
    },
    "base_fit": {
      "formula": "hard_gate_cap * (weighted_structured_score * 0.75 + semantic_score * 0.25)",
      "bounds": {"min": 0, "max": 100}
    },
    "eligibility": {
      "eligible":   {"hard_gate_cap": 1.0},
      "near_fit":   {"hard_gate_cap": 0.75},
      "ineligible": {"hard_gate_cap": 0.35}
    },
    "structured_score": {
      "total_weight": 100,
      "weights": {
        "trade_program_alignment":       25,
        "geography_alignment":           20,
        "credential_readiness":          15,
        "timing_readiness":              10,
        "experience_internship_alignment": 10,
        "industry_alignment":             5,
        "compensation_alignment":         5,
        "work_style_signal_alignment":    5,
        "employer_soft_pref_alignment":   5
      }
    },
    "semantic_score": {
      "enabled": true,
      "formula": "0.4*skills_overlap + 0.3*job_family_similarity + 0.2*experience_text_relevance + 0.1*intent_alignment"
    },
    "policy_reranking": {
      "enabled": true,
      "formula": "policy_adjusted_score = clamp(base_fit_score + sum(policy_modifiers), 0, 100)",
      "policies": {
        "partner_employer_preference": {
          "enabled": true,
          "modifiers": {"partner_employer": 5, "non_partner": 0},
          "constraints": {"max_override_gap": 12}
        },
        "funded_training_pathway_alignment": {
          "enabled": true,
          "modifiers": {"direct_alignment": 6, "adjacent_alignment": 3, "unrelated": 0}
        },
        "geography_preference": {
          "enabled": true,
          "modifiers": {
            "local_feasible": 6,
            "same_state_or_regional": 4,
            "relocation_required_and_willing": 1,
            "travel_heavy_and_willing": 1,
            "uncertain": 0,
            "infeasible": 0
          }
        },
        "readiness_preference": {
          "enabled": true,
          "modifiers": {
            "ready_now_or_timing_aligned": 5,
            "near_completion": 3,
            "significant_wait": 0
          }
        },
        "opportunity_upside": {
          "enabled": true,
          "modifiers": {"meaningful_upside_and_near_fit_or_better": 2, "otherwise": 0}
        },
        "missing_critical_requirement_penalty": {
          "enabled": true,
          "modifiers": {
            "missing_mandatory_credential": -12,
            "missing_important_nonmandatory_skill_cluster": -6,
            "missing_minor_requirements_only": -2
          }
        }
      }
    },
    "null_handling": {
      "defaults": {
        "compensation_alignment_unknown": 70,
        "employer_soft_pref_alignment_unknown": 50,
        "work_style_signal_alignment_unknown": 50,
        "geography_partially_known": 50,
        "geography_fully_unknown": 35,
        "credentials_unknown_nonrequired": 50,
        "experience_unknown": 50
      },
      "required_credential_behavior": {
        "if_job_requires_credential_and_applicant_data_missing": {
          "eligibility_status": "near_fit",
          "auto_fail": false,
          "requires_review_if_low_confidence": true
        }
      }
    },
    "confidence": {
      "extraction_levels": ["high", "medium", "low"],
      "admin_review_thresholds": {
        "review_low_extraction_confidence": true,
        "review_low_match_confidence": true,
        "review_conflicting_signals": true,
        "review_credential_ambiguity": true,
        "review_taxonomy_mismatch": true,
        "review_geography_ambiguity": true
      }
    },
    "feature_flags": {
      "applicant_self_signup": true,
      "employer_invite_only_default": true,
      "employer_global_candidate_search_default": false,
      "direct_messaging_default": false,
      "applicant_chat_enabled": true,
      "admin_policy_editor_enabled": true,
      "admin_override_enabled": true
    }
  }'::jsonb
)
ON CONFLICT (version) DO UPDATE SET
  config      = EXCLUDED.config,
  description = EXCLUDED.description,
  is_active   = EXCLUDED.is_active;


-- ============================================================
-- 5. Taxonomy expansion (2026-08): industries + SPF definitive job list
--    Mirrors migration 20260801062752_taxonomy_industries_and_scholarship_import.sql
--    so a fresh `supabase db reset` ends in the same state (this section runs
--    AFTER the base upserts above and re-merges the extended aliases).
--    Aliases are merged (array union), never overwritten.
-- ============================================================
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

-- ---------------------------------------------------------------
-- Canonical credential taxonomy (mirror of the in-code registry in
-- apps/api/app/skilled_pro/taxonomy.py; generated by
-- scripts/gen_credential_definitions_sql.py — regenerate on change).
-- ---------------------------------------------------------------
INSERT INTO public.credential_definitions
  (canonical_code, canonical_name, credential_type, authority, aliases,
   job_families, validity_note, verification_url)
VALUES
  ('osha_10', 'OSHA 10-Hour Safety Card', 'safety', 'OSHA-authorized trainer', ARRAY['osha 10','osha10','osha 10 hour','10 hour osha','osha 10 card','10 hour card','osha 10 construction','osha 10 general industry'], ARRAY['construction','electrical','welding','hvac','manufacturing','logistics'], 'No federal expiration; many employers and some state laws want completion within the last 5 years', NULL),
  ('osha_30', 'OSHA 30-Hour Safety Card', 'safety', 'OSHA-authorized trainer', ARRAY['osha 30','osha30','osha 30 hour','30 hour osha','osha 30 card','osha 30 construction','osha 30 general industry'], ARRAY['construction','electrical','welding','hvac','manufacturing','construction_mgmt'], 'No federal expiration; many employers and some state laws want completion within the last 5 years', NULL),
  ('hazwoper_40', 'OSHA HAZWOPER 40-Hour', 'safety', 'OSHA-authorized trainer', ARRAY['hazwoper','hazwoper 40','40 hour hazwoper','hazwoper certification'], ARRAY['construction','manufacturing','industrial_maintenance'], '8-hour refresher required annually', NULL),
  ('nfpa_70e', 'NFPA 70E Arc Flash / Electrical Safety Training', 'safety', 'NFPA-aligned trainer', ARRAY['nfpa 70e','70e','arc flash','arc flash training','electrical safety training'], ARRAY['electrical','energy_lineman','building_automation','industrial_maintenance'], 'Retraining at least every 3 years', NULL),
  ('confined_space', 'Confined Space Entry Training', 'safety', NULL, ARRAY['confined space','confined space entry','confined space training'], ARRAY['construction','manufacturing','industrial_maintenance'], NULL, NULL),
  ('fall_protection', 'Fall Protection Training', 'safety', NULL, ARRAY['fall protection','fall arrest','fall protection training'], ARRAY['construction','wind_energy','energy_lineman'], 'Employers commonly require refresh every 2 years', NULL),
  ('loto', 'Lockout/Tagout (LOTO) Training', 'safety', NULL, ARRAY['lockout tagout','loto','lock out tag out'], ARRAY['manufacturing','industrial_maintenance','power_plant'], 'Employer retraining on procedure change; annual review is common', NULL),
  ('cpr_first_aid', 'CPR / First Aid / AED', 'safety', 'American Red Cross / American Heart Association', ARRAY['cpr','first aid','cpr first aid','cpr and first aid','aed','cpr aed'], ARRAY['construction','manufacturing','healthcare_support','childcare_education','security'], 'Renew every 2 years', NULL),
  ('bls', 'Basic Life Support (BLS) Provider', 'safety', 'American Heart Association', ARRAY['bls','basic life support','bls provider','bls cpr','bls certification'], ARRAY['nursing','healthcare_support','surgical_tech','respiratory','radiology','dental','pharmacy'], 'Renew every 2 years', NULL),
  ('acls', 'Advanced Cardiovascular Life Support (ACLS)', 'safety', 'American Heart Association', ARRAY['acls','advanced cardiac life support','advanced cardiovascular life support'], ARRAY['nursing','respiratory'], 'Renew every 2 years', NULL),
  ('gwo_bst', 'GWO Basic Safety Training', 'safety', 'Global Wind Organisation', ARRAY['gwo','gwo bst','gwo basic safety training','winda'], ARRAY['wind_energy'], 'Valid 2 years; refresh modules required', 'https://winda.globalwindsafety.org'),
  ('twic', 'TWIC — Transportation Worker Identification Credential', 'license', 'TSA', ARRAY['twic','twic card','transportation worker identification credential'], ARRAY['logistics','marine','rail_transit'], 'Valid 5 years', NULL),
  ('dot_medical', 'DOT Medical Examiner''s Certificate', 'other', 'FMCSA-certified medical examiner', ARRAY['dot medical card','dot physical','dot med card','medical examiners certificate'], ARRAY['logistics','heavy_equipment'], 'Valid up to 2 years', NULL),
  ('forklift_pit', 'Forklift / Powered Industrial Truck Operator', 'certification', 'OSHA (employer-certified)', ARRAY['forklift','forklift certification','forklift license','forklift operator','powered industrial truck','lift truck'], ARRAY['manufacturing','logistics','construction'], 'Employer re-evaluation at least every 3 years', NULL),
  ('nccer_core', 'NCCER Core', 'certification', 'NCCER', ARRAY['nccer','nccer core','nccer certified','core curriculum','national center for construction education'], ARRAY['construction'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_electrical', 'NCCER Electrical (Craft Level)', 'certification', 'NCCER', ARRAY['nccer electrical','nccer electrician','electrical levels 1 4'], ARRAY['electrical'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_welding', 'NCCER Welding (Craft Level)', 'certification', 'NCCER', ARRAY['nccer welding','nccer welder'], ARRAY['welding'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_hvac', 'NCCER HVAC (Craft Level)', 'certification', 'NCCER', ARRAY['nccer hvac','nccer hvac r'], ARRAY['hvac'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_plumbing', 'NCCER Plumbing (Craft Level)', 'certification', 'NCCER', ARRAY['nccer plumbing','nccer plumber'], ARRAY['plumbing'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_pipefitting', 'NCCER Pipefitting (Craft Level)', 'certification', 'NCCER', ARRAY['nccer pipefitting','nccer pipefitter','pipefitter certification'], ARRAY['plumbing','construction'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_carpentry', 'NCCER Carpentry (Craft Level)', 'certification', 'NCCER', ARRAY['nccer carpentry','nccer carpenter','carpentry certification'], ARRAY['construction'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_millwright', 'NCCER Millwright (Craft Level)', 'certification', 'NCCER', ARRAY['nccer millwright','millwright certification'], ARRAY['industrial_maintenance','manufacturing'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_industrial_maint', 'NCCER Industrial Maintenance', 'certification', 'NCCER', ARRAY['nccer industrial maintenance','industrial maintenance craft'], ARRAY['industrial_maintenance'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('nccer_heavy_equip', 'NCCER Heavy Equipment Operations', 'certification', 'NCCER', ARRAY['nccer heavy equipment','nccer heavy equipment operations'], ARRAY['heavy_equipment'], 'Does not expire; recorded in the NCCER Registry', 'https://registry.nccer.org'),
  ('heavy_equip_cert', 'Heavy Equipment Operator Certification', 'certification', 'NCCER / IUOE / trade school', ARRAY['heavy equipment operator','heavy equipment certification','heavy equipment operator certification','equipment operator certification'], ARRAY['heavy_equipment','construction'], NULL, NULL),
  ('epa_lead_rrp', 'EPA Lead RRP (Renovation, Repair & Painting)', 'certification', 'EPA', ARRAY['lead rrp','epa rrp','rrp','rrp certification','lead renovator','renovation repair and painting','renovation repair painting'], ARRAY['construction'], 'Valid 5 years', NULL),
  ('nccco_crane', 'NCCCO Certified Crane Operator', 'certification', 'NCCCO', ARRAY['nccco','cco','crane operator certification','certified crane operator','nccco crane','crane certification'], ARRAY['heavy_equipment','construction'], 'Valid 5 years; recertify in the final 12 months', 'https://www.nccco.org/nccco/verify-cco'),
  ('nccco_rigger', 'NCCCO Rigger / Signalperson', 'certification', 'NCCCO', ARRAY['rigger certification','signalperson','rigger signalperson','qualified rigger','certified rigger'], ARRAY['construction','heavy_equipment'], 'Valid 5 years', 'https://www.nccco.org/nccco/verify-cco'),
  ('aerial_lift', 'Aerial Lift / MEWP Operator Training', 'certification', NULL, ARRAY['aerial lift','mewp','boom lift certification','scissor lift certification','aerial lift certification'], ARRAY['construction','field_service'], 'Re-evaluation every 3 years is standard (ANSI A92)', NULL),
  ('contractor_license', 'State Contractor License', 'license', 'State contractor licensing board', ARRAY['contractor license','general contractor license','licensed contractor','gc license'], ARRAY['construction','construction_mgmt'], 'State license; renewal cycle varies by state (search your state''s contractor license lookup)', NULL),
  ('leed_ga', 'LEED Green Associate', 'certification', 'GBCI / USGBC', ARRAY['leed','leed green associate','leed ap'], ARRAY['construction_mgmt'], '2-year continuing-education cycle', NULL),
  ('elec_apprentice', 'Electrical Apprenticeship', 'apprenticeship', 'DOL / IBEW / IEC', ARRAY['electrical apprentice','electrician apprentice','apprentice electrician','electrical apprenticeship'], ARRAY['electrical'], NULL, NULL),
  ('elec_journeyman', 'Journeyman Electrician License', 'license', 'State licensing board', ARRAY['journeyman electrician','journeyman electrical license','journeyperson electrician','licensed journeyman electrician','j man electrician','journeyman electrician license'], ARRAY['electrical'], 'State license; typically renews every 1–3 years with continuing education (verify via your state''s license lookup)', NULL),
  ('elec_master', 'Master Electrician License', 'license', 'State licensing board', ARRAY['master electrician','master electrical license','licensed master electrician'], ARRAY['electrical'], 'State license; typically renews every 1–3 years (verify via your state''s license lookup)', NULL),
  ('low_voltage', 'Low-Voltage / Limited Energy Technician License', 'license', 'State licensing board', ARRAY['low voltage license','low voltage technician','limited energy','low voltage'], ARRAY['electrical','building_automation','electronics'], NULL, NULL),
  ('lineman_journey', 'Journeyman Lineman', 'apprenticeship', 'DOL / IBEW', ARRAY['journeyman lineman','journeyman lineworker','lineman','lineworker'], ARRAY['energy_lineman'], NULL, NULL),
  ('nabcep_pv', 'NABCEP PV Installation Professional', 'certification', 'NABCEP', ARRAY['nabcep','nabcep pv','pv installation professional','solar installer certification','solar certification'], ARRAY['solar_energy','electrical'], 'Valid 3 years', 'https://www.nabcep.com/certification-verification'),
  ('boiler_operator', 'Stationary Engineer / Boiler Operator License', 'license', 'City/state licensing authority', ARRAY['boiler operator','stationary engineer','boiler license','high pressure boiler operator'], ARRAY['power_plant','industrial_maintenance'], NULL, NULL),
  ('epa_608', 'EPA Section 608 Technician Certification', 'certification', 'EPA', ARRAY['epa 608','epa section 608','section 608','608 certification','epa universal','universal epa','epa 608 universal','608 universal','epa refrigerant','refrigerant certification','universal refrigerant','epa 608 type i','epa 608 type ii','epa 608 type iii'], ARRAY['hvac','field_service'], 'Lifetime — does not expire under 40 CFR Part 82', NULL),
  ('epa_609', 'EPA Section 609 MVAC Certification', 'certification', 'EPA', ARRAY['epa 609','section 609','mvac','mvac certification','609 certification'], ARRAY['automotive','hvac'], 'Lifetime — does not expire', NULL),
  ('nate', 'NATE (North American Technician Excellence)', 'certification', 'NATE', ARRAY['nate','nate certified','nate certification','north american technician excellence'], ARRAY['hvac'], 'Valid 2 years; renew with 16 CEHs or by retesting', NULL),
  ('hvac_excellence', 'HVAC Excellence Certification', 'certification', 'HVAC Excellence', ARRAY['hvac excellence','hvac excellence certified'], ARRAY['hvac'], NULL, NULL),
  ('hvac_license', 'State HVAC Contractor / Technician License', 'license', 'State licensing board', ARRAY['hvac license','hvac contractor license','hvac technician license','licensed hvac technician'], ARRAY['hvac'], 'State license; renewal cycle varies by state (verify via your state''s license lookup)', NULL),
  ('plumb_apprentice', 'Plumbing Apprenticeship', 'apprenticeship', 'DOL / UA', ARRAY['plumbing apprentice','apprentice plumber','plumbing apprenticeship'], ARRAY['plumbing'], NULL, NULL),
  ('plumb_journeyman', 'Journeyman Plumber License', 'license', 'State licensing board', ARRAY['journeyman plumber','journeyman plumbing license','licensed journeyman plumber','journeyman plumber license'], ARRAY['plumbing'], 'State license; typically renews every 1–3 years (verify via your state''s license lookup)', NULL),
  ('plumb_master', 'Master Plumber License', 'license', 'State licensing board', ARRAY['master plumber','master plumbing license','licensed master plumber'], ARRAY['plumbing'], 'State license; typically renews every 1–3 years (verify via your state''s license lookup)', NULL),
  ('backflow', 'Backflow Prevention Assembly Tester', 'certification', 'ASSE / state program', ARRAY['backflow','backflow tester','backflow prevention','asse 5110','backflow certification'], ARRAY['plumbing'], 'Typically valid 3 years', NULL),
  ('med_gas', 'Medical Gas Installer (ASSE 6010)', 'certification', 'ASSE', ARRAY['medical gas','med gas','asse 6010','medical gas installer'], ARRAY['plumbing'], 'Valid 3 years', NULL),
  ('aws_cw', 'AWS Certified Welder', 'certification', 'American Welding Society', ARRAY['aws certified welder','certified welder','aws cw','aws welding certification','certified welding'], ARRAY['welding'], 'Stays active with a maintenance form every 6 months confirming continued use of the process', NULL),
  ('aws_cwi', 'AWS Certified Welding Inspector', 'certification', 'American Welding Society', ARRAY['aws cwi','cwi','certified welding inspector','welding inspector'], ARRAY['welding'], 'Renew every 3 years; full recertification every 9 years', NULL),
  ('aws_d1_1', 'AWS D1.1 Structural Steel Qualification', 'certification', 'American Welding Society', ARRAY['aws d1 1','d1 1','structural welding certification','structural steel welding'], ARRAY['welding'], 'Code qualification; continuity typically required every 6 months', NULL),
  ('welder_qual', 'Welder Performance Qualification (process-specific)', 'certification', 'Employer / accredited test facility (AWS, ASME)', ARRAY['welder qualification','welding qualification','wpq','tig certification','mig certification','stick certification','gtaw certification','gmaw certification','smaw certification','fcaw certification','certified tig welder','certified mig welder','tig certified','mig certified'], ARRAY['welding','manufacturing'], 'Continuity typically required every 6 months per code', NULL),
  ('asme_ix', 'ASME Section IX Welder Qualification', 'certification', 'ASME-accredited test facility', ARRAY['asme section ix','asme ix','asme welding','pressure vessel welding'], ARRAY['welding','manufacturing','power_plant'], 'Continuity typically required every 6 months', NULL),
  ('api_1104', 'API 1104 Pipeline Welding Qualification', 'certification', 'API-accredited test facility', ARRAY['api 1104','pipeline welding','pipeline welding qualification'], ARRAY['welding'], 'Continuity typically required every 6 months', NULL),
  ('mssc_cpt', 'MSSC Certified Production Technician', 'certification', 'MSSC', ARRAY['cpt','mssc cpt','mssc','certified production technician'], ARRAY['manufacturing'], 'Valid 5 years; 100 recertification points to renew', NULL),
  ('mssc_clt', 'MSSC Certified Logistics Technician', 'certification', 'MSSC', ARRAY['clt','mssc clt','certified logistics technician'], ARRAY['logistics'], 'Valid 5 years', NULL),
  ('nims_machining', 'NIMS Machining Credential', 'certification', 'NIMS', ARRAY['nims','nims machining','nims credential','nims certified'], ARRAY['manufacturing'], 'Does not expire', NULL),
  ('cmrt', 'SMRP Certified Maintenance & Reliability Technician', 'certification', 'SMRP', ARRAY['cmrt','certified maintenance and reliability technician'], ARRAY['industrial_maintenance'], 'Valid 3 years', NULL),
  ('lean_six_sigma', 'Lean Six Sigma Belt', 'certification', 'Varies (ASQ, IASSC, employer programs)', ARRAY['six sigma','lean six sigma','six sigma green belt','six sigma black belt','lean manufacturing certification','green belt','yellow belt'], ARRAY['manufacturing','construction_mgmt','administrative'], NULL, NULL),
  ('fanuc_robot', 'FANUC Robot Operations & Programming Certificate', 'certification', 'FANUC', ARRAY['fanuc','fanuc certified','robot programming certificate','fanuc robot'], ARRAY['robotics','manufacturing'], NULL, NULL),
  ('ipc_610', 'IPC-A-610 Certified (Electronics Assembly)', 'certification', 'IPC', ARRAY['ipc a 610','ipc 610','ipc certified'], ARRAY['electronics','manufacturing'], 'Valid 2 years', NULL),
  ('j_std_001', 'IPC J-STD-001 Soldering Certification', 'certification', 'IPC', ARRAY['j std 001','ipc j std','soldering certification'], ARRAY['electronics'], 'Valid 2 years', NULL),
  ('ase', 'ASE (Automotive Service Excellence) Certification', 'certification', 'ASE', ARRAY['ase','ase certified','ase certification','automotive service excellence','ase master','ase master technician','ase a series'], ARRAY['automotive'], 'Valid 5 years; recertification test (or ASE renewal app) to maintain', NULL),
  ('icar', 'I-CAR Training (Collision Repair)', 'certification', 'I-CAR', ARRAY['i car','icar','i car platinum','i car gold'], ARRAY['auto_body'], 'Platinum recognition renews annually', NULL),
  ('faa_ap', 'FAA Airframe & Powerplant (A&P) Mechanic Certificate', 'license', 'FAA', ARRAY['a p license','a p mechanic','faa a p','ap mechanic','airframe and powerplant','airframe powerplant','powerplant mechanic'], ARRAY['aviation'], 'Does not expire; FAA recent-experience requirements apply', 'https://amsrvs.registry.faa.gov/airmeninquiry/'),
  ('faa_107', 'FAA Part 107 Remote Pilot Certificate', 'license', 'FAA', ARRAY['part 107','faa part 107','remote pilot','drone license','drone pilot certificate','remote pilot certificate'], ARRAY['aviation','civil_survey','field_service'], 'Recurrent online training every 24 months', 'https://amsrvs.registry.faa.gov/airmeninquiry/'),
  ('abyc', 'ABYC Marine Technician Certification', 'certification', 'ABYC', ARRAY['abyc','abyc certified','marine technician certification'], ARRAY['marine'], 'Valid 5 years', NULL),
  ('uscg_mmc', 'USCG Merchant Mariner Credential', 'license', 'U.S. Coast Guard', ARRAY['mmc','merchant mariner','merchant mariner credential','uscg mmc'], ARRAY['marine'], 'Valid 5 years', NULL),
  ('cdl_a', 'Commercial Driver''s License — Class A', 'license', 'State DMV', ARRAY['cdl a','class a cdl','cdl class a','class a commercial drivers license','class a license'], ARRAY['logistics','heavy_equipment'], 'Renews on the state driver''s-license cycle (typically 4–8 years); verify via the issuing state DMV', NULL),
  ('cdl_b', 'Commercial Driver''s License — Class B', 'license', 'State DMV', ARRAY['cdl b','class b cdl','cdl class b','class b license'], ARRAY['logistics','rail_transit','heavy_equipment'], 'Renews on the state driver''s-license cycle; verify via the issuing state DMV', NULL),
  ('cdl_c', 'Commercial Driver''s License — Class C', 'license', 'State DMV', ARRAY['cdl c','class c cdl','cdl class c'], ARRAY['logistics'], 'Renews on the state driver''s-license cycle; verify via the issuing state DMV', NULL),
  ('cdl_unspec', 'Commercial Driver''s License (CDL)', 'license', 'State DMV', ARRAY['cdl','commercial drivers license','commercial driver license','commercial license'], ARRAY['logistics','heavy_equipment'], 'Class unspecified — ask which class (A/B/C); renews on the state cycle', NULL),
  ('cdl_hazmat', 'CDL Hazmat Endorsement (H)', 'license', 'State DMV + TSA', ARRAY['hazmat endorsement','hazmat','h endorsement','cdl hazmat'], ARRAY['logistics'], 'TSA security threat assessment renews every 5 years', NULL),
  ('cdl_tanker', 'CDL Tanker Endorsement (N)', 'license', 'State DMV', ARRAY['tanker endorsement','n endorsement','tanker'], ARRAY['logistics'], NULL, NULL),
  ('cdl_doubles', 'CDL Doubles/Triples Endorsement (T)', 'license', 'State DMV', ARRAY['doubles triples','t endorsement','doubles triples endorsement'], ARRAY['logistics'], NULL, NULL),
  ('cdl_passenger', 'CDL Passenger Endorsement (P)', 'license', 'State DMV', ARRAY['passenger endorsement','p endorsement'], ARRAY['logistics','rail_transit'], NULL, NULL),
  ('cdl_school_bus', 'CDL School Bus Endorsement (S)', 'license', 'State DMV', ARRAY['school bus endorsement','s endorsement','school bus certificate'], ARRAY['logistics','childcare_education'], NULL, NULL),
  ('cna', 'Certified Nursing Assistant (CNA)', 'certification', 'State nurse aide registry', ARRAY['cna','certified nursing assistant','nurse aide','nursing assistant','state tested nursing assistant','stna'], ARRAY['nursing','healthcare_support'], '2-year renewal with paid work requirement; verify via the state nurse aide registry', NULL),
  ('lpn_lvn', 'Licensed Practical / Vocational Nurse (LPN/LVN)', 'license', 'State board of nursing', ARRAY['lpn','lvn','licensed practical nurse','licensed vocational nurse','practical nurse'], ARRAY['nursing'], 'State license; typically renews every 2 years', 'https://www.nursys.com'),
  ('rn', 'Registered Nurse (RN) License', 'license', 'State board of nursing', ARRAY['rn','registered nurse','rn license','registered nurse license'], ARRAY['nursing'], 'State license; typically renews every 2 years', 'https://www.nursys.com'),
  ('cma', 'Certified Medical Assistant (CMA/CCMA/RMA)', 'certification', 'AAMA / NHA / AMT', ARRAY['cma','ccma','rma','certified medical assistant','medical assistant certification','registered medical assistant','certified clinical medical assistant'], ARRAY['healthcare_support','administrative'], 'Typically 2–5 year renewal depending on issuer', NULL),
  ('phlebotomy', 'Certified Phlebotomy Technician', 'certification', 'NHA / ASCP / NCCT', ARRAY['phlebotomy','phlebotomy certification','certified phlebotomy technician','cpt phlebotomy','pbt','phlebotomist'], ARRAY['lab_sciences','healthcare_support'], 'Typically valid 2 years', NULL),
  ('ekg_tech', 'Certified EKG Technician (CET)', 'certification', 'NHA', ARRAY['cet','ekg technician','ekg certification','ecg technician','certified ekg technician'], ARRAY['healthcare_support'], 'Valid 2 years', NULL),
  ('ptcb_cpht', 'Certified Pharmacy Technician (CPhT)', 'certification', 'PTCB', ARRAY['cpht','ptcb','pharmacy technician certification','certified pharmacy technician','pharmacy technician license'], ARRAY['pharmacy'], 'Renew every 2 years with 20 CE hours', 'https://www.ptcb.org'),
  ('rbt', 'Registered Behavior Technician (RBT)', 'certification', 'BACB', ARRAY['rbt','registered behavior technician','behavior technician'], ARRAY['healthcare_support','childcare_education'], 'Annual renewal', 'https://www.bacb.com'),
  ('cst', 'Certified Surgical Technologist (CST)', 'certification', 'NBSTSA', ARRAY['cst','certified surgical technologist','surgical tech certification','surgical technologist'], ARRAY['surgical_tech'], 'Valid 4 years (CE or retest)', 'https://www.nbstsa.org'),
  ('arrt', 'ARRT Registered Technologist (Radiography)', 'certification', 'ARRT', ARRAY['arrt','registered radiologic technologist','radiologic technologist','rad tech certification','rt r'], ARRAY['radiology'], 'Annual registration + 24 CE credits every 2 years; most states also require a license', 'https://www.arrt.org/pages/verify-credentials'),
  ('nbrc_rrt', 'Registered Respiratory Therapist (RRT)', 'certification', 'NBRC', ARRAY['rrt','crt','registered respiratory therapist','certified respiratory therapist','respiratory therapist'], ARRAY['respiratory'], 'NBRC credential + state RT license; renewal cycles vary', NULL),
  ('pta_license', 'Physical Therapist Assistant (PTA) License', 'license', 'State licensing board', ARRAY['pta','physical therapist assistant','pta license','licensed physical therapist assistant'], ARRAY['physical_therapy'], 'State license; typically renews every 2 years', NULL),
  ('danb_cda', 'DANB Certified Dental Assistant', 'certification', 'DANB', ARRAY['certified dental assistant','danb','danb cda','dental assistant certification'], ARRAY['dental'], 'Annual renewal with CE', NULL),
  ('rdh', 'Registered Dental Hygienist (RDH) License', 'license', 'State dental board', ARRAY['rdh','dental hygienist','registered dental hygienist','dental hygiene license'], ARRAY['dental'], 'State license; typically renews every 1–2 years', NULL),
  ('hha', 'Home Health Aide (HHA) Certificate', 'certification', 'State-approved program', ARRAY['hha','home health aide','home care aide'], ARRAY['healthcare_support'], 'State renewal with in-service hours (12/yr federal minimum)', NULL),
  ('cpc', 'Certified Professional Coder (CPC)', 'certification', 'AAPC', ARRAY['cpc','certified professional coder','medical coding certification','medical coder'], ARRAY['health_information','administrative'], 'Annual membership + 36 CEUs per 2 years', NULL),
  ('rhit', 'Registered Health Information Technician (RHIT)', 'certification', 'AHIMA', ARRAY['rhit','health information technician'], ARRAY['health_information'], 'CE-based renewal every 2 years', NULL),
  ('cvt', 'Credentialed Veterinary Technician (CVT/RVT/LVT)', 'license', 'State veterinary board', ARRAY['cvt','rvt','lvt','veterinary technician','vet tech license','credentialed veterinary technician','vet tech'], ARRAY['veterinary'], 'State credential; typically renews every 1–3 years', NULL),
  ('cdm', 'Certified Dietary Manager (CDM, CFPP)', 'certification', 'ANFP', ARRAY['cdm','certified dietary manager','dietary manager'], ARRAY['dietetics','culinary'], '45 CE hours every 3 years', NULL),
  ('mlt', 'Medical Laboratory Technician (MLT) Certification', 'certification', 'ASCP', ARRAY['mlt','medical laboratory technician','lab technician certification','ascp mlt'], ARRAY['lab_sciences'], '3-year Credential Maintenance Program cycle', NULL),
  ('cosmetology_lic', 'Cosmetology License', 'license', 'State board of cosmetology', ARRAY['cosmetology license','licensed cosmetologist','cosmetologist'], ARRAY['cosmetology'], 'State license; typically renews every 1–2 years', NULL),
  ('barber_lic', 'Barber License', 'license', 'State barbering board', ARRAY['barber license','licensed barber','barbering license'], ARRAY['cosmetology'], 'State license; typically renews every 1–2 years', NULL),
  ('esthetician_lic', 'Esthetician License', 'license', 'State board of cosmetology', ARRAY['esthetician license','esthetician','aesthetician license'], ARRAY['cosmetology'], 'State license; typically renews every 1–2 years', NULL),
  ('nail_tech_lic', 'Nail Technician License', 'license', 'State board of cosmetology', ARRAY['nail technician license','nail tech','manicurist license'], ARRAY['cosmetology'], 'State license; typically renews every 1–2 years', NULL),
  ('servsafe_mgr', 'ServSafe Food Protection Manager', 'certification', 'National Restaurant Association', ARRAY['servsafe','servsafe manager','food protection manager','food safety manager'], ARRAY['culinary','dietetics'], 'Valid 5 years', NULL),
  ('food_handler', 'Food Handler Card', 'certification', 'ServSafe / state program', ARRAY['food handler','food handlers card','food handler certificate','food handler card'], ARRAY['culinary'], 'Typically 2–3 years, set by state/county', NULL),
  ('acf_cc', 'ACF Certified Culinarian', 'certification', 'American Culinary Federation', ARRAY['certified culinarian','acf certified','acf certification'], ARRAY['culinary'], NULL, NULL),
  ('guard_card', 'State Security Guard License / Registration', 'license', 'State licensing authority', ARRAY['guard card','security guard license','security license','unarmed guard','armed guard license','security guard card'], ARRAY['security'], 'State registration; typically renews every 1–2 years', NULL),
  ('cda_credential', 'Child Development Associate (CDA) Credential', 'certification', 'Council for Professional Recognition', ARRAY['cda credential','child development associate'], ARRAY['childcare_education'], 'Valid 3 years', NULL),
  ('comptia_a', 'CompTIA A+', 'certification', 'CompTIA', ARRAY['comptia a','comptia a plus','a plus certification'], ARRAY['it_support','field_service','data_center'], 'Valid 3 years (Continuing Education program)', NULL),
  ('comptia_net', 'CompTIA Network+', 'certification', 'CompTIA', ARRAY['comptia network','network plus','comptia network plus'], ARRAY['it_support','data_center'], 'Valid 3 years (Continuing Education program)', NULL),
  ('comptia_sec', 'CompTIA Security+', 'certification', 'CompTIA', ARRAY['comptia security','security plus','comptia security plus'], ARRAY['it_support','data_center','security'], 'Valid 3 years (Continuing Education program)', NULL),
  ('ccna', 'Cisco CCNA', 'certification', 'Cisco', ARRAY['ccna','cisco certified network associate'], ARRAY['it_support','data_center'], 'Valid 3 years', NULL),
  ('bicsi', 'BICSI Installer / Technician', 'certification', 'BICSI', ARRAY['bicsi','bicsi installer','bicsi technician'], ARRAY['data_center','building_automation','electronics'], 'Valid 3 years with CE', NULL),
  ('nicet', 'NICET Certification (Fire Alarm / Low Voltage)', 'certification', 'NICET', ARRAY['nicet','nicet ii','nicet certification','fire alarm certification'], ARRAY['building_automation','electrical'], 'Recertify every 3 years with CPD points', NULL),
  ('cfot', 'FOA Certified Fiber Optic Technician (CFOT)', 'certification', 'Fiber Optic Association', ARRAY['cfot','fiber optic technician','fiber optics certification','fiber optic certification'], ARRAY['electronics','data_center'], NULL, NULL),
  ('niagara', 'Tridium Niagara 4 Certification', 'certification', 'Tridium', ARRAY['niagara','tridium','niagara 4'], ARRAY['building_automation'], NULL, NULL),
  ('autocad_cert', 'Autodesk Certified User (AutoCAD / Revit)', 'certification', 'Autodesk', ARRAY['autocad certification','autodesk certified','autocad certified user','revit certification','revit certified'], ARRAY['drafting'], NULL, NULL),
  ('mos', 'Microsoft Office Specialist', 'certification', 'Microsoft', ARRAY['microsoft office specialist','mos certification'], ARRAY['administrative','it_support'], NULL, NULL),
  ('pls', 'Professional Land Surveyor (PLS) License', 'license', 'State licensing board', ARRAY['pls','professional land surveyor','land surveyor license','licensed surveyor'], ARRAY['civil_survey'], 'State license; typically renews every 2 years', NULL),
  ('dol_journeyworker', 'DOL Registered Apprenticeship — Journeyworker', 'apprenticeship', 'DOL Office of Apprenticeship', ARRAY['journeyman','journeyworker','journeyman card','journeyman certificate','registered apprenticeship','dol apprenticeship'], ARRAY['electrical','plumbing','hvac','welding','construction','manufacturing','energy_lineman'], 'Completion credential — does not expire', NULL),
  ('union_member', 'Union Membership', 'union', 'Local union', ARRAY['union member','union membership','ibew member','ua member','uaw member','ibew','teamsters'], ARRAY[]::text[], NULL, NULL),
  ('hs_diploma', 'High School Diploma', 'degree', NULL, ARRAY['high school diploma','hs diploma','high school graduate','highschool diploma'], ARRAY[]::text[], NULL, NULL),
  ('ged', 'GED / High School Equivalency', 'degree', 'GED Testing Service / state equivalency program', ARRAY['ged','hiset','high school equivalency','tasc'], ARRAY[]::text[], NULL, NULL),
  ('cert_of_completion', 'Certificate of Completion', 'degree', NULL, ARRAY['certificate of completion','completion certificate','program certificate','trade certificate'], ARRAY[]::text[], NULL, NULL),
  ('diploma', 'Trade / Technical Diploma', 'degree', NULL, ARRAY['diploma','technical diploma','trade diploma','vocational diploma'], ARRAY[]::text[], NULL, NULL),
  ('associate', 'Associate Degree', 'degree', NULL, ARRAY['associate degree','associates degree','associate''s degree','aa degree','associate of arts'], ARRAY[]::text[], NULL, NULL),
  ('associate_science', 'Associate of Science (AS)', 'degree', NULL, ARRAY['as degree','a.s.','associate of science','associate in science'], ARRAY[]::text[], NULL, NULL),
  ('associate_applied_science', 'Associate of Applied Science (AAS)', 'degree', NULL, ARRAY['aas','a.a.s.','aas degree','associate of applied science','applied science degree'], ARRAY[]::text[], NULL, NULL),
  ('bachelor', 'Bachelor''s Degree', 'degree', NULL, ARRAY['bachelors degree','bachelor''s degree','bachelors','bachelor of science','bachelor of arts','bs degree','ba degree'], ARRAY[]::text[], NULL, NULL)
ON CONFLICT (canonical_code) DO UPDATE SET
  canonical_name   = EXCLUDED.canonical_name,
  credential_type  = EXCLUDED.credential_type,
  authority        = COALESCE(EXCLUDED.authority, credential_definitions.authority),
  aliases          = EXCLUDED.aliases,
  job_families     = EXCLUDED.job_families,
  validity_note    = EXCLUDED.validity_note,
  verification_url = EXCLUDED.verification_url,
  active           = true,
  updated_at       = now();
