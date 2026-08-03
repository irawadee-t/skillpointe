-- Cache of parsed job display sections (see apps/api/app/skilled_pro/job_sections.py).
-- Additive only: jobs table is untouched. content_hash is the sha256 of the raw
-- text fields so a re-scrape invalidates the cached parse automatically.
CREATE TABLE IF NOT EXISTS job_display_sections (
  job_id UUID PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  sections JSONB NOT NULL,
  source TEXT NOT NULL DEFAULT 'parser',
  content_hash TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
