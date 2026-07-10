-- ============================================================================
-- Indexes for the employer Verified-Worker Directory / SKILLED Verify search.
-- Additive + idempotent.
-- ============================================================================

-- The discovery gate filters on `external_sharing ? 'employer'` (JSONB
-- containment). A GIN index with jsonb_path_ops makes that predicate fast.
CREATE INDEX IF NOT EXISTS idx_consent_settings_external_sharing
    ON public.consent_settings USING gin (external_sharing jsonb_path_ops);

-- Common discovery filters / ranking.
CREATE INDEX IF NOT EXISTS idx_credentials_applicant_level
    ON public.credentials (applicant_id, verification_level);
CREATE INDEX IF NOT EXISTS idx_applicants_state
    ON public.applicants (state);
CREATE INDEX IF NOT EXISTS idx_applicants_job_family
    ON public.applicants (canonical_job_family_id);
