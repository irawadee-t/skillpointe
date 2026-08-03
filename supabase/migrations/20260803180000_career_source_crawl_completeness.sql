-- Career-source crawl completeness + removal blast-radius guard. All additive.
--
-- Removal detection (a posting vanishing from a listing -> row stale -> live
-- job deactivated) was previously driven by ANY successful listing pull, even
-- one that only saw the first page. A partial listing therefore read as "every
-- posting below the fold was removed" and mass-deactivated the catalog.
--
-- 1. career_source_pulls.listing_complete — did this pull observe the WHOLE
--    listing (paginated to the end / full platform result set, no cap hit)?
--    Only a complete crawl may accrue misses or stale rows. NULL for pulls
--    that never crawled a listing (blocked / errored / 304 short-circuit).
--
-- 2. career_source_pulls.removal_detection — what the pull actually did about
--    removals, so the sync timeline can say it out loud:
--      applied             — complete crawl, removals processed normally
--      skipped_incomplete  — partial crawl, nothing staled
--      held_for_review     — complete crawl, but the removal set exceeded the
--                            blast-radius threshold; nothing staled, admin
--                            review queued
--      not_applicable      — no listing diff happened (304, blocked, error)
--
-- 3. employer_career_sources.needs_attention — a source parked for a human.
--    Set when a sync is held by the blast-radius guard; cleared by the next
--    sync that completes cleanly.

ALTER TABLE public.career_source_pulls
    ADD COLUMN IF NOT EXISTS listing_complete boolean,
    ADD COLUMN IF NOT EXISTS removal_detection text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'career_source_pulls_removal_detection_check'
    ) THEN
        ALTER TABLE public.career_source_pulls
            ADD CONSTRAINT career_source_pulls_removal_detection_check
            CHECK (removal_detection IS NULL OR removal_detection IN
                   ('applied', 'skipped_incomplete', 'held_for_review', 'not_applicable'));
    END IF;
END $$;

COMMENT ON COLUMN public.career_source_pulls.listing_complete IS
    'TRUE only when the pull walked the listing to its end with no cap or page '
    'bound hit. Removal detection runs on complete crawls only.';

ALTER TABLE public.employer_career_sources
    ADD COLUMN IF NOT EXISTS needs_attention boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS attention_reason text,
    ADD COLUMN IF NOT EXISTS attention_at timestamptz;

CREATE INDEX IF NOT EXISTS employer_career_sources_attention_idx
    ON public.employer_career_sources (attention_at DESC) WHERE needs_attention;

COMMENT ON COLUMN public.employer_career_sources.needs_attention IS
    'A sync was held for a human decision (blast-radius guard). The next clean '
    'complete sync clears it.';
