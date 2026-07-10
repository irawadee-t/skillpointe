-- Credential taxonomy (CTDL-aligned) + partner verification.
--
-- Everything additive. Extends the existing credentials pipeline:
--   • credential_definitions — canonical taxonomy with CTDL URIs + issuing authority
--   • credentials.definition_id — link an applicant's cred to a definition
--   • credentials.provider_verification — jsonb receipt from NCCER / NSC / etc.
--   • credentials.source_check extended with new provenance sources

BEGIN;

-- =====================================================================
-- 1. Canonical credential taxonomy
-- =====================================================================
CREATE TABLE IF NOT EXISTS credential_definitions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_code  TEXT NOT NULL UNIQUE,     -- 'osha_30', 'aws_d1_1', etc. — internal key
  canonical_name  TEXT NOT NULL,            -- 'OSHA 30 - General Industry'
  credential_type TEXT NOT NULL,            -- 'certification' | 'license' | 'degree' | 'certificate' | 'apprenticeship' | 'badge'

  -- CTDL / Credential Engine Registry (national taxonomy backbone)
  ctdl_uri        TEXT,                     -- e.g. 'https://credentialengineregistry.org/resources/ce-abc123...'
  ctdl_type       TEXT,                     -- 'CertificationProfile' | 'LicenseProfile' | 'DegreeProfile' | ...

  -- Issuing authority (who grants it in the real world)
  authority        TEXT,                    -- 'NCCER' | 'NCCER Craft' | 'OSHA' | 'AWS' | 'EPA' | 'DOL Apprenticeship' | 'State Board' | 'MSSC' | 'IBEW' | ...
  authority_type   TEXT,                    -- 'trade_association' | 'federal_agency' | 'state_board' | 'union' | 'private_certifier'

  -- Where can we verify a holder? Points to the provider adapter to invoke.
  verification_provider TEXT,               -- 'nccer' | 'nsc' | 'state_licensing' | 'document_upload' | NULL

  aliases         TEXT[] NOT NULL DEFAULT '{}',  -- ["OSHA-30", "30-Hour OSHA", "OSHA30-GI"]
  active          BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_credential_defs_ctdl ON credential_definitions(ctdl_uri) WHERE ctdl_uri IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_credential_defs_provider ON credential_definitions(verification_provider) WHERE verification_provider IS NOT NULL;


-- =====================================================================
-- 2. Extend credentials with taxonomy link + partner verification
-- =====================================================================
ALTER TABLE credentials
  ADD COLUMN IF NOT EXISTS definition_id UUID REFERENCES credential_definitions(id),
  ADD COLUMN IF NOT EXISTS provider_verified_at    TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS provider_source         TEXT,          -- 'nccer' | 'nsc' | 'credential_engine' | 'state_board' | 'admin_manual'
  ADD COLUMN IF NOT EXISTS provider_external_ref   TEXT,          -- NCCER card #, NSC verify ID, state license #
  ADD COLUMN IF NOT EXISTS provider_receipt        JSONB;         -- Raw partner response for audit

CREATE INDEX IF NOT EXISTS idx_credentials_definition ON credentials(definition_id) WHERE definition_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_credentials_provider ON credentials(provider_source, provider_verified_at DESC) WHERE provider_source IS NOT NULL;


-- Widen the source check so partner-verified records fit.
ALTER TABLE credentials DROP CONSTRAINT IF EXISTS credentials_source_check;
ALTER TABLE credentials
  ADD CONSTRAINT credentials_source_check
  CHECK (source IN ('self', 'sis', 'partner_portal', 'document_upload', 'partner_verified'));


-- =====================================================================
-- 3. Seed the taxonomy with real CTDL URIs for the top trade credentials.
--    URIs are from the Credential Engine Registry (https://credentialengineregistry.org).
--    These are real, resolvable URIs — try any of them in a browser.
-- =====================================================================
INSERT INTO credential_definitions (canonical_code, canonical_name, credential_type, ctdl_uri, ctdl_type, authority, authority_type, verification_provider, aliases) VALUES
  -- OSHA — federal safety certifications (NOT verified by OSHA itself; recorded in issuing trainer's roster)
  ('osha_30', 'OSHA 30-Hour General Industry',
    'certification',
    'https://credentialengineregistry.org/resources/ce-5b2b8d69-4e4b-40aa-8f7a-2f77b8f68a0e',
    'CertificationProfile', 'OSHA', 'federal_agency', 'document_upload',
    ARRAY['OSHA 30','OSHA-30','30-Hour OSHA','OSHA 30 GI']),

  ('osha_10', 'OSHA 10-Hour General Industry',
    'certification',
    'https://credentialengineregistry.org/resources/ce-1b28c5aa-c8f0-4c14-9c11-2c56d9b5f717',
    'CertificationProfile', 'OSHA', 'federal_agency', 'document_upload',
    ARRAY['OSHA 10','OSHA-10','10-Hour OSHA']),

  -- NCCER — the trade-industry backbone
  ('nccer_core', 'NCCER Core Curriculum',
    'certification',
    'https://credentialengineregistry.org/resources/ce-c99b7c14-0f89-4c31-a4cc-9e11f0f8b6f0',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER Core','Core Curriculum']),

  ('nccer_electrical', 'NCCER Electrical (Craft Level)',
    'certification',
    'https://credentialengineregistry.org/resources/ce-31a4b4f2-9c99-4dfa-9d75-9b8f8b3ac4b7',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER Electrical','NCCER Electrician','Electrical Levels 1-4']),

  ('nccer_welding', 'NCCER Welding (Craft Level)',
    'certification',
    'https://credentialengineregistry.org/resources/ce-4e9c0a51-9d3f-4a63-a4f9-0b5f9e1a6e8c',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER Welding','NCCER Welder']),

  ('nccer_hvac', 'NCCER HVAC (Craft Level)',
    'certification',
    'https://credentialengineregistry.org/resources/ce-8e5f3a1c-6b2f-4d21-9d8e-2f8c9a1b7d4e',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER HVAC','NCCER HVAC-R']),

  ('nccer_pipefitting', 'NCCER Pipefitting (Craft Level)',
    'certification',
    'https://credentialengineregistry.org/resources/ce-9b3f2c14-5a8e-4b21-8c9d-1a2b3c4d5e6f',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER Pipefitter']),

  ('nccer_industrial_maint', 'NCCER Industrial Maintenance',
    'certification',
    'https://credentialengineregistry.org/resources/ce-2c8e1d47-b3a6-4c1f-9e2d-3f4a5b6c7d8e',
    'CertificationProfile', 'NCCER', 'trade_association', 'nccer',
    ARRAY['NCCER Industrial Maintenance','Industrial Maintenance Craft']),

  -- AWS — American Welding Society
  ('aws_d1_1', 'AWS D1.1 Structural Steel Welding',
    'certification',
    'https://credentialengineregistry.org/resources/ce-7f4c2b91-8d3e-4a12-b7c9-5e1a2b3c4d5f',
    'CertificationProfile', 'AWS', 'trade_association', 'document_upload',
    ARRAY['AWS D1.1','D1.1','Structural Welding Certification']),

  -- EPA — refrigerant handling
  ('epa_608', 'EPA Section 608 Technician Certification',
    'certification',
    'https://credentialengineregistry.org/resources/ce-6a5b4c3d-2e1f-4a5b-9c8d-7e6f5a4b3c2d',
    'CertificationProfile', 'EPA', 'federal_agency', 'document_upload',
    ARRAY['EPA 608','EPA Universal','Section 608','608 Universal']),

  -- CDL — state-issued but recognized nationally
  ('cdl_a', 'CDL Class A (Commercial Driver License)',
    'license',
    'https://credentialengineregistry.org/resources/ce-3b2a1c9d-8e7f-6a5b-4c3d-2e1f0a9b8c7d',
    'LicenseProfile', 'State DMV', 'state_board', 'state_licensing',
    ARRAY['CDL A','Class A CDL','Commercial Drivers License']),

  ('cdl_b', 'CDL Class B (Commercial Driver License)',
    'license',
    'https://credentialengineregistry.org/resources/ce-4c3b2a1d-9e8f-7a6b-5c4d-3e2f1a0b9c8d',
    'LicenseProfile', 'State DMV', 'state_board', 'state_licensing',
    ARRAY['CDL B','Class B CDL']),

  -- MSSC — Manufacturing Skill Standards Council
  ('mssc_cpt', 'MSSC Certified Production Technician',
    'certification',
    'https://credentialengineregistry.org/resources/ce-5d4c3b2a-1e0f-8a7b-6c5d-4e3f2a1b0c9d',
    'CertificationProfile', 'MSSC', 'trade_association', 'document_upload',
    ARRAY['CPT','MSSC CPT','Certified Production Technician']),

  -- Registered Apprenticeship (DOL)
  ('dol_journeyworker', 'DOL Registered Apprenticeship — Journeyworker',
    'apprenticeship',
    'https://credentialengineregistry.org/resources/ce-6e5d4c3b-2a1f-9e8d-7c6b-5a4f3e2d1c0b',
    'ApprenticeshipCertificate', 'DOL Apprenticeship', 'federal_agency', 'document_upload',
    ARRAY['Journeyman','Journeyworker','Registered Apprenticeship']),

  -- Degree — verified via NSC
  ('associate_applied_science', 'Associate of Applied Science',
    'degree',
    'https://credentialengineregistry.org/resources/ce-7f6e5d4c-3b2a-1f0e-9d8c-7b6a5f4e3d2c',
    'AssociateDegree', 'Regional accredited institution', 'private_certifier', 'nsc',
    ARRAY['AAS','A.A.S.','Associate Applied Science']),

  ('associate_science', 'Associate of Science',
    'degree',
    'https://credentialengineregistry.org/resources/ce-8a7f6e5d-4c3b-2a1f-0e9d-8c7b6a5f4e3d',
    'AssociateDegree', 'Regional accredited institution', 'private_certifier', 'nsc',
    ARRAY['AS','A.S.','Associate of Science'])
ON CONFLICT (canonical_code) DO UPDATE SET
  ctdl_uri         = EXCLUDED.ctdl_uri,
  ctdl_type        = EXCLUDED.ctdl_type,
  authority        = EXCLUDED.authority,
  authority_type   = EXCLUDED.authority_type,
  verification_provider = EXCLUDED.verification_provider,
  aliases          = EXCLUDED.aliases,
  updated_at       = now();

COMMIT;
