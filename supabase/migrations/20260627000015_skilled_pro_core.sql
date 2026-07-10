-- ============================================================================
-- SKILLED Pro core: verified credentials, consent, and the SKILLED ID B2B API.
-- Additive and idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Credentials held by an applicant (current state).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credentials (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    applicant_id             uuid NOT NULL REFERENCES public.applicants(id) ON DELETE CASCADE,
    raw_name                 text NOT NULL,
    canonical_code           text,                 -- taxonomy code, null if unmatched
    canonical_name           text,
    credential_type          text,                 -- license/certification/degree/apprenticeship/safety
    issuer                   text,
    normalization_confidence numeric(4,3) DEFAULT 0,
    needs_review             boolean NOT NULL DEFAULT false,
    source                   text NOT NULL DEFAULT 'self'
                                 CHECK (source IN ('self','sis','partner_portal','document_upload')),
    verification_level       smallint NOT NULL DEFAULT 0
                                 CHECK (verification_level BETWEEN 0 AND 2),
    issued_date              date,
    expires_date             date,
    document_url             text,
    metadata                 jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_credentials_applicant ON public.credentials(applicant_id);
CREATE INDEX IF NOT EXISTS idx_credentials_code ON public.credentials(canonical_code);
CREATE INDEX IF NOT EXISTS idx_credentials_level ON public.credentials(verification_level);

-- ---------------------------------------------------------------------------
-- Append-only, cryptographically signed credential audit trail.
-- One row per state transition; hash-chained per applicant (prev_hash).
-- (Immutability is enforced at the app layer + RLS; never UPDATE/DELETE.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credential_records (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    credential_id uuid REFERENCES public.credentials(id) ON DELETE SET NULL,
    applicant_id  uuid NOT NULL,
    event         text NOT NULL,            -- created/updated/verified/revoked
    payload       jsonb NOT NULL,
    content_hash  text NOT NULL,
    prev_hash     text NOT NULL,
    chain_hash    text NOT NULL,
    signature     text NOT NULL,
    algorithm     text NOT NULL DEFAULT 'Ed25519',
    signing_key_id text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cred_records_applicant ON public.credential_records(applicant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cred_records_credential ON public.credential_records(credential_id);

-- ---------------------------------------------------------------------------
-- Granular consent settings — per applicant, per data category.
-- external_sharing is a JSONB array of requester categories.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.consent_settings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    applicant_id     uuid NOT NULL REFERENCES public.applicants(id) ON DELETE CASCADE,
    data_category    text NOT NULL,        -- e.g. certifications, employment_history, wage_expectations
    display          boolean NOT NULL DEFAULT false,
    internal_use     boolean NOT NULL DEFAULT true,
    external_sharing jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (applicant_id, data_category)
);
CREATE INDEX IF NOT EXISTS idx_consent_settings_applicant ON public.consent_settings(applicant_id);

-- ---------------------------------------------------------------------------
-- Append-only, signed consent change log (cryptographically verifiable).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.consent_records (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    applicant_id       uuid NOT NULL,
    data_category      text NOT NULL,
    scope              text NOT NULL,        -- display/internal_use/external_sharing
    action             text NOT NULL,        -- grant/revoke
    requester_category text,
    payload            jsonb NOT NULL,
    content_hash       text NOT NULL,
    prev_hash          text NOT NULL,
    chain_hash         text NOT NULL,
    signature          text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_consent_records_applicant ON public.consent_records(applicant_id, created_at);

-- ---------------------------------------------------------------------------
-- SKILLED ID B2B API partners (third-party consumers of verified status).
-- key_hash stores only the SHA-256 of the secret; raw keys are shown once.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.api_clients (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name               text NOT NULL,
    contact_email      text,
    requester_category text NOT NULL DEFAULT 'other',
    tier               text NOT NULL DEFAULT 'free'
                           CHECK (tier IN ('free','standard','premium','bulk')),
    key_prefix         text NOT NULL UNIQUE,
    key_hash           text NOT NULL,
    active             boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_used_at       timestamptz
);
CREATE INDEX IF NOT EXISTS idx_api_clients_prefix ON public.api_clients(key_prefix);

-- ---------------------------------------------------------------------------
-- SKILLED ID request log — audit + per-query metering/billing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.api_request_logs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    api_client_id uuid REFERENCES public.api_clients(id) ON DELETE SET NULL,
    endpoint      text NOT NULL,
    subject_count integer NOT NULL DEFAULT 1,
    status_code   integer NOT NULL,
    billable      boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_api_logs_client ON public.api_request_logs(api_client_id, created_at);

-- ---------------------------------------------------------------------------
-- Employer subscription tier (Free / Standard / Premium) for the portal.
-- ---------------------------------------------------------------------------
ALTER TABLE public.employers
    ADD COLUMN IF NOT EXISTS subscription_tier text NOT NULL DEFAULT 'free'
        CHECK (subscription_tier IN ('free','standard','premium'));

-- ---------------------------------------------------------------------------
-- Applicant identity verification + AI profile summary fields.
-- ---------------------------------------------------------------------------
ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS identity_verified boolean NOT NULL DEFAULT false;
ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS profile_summary text;
ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS profile_summary_generated_at timestamptz;
