"use client";

import { useState } from "react";
import {
  ShieldCheck, ShieldAlert, ShieldQuestion, Shield, Loader2, ExternalLink,
} from "lucide-react";

import { VerifyPayload, VerifyResult, verifyCredential } from "@/lib/api/robustness";
import { formatDate } from "@/lib/format";
import { MonoLabel } from "@/components/ui";

type Provider = "nccer" | "nsc" | "credential_engine" | "state_licensing" | "document_upload" | null;

const PROVIDER_LABEL: Record<string, string> = {
  nccer:             "NCCER National Registry",
  nsc:               "National Student Clearinghouse",
  credential_engine: "Credential Engine (CTDL)",
  state_licensing:   "State licensing board",
  document_upload:   "Uploaded document",
};

/**
 * Compact chip showing verification provenance, matching the site's chip
 * language (rounded pill, hairline border, muted washes). Renders in one of
 * four states:
 *   • Partner-verified — green wash, authority named
 *   • Stubbed          — coral wash ("Test only — key not configured")
 *   • Self-reported    — neutral, subtle "Self-reported"
 *   • Verify available — inline button when the credential can be verified
 */
export function VerificationBadge({
  providerSource,
  stubbed,
  verifiedAt,
  externalRef,
  className,
}: {
  providerSource: string | null | undefined;
  stubbed?: boolean;
  verifiedAt?: string | null;
  externalRef?: string | null;
  className?: string;
}) {
  if (!providerSource) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] text-slate ${className ?? ""}`}>
        <Shield className="h-3 w-3 text-slate-muted" strokeWidth={1.75} />
        Self-reported
      </span>
    );
  }

  if (stubbed) {
    return (
      <span
        title={`Would call ${PROVIDER_LABEL[providerSource] ?? providerSource}. Add API key to enable live verification.`}
        className={`inline-flex items-center gap-1.5 rounded-full border border-studio-maroon bg-studio-maroon px-2 py-0.5 text-[11px] text-white ${className ?? ""}`}
      >
        <ShieldQuestion className="h-3 w-3" strokeWidth={1.75} />
        Test verify, {shortLabel(providerSource)}
      </span>
    );
  }

  const label = PROVIDER_LABEL[providerSource] ?? providerSource;
  // Pulse briefly on freshly-verified badges (within last 5s of verifiedAt).
  const isFresh = verifiedAt ? Date.now() - new Date(verifiedAt).getTime() < 5_000 : false;
  return (
    <span
      title={`Verified by ${label}${verifiedAt ? `, ${formatDate(verifiedAt)}` : ""}${externalRef ? `, ref ${externalRef}` : ""}`}
      className={`inline-flex items-center gap-1.5 rounded-full border border-cohere-green bg-cohere-green px-2 py-0.5 text-[11px] font-medium text-white ${isFresh ? "cred-pulse" : ""} ${className ?? ""}`}
    >
      <ShieldCheck className="h-3 w-3" strokeWidth={1.75} />
      Verified, {shortLabel(providerSource)}
    </span>
  );
}

function shortLabel(p: string): string {
  const short: Record<string, string> = {
    nccer:             "NCCER",
    nsc:               "NSC",
    credential_engine: "CTDL",
    state_licensing:   "State board",
    document_upload:   "Document",
  };
  return short[p] ?? p;
}

/**
 * Inline verify affordance — sits alongside a credential row when the
 * definition has a verification_provider. Prompts for just the fields the
 * provider needs, dispatches, and swaps in the resulting badge.
 */
export function VerifyCredentialButton({
  token, credentialId, provider, onVerified,
}: {
  token: string;
  credentialId: string;
  provider: "nccer" | "nsc" | "credential_engine";
  onVerified: (r: VerifyResult) => void;
}) {
  const [open, setOpen] = useState(false);
  const [payload, setPayload] = useState<VerifyPayload>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);

  async function run() {
    setRunning(true); setError(null);
    try {
      const r = await verifyCredential(token, credentialId, payload);
      setResult(r);
      onVerified(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setRunning(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-caption text-cohere-blue underline decoration-cohere-blue/40 underline-offset-2 hover:decoration-cohere-blue"
      >
        Verify via {shortLabel(provider)}
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-lg border border-hairline bg-stone/40 p-4">
      <div className="flex items-center justify-between">
        <MonoLabel>Verify, {PROVIDER_LABEL[provider]}</MonoLabel>
        <button onClick={() => setOpen(false)} className="text-micro text-slate-muted hover:text-cohere-ink">Cancel</button>
      </div>

      {provider === "nccer" && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <FieldInput label="NCCER card number" value={payload.card_number ?? ""} onChange={(v) => setPayload((p) => ({ ...p, card_number: v }))} placeholder="e.g. 12345678" />
          <FieldInput label="Last name (on file)" value={payload.last_name ?? ""} onChange={(v) => setPayload((p) => ({ ...p, last_name: v }))} placeholder="Smith" />
        </div>
      )}

      {provider === "nsc" && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <FieldInput label="First name" value={payload.first_name ?? ""} onChange={(v) => setPayload((p) => ({ ...p, first_name: v }))} />
          <FieldInput label="Last name" value={payload.last_name ?? ""} onChange={(v) => setPayload((p) => ({ ...p, last_name: v }))} />
          <FieldInput label="Date of birth" value={payload.dob ?? ""} onChange={(v) => setPayload((p) => ({ ...p, dob: v }))} placeholder="YYYY-MM-DD" />
          <FieldInput label="School code (OPEID, optional)" value={payload.school_code ?? ""} onChange={(v) => setPayload((p) => ({ ...p, school_code: v }))} />
        </div>
      )}

      {provider === "credential_engine" && (
        <p className="mt-3 text-caption text-slate">
          This resolves the Credential Engine (CTDL) definition behind this credential, a taxonomy check.
        </p>
      )}

      {error && <p className="mt-3 text-caption text-studio-maroon">{error}</p>}

      {result && (
        <div className={`mt-3 rounded-md border p-3 text-caption ${
          result.ok
            ? "border-cohere-green/30 bg-wash-green text-cohere-ink"
            : "border-studio-maroon/30 bg-studio-maroon/[0.06] text-cohere-ink"
        }`}>
          {result.ok ? <ShieldCheck className="inline h-3.5 w-3.5 mr-1 text-cohere-green" /> : <ShieldAlert className="inline h-3.5 w-3.5 mr-1 text-studio-maroon" />}
          {result.message}
          {result.verified_name && <div className="mt-1 text-micro text-slate">Name on file: <strong>{result.verified_name}</strong></div>}
          {result.credential && <div className="text-micro text-slate">Credential: <strong>{result.credential}</strong></div>}
          {result.external_ref && <div className="text-micro text-slate-muted">Reference: {result.external_ref}</div>}
        </div>
      )}

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          onClick={run}
          disabled={running || (provider === "nccer" && !payload.card_number) || (provider === "nsc" && !(payload.first_name && payload.last_name && payload.dob))}
          className="btn-primary-green inline-flex items-center gap-1.5"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
          Run verification
        </button>
      </div>

      {provider === "nccer" && (
        <p className="mt-2 text-micro text-slate-muted">
          NCCER National Registry, <a href="https://www.nccer.org/registry" target="_blank" rel="noopener noreferrer" className="text-cohere-blue underline inline-flex items-center gap-0.5">what is my card # <ExternalLink className="h-2.5 w-2.5" /></a>
        </p>
      )}
      {provider === "nsc" && (
        <p className="mt-2 text-micro text-slate-muted">
          National Student Clearinghouse, covers ~97% of US postsecondary institutions
        </p>
      )}
    </div>
  );
}

function FieldInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-micro text-slate">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="input-cohere text-caption" />
    </label>
  );
}
