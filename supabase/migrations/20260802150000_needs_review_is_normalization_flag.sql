-- credentials.needs_review is the TAXONOMY-NORMALIZATION flag: it feeds the
-- admin credentials "Needs review" queue and the sidebar badge, and means
-- "the free-form name did not confidently map to the canonical registry".
--
-- Historically the document-upload / doc-verify / badge-verify flows also
-- flipped this flag when a document needed a human look, which put
-- perfectly-normalized credentials (exact alias match, 100% confidence) into
-- the normalization queue. Those flows now route review work exclusively
-- through review_queue_items (item_type 'credential_ambiguity' → /admin/review)
-- and no longer touch needs_review.
--
-- Backfill: clear the flag wherever the normalization itself is confident
-- (canonical mapping present at/above the 0.82 is_confident threshold —
-- exact/alias matches score 1.0). Genuinely uncertain mappings (partial,
-- fuzzy, or no match) keep the flag and stay in the queue.
UPDATE public.credentials
   SET needs_review = false,
       updated_at = now()
 WHERE needs_review = true
   AND canonical_code IS NOT NULL
   AND normalization_confidence >= 0.82;
