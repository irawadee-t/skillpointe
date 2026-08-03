-- Perf: covering index for per-applicant eligibility rollups on matches.
--
-- The admin applicant directory (GET /admin/applicants) counts eligible /
-- near_fit matches per applicant. At current scale (130k+ matches rows) the
-- existing matches_applicant_id_idx forces a heap fetch per match row
-- (~7000 heap blocks for one page of 50 applicants — EXPLAIN ANALYZE showed
-- ~104ms). A composite (applicant_id, eligibility_status) index makes those
-- rollups index-only scans (~3ms measured on the same page).
--
-- Unlike matches_applicant_elig_score_idx this one is NOT partial on
-- is_visible_to_applicant, so admin-side rollups (which count all matches
-- regardless of visibility) can use it.
CREATE INDEX IF NOT EXISTS matches_applicant_elig_idx
    ON public.matches (applicant_id, eligibility_status);
