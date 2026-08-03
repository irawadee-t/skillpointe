-- Real undo for employer decisions.
--
-- Store the stage an application was in BEFORE the last employer status
-- change so a shortlist/reject/hire can be reverted faithfully (back to the
-- true previous stage) instead of guessing. Additive only.
--
-- previous_status is written by PATCH /employer/me/applications/{id} on every
-- status change, consumed (and cleared) by
-- POST /employer/me/applications/{id}/revert. NULL on legacy rows — the
-- revert endpoint falls back to 'reviewed' (In review) for those.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS previous_status application_status_enum;

COMMENT ON COLUMN public.applications.previous_status IS
  'Stage before the most recent employer status change. Consumed and cleared by the revert endpoint; NULL = nothing to revert to (falls back to reviewed).';
