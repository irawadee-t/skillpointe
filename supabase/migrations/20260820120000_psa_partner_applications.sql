-- Staging for the partner-ready application extract (SN Data.xlsx,
-- 2026-08-20). Keyed by the sponsor's pseudonymous Stable Applicant ID
-- (hashed Zengine Contact ID). This extract carries NO identity, location,
-- or program fields, so it cannot create or replace applicant profiles —
-- it holds the application-side fields (program dates, partner-sharing
-- consent, internship text) until the full student export arrives with the
-- SAME stable id, at which point applicants.stable_applicant_id makes the
-- join trivial and these fields flow into matching (timing gate + consent
-- gating + experience signals).
CREATE TABLE IF NOT EXISTS public.psa_partner_applications (
    stable_applicant_id   text PRIMARY KEY,
    funding_opportunity   text,
    application_status    text,
    record_completion     text,
    submitted_at          date,
    program_start_date    date,
    program_end_date      date,
    career_interest       text,      -- 'Yes'/'No'/NULL — NULL = not collected
    partner_share_consent boolean,   -- TRUE only on recorded affirmative
    has_internship_text   boolean,
    internship_details    text,
    imported_at           timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS stable_applicant_id text;
CREATE INDEX IF NOT EXISTS applicants_stable_id_idx
    ON public.applicants (stable_applicant_id)
    WHERE stable_applicant_id IS NOT NULL;
