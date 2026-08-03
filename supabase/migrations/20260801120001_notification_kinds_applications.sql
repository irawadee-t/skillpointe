-- The transactions stack (20260630000024) documented an extended set of
-- notification `kind` strings but never added them to notification_kind_enum —
-- so every notify() call for an application/interview/credential event failed
-- with InvalidTextRepresentationError and 500'd the calling endpoint.
--
-- Additive only: ALTER TYPE ... ADD VALUE IF NOT EXISTS.

ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_submitted';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_viewed';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_proposed';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_accepted';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_declined';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'offer_received';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'credential_verified';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'credential_needs_review';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'sla_dormant_application';
