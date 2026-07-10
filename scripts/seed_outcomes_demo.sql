-- Demo seed for SKILLED Foundation outcomes analytics.
-- Idempotent + deterministic (placement/wage derived from hashtext(applicant id)),
-- so re-running yields identical data. Markered for clean teardown:
--   hire_outcomes.notes = 'demo-seed:foundation'
--   credentials.source  = 'demo_program'
-- Run:  docker exec -i <db> psql -U postgres -d postgres -f - < scripts/seed_outcomes_demo.sql

BEGIN;

DELETE FROM public.hire_outcomes WHERE notes = 'demo-seed:foundation';
DELETE FROM public.credentials   WHERE metadata->>'demo_seed' = 'foundation';

WITH params AS (
    SELECT (SELECT id FROM public.employers ORDER BY created_at LIMIT 1) AS employer_id,
           (SELECT id FROM public.jobs ORDER BY created_at LIMIT 1)      AS job_id
),
base AS (
    SELECT
        a.id,
        COALESCE(NULLIF(btrim(a.program_field), ''), NULLIF(btrim(a.program_name_raw), ''), 'Unspecified') AS program,
        COALESCE(a.program_start_date, a.created_at::date) AS start_ref,
        (abs(hashtext(a.id::text)) % 100) AS h
    FROM public.applicants a
),
scored AS (
    SELECT *,
        CASE program
            WHEN 'Welding' THEN 72 WHEN 'HVAC' THEN 66 WHEN 'Electrical' THEN 78
            WHEN 'Automotive Technology' THEN 58 WHEN 'Diesel Technology' THEN 70
            WHEN 'Plumbing' THEN 68 WHEN 'Carpentry' THEN 62 ELSE 60
        END AS place_threshold,
        CASE program
            WHEN 'Welding' THEN 53000 WHEN 'HVAC' THEN 55000 WHEN 'Electrical' THEN 63000
            WHEN 'Automotive Technology' THEN 48000 WHEN 'Diesel Technology' THEN 59000
            WHEN 'Plumbing' THEN 61000 WHEN 'Carpentry' THEN 50000 ELSE 51000
        END AS base_wage
    FROM base
)
INSERT INTO public.hire_outcomes
    (applicant_id, job_id, employer_id, outcome_type, hire_date, start_date,
     reported_wage_annual, notes)
SELECT
    s.id, p.job_id, p.employer_id, 'placed',
    (s.start_ref + (90 + (s.h % 120)))::date AS hire_date,
    (s.start_ref + (95 + (s.h % 120)))::date AS start_date,
    s.base_wage + ((s.h % 9) - 4) * 1000 AS reported_wage_annual,
    'demo-seed:foundation'
FROM scored s CROSS JOIN params p
WHERE s.h < s.place_threshold;

-- Credential attainment for ~65% of learners (program completion certificate).
INSERT INTO public.credentials
    (applicant_id, raw_name, canonical_name, credential_type, issuer,
     normalization_confidence, needs_review, source, verification_level, issued_date, metadata)
SELECT
    a.id,
    COALESCE(NULLIF(btrim(a.program_field), ''), NULLIF(btrim(a.program_name_raw), ''), 'Unspecified') || ' Completion Certificate',
    COALESCE(NULLIF(btrim(a.program_field), ''), NULLIF(btrim(a.program_name_raw), ''), 'Unspecified') || ' Completion Certificate',
    'certificate', 'SKILLED Foundation', 1.0, false, 'partner_portal', 1,
    (COALESCE(a.program_start_date, a.created_at::date) + 80)::date,
    '{"demo_seed":"foundation"}'::jsonb
FROM public.applicants a
WHERE (abs(hashtext(a.id::text || 'cred')) % 100) < 65;

COMMIT;
