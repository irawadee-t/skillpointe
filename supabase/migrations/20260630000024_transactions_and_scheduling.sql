-- Transactions & scheduling — closes the loop after match:
--   • screening questions on jobs (employer-configured knockouts)
--   • applications (in-platform, with resume snapshot + screening answers)
--   • interview availability + slot proposals
--   • account-change requests (email/phone/SKILLED ID recovery)
--   • notification kind extensions
--
-- Additive only.

BEGIN;

-- =====================================================================
-- 1. Screening questions on a job
-- =====================================================================
CREATE TYPE screening_question_kind_enum AS ENUM ('yes_no', 'multiple_choice', 'short_text');

CREATE TABLE IF NOT EXISTS job_screening_questions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id            UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  position          SMALLINT NOT NULL DEFAULT 0,          -- 0..4 render order
  kind              screening_question_kind_enum NOT NULL,
  prompt            TEXT NOT NULL,                        -- "Do you have a valid CDL Class A?"
  options           TEXT[] NOT NULL DEFAULT '{}',         -- for multiple_choice
  required_answer   TEXT,                                 -- knockout — if applicant's answer != this, disqualify
  is_knockout       BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_screening_by_job ON job_screening_questions(job_id, position);


-- =====================================================================
-- 2. Applications — real in-platform apply, not just "interested"
-- =====================================================================
CREATE TYPE application_status_enum AS ENUM (
  'submitted',    -- applicant submitted the form
  'reviewed',    -- employer viewed
  'shortlisted', -- employer marked as promising
  'interviewing',-- interview scheduled
  'offered',
  'hired',
  'rejected',
  'withdrawn'    -- applicant withdrew
);

CREATE TABLE IF NOT EXISTS applications (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id     UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
  job_id           UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  employer_id      UUID NOT NULL REFERENCES employers(id) ON DELETE CASCADE,
  match_id         UUID REFERENCES matches(id) ON DELETE SET NULL,

  status           application_status_enum NOT NULL DEFAULT 'submitted',

  -- Snapshot the applicant's profile at time of apply so employers see a stable view.
  resume_snapshot  JSONB NOT NULL DEFAULT '{}'::jsonb,      -- { first_name, last_name, phone, email, city, state, experience_raw, career_goals_raw, skills:[], certifications:[], years_experience }
  screening_answers JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{ question_id, prompt, answer, knockout_pass:bool }]
  knockout_failed  BOOLEAN NOT NULL DEFAULT false,          -- convenience flag

  cover_note       TEXT,                                    -- optional message to employer

  submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  employer_viewed_at TIMESTAMPTZ,                            -- first view — used for SLA tracking
  reviewed_at      TIMESTAMPTZ,                              -- moved past 'submitted'
  decision_at      TIMESTAMPTZ,                              -- hired/rejected/withdrawn timestamp
  decision_note    TEXT,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (applicant_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_apps_employer ON applications(employer_id, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_job      ON applications(job_id,      status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_applicant ON applications(applicant_id, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_sla       ON applications(employer_viewed_at, submitted_at)
  WHERE employer_viewed_at IS NULL;


-- =====================================================================
-- 3. Interview scheduling
-- =====================================================================
CREATE TABLE IF NOT EXISTS interview_availability (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employer_id   UUID NOT NULL REFERENCES employers(id) ON DELETE CASCADE,
  weekday       SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),  -- 0 = Sunday
  start_time    TIME NOT NULL,
  end_time      TIME NOT NULL,
  timezone      TEXT NOT NULL DEFAULT 'America/New_York',
  active        BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (employer_id, weekday, start_time, end_time)
);


CREATE TYPE interview_slot_status_enum AS ENUM (
  'proposed',
  'accepted',
  'declined',
  'cancelled',
  'completed'
);

CREATE TABLE IF NOT EXISTS interview_slots (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  proposed_by    UUID NOT NULL,                              -- employer_contact.user_id
  start_at       TIMESTAMPTZ NOT NULL,
  end_at         TIMESTAMPTZ NOT NULL,
  status         interview_slot_status_enum NOT NULL DEFAULT 'proposed',
  location       TEXT,                                       -- "On-site: 500 Southwire Rd, Carrollton, GA"
  meeting_url    TEXT,                                       -- Zoom / Teams / phone
  notes          TEXT,
  accepted_at    TIMESTAMPTZ,
  declined_at    TIMESTAMPTZ,
  cancelled_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_slots_by_application ON interview_slots(application_id, status);
CREATE INDEX IF NOT EXISTS idx_slots_by_start       ON interview_slots(start_at) WHERE status = 'accepted';


-- =====================================================================
-- 4. Account change requests (email / phone / SKILLED ID recovery)
-- =====================================================================
CREATE TYPE account_change_kind_enum AS ENUM (
  'email_change',
  'phone_change',
  'skilled_id_recovery'
);

CREATE TYPE account_change_status_enum AS ENUM (
  'pending_confirmation',
  'confirmed',
  'expired',
  'cancelled',
  'admin_review',           -- SKILLED ID recovery kicked to admin
  'admin_resolved'
);

CREATE TABLE IF NOT EXISTS account_change_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,                    -- auth.users.id
  kind              account_change_kind_enum NOT NULL,
  new_value         TEXT,                              -- new email or phone (null for SKILLED ID recovery)
  token_hash        TEXT,                              -- SHA256 of confirmation code — never store raw
  status            account_change_status_enum NOT NULL DEFAULT 'pending_confirmation',
  reason            TEXT,                              -- for SKILLED ID recovery: applicant's explanation
  reviewer_user_id  UUID,                              -- admin who resolved recovery
  reviewer_note     TEXT,
  ip_address        TEXT,
  user_agent        TEXT,
  expires_at        TIMESTAMPTZ,
  confirmed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_acr_user ON account_change_requests(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_acr_admin_review ON account_change_requests(status)
  WHERE status = 'admin_review';


-- =====================================================================
-- 5. Notification kinds — the enum already exists (from 20260627000020),
--    but is used with a check constraint we can leave alone. We'll simply
--    document the extended set of `kind` strings the app now writes:
--      job_import_submitted | approved | rejected | partial
--      application_submitted   (employer)
--      application_viewed      (applicant)
--      interview_proposed      (applicant)
--      interview_accepted      (employer)
--      interview_declined      (employer)
--      offer_received          (applicant)
--      credential_verified     (applicant)
--      credential_needs_review (applicant)
--      sla_dormant_application (admin)
-- =====================================================================
-- Add index for fast unread lookup per user
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
  ON notifications (recipient_user_id, created_at DESC)
  WHERE read_at IS NULL;

COMMIT;
