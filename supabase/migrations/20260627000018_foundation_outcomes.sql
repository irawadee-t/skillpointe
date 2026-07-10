-- SKILLED Foundation outcomes analytics.
--
-- WIOA-style outcome reporting needs a reported placement wage (median earnings
-- is a reported figure, not derived from a job posting). Add it to hire_outcomes,
-- then expose a per-applicant fact view that the analytics layer aggregates into
-- cohorts (with k-anonymity applied at the API boundary for any public feed).

ALTER TABLE public.hire_outcomes
    ADD COLUMN IF NOT EXISTS reported_wage_annual integer;

COMMENT ON COLUMN public.hire_outcomes.reported_wage_annual IS
    'Annualized placement wage (USD) as reported for outcomes tracking.';

CREATE OR REPLACE VIEW public.applicant_outcomes AS
SELECT
    a.id AS applicant_id,
    COALESCE(NULLIF(btrim(a.program_field), ''), NULLIF(btrim(a.program_name_raw), ''), 'Unspecified') AS program,
    COALESCE(NULLIF(btrim(a.region), ''), NULLIF(btrim(a.state), ''), 'Unspecified') AS region,
    a.state,
    COALESCE(a.military_status, false) AS military,
    EXTRACT(YEAR FROM COALESCE(a.program_start_date, a.created_at::date))::int AS cohort_year,
    (ho.id IS NOT NULL) AS placed,
    ho.reported_wage_annual AS wage,
    CASE
        WHEN ho.hire_date IS NOT NULL
        THEN (ho.hire_date - COALESCE(a.program_start_date, a.created_at::date))
    END AS time_to_hire_days,
    (SELECT count(*) FROM public.credentials c WHERE c.applicant_id = a.id) AS credential_count,
    (SELECT count(*) FROM public.credentials c
        WHERE c.applicant_id = a.id AND c.verification_level >= 1) AS verified_credential_count
FROM public.applicants a
LEFT JOIN LATERAL (
    SELECT h.*
    FROM public.hire_outcomes h
    WHERE h.applicant_id = a.id AND h.outcome_type IN ('placed', 'hired')
    ORDER BY h.hire_date DESC NULLS LAST
    LIMIT 1
) ho ON true;
