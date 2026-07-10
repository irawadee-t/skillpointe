-- Employer self-serve job import workflow.
--
-- Employers can submit batches of jobs (parsed from a career URL, CSV/XLSX,
-- Google Sheet, PDF/DOCX, or manual entry). Batches sit in `job_import_batches`
-- with rows in `job_import_rows` until an admin reviews + approves them, at
-- which point rows publish into public.jobs.
--
-- `notifications` is a unified in-app feed (admins on submission, employers on
-- approval/rejection). Email delivery is stubbed: the dispatcher reads from
-- this table — wire Resend/Postmark later without touching call sites.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE job_import_source_enum AS ENUM (
  'url',          -- career-page URL the employer pasted
  'csv',          -- spreadsheet upload (CSV/XLSX/TSV)
  'sheet',        -- Google Sheet link
  'doc',          -- PDF / DOCX upload
  'manual'        -- one-at-a-time form
);

CREATE TYPE job_import_batch_status_enum AS ENUM (
  'draft',        -- employer is still editing
  'pending',      -- submitted, awaiting admin review
  'approved',     -- admin approved; rows published
  'rejected',     -- admin rejected the batch (with note)
  'published'     -- terminal state once rows live in public.jobs
);

CREATE TYPE job_import_row_status_enum AS ENUM (
  'staged',       -- in the batch, eligible for publish
  'excluded',     -- employer deselected this row pre-submit
  'published',    -- already pushed to public.jobs
  'rejected'      -- admin removed this single row from approval
);

CREATE TYPE notification_kind_enum AS ENUM (
  'job_import_submitted',     -- to admins
  'job_import_approved',      -- to employer
  'job_import_rejected',      -- to employer
  'job_import_partial'        -- to employer (admin approved some, not all)
);

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.job_import_batches (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id     uuid NOT NULL REFERENCES public.employers(id) ON DELETE CASCADE,
  created_by      uuid NOT NULL REFERENCES auth.users(id),
  source          job_import_source_enum NOT NULL,
  source_label    text,                  -- the URL pasted, filename, or "manual"
  platform        text,                  -- workday | greenhouse | lever | successfactors | iCIMS | avature | custom | null
  status          job_import_batch_status_enum NOT NULL DEFAULT 'draft',
  reviewer_id     uuid REFERENCES auth.users(id),   -- admin who actioned this
  reviewer_note   text,
  rows_total      integer NOT NULL DEFAULT 0,
  rows_approved   integer NOT NULL DEFAULT 0,
  rows_rejected   integer NOT NULL DEFAULT 0,
  submitted_at    timestamptz,
  reviewed_at     timestamptz,
  published_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS job_import_batches_employer_idx ON public.job_import_batches(employer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS job_import_batches_status_idx   ON public.job_import_batches(status, submitted_at DESC);

CREATE TABLE IF NOT EXISTS public.job_import_rows (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id               uuid NOT NULL REFERENCES public.job_import_batches(id) ON DELETE CASCADE,
  -- Mirrors the public.jobs columns we care about — same shape so publishing
  -- is a single INSERT mapping, not a translation layer.
  title_raw              text NOT NULL,
  description_raw        text,
  responsibilities_raw   text,
  requirements_raw       text,
  preferred_qualifications_raw text,
  city                   text,
  state                  text,
  country                text NOT NULL DEFAULT 'US',
  work_setting           text,           -- on_site | hybrid | remote | flexible
  travel_requirement     text,
  pay_min                numeric(12,2),
  pay_max                numeric(12,2),
  pay_type               text,
  pay_raw                text,
  experience_level       text,
  posted_date            text,
  job_category           text,
  employment_type        text,
  req_id                 text,
  source_url             text,
  canonical_job_family_id uuid REFERENCES public.canonical_job_families(id),
  status                 job_import_row_status_enum NOT NULL DEFAULT 'staged',
  published_job_id       uuid REFERENCES public.jobs(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS job_import_rows_batch_idx ON public.job_import_rows(batch_id);
-- Uniqueness on (batch_id, source_url) prevents the same listing from being
-- added twice within a batch.
CREATE UNIQUE INDEX IF NOT EXISTS job_import_rows_batch_url_idx
  ON public.job_import_rows(batch_id, source_url)
  WHERE source_url IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.notifications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Targeted by user id OR role broadcast (one of the two is set).
  recipient_user_id  uuid REFERENCES auth.users(id),
  recipient_role     text CHECK (recipient_role IN ('admin','employer','applicant','institution')),
  kind            notification_kind_enum NOT NULL,
  title           text NOT NULL,
  body            text,
  link_href       text,
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  read_at         timestamptz,
  -- Email delivery — stubbed: we record intent here; a future Resend worker
  -- reads `email_pending=true` and clears it.
  email_pending   boolean NOT NULL DEFAULT TRUE,
  email_sent_at   timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notifications_user_idx  ON public.notifications(recipient_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_role_idx  ON public.notifications(recipient_role,    created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_unread_idx ON public.notifications(read_at) WHERE read_at IS NULL;
