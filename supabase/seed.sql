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
