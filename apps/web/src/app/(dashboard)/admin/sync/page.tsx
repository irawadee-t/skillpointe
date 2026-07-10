import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import {
  getSyncStatus, getPartnerHealth,
  SyncStatus, PartnerHealthResponse,
} from "@/lib/api/sync";
import { SyncConsole } from "./SyncConsole";

const EMPTY_STATUS: SyncStatus = {
  outbox_unpublished: 0, outbox_total: 0, inbox_total: 0,
  stream_depth: 0, pending: 0, in_sync: true, recent: [],
};

const EMPTY_PARTNERS: PartnerHealthResponse = {
  partners: [], stuck: [], total_backlog: 0, total_events_24h: 0,
};

export default async function SyncPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const [status, partners] = await Promise.all([
    getSyncStatus(session.access_token).catch(() => EMPTY_STATUS),
    getPartnerHealth(session.access_token).catch(() => EMPTY_PARTNERS),
  ]);
  return <SyncConsole initialStatus={status} initialPartners={partners} token={session.access_token} />;
}
