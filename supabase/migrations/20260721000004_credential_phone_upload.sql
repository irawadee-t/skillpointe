-- Credential document upload via phone handoff (QR code flow).
-- Single-use, short-lived tokens that let an unauthenticated phone browser
-- upload a photo of a certificate for a specific credential. Only the SHA-256
-- of the token is stored; the raw token lives solely in the QR-code URL.

CREATE TABLE IF NOT EXISTS credential_upload_tokens (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  credential_id UUID NOT NULL REFERENCES credentials(id) ON DELETE CASCADE,
  applicant_id  UUID NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,
  used_at       TIMESTAMPTZ,
  expires_at    TIMESTAMPTZ NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS credential_upload_tokens_credential_idx
  ON credential_upload_tokens (credential_id, created_at DESC);

ALTER TABLE credential_upload_tokens ENABLE ROW LEVEL SECURITY;
-- Service-role only: all access goes through FastAPI.

-- Private storage bucket for uploaded credential documents (photos/PDFs of
-- certificates and licenses). Written by the API with the service-role key;
-- no public read (public = false), no anon policies.
INSERT INTO storage.buckets (id, name, public)
VALUES ('documents', 'documents', false)
ON CONFLICT (id) DO NOTHING;
