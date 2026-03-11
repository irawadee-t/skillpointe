-- =============================================================
-- Migration: matches, match_dimension_scores, saved_jobs
-- Phase 3 — Core Data Model
--
-- The matches table is the core output of the ranking pipeline.
-- Key design principles:
--
--   base_fit_score      ← deterministic estimate of compatibility
--   policy_adjusted_score ← separate, modified for SkillPointe priorities
--   These MUST remain separate columns (DECISIONS.md 1.6, 2.2).
--
--   match_dimension_scores stores per-dimension score breakdown for
--   transparency, explainability, and admin audit.
--
--   No batch-matching columns; scores are continuously recomputed.
-- =============================================================


-- ---------------------------------------------------------------
-- matches
-- One row per (applicant, job) pair.
-- Upserted on each scoring run (UNIQUE constraint on the pair).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.matches (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id  UUID    NOT NULL REFERENCES public.applicants (id) ON DELETE CASCADE,
  job_id        UUID    NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,

  CONSTRAINT matches_applicant_job_unique UNIQUE (applicant_id, job_id),

  -- ---- Stage 1: Hard eligibility gate outputs ----
  eligibility_status    public.eligibility_status_enum NOT NULL DEFAULT 'near_fit',
  hard_gate_cap         NUMERIC(4,3)  NOT NULL DEFAULT 0.75,
    -- 1.0 = eligible, 0.75 = near_fit, 0.35 = ineligible
  hard_gate_failures    JSONB,
    -- [{gate_name, reason, severity}] — transparent failure list
  hard_gate_rationale   JSONB,
    -- free-form evidence for each gate evaluation

  -- ---- Stage 2A: Structured score ----
  weighted_structured_score NUMERIC(6,2),
    -- sum(weight_i * score_i) / 100, range 0–100

  -- ---- Stage 2B: Semantic score ----
  semantic_score  NUMERIC(6,2),
    -- 0.4*skills_overlap + 0.3*job_family_similarity +
    -- 0.2*experience_text_relevance + 0.1*intent_alignment

  -- ---- Stage 2: Base fit (combined, capped) ----
  base_fit_score  NUMERIC(6,2),
    -- hard_gate_cap * (weighted_structured_score * 0.75 + semantic_score * 0.25)

  -- ---- Stage 3: Policy reranking ----
  policy_modifiers      JSONB,
    -- [{policy_name, modifier_value, reason}]
  policy_adjusted_score NUMERIC(6,2),
    -- clamp(base_fit_score + sum(policy_modifiers), 0, 100)

  -- ---- UI label ----
  match_label public.match_label_enum,

  -- ---- Explanation outputs (displayed in UI) ----
  top_strengths         JSONB,   -- list of strength descriptions
  top_gaps              JSONB,   -- list of gap descriptions
  required_missing_items JSONB,  -- mandatory items that are absent
  recommended_next_step TEXT,    -- short suggested action

  -- ---- Confidence ----
  confidence_level  public.confidence_level_enum,
  requires_review   BOOLEAN NOT NULL DEFAULT FALSE,

  -- ---- Scoring run metadata ----
  scoring_run_id    UUID,
  scoring_run_at    TIMESTAMPTZ,
  policy_version    TEXT,   -- which policy_config version was used

  -- ---- Admin review ----
  review_status   public.review_status_enum NOT NULL DEFAULT 'pending',
  reviewed_by     UUID        REFERENCES auth.users (id),
  reviewed_at     TIMESTAMPTZ,
  reviewer_notes  TEXT,

  -- ---- Visibility control (policy-driven) ----
  is_visible_to_applicant BOOLEAN NOT NULL DEFAULT TRUE,
  is_visible_to_employer  BOOLEAN NOT NULL DEFAULT TRUE,

  -- Audit
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_matches_updated_at
  BEFORE UPDATE ON public.matches
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.matches ENABLE ROW LEVEL SECURITY;

-- Applicants see only their own matches (and only visible ones)
CREATE POLICY "applicants_read_own_matches"
  ON public.matches FOR SELECT
  USING (
    is_visible_to_applicant = TRUE
    AND EXISTS (
      SELECT 1 FROM public.applicants a
      WHERE a.id = applicant_id AND a.user_id = auth.uid()
    )
  );

-- Employers see matches for their own jobs only (job-scoped visibility)
CREATE POLICY "employers_read_own_job_matches"
  ON public.matches FOR SELECT
  USING (
    is_visible_to_employer = TRUE
    AND EXISTS (
      SELECT 1 FROM public.jobs j
      JOIN public.employer_contacts ec ON ec.employer_id = j.employer_id
      WHERE j.id = job_id AND ec.user_id = auth.uid()
    )
  );

-- Service-role handles all writes and admin reads

CREATE INDEX IF NOT EXISTS matches_applicant_id_idx
  ON public.matches (applicant_id);

CREATE INDEX IF NOT EXISTS matches_job_id_idx
  ON public.matches (job_id);

CREATE INDEX IF NOT EXISTS matches_policy_adjusted_score_idx
  ON public.matches (policy_adjusted_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS matches_eligibility_status_idx
  ON public.matches (eligibility_status);

CREATE INDEX IF NOT EXISTS matches_requires_review_idx
  ON public.matches (requires_review)
  WHERE requires_review = TRUE;

-- Composite: used by applicant ranked-jobs query
CREATE INDEX IF NOT EXISTS matches_applicant_score_idx
  ON public.matches (applicant_id, policy_adjusted_score DESC NULLS LAST)
  WHERE is_visible_to_applicant = TRUE;

-- Composite: used by employer ranked-applicants-per-job query
CREATE INDEX IF NOT EXISTS matches_job_score_idx
  ON public.matches (job_id, policy_adjusted_score DESC NULLS LAST)
  WHERE is_visible_to_employer = TRUE;


-- ---------------------------------------------------------------
-- match_dimension_scores
-- Per-dimension breakdown of the structured score for a match.
-- One row per (match, dimension).  Used for explainability and audit.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.match_dimension_scores (
  id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id        UUID    NOT NULL REFERENCES public.matches (id) ON DELETE CASCADE,

  -- Dimension name maps to SCORING_CONFIG.yaml structured_score.weights keys
  dimension       TEXT    NOT NULL,
    -- e.g. 'trade_program_alignment', 'geography_alignment', ...

  -- Weight and score
  weight          NUMERIC(6,2)  NOT NULL,  -- configured weight (0–100)
  raw_score       NUMERIC(6,2)  NOT NULL,  -- 0–100 score for this dimension
  weighted_score  NUMERIC(8,4)  NOT NULL,  -- weight * raw_score / 100

  -- Explanation
  rationale       TEXT,   -- short human-readable explanation

  -- Null-handling metadata
  null_handling_applied   BOOLEAN NOT NULL DEFAULT FALSE,
  null_handling_default   NUMERIC(6,2),  -- default value used if null

  CONSTRAINT match_dimension_scores_unique UNIQUE (match_id, dimension),

  -- Audit
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.match_dimension_scores ENABLE ROW LEVEL SECURITY;

-- Applicants can read dimension breakdowns for their own matches
CREATE POLICY "applicants_read_own_dimension_scores"
  ON public.match_dimension_scores FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.matches m
      JOIN public.applicants a ON a.id = m.applicant_id
      WHERE m.id = match_id
        AND a.user_id = auth.uid()
        AND m.is_visible_to_applicant = TRUE
    )
  );

-- Employers can read dimension scores for matches on their own jobs
CREATE POLICY "employers_read_job_dimension_scores"
  ON public.match_dimension_scores FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.matches m
      JOIN public.jobs j ON j.id = m.job_id
      JOIN public.employer_contacts ec ON ec.employer_id = j.employer_id
      WHERE m.id = match_id AND ec.user_id = auth.uid()
        AND m.is_visible_to_employer = TRUE
    )
  );

CREATE INDEX IF NOT EXISTS match_dimension_scores_match_id_idx
  ON public.match_dimension_scores (match_id);


-- ---------------------------------------------------------------
-- saved_jobs
-- Applicant interest / saved-job actions.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.saved_jobs (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id  UUID    NOT NULL REFERENCES public.applicants (id) ON DELETE CASCADE,
  job_id        UUID    NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,

  CONSTRAINT saved_jobs_applicant_job_unique UNIQUE (applicant_id, job_id),

  interest_level  TEXT    NOT NULL DEFAULT 'saved',
    -- 'saved', 'applied', 'not_interested'
  notes           TEXT,

  saved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_saved_jobs_updated_at
  BEFORE UPDATE ON public.saved_jobs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.saved_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "applicants_manage_own_saved_jobs"
  ON public.saved_jobs
  USING (
    EXISTS (
      SELECT 1 FROM public.applicants a
      WHERE a.id = applicant_id AND a.user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS saved_jobs_applicant_id_idx
  ON public.saved_jobs (applicant_id);

CREATE INDEX IF NOT EXISTS saved_jobs_job_id_idx
  ON public.saved_jobs (job_id);
