-- Production-readiness audit (cross-role propagation):
--
-- 1) notify() call sites emit six kinds that were never added to
--    notification_kind_enum, so every one of those inserts fails with
--    InvalidTextRepresentationError (verified live):
--      - worker/scheduler.py     -> interview_reminder_24h / interview_reminder_1h
--                                   / interview_followup
--      - routers/account.py      -> account_recovery_ticket /
--                                   account_recovery_resolved /
--                                   account_deletion_scheduled
--    Same failure mode (and same fix) as 20260801120001. Additive only.
--
-- 2) New kinds for status changes that previously propagated silently
--    (employer decision -> applicant, withdraw -> employer, DM -> tray).
--
-- 3) The frontend subscribes to postgres_changes on public.notifications
--    (NotificationTray) and public.direct_messages (MessageThread, inboxes),
--    but the supabase_realtime publication contained ZERO tables — every
--    subscription was dead and surfaces fell back to their poll intervals.
--    Enrolling a table in realtime requires subscribers to pass RLS, and
--    notifications had RLS DISABLED (any authenticated client could read
--    every user's notifications through PostgREST) while direct_messages had
--    RLS enabled with no policies. Fix both, then add them to the publication.

-- 1 + 2: enum values -------------------------------------------------------
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_reminder_24h';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_reminder_1h';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'interview_followup';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'account_recovery_ticket';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'account_recovery_resolved';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'account_deletion_scheduled';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_shortlisted';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_rejected';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_hired';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'application_withdrawn';
ALTER TYPE notification_kind_enum ADD VALUE IF NOT EXISTS 'dm_received';

-- 3a: notifications — close the PostgREST leak and let owners subscribe ----
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS notifications_select_own ON public.notifications;
CREATE POLICY notifications_select_own ON public.notifications
  FOR SELECT TO authenticated
  USING (
    recipient_user_id = auth.uid()
    OR (
      recipient_role IS NOT NULL
      AND recipient_role = (
        SELECT role::text FROM public.user_profiles WHERE user_id = auth.uid()
      )
    )
  );
-- Writes stay service-role only (no INSERT/UPDATE/DELETE policies).

-- 3b: direct_messages — participants may read their conversations ----------
DROP POLICY IF EXISTS direct_messages_select_participant ON public.direct_messages;
CREATE POLICY direct_messages_select_participant ON public.direct_messages
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1
        FROM public.conversations c
       WHERE c.id = direct_messages.conversation_id
         AND (
           c.applicant_id IN (SELECT id FROM public.applicants WHERE user_id = auth.uid())
           OR c.employer_id IN (SELECT employer_id FROM public.employer_contacts WHERE user_id = auth.uid())
         )
    )
  );

-- 3c: enroll both tables in the realtime publication ------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
     WHERE pubname = 'supabase_realtime'
       AND schemaname = 'public' AND tablename = 'notifications'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.notifications;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
     WHERE pubname = 'supabase_realtime'
       AND schemaname = 'public' AND tablename = 'direct_messages'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.direct_messages;
  END IF;
END $$;
