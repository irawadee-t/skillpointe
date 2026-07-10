"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  KeyRound,
  Plus,
  RefreshCw,
  BarChart3,
  FlaskConical,
  Copy,
  Check,
  X,
  Loader2,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";

import {
  Partner,
  KeyIssued,
  UsageReport,
  TestResult,
  TIERS,
  REQUESTER_CATEGORIES,
  REQUESTER_LABELS,
  listPartners,
  createPartner,
  rotateKey,
  updatePartner,
  getUsage,
  testVerify,
} from "@/lib/api/skilledIdAdmin";
import { PageHeader, MonoLabel, MetricCard, Breadcrumb, useToast } from "@/components/ui";
import { easeCohere } from "@/lib/motion";
import { cn } from "@/lib/utils";

export function SkilledIdConsole({ initial, token }: { initial: Partner[]; token: string }) {
  const [partners, setPartners] = useState<Partner[]>(initial);
  const [issued, setIssued] = useState<KeyIssued | null>(null);
  const [usageFor, setUsageFor] = useState<Partner | null>(null);
  const [testFor, setTestFor] = useState<Partner | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function refresh() {
    try {
      setPartners(await listPartners(token));
    } catch {
      /* keep current */
    }
  }

  const activeCount = partners.filter((p) => p.active).length;
  const totalReqs = partners.reduce((s, p) => s + p.total_requests, 0);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "SKILLED ID" }]} />
        <PageHeader
          eyebrow="SKILLED Pro"
          title="SKILLED ID — Partners"
          lead="Issue and manage API keys for third parties (job boards, staffing agencies, background-check firms) that query verified credential status. Keys are shown once; usage is metered for billing."
        />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <MetricCard label="Partners" value={partners.length} icon={KeyRound} />
          <MetricCard label="Active" value={activeCount} icon={ShieldCheck} tone="stone" />
          <MetricCard label="Total queries" value={totalReqs} icon={BarChart3} tone="white" className="col-span-2 sm:col-span-1" />
        </div>

        {issued && <KeyRevealBanner issued={issued} onClose={() => setIssued(null)} />}

        <CreatePartner
          token={token}
          onCreated={(k) => {
            setIssued(k);
            setPartners((p) => [k.partner, ...p]);
          }}
          onError={setError}
        />

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-error-red">{error}</p>
        )}

        {/* Partner table */}
        {partners.length === 0 ? (
          <div className="rounded-md border border-border-light bg-white p-10 text-center">
            <KeyRound className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
            <p className="mt-3 font-display text-feature text-cohere-ink">No partners yet</p>
            <p className="mt-1 text-body text-slate">Issue your first API key above.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border-light bg-white">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="mono-label px-4 py-2.5 text-left">Partner</th>
                  <th className="mono-label px-4 py-2.5 text-left">Category</th>
                  <th className="mono-label px-4 py-2.5 text-left">Tier</th>
                  <th className="mono-label px-4 py-2.5 text-left">Key</th>
                  <th className="mono-label px-4 py-2.5 text-right">30-day</th>
                  <th className="mono-label px-4 py-2.5 text-left">Status</th>
                  <th className="mono-label px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {partners.map((p) => (
                  <PartnerRow
                    key={p.id}
                    p={p}
                    token={token}
                    onChange={(np) => setPartners((all) => all.map((x) => (x.id === np.id ? np : x)))}
                    onRotated={(k) => {
                      setIssued(k);
                      setPartners((all) => all.map((x) => (x.id === k.partner.id ? k.partner : x)));
                      toast.success("Key rotated. Old key is invalid.");
                    }}
                    onUsage={() => setUsageFor(p)}
                    onTest={() => setTestFor(p)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-caption text-slate-muted">
          Endpoint: <code className="">GET /skilled-id/v1/verify?subject_id=…</code> with header{" "}
          <code className="">X-API-Key</code>. Responses are consent-gated and verified-only.
        </p>
      </div>

      <AnimatePresence>
        {usageFor && <UsageModal partner={usageFor} token={token} onClose={() => { setUsageFor(null); refresh(); }} />}
        {testFor && <TestModal partner={testFor} token={token} onClose={() => setTestFor(null)} />}
      </AnimatePresence>
    </main>
  );
}

function KeyRevealBanner({ issued, onClose }: { issued: KeyIssued; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="rounded-md border border-cohere-green/30 bg-wash-green p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <MonoLabel className="text-cohere-green">New API key — copy it now</MonoLabel>
          <p className="mt-1 text-caption text-cohere-green/90">
            This is shown <strong>once</strong>. Store it securely; it cannot be retrieved again.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="overflow-x-auto rounded-sm border border-cohere-green/30 bg-white px-3 py-2 text-caption text-cohere-ink">
              {issued.api_key}
            </code>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(issued.api_key);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="btn-pill-outline shrink-0"
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-2 text-micro text-cohere-green/80">
            Partner: {issued.partner.name} ({issued.partner.tier} tier)
          </p>
        </div>
        <button onClick={onClose} aria-label="Dismiss" className="text-cohere-green/70 hover:text-cohere-green">
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

function CreatePartner({
  token,
  onCreated,
  onError,
}: {
  token: string;
  onCreated: (k: KeyIssued) => void;
  onError: (e: string | null) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [category, setCategory] = useState("job_board");
  const [tier, setTier] = useState("standard");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || loading) return;
    setLoading(true);
    onError(null);
    try {
      const k = await createPartner(token, {
        name: name.trim(),
        contact_email: email.trim() || null,
        requester_category: category,
        tier,
      });
      onCreated(k);
      setName("");
      setEmail("");
    } catch {
      onError("Could not create partner. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-md border border-border-light bg-white p-5">
      <MonoLabel className="mb-3 block">Issue a partner key</MonoLabel>
      <div className="grid gap-3 sm:grid-cols-[1.3fr_1.3fr_1fr_0.9fr_auto] sm:items-end">
        <label className="block">
          <span className="mono-label mb-1.5 block">Name</span>
          <input className="input-cohere" placeholder="e.g. Indeed" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="block">
          <span className="mono-label mb-1.5 block">Contact email</span>
          <input className="input-cohere" placeholder="api@partner.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block">
          <span className="mono-label mb-1.5 block">Category</span>
          <select className="input-cohere" value={category} onChange={(e) => setCategory(e.target.value)}>
            {REQUESTER_CATEGORIES.map((c) => (
              <option key={c} value={c}>{REQUESTER_LABELS[c]}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mono-label mb-1.5 block">Tier</span>
          <select className="input-cohere capitalize" value={tier} onChange={(e) => setTier(e.target.value)}>
            {TIERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={loading || !name.trim()} className="btn-primary">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Issue key
        </button>
      </div>
    </form>
  );
}

function PartnerRow({
  p,
  token,
  onChange,
  onRotated,
  onUsage,
  onTest,
}: {
  p: Partner;
  token: string;
  onChange: (p: Partner) => void;
  onRotated: (k: KeyIssued) => void;
  onUsage: () => void;
  onTest: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function setTier(tier: string) {
    setBusy(true);
    try { onChange(await updatePartner(token, p.id, { tier })); } finally { setBusy(false); }
  }
  async function toggleActive() {
    setBusy(true);
    try { onChange(await updatePartner(token, p.id, { active: !p.active })); } finally { setBusy(false); }
  }
  async function rotate() {
    setBusy(true);
    try { onRotated(await rotateKey(token, p.id)); } finally { setBusy(false); }
  }

  return (
    <tr className={cn("align-middle", !p.active && "opacity-55")}>
      <td className="px-4 py-3">
        <div className="font-semibold text-cohere-ink">{p.name}</div>
        {p.contact_email && <div className="text-caption text-slate">{p.contact_email}</div>}
      </td>
      <td className="px-4 py-3 text-caption text-slate">{REQUESTER_LABELS[p.requester_category] ?? p.requester_category}</td>
      <td className="px-4 py-3">
        <select
          value={p.tier}
          disabled={busy}
          onChange={(e) => setTier(e.target.value)}
          className="rounded-sm border border-hairline bg-white px-2 py-1 text-caption capitalize"
        >
          {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="mt-1 text-micro text-slate-muted tabular-nums">{p.rate_limit.toLocaleString()}/window</div>
      </td>
      <td className="px-4 py-3 text-caption text-slate">{p.key_prefix}…</td>
      <td className="px-4 py-3 text-right font-semibold tabular-nums text-cohere-ink">{p.requests_30d}</td>
      <td className="px-4 py-3">
        <button
          onClick={toggleActive}
          disabled={busy}
          className={cn(
            "rounded-sm border px-2.5 py-1 text-micro font-medium transition-colors",
            p.active
              ? "border-cohere-green/25 bg-wash-green text-cohere-green"
              : "border-hairline bg-stone text-slate",
          )}
        >
          {p.active ? "Active" : "Inactive"}
        </button>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1.5">
          <IconBtn title="Test" onClick={onTest}><FlaskConical className="h-4 w-4" /></IconBtn>
          <IconBtn title="Usage" onClick={onUsage}><BarChart3 className="h-4 w-4" /></IconBtn>
          <IconBtn title="Rotate key" onClick={rotate} busy={busy}><RefreshCw className="h-4 w-4" /></IconBtn>
        </div>
      </td>
    </tr>
  );
}

function IconBtn({ title, onClick, busy, children }: { title: string; onClick: () => void; busy?: boolean; children: React.ReactNode }) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={busy}
      className="rounded-sm border border-hairline p-1.5 text-slate-muted transition-colors hover:border-cohere-ink hover:text-cohere-ink disabled:opacity-50"
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : children}
    </button>
  );
}

function ModalShell({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end justify-center bg-studio-dark-cork/40 p-0 sm:items-center sm:p-6"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
    >
      <motion.div
        className="w-full max-w-lg overflow-hidden rounded-t-lg bg-white sm:rounded-lg"
        initial={{ y: 24, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }}
        exit={{ y: 24, opacity: 0, scale: 0.98 }} transition={{ duration: 0.3, ease: easeCohere }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-cohere-green p-5 text-white">
          <div className="flex items-start justify-between">
            <div>
              <MonoLabel className="text-white/60">{subtitle}</MonoLabel>
              <h2 className="mt-1 font-display text-card text-white">{title}</h2>
            </div>
            <button onClick={onClose} aria-label="Close" className="text-white/70 hover:text-white"><X className="h-5 w-5" /></button>
          </div>
        </div>
        <div className="max-h-[65vh] overflow-y-auto p-5">{children}</div>
      </motion.div>
    </motion.div>
  );
}

function UsageModal({ partner, token, onClose }: { partner: Partner; token: string; onClose: () => void }) {
  const [data, setData] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let on = true;
    getUsage(token, partner.id).then((d) => on && setData(d)).catch(() => on && setError("Could not load usage."));
    return () => { on = false; };
  }, [token, partner.id]);

  const max = data ? Math.max(1, ...data.daily.map((d) => d.count)) : 1;

  return (
    <ModalShell title={partner.name} subtitle="Usage over the last 30 days" onClose={onClose}>
      {error ? <p className="text-caption text-error-red">{error}</p>
        : !data ? <div className="flex justify-center py-8 text-slate"><Loader2 className="h-4 w-4 animate-spin" /></div>
        : (
          <div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Total queries" value={data.total_requests} />
              <Stat label="Subjects" value={data.total_subjects} />
              <Stat label="Last 30d" value={data.requests_30d} />
            </div>
            <div>
              <MonoLabel className="mb-2 block">Daily queries</MonoLabel>
              <div className="flex h-24 items-end gap-0.5">
                {data.daily.map((d) => (
                  <div key={d.date} title={`${d.date}: ${d.count}`} className="flex-1 rounded-t-sm bg-cohere-green/80"
                    style={{ height: `${Math.max(2, (d.count / max) * 100)}%` }} />
                ))}
              </div>
              <div className="mt-1 flex justify-between text-micro text-slate-muted">
                <span>{data.daily[0]?.date}</span><span>{data.daily[data.daily.length - 1]?.date}</span>
              </div>
            </div>
            {data.by_endpoint.length > 0 && (
              <div>
                <MonoLabel className="mb-2 block">By endpoint</MonoLabel>
                <ul className="space-y-1.5">
                  {data.by_endpoint.map((e) => (
                    <li key={e.endpoint} className="flex items-center justify-between text-caption">
                      <code className="text-ink">{e.endpoint}</code>
                      <span className="font-semibold tabular-nums text-cohere-ink">{e.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.recent.length > 0 && (
              <div>
                <MonoLabel className="mb-2 block">Recent</MonoLabel>
                <ul className="divide-y divide-hairline">
                  {data.recent.map((r, i) => (
                    <li key={i} className="flex items-center justify-between py-1.5 text-caption text-slate">
                      <code className="">{r.endpoint}</code>
                      <span>{r.subject_count} subj, {r.status_code}, {new Date(r.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.total_requests === 0 && <p className="text-center text-caption text-slate-muted">No queries yet.</p>}
          </div>
        )}
    </ModalShell>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border-light p-3">
      <div className="font-display text-card tabular-nums text-cohere-ink">{value}</div>
      <MonoLabel className="mt-1 block">{label}</MonoLabel>
    </div>
  );
}

function TestModal({ partner, token, onClose }: { partner: Partner; token: string; onClose: () => void }) {
  const [subject, setSubject] = useState("");
  const [result, setResult] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!subject.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try { setResult(await testVerify(token, partner.id, subject.trim())); }
    catch { setError("Verify failed. Check the subject id."); }
    finally { setLoading(false); }
  }

  return (
    <ModalShell title={partner.name} subtitle="SKILLED ID, live test" onClose={onClose}>
      <p className="mb-3 text-caption text-slate">
        Run a consent-gated verify as this partner ({REQUESTER_LABELS[partner.requester_category]}). Does not consume rate limit or billing.
      </p>
      <div className="flex gap-2">
        <input className="input-cohere text-caption" placeholder="subject_id (applicant UUID)" value={subject} onChange={(e) => setSubject(e.target.value)} />
        <button onClick={run} disabled={loading || !subject.trim()} className="btn-primary shrink-0">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />} Verify
        </button>
      </div>
      {error && <p className="mt-3 text-caption text-error-red">{error}</p>}
      {result && (
        <div className="mt-4 rounded-md border border-border-light p-4">
          <div className="flex items-center gap-2 text-caption">
            {result.found
              ? result.consented
                ? <span className="flex items-center gap-1 text-cohere-green"><ShieldCheck className="h-4 w-4" /> Consented — {result.credentials.length} verified credential(s)</span>
                : <span className="flex items-center gap-1 text-studio-maroon"><AlertTriangle className="h-4 w-4" /> Worker found, but not consented to this partner</span>
              : <span className="flex items-center gap-1 text-slate"><AlertTriangle className="h-4 w-4" /> No such subject</span>}
          </div>
          {result.credentials.length > 0 && (
            <ul className="mt-3 space-y-2">
              {result.credentials.map((c, i) => (
                <li key={i} className="flex items-center justify-between rounded-sm border border-border-light px-3 py-2 text-caption">
                  <span className="text-cohere-ink">{c.canonical_name}</span>
                  <span className="rounded-sm bg-wash-green px-1.5 py-0.5 text-micro text-cohere-green">{c.verification_badge}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </ModalShell>
  );
}
