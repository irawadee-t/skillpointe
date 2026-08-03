-- Extend the allowed credential sources for the new verification paths:
--   digital_badge   — a verified Credly / Open Badges assertion (registry-grade)
--   background_check — a completed third-party CRA report (Checkr)

ALTER TABLE credentials DROP CONSTRAINT IF EXISTS credentials_source_check;
ALTER TABLE credentials ADD CONSTRAINT credentials_source_check
  CHECK (source = ANY (ARRAY[
    'self', 'sis', 'partner_portal', 'document_upload', 'partner_verified',
    'digital_badge', 'background_check'
  ]));

-- Tracks a Checkr background/verification invitation per credential so a webhook
-- can find the credential to update when the report completes.
CREATE TABLE IF NOT EXISTS checkr_verifications (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  credential_id  UUID REFERENCES credentials(id) ON DELETE CASCADE,
  applicant_id   UUID NOT NULL,
  candidate_id   TEXT,                     -- Checkr candidate id
  invitation_id  TEXT,                     -- Checkr invitation id
  report_id      TEXT,                     -- Checkr report id (set on report.created)
  status         TEXT NOT NULL DEFAULT 'invited',  -- invited | pending | clear | consider | error
  package        TEXT,
  invitation_url TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_checkr_report ON checkr_verifications(report_id);
CREATE INDEX IF NOT EXISTS idx_checkr_candidate ON checkr_verifications(candidate_id);
CREATE INDEX IF NOT EXISTS idx_checkr_applicant ON checkr_verifications(applicant_id, created_at DESC);
