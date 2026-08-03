-- Production-readiness structural fixes (interview cancel + notification
-- timing). Additive only.
--
-- 1) 'interview_cancelled' — an employer can now cancel a booked (accepted)
--    or proposed interview slot; the applicant hears about it honestly.
-- 2) 'credential_review_dismissed' — when admin dismisses a document-review
--    item, the applicant's credential returns to self-reported WITH a
--    notification instead of sitting "in review" forever.
-- 3) notifications.deliver_after — a quiet window for the applicant-facing
--    rejection notification. The row is written at decision time but stays
--    invisible to the recipient until deliver_after passes; a revert inside
--    the window deletes the pending row so an undone rejection never pings
--    the applicant. NULL = deliver immediately (every existing row).

ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_cancelled';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'credential_review_dismissed';

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS deliver_after timestamptz;

-- Cheap lookup for "pending, not yet deliverable" rows (revert cancellation
-- + the delivery filter). Partial: almost every row has NULL deliver_after.
CREATE INDEX IF NOT EXISTS notifications_deliver_after_idx
  ON public.notifications (deliver_after)
  WHERE deliver_after IS NOT NULL;
