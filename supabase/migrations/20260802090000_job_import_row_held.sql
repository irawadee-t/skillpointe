-- Broken-link hold becomes a first-class row state.
--
-- Previously a row whose apply link failed validation was silently skipped on
-- a blanket batch approve and stayed 'staged' — invisible to both the admin
-- queue (batch left 'approved') and the employer. 'held' makes the outcome
-- explicit: the row is parked pending a working link or an explicit admin
-- override, and both sides can see and count it.
ALTER TYPE public.job_import_row_status_enum ADD VALUE IF NOT EXISTS 'held';
