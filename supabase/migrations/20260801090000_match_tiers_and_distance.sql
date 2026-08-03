-- Match tiers + distance (additive only).
--
-- match_tier: which relaxation tier admitted this pair to the applicant's
-- matches surface. Tiers change VISIBILITY/grouping only — they never alter
-- base_fit_score or policy_adjusted_score (DECISIONS.md 1.6).
--   'strict'   — all hard gates pass (eligible)
--   'adjacent' — near-fit whose trade is direct/adjacent and geography works
--   'stretch'  — near-fit admitted by a geography/timing/credential stretch
--   'nearby'   — geography passes but the trade is unrelated
--                ("Near you — different trade"); surfaced only when stricter
--                tiers yield too few results (policy_configs §relaxation)
--   NULL       — not surfaced by any tier
--
-- tier_reason: short human sentence for the UI group header/chip.
-- distance_miles: geodesic home → job-city distance when both sides have
-- coordinates; used for honest display and deterministic tie-breaking.

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS match_tier text,
  ADD COLUMN IF NOT EXISTS tier_reason text,
  ADD COLUMN IF NOT EXISTS distance_miles numeric(7,1);

ALTER TABLE public.matches
  DROP CONSTRAINT IF EXISTS matches_match_tier_check;
ALTER TABLE public.matches
  ADD CONSTRAINT matches_match_tier_check
  CHECK (match_tier IS NULL OR match_tier IN ('strict', 'adjacent', 'stretch', 'nearby'));

-- Applicant matches surface: tiered fetch ordered by score with deterministic
-- distance tie-break.
CREATE INDEX IF NOT EXISTS matches_applicant_tier_score_idx
  ON public.matches (applicant_id, match_tier, policy_adjusted_score DESC NULLS LAST)
  WHERE is_visible_to_applicant = TRUE AND match_tier IS NOT NULL;
