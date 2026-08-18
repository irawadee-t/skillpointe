-- O*NET-SOC occupation mapping columns on jobs.
--
-- External ground truth for the hand-rolled canonical family taxonomy:
-- every active job title is mapped deterministically to an O*NET-SOC
-- occupation code by scripts/map_onet.py (title-string matching against
-- the O*NET database text distribution — Occupation Data + Alternate
-- Titles). Schema only; the data itself is populated by running
--   python scripts/map_onet.py --write-db
-- and the audit artifacts live under audit/onet/.
--
-- onet_soc_code   : O*NET-SOC 2019 code, e.g. '51-4041.00' (NULL = unmapped)
-- onet_match_tier : how the code was found — 'exact' | 'segment' | 'fuzzy'
--                   | 'unmapped' (lower tiers are lower confidence)

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS onet_soc_code text,
  ADD COLUMN IF NOT EXISTS onet_match_tier text;

COMMENT ON COLUMN public.jobs.onet_soc_code IS
  'O*NET-SOC occupation code mapped deterministically from title_raw by scripts/map_onet.py (NULL = unmapped)';
COMMENT ON COLUMN public.jobs.onet_match_tier IS
  'Match tier from scripts/map_onet.py: exact | segment | fuzzy | unmapped';
