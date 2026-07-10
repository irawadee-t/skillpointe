"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  BadgeCheck,
  CircleDashed,
  Plus,
  Trash2,
  AlertTriangle,
  Loader2,
  CheckCircle2,
  CalendarDays,
  Building2,
  FileCheck2,
  X,
} from "lucide-react";

import { VerificationBadge, VerifyCredentialButton } from "@/components/applicant/CredentialTrust";
import {
  Credential,
  VerificationLevel,
  addCredential,
  deleteCredential,
  verifyDocument,
  DocVerifyResult,
} from "@/lib/api/credentials";
import { ApiError } from "@/lib/api/client";
import { PageHeader, MonoLabel, MetricCard, Field } from "@/components/ui";
import { cn } from "@/lib/utils";

const LEVEL_META: Record<
  VerificationLevel,
  { label: string; icon: typeof ShieldCheck; chip: string }
> = {
  2: { label: "SKILLED Verified", icon: ShieldCheck, chip: "bg-cohere-green text-white border-cohere-green" },
  1: { label: "Institution-Verified", icon: BadgeCheck, chip: "bg-wash-blue text-cohere-blue border-cohere-blue/25" },
  0: { label: "Self-Reported", icon: CircleDashed, chip: "bg-stone text-slate border-hairline" },
};

export function CredentialsClient({
  initial,
  token,
  credentialsError,
}: {
  initial: Credential[];
  token: string;
  credentialsError?: string | null;
}) {
  const [items, setItems] = useState<Credential[]>(initial);

  const stats = useMemo(() => {
    const verified = items.filter((c) => c.verification_level >= 1).length;
    const review = items.filter((c) => c.needs_review).length;
    return { total: items.length, verified, review };
  }, [items]);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="SKILLED Pro"
          title="Credentials"
          lead="Add your certifications, licenses, and degrees. Verified credentials power your SKILLED ID and strengthen every job match."
          actions={
            <div className="flex flex-wrap gap-2">
              <Link href="/applicant/resume" className="btn-secondary">
                Résumé & summary →
              </Link>
              <Link href="/applicant/consent" className="btn-secondary">
                Data sharing settings →
              </Link>
            </div>
          }
        />

        {/* Verification summary */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <MetricCard label="Total credentials" value={stats.total} icon={ShieldCheck} />
          <MetricCard label="Verified" value={stats.verified} icon={BadgeCheck} tone="stone" />
          <MetricCard
            label="Needs review"
            value={stats.review}
            icon={AlertTriangle}
            tone="white"
            className="col-span-2 sm:col-span-1"
          />
        </div>

        <AddCredentialForm
          token={token}
          onAdded={(c) => setItems((prev) => [c, ...prev])}
        />

        {/* Panel-level error banner — only shows if the list fetch failed on
            the server. Add-form and explainer still render. (item 17) */}
        {credentialsError && (
          <div className="rounded-md border border-studio-maroon-soft bg-studio-maroon/10 px-4 py-3 text-caption text-error-red">
            <strong>Couldn&apos;t load your credentials.</strong> Your other panels are still available — try refreshing.
          </div>
        )}

        {/* List */}
        {items.length === 0 && !credentialsError ? (
          <div className="rounded-md border border-border-light bg-white p-10 text-center">
            <ShieldCheck className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
            <p className="mt-3 font-display text-feature text-cohere-ink">No credentials yet</p>
            <p className="mt-1 text-body text-slate">
              Add your first certification or license above to get started.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {items.map((c) => (
              <CredentialRow
                key={c.id}
                cred={c}
                token={token}
                onDeleted={() => setItems((prev) => prev.filter((x) => x.id !== c.id))}
                onVerified={(level, badge, review) =>
                  setItems((prev) => prev.map((x) =>
                    x.id === c.id
                      ? { ...x, verification_level: level, verification_badge: badge, needs_review: review }
                      : x))
                }
              />
            ))}
          </ul>
        )}

        {/* How tiers work */}
        <div className="rounded-md bg-stone p-5">
          <MonoLabel className="mb-3 block">How verification works</MonoLabel>
          <div className="grid gap-3 sm:grid-cols-3">
            {([0, 1, 2] as VerificationLevel[]).map((lvl) => {
              const m = LEVEL_META[lvl];
              return (
                <div key={lvl} className="flex items-start gap-2.5">
                  <m.icon className="mt-0.5 h-4 w-4 shrink-0 text-cohere-green" strokeWidth={1.75} />
                  <div>
                    <div className="text-body font-medium text-cohere-ink">{m.label}</div>
                    <div className="text-caption text-slate">
                      {lvl === 0 && "You entered it. No proof attached yet."}
                      {lvl === 1 && "Confirmed by your school or an authentic document."}
                      {lvl === 2 && "Institution-verified, identity-matched, and cryptographically signed."}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </main>
  );
}

function AddCredentialForm({
  token,
  onAdded,
}: {
  token: string;
  onAdded: (c: Credential) => void;
}) {
  const [rawName, setRawName] = useState("");
  const [issuer, setIssuer] = useState("");
  const [issued, setIssued] = useState("");
  const [expires, setExpires] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMatch, setLastMatch] = useState<Credential | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!rawName.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const created = await addCredential(token, {
        raw_name: rawName.trim(),
        issuer: issuer.trim() || null,
        issued_date: issued || null,
        expires_date: expires || null,
      });
      onAdded(created);
      setLastMatch(created);
      setRawName("");
      setIssuer("");
      setIssued("");
      setExpires("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "Complete your profile setup before adding credentials."
          : "Could not add that credential. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-md border border-border-light bg-white p-5">
      <MonoLabel className="mb-3 block">Add a credential</MonoLabel>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Certification, license, or degree">
            <input
              className="input-cohere"
              placeholder="e.g. EPA 608, Journeyman Electrician, OSHA 30"
              value={rawName}
              onChange={(e) => setRawName(e.target.value)}
              required
            />
          </Field>
        </div>
        <Field label="Issuer (optional)">
          <input
            className="input-cohere"
            placeholder="e.g. EPA, IBEW, state board"
            value={issuer}
            onChange={(e) => setIssuer(e.target.value)}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Issued">
            <input type="date" className="input-cohere" value={issued} onChange={(e) => setIssued(e.target.value)} />
          </Field>
          <Field label="Expires">
            <input type="date" className="input-cohere" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-error-red">
          {error}
        </p>
      )}

      {lastMatch && !error && (
        <p className="mt-3 flex items-center gap-2 rounded-sm bg-wash-green px-3 py-2 text-caption text-cohere-green">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {lastMatch.canonical_name
            ? `Added — matched to “${lastMatch.canonical_name}” (${Math.round(lastMatch.normalization_confidence * 100)}% confidence).`
            : "Added — we'll review this one to match it to our credential catalog."}
        </p>
      )}

      <div className="mt-4">
        <button type="submit" disabled={loading || !rawName.trim()} className="btn-primary">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          {loading ? "Adding…" : "Add credential"}
        </button>
      </div>
    </form>
  );
}

function CredentialRow({
  cred,
  token,
  onDeleted,
  onVerified,
}: {
  cred: Credential;
  token: string;
  onDeleted: () => void;
  onVerified: (level: VerificationLevel, badge: string, review: boolean) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [docText, setDocText] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<DocVerifyResult | null>(null);

  const meta = LEVEL_META[cred.verification_level];
  const title = cred.canonical_name ?? cred.raw_name;

  async function runVerify() {
    if (!docText.trim()) return;
    setVerifying(true);
    setError(null);
    try {
      const r = await verifyDocument(token, cred.id, docText.trim());
      setResult(r);
      onVerified(r.new_verification_level, r.new_badge, r.decision === "review");
    } catch {
      setError("Could not verify the document. Try again.");
    } finally {
      setVerifying(false);
    }
  }

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await deleteCredential(token, cred.id);
      onDeleted();
    } catch {
      setError("Could not remove. Try again.");
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <li className="rounded-md border border-border-light bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-feature text-cohere-ink">{title}</h3>
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-sm border px-2.5 py-1 text-micro font-medium",
                meta.chip,
              )}
            >
              <meta.icon className="h-3 w-3" /> {meta.label}
            </span>
            {cred.needs_review && (
              <span className="inline-flex items-center gap-1 rounded-sm border border-studio-maroon-soft bg-studio-maroon/10 px-2.5 py-1 text-micro font-medium text-studio-maroon">
                <AlertTriangle className="h-3 w-3" /> In review
              </span>
            )}
            {cred.provider_source && (
              <VerificationBadge
                providerSource={cred.provider_source}
                stubbed={cred.provider_stubbed}
                verifiedAt={cred.provider_verified_at}
                externalRef={cred.provider_external_ref}
              />
            )}
          </div>

          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-caption text-slate">
            {cred.credential_type && <span className="capitalize">{cred.credential_type}</span>}
            {cred.issuer && (
              <span className="flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5 text-slate-muted" /> {cred.issuer}
              </span>
            )}
            {(cred.issued_date || cred.expires_date) && (
              <span className="flex items-center gap-1">
                <CalendarDays className="h-3.5 w-3.5 text-slate-muted" />
                {cred.issued_date ?? "—"}
                {cred.expires_date ? ` → ${cred.expires_date}` : ""}
              </span>
            )}
          </div>
          {!cred.canonical_name && (
            <p className="mt-1 text-micro text-slate-muted">Entered as “{cred.raw_name}”.</p>
          )}

          {/* Partner-verify affordance — shown when the definition supports it and
              we don't yet have a verified receipt on this row. */}
          {!cred.provider_source && (cred.verification_provider === "nccer" || cred.verification_provider === "nsc" || cred.verification_provider === "credential_engine") && (
            <div className="mt-3">
              <VerifyCredentialButton
                token={token}
                credentialId={cred.id}
                provider={cred.verification_provider as "nccer" | "nsc" | "credential_engine"}
                onVerified={(r) => onVerified(r.ok ? 2 : 0, r.ok ? "Partner-Verified" : "Self-Reported", false)}
              />
              {cred.authority && (
                <p className="mt-1 text-micro text-slate-muted">
                  Issued by <strong>{cred.authority}</strong>{cred.ctdl_uri ? ", CTDL-mapped" : ""}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {confirming ? (
            <>
              <button
                onClick={remove}
                disabled={deleting}
                className="rounded-pill bg-error-red px-3 py-1.5 text-micro font-medium text-white hover:opacity-90"
              >
                {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Confirm remove"}
              </button>
              <button
                onClick={() => setConfirming(false)}
                disabled={deleting}
                className="text-micro text-slate hover:text-ink"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              {cred.verification_level < 1 && (
                <button
                  onClick={() => setVerifyOpen((v) => !v)}
                  className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2.5 py-1.5 text-micro font-medium text-slate transition-colors hover:border-cohere-green hover:text-cohere-green"
                >
                  <FileCheck2 className="h-3.5 w-3.5" /> Verify with document
                </button>
              )}
              <button
                onClick={() => setConfirming(true)}
                className="rounded-sm border border-hairline p-1.5 text-slate-muted transition-colors hover:border-error-red hover:text-error-red"
                aria-label="Remove credential"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {verifyOpen && (
        <div className="mt-4 rounded-md border border-border-light bg-stone/40 p-4">
          <div className="flex items-center justify-between">
            <MonoLabel>Verify with a document</MonoLabel>
            <button onClick={() => { setVerifyOpen(false); setResult(null); }} aria-label="Close"
              className="text-slate-muted hover:text-cohere-ink"><X className="h-4 w-4" /></button>
          </div>
          <p className="mt-1 text-micro text-slate-muted">
            Paste the text of your certificate, diploma, or license. We check the issuer and name,
            then raise verified credentials to Institution-Verified.
          </p>
          <p
            className="mt-1 text-micro text-slate"
            title="Paste the certificate ID from your card/PDF — usually 6–12 digits after your name."
          >
            <strong className="font-medium">Tip:</strong> paste the certificate ID from your card or
            PDF — usually 6&ndash;12 digits after your name.
          </p>
          <textarea
            value={docText}
            onChange={(e) => setDocText(e.target.value)}
            rows={4}
            placeholder="e.g. Coastal Technical College — Certificate ID 004829173 — this certifies completion of EPA Section 608… Authorized by the Registrar, 2024"
            className="input-cohere mt-2 w-full resize-y text-caption"
          />
          <div className="mt-2 flex items-center gap-2">
            <button onClick={runVerify} disabled={verifying || !docText.trim()} className="btn-primary">
              {verifying ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck2 className="h-4 w-4" />}
              Check document
            </button>
          </div>
          {result && (
            <div className={cn("mt-3 rounded-sm border p-3 text-caption",
              result.decision === "verified" ? "border-cohere-green/30 bg-wash-green text-cohere-green"
                : result.decision === "review" ? "border-studio-maroon/30 bg-studio-maroon/10 text-cohere-ink"
                : "border-hairline bg-white text-slate")}>
              <div className="font-semibold">
                {result.decision === "verified" ? `Verified → ${result.new_badge}`
                  : result.decision === "review" ? "Sent to admin review"
                  : "Could not confirm"}, score {(result.score * 100).toFixed(0)}%
              </div>
              <ul className="mt-1 list-disc pl-4 text-micro">
                {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-micro text-error-red">{error}</p>}
    </li>
  );
}
