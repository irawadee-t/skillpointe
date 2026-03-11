-- =============================================================
-- Migration: applicant_documents, extracted_applicant_signals,
--            extracted_job_signals
-- Phase 3 — Core Data Model
--
-- Key design principles:
--   - raw LLM output always stored alongside parsed structured output
--   - confidence level tracked on every extraction row
--   - prompt_version tracked for reproducibility and audit
--   - requires_review flag routes low-confidence items to admin queue
--   - embedding column (pgvector) reserved for Phase 7 semantic scoring
--     (nullable — populated during extraction pipeline run)
-- =============================================================


-- ---------------------------------------------------------------
-- applicant_documents
-- Metadata for files uploaded by applicants to Supabase Storage.
-- The actual file lives in Supabase Storage; this row tracks it.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.applicant_documents (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id    UUID        NOT NULL
                              REFERENCES public.applicants (id) ON DELETE CASCADE,
  document_type   public.document_type_enum NOT NULL DEFAULT 'other',
  file_name       TEXT        NOT NULL,
  storage_path    TEXT        NOT NULL UNIQUE, -- Supabase Storage object path
  mime_type       TEXT,
  file_size_bytes BIGINT,

  -- Extraction state
  extracted           BOOLEAN     NOT NULL DEFAULT FALSE,
  extraction_run_at   TIMESTAMPTZ,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_applicant_documents_updated_at
  BEFORE UPDATE ON public.applicant_documents
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.applicant_documents ENABLE ROW LEVEL SECURITY;

-- Applicants can manage their own documents
CREATE POLICY "applicants_manage_own_documents"
  ON public.applicant_documents
  USING (
    EXISTS (
      SELECT 1 FROM public.applicants a
      WHERE a.id = applicant_id AND a.user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS applicant_documents_applicant_id_idx
  ON public.applicant_documents (applicant_id);

CREATE INDEX IF NOT EXISTS applicant_documents_extracted_idx
  ON public.applicant_documents (extracted);


-- ---------------------------------------------------------------
-- extracted_applicant_signals
-- Structured extraction output from LLM processing of applicant
-- documents and profile text.
--
-- One row per extraction run per applicant (or per document if
-- document_id is set).  Multiple runs may exist; the matching
-- engine uses the latest non-overridden row.
--
-- Separation maintained per CLAUDE.md:
--   raw values  → raw_llm_output (JSONB)
--   extracted   → skills_extracted, certifications_extracted, etc.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.extracted_applicant_signals (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id    UUID        NOT NULL
                              REFERENCES public.applicants (id) ON DELETE CASCADE,
  document_id     UUID        REFERENCES public.applicant_documents (id),

  -- Structured extraction outputs (JSONB arrays of objects)
  -- Each item typically: {value, confidence, evidence_snippet}
  skills_extracted            JSONB,  -- [{skill, confidence, evidence_snippet}]
  certifications_extracted    JSONB,  -- [{cert_name, confidence, evidence}]
  desired_job_families        JSONB,  -- [{family_code, family_name, confidence}]
  work_style_signals          JSONB,  -- [{signal, value, confidence}]
  experience_signals          JSONB,  -- [{description, years_estimated, confidence}]
  readiness_signals           JSONB,  -- [{type, value, date_estimated, confidence}]
  location_signals            JSONB,  -- [{city, state, confidence}]
  intent_signals              JSONB,  -- [{intent_type, description, confidence}]

  -- Embedding for semantic scoring (Phase 7+); nullable until populated
  embedding extensions.vector(1536),

  -- LLM provenance
  llm_model       TEXT,
  prompt_version  TEXT,
  raw_llm_output  JSONB,              -- full raw LLM response for audit

  -- Confidence and review
  confidence_level  public.confidence_level_enum,
  requires_review   BOOLEAN     NOT NULL DEFAULT FALSE,
  review_status     public.review_status_enum NOT NULL DEFAULT 'pending',
  reviewed_by       UUID        REFERENCES auth.users (id),
  reviewed_at       TIMESTAMPTZ,
  reviewer_notes    TEXT,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_extracted_applicant_signals_updated_at
  BEFORE UPDATE ON public.extracted_applicant_signals
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.extracted_applicant_signals ENABLE ROW LEVEL SECURITY;

-- Applicants can read their own signals (so they can see their profile extraction)
CREATE POLICY "applicants_read_own_signals"
  ON public.extracted_applicant_signals FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.applicants a
      WHERE a.id = applicant_id AND a.user_id = auth.uid()
    )
  );

-- Service-role handles all writes and admin reads

CREATE INDEX IF NOT EXISTS extracted_applicant_signals_applicant_id_idx
  ON public.extracted_applicant_signals (applicant_id);

CREATE INDEX IF NOT EXISTS extracted_applicant_signals_requires_review_idx
  ON public.extracted_applicant_signals (requires_review)
  WHERE requires_review = TRUE;

CREATE INDEX IF NOT EXISTS extracted_applicant_signals_review_status_idx
  ON public.extracted_applicant_signals (review_status);

-- ivfflat index for approximate nearest-neighbour search (Phase 7+)
-- Lists = 100 is a reasonable default; tune after data volume is known.
-- Commented out until embedding column is populated in production.
-- CREATE INDEX extracted_applicant_signals_embedding_idx
--   ON public.extracted_applicant_signals
--   USING ivfflat (embedding extensions.vector_cosine_ops) WITH (lists = 100);


-- ---------------------------------------------------------------
-- extracted_job_signals
-- Structured extraction output from LLM processing of job postings.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.extracted_job_signals (
  id      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id  UUID    NOT NULL
                  REFERENCES public.jobs (id) ON DELETE CASCADE,

  -- Structured extraction outputs
  required_skills             JSONB,  -- [{skill, confidence, evidence}]
  preferred_skills            JSONB,
  required_credentials        JSONB,  -- [{credential, confidence}]
  preferred_credentials       JSONB,
  job_family_signals          JSONB,  -- [{family_code, family_name, confidence}]
  experience_signals          JSONB,  -- [{level, years, confidence}]
  work_style_signals          JSONB,
  physical_requirement_signals JSONB,
  geography_signals           JSONB,  -- [{city, state, work_setting, confidence}]

  -- Embedding for semantic scoring (Phase 7+)
  embedding extensions.vector(1536),

  -- LLM provenance
  llm_model       TEXT,
  prompt_version  TEXT,
  raw_llm_output  JSONB,

  -- Confidence and review
  confidence_level  public.confidence_level_enum,
  requires_review   BOOLEAN     NOT NULL DEFAULT FALSE,
  review_status     public.review_status_enum NOT NULL DEFAULT 'pending',
  reviewed_by       UUID        REFERENCES auth.users (id),
  reviewed_at       TIMESTAMPTZ,
  reviewer_notes    TEXT,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_extracted_job_signals_updated_at
  BEFORE UPDATE ON public.extracted_job_signals
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.extracted_job_signals ENABLE ROW LEVEL SECURITY;

-- Employer contacts can read signals for their own jobs
CREATE POLICY "employer_contacts_read_own_job_signals"
  ON public.extracted_job_signals FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.jobs j
      JOIN public.employer_contacts ec ON ec.employer_id = j.employer_id
      WHERE j.id = job_id AND ec.user_id = auth.uid()
    )
  );

-- Service-role handles all writes and admin reads

CREATE INDEX IF NOT EXISTS extracted_job_signals_job_id_idx
  ON public.extracted_job_signals (job_id);

CREATE INDEX IF NOT EXISTS extracted_job_signals_requires_review_idx
  ON public.extracted_job_signals (requires_review)
  WHERE requires_review = TRUE;
