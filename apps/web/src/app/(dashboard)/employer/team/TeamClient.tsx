"use client";

import { useEffect, useState } from "react";
import { Loader2, Mail, UserPlus } from "lucide-react";

import {
  OrgRole, TeamInvite, TeamOverview,
  createTeamInvite, getTeamOverview, resendTeamInvite, revokeTeamInvite,
} from "@/lib/api/team";
import { MonoLabel, PageHeader, useToast } from "@/components/ui";
import { formatDateShort } from "@/lib/format";
import { formatRelative } from "@/lib/time";

const ROLE_LABEL: Record<OrgRole, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

const ROLE_HELP: Record<OrgRole, string> = {
  member: "Works applications, schedules interviews, messages candidates.",
  admin: "Everything a member does, plus inviting and removing teammates.",
  owner: "Full control of the workspace, including other owners.",
};

function RoleChip({ role }: { role: OrgRole }) {
  return (
    <span className="inline-flex items-center rounded-full border border-hairline bg-white px-2.5 py-0.5 text-micro font-medium text-slate">
      {ROLE_LABEL[role] ?? role}
    </span>
  );
}

export function TeamClient({ token }: { token: string }) {
  const toast = useToast();
  const [data, setData] = useState<TeamOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Invite form
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const [title, setTitle] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);

  async function load() {
    try {
      setData(await getTeamOverview(token));
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load your team.");
    }
  }
  useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submitInvite(e: React.FormEvent) {
    e.preventDefault();
    setFormErr(null);
    if (!email.trim()) { setFormErr("Add the teammate's email."); return; }
    setBusy("invite");
    try {
      const inv: TeamInvite = await createTeamInvite(token, {
        email: email.trim(),
        role,
        ...(title.trim() ? { title: title.trim() } : {}),
      });
      if (inv.email_sent) {
        toast.success(`Invite emailed to ${inv.email}. It expires in 7 days.`);
      } else {
        // Honest: the row exists but the email didn't go out.
        toast.error(`Invite created, but the email to ${inv.email} could not be sent. Use Resend.`);
      }
      setEmail(""); setTitle(""); setRole("member"); setInviteOpen(false);
      await load();
    } catch (e: unknown) {
      setFormErr(e instanceof Error ? e.message : "Could not send the invite.");
    } finally {
      setBusy(null);
    }
  }

  async function doResend(inv: TeamInvite) {
    setBusy(`resend-${inv.id}`);
    try {
      const fresh = await resendTeamInvite(token, inv.id);
      if (fresh.email_sent) toast.success(`Invite re-sent to ${inv.email}. The old link no longer works.`);
      else toast.error(`Could not send the email to ${inv.email}. Try again in a moment.`);
      await load();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not resend.");
    } finally {
      setBusy(null);
    }
  }

  async function doRevoke(inv: TeamInvite) {
    setBusy(`revoke-${inv.id}`);
    try {
      await revokeTeamInvite(token, inv.id);
      toast.info(`Invite for ${inv.email} revoked. The link no longer works.`);
      await load();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not revoke.");
    } finally {
      setBusy(null);
    }
  }

  if (err) {
    return (
      <main className="page-shell">
        <PageHeader title="Team" lead={err} />
      </main>
    );
  }
  if (!data) {
    return (
      <main className="page-shell">
        <div className="flex items-center gap-2 py-16 text-body text-slate">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading your team…
        </div>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <div className="space-y-10">
        <PageHeader
          eyebrow={data.company_name}
          title="Team"
          lead={
            data.can_manage
              ? "Everyone with access to this workspace. Invites go out by email and expire after 7 days."
              : "Everyone with access to this workspace. Only owners and admins can invite or revoke."
          }
          actions={
            data.can_manage ? (
              <button
                onClick={() => setInviteOpen((v) => !v)}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                <UserPlus className="h-4 w-4" /> Invite a member
              </button>
            ) : undefined
          }
        />

        {inviteOpen && data.can_manage && (
          <form
            onSubmit={submitInvite}
            className="rounded-[14px] border border-hairline bg-white p-6"
          >
            <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Invite a member</h2>
            <p className="mt-1 text-caption text-slate">
              They get an email with a link to create their account and land in this workspace.
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <label className="block sm:col-span-1">
                <MonoLabel className="mb-1 block">Email</MonoLabel>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  className="input-cohere text-caption"
                  autoFocus
                />
              </label>
              <label className="block sm:col-span-1">
                <MonoLabel className="mb-1 block">Role</MonoLabel>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as OrgRole)}
                  className="input-cohere text-caption"
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Owner</option>
                </select>
                <p className="mt-1 text-micro text-slate-muted">{ROLE_HELP[role]}</p>
              </label>
              <label className="block sm:col-span-1">
                <MonoLabel className="mb-1 block">Title (optional)</MonoLabel>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Production Supervisor"
                  className="input-cohere text-caption"
                />
              </label>
            </div>
            {formErr && <p className="mt-3 text-caption text-studio-maroon">{formErr}</p>}
            <div className="mt-4 flex items-center gap-2">
              <button
                type="submit"
                disabled={busy === "invite"}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                {busy === "invite" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                Send invite
              </button>
              <button type="button" onClick={() => setInviteOpen(false)} className="btn-pill-outline">
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Members */}
        <section>
          <h2 className="font-display text-feature text-cohere-ink">
            Members <span className="text-slate-muted">· {data.members.length}</span>
          </h2>
          <div className="mt-4 rounded-[10px] border border-hairline bg-white">
            {data.members.map((m, i) => (
              <div
                key={m.contact_id}
                className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 ${i > 0 ? "border-t border-hairline" : ""}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-body font-medium text-cohere-ink">
                    {m.name || m.email}
                    {m.is_me && <span className="ml-2 text-micro text-slate-muted">(you)</span>}
                  </p>
                  <p className="truncate text-caption text-slate">
                    {m.email}
                    {m.title ? ` · ${m.title}` : ""}
                  </p>
                </div>
                <RoleChip role={m.role} />
                <span className="text-caption text-slate-muted">
                  Joined {formatDateShort(m.joined_at)}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Pending invites */}
        <section>
          <h2 className="font-display text-feature text-cohere-ink">
            Pending invites{data.invites.length > 0 && <span className="text-slate-muted"> · {data.invites.length}</span>}
          </h2>
          {data.invites.length === 0 ? (
            <p className="mt-3 text-body text-slate">
              No invites waiting.{" "}
              {data.can_manage
                ? "Invite a member and they'll appear here until they accept."
                : "When an owner or admin invites someone, they'll appear here until they accept."}
            </p>
          ) : (
            <div className="mt-4 rounded-[10px] border border-hairline bg-white">
              {data.invites.map((inv, i) => (
                <div
                  key={inv.id}
                  className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 ${i > 0 ? "border-t border-hairline" : ""}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-body font-medium text-cohere-ink">{inv.email}</p>
                    <p className="text-caption text-slate">
                      Invited {formatRelative(inv.sent_at)}
                      {inv.invited_by_email ? ` by ${inv.invited_by_email}` : ""}
                      {inv.expired
                        ? " · expired"
                        : ` · expires ${formatDateShort(inv.expires_at)}`}
                    </p>
                  </div>
                  <RoleChip role={inv.role} />
                  {inv.expired && (
                    <span className="text-micro font-medium text-studio-maroon">Expired</span>
                  )}
                  {data.can_manage && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => doResend(inv)}
                        disabled={busy !== null}
                        className="btn-pill-outline inline-flex items-center gap-1.5 text-caption"
                      >
                        {busy === `resend-${inv.id}` && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        Resend
                      </button>
                      <button
                        onClick={() => doRevoke(inv)}
                        disabled={busy !== null}
                        className="inline-flex items-center gap-1.5 text-caption text-slate underline underline-offset-2 transition-colors hover:text-studio-maroon disabled:opacity-50"
                      >
                        {busy === `revoke-${inv.id}` && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        Revoke
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
