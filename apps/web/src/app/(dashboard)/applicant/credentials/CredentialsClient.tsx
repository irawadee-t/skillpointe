"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import QRCode from "qrcode";
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
  ChevronDown,
  FileCheck2,
  Smartphone,
  UploadCloud,
  X,
} from "lucide-react";

import { motion } from "motion/react";

import { VerificationBadge, VerifyCredentialButton } from "@/components/applicant/CredentialTrust";
import {
  Credential,
  CredentialCategory,
  CredentialSuggestion,
  VerificationLevel,
  addCredential,
  deleteCredential,
  suggestCredentials,
  uploadCredentialDocument,
  DocUploadResult,
  createPhoneLink,
  getPhoneStatus,
  verifyBadge,
  BadgeVerifyResult,
  createCheckrInvite,
} from "@/lib/api/credentials";
import { ApiError } from "@/lib/api/client";
import { formatDate, isImpossibleRange, isPastDate } from "@/lib/format";
import { peekApplyReturn } from "@/lib/applyReturn";
import { useTypeahead } from "@/hooks/useTypeahead";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";
import { PageHeader, MonoLabel, MetricCard, Field, STATUS_TONE_CLASSES, STATUS_CHIP_BASE as CHIP_BASE } from "@/components/ui";
import { cn } from "@/lib/utils";

/**
 * Structured categories — sentence-case labels over the backend taxonomy
 * (CTDL credential types collapsed to a trades-appropriate set).
 */
const CATEGORY_OPTIONS: { value: CredentialCategory; label: string }[] = [
  { value: "certification", label: "Certification" },
  { value: "license", label: "License" },
  { value: "degree", label: "Degree or diploma" },
  { value: "apprenticeship", label: "Apprenticeship" },
  { value: "safety", label: "Safety training" },
  { value: "union", label: "Union membership" },
  { value: "other", label: "Other" },
];

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  CATEGORY_OPTIONS.map((o) => [o.value, o.label]),
);

/** Display label for a stored credential_type (legacy values fall back to capitalized raw). */
function categoryLabel(type: string): string {
  return CATEGORY_LABELS[type] ?? type.charAt(0).toUpperCase() + type.slice(1);
}

const LEVEL_META: Record<
  VerificationLevel,
  { label: string; icon: typeof ShieldCheck; chip: string }
> = {
  // Verified (any level) = positive green tint; self-reported = neutral.
  // Level is carried by the label + icon, never by a different hue
  // (DESIGN_CONTRACT.md, "Status & chip color semantics").
  2: { label: "SKILLED-verified", icon: ShieldCheck, chip: STATUS_TONE_CLASSES.positive },
  1: { label: "Institution-verified", icon: BadgeCheck, chip: STATUS_TONE_CLASSES.positive },
  0: { label: "Self-reported", icon: CircleDashed, chip: STATUS_TONE_CLASSES.neutral },
};

type VerifyTab = "badge" | "upload" | "phone" | "checkr";

/** True on touch/coarse-pointer devices — phones default to the phone-QR verify path. */
function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(pointer: coarse)");
    setCoarse(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setCoarse(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return coarse;
}

export function CredentialsClient({
  initial,
  token,
  credentialsError,
  checkrEnabled = false,
}: {
  initial: Credential[];
  token: string;
  credentialsError?: string | null;
  /** True only when a real Checkr key is configured server-side — otherwise
      the background-check verify method is not offered at all. */
  checkrEnabled?: boolean;
}) {
  const [items, setItems] = useState<Credential[]>(initial);
  const [verifyOpenId, setVerifyOpenId] = useState<string | null>(null);
  const [justAddedId, setJustAddedId] = useState<string | null>(null);
  const coarse = useCoarsePointer();

  // Return-trip from the ApplySheet: /applicant/credentials?return=<jobId>.
  const searchParams = useSearchParams();
  const returnJobId = searchParams.get("return");
  const [returnInfo, setReturnInfo] = useState<{ href: string; title?: string } | null>(null);
  useEffect(() => {
    if (!returnJobId) return;
    const pending = peekApplyReturn();
    if (pending && pending.jobId === returnJobId) {
      setReturnInfo({ href: pending.href, title: pending.title });
    } else {
      setReturnInfo({ href: "/applicant/jobs" });
    }
  }, [returnJobId]);

  const stats = useMemo(() => {
    const verified = items.filter((c) => c.verification_level >= 1).length;
    const review = items.filter((c) => c.needs_review || c.verification_review_pending).length;
    return { total: items.length, verified, review };
  }, [items]);

  // Add→verify bridge: the new row scrolls into view with its verify panel
  // already open (phone-QR first on touch, Upload first on desktop).
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleAdded = useCallback((c: Credential) => {
    setItems((prev) => [c, ...prev]);
    setVerifyOpenId(c.id);
    setJustAddedId(c.id);
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setJustAddedId(null), 2600);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(() => {
      document
        .getElementById(`credential-${c.id}`)
        ?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    }, 120);
  }, []);
  useEffect(() => () => { if (highlightTimer.current) clearTimeout(highlightTimer.current); }, []);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Your record"
          title="Credentials"
          lead="Add your certifications, licenses, and degrees. Verified credentials strengthen every job match."
          actions={
            <div className="flex flex-wrap gap-2">
              <Link href="/applicant/resume" className="btn-secondary">
                Résumé &amp; summary →
              </Link>
              <Link href="/applicant/consent" className="btn-secondary">
                Data sharing settings →
              </Link>
            </div>
          }
        />

        {/* Return-trip banner — the user is mid-application on another page. */}
        {returnJobId && returnInfo && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-hairline bg-white px-4 py-3">
            <p className="min-w-0 text-caption text-slate">
              You&rsquo;re adding a credential for your application
              {returnInfo.title ? <> to <strong className="text-cohere-ink">{returnInfo.title}</strong></> : null}.
              Add it below, then head back. The application reopens where you left off.
            </p>
            <Link href={returnInfo.href} className="btn-secondary shrink-0">
              Back to your application →
            </Link>
          </div>
        )}

        {/* Verification summary */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-tour-id="credentials-summary">
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

        <div data-tour-id="credentials-add">
          <AddCredentialForm token={token} onAdded={handleAdded} />
        </div>

        {/* Panel-level error banner — only shows if the list fetch failed on
            the server. Add-form and explainer still render. (item 17) */}
        {credentialsError && (
          <div className="rounded-md border border-studio-maroon/30 bg-studio-maroon/[0.06] px-4 py-3 text-caption text-cohere-ink">
            <strong>Couldn&apos;t load your credentials.</strong> Your other panels are still available. Try refreshing.
          </div>
        )}

        {/* Credential list */}
        <MonoLabel>Your credentials</MonoLabel>

        {items.length === 0 && !credentialsError ? (
          <div className="rounded-md border border-border-light bg-white p-10 text-center" data-tour-id="credentials-list">
            <ShieldCheck className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
            <p className="mt-3 text-[1.0625rem] font-medium text-cohere-ink">No credentials yet</p>
            <p className="mt-1 text-body text-slate">
              Add your first certification or license above to get started.
            </p>
          </div>
        ) : (
          <ul className="space-y-3" data-tour-id="credentials-list">
            {items.map((c) => (
              <CredentialRow
                key={c.id}
                cred={c}
                token={token}
                coarse={coarse}
                checkrEnabled={checkrEnabled}
                highlight={justAddedId === c.id}
                verifyOpen={verifyOpenId === c.id}
                onToggleVerify={(open) => setVerifyOpenId(open ? c.id : null)}
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
                  <m.icon className={`mt-0.5 h-4 w-4 shrink-0 ${lvl >= 1 ? "text-cohere-green" : "text-slate-muted"}`} strokeWidth={1.75} />
                  <div>
                    <div className="text-body font-medium text-cohere-ink">{m.label}</div>
                    <div className="text-caption text-slate">
                      {lvl === 0 && "You entered it. No proof attached yet."}
                      {lvl === 1 && "Confirmed by your school or an authentic document."}
                      {lvl === 2 && "Granted after an identity match. A partner registry or background check confirms the record is yours. No extra upload needed."}
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

/**
 * Add a credential — a single prominent combobox. The detail fields (category,
 * issuer, dates) appear only after a pick or a free-text commit; Credential ID
 * and URL sit behind an "Add details" disclosure. The list below stays the
 * page's center of gravity.
 */
function AddCredentialForm({
  token,
  onAdded,
}: {
  token: string;
  onAdded: (c: Credential) => void;
}) {
  const { isViewAs } = useViewAs();
  const [expanded, setExpanded] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [rawName, setRawName] = useState("");
  const [category, setCategory] = useState<CredentialCategory>("certification");
  const [issuer, setIssuer] = useState("");
  const [issued, setIssued] = useState("");
  const [expires, setExpires] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [credentialUrl, setCredentialUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMatch, setLastMatch] = useState<Credential | null>(null);

  // Canonical-registry type-ahead: as the worker types the name we suggest
  // canonical matches; picking one fills name + category + issuer. Free text
  // is always allowed — unmatched entries are flagged for review server-side.
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [picked, setPicked] = useState<CredentialSuggestion | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);
  const suggestRootRef = useRef<HTMLDivElement | null>(null);
  const { results: suggestions, loading: suggestLoading } = useTypeahead<CredentialSuggestion>(
    suggestOpen && !picked ? rawName : "",
    (q, signal) => suggestCredentials(token, q, signal),
    { minChars: 2, debounceMs: 180 },
  );

  useEffect(() => { setActiveIdx(0); }, [suggestions]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!suggestRootRef.current?.contains(e.target as Node)) setSuggestOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function pickSuggestion(s: CredentialSuggestion) {
    setPicked(s);
    setRawName(s.name);
    setCategory(s.category);
    if (s.issuer) setIssuer(s.issuer);
    setSuggestOpen(false);
    setExpanded(true);
    setLastMatch(null);
  }

  /** Commit free text (no canonical match) — expand the detail fields anyway. */
  function commitFreeText() {
    if (!rawName.trim()) return;
    setSuggestOpen(false);
    setExpanded(true);
    setLastMatch(null);
  }

  function reset() {
    setExpanded(false);
    setShowDetails(false);
    setRawName("");
    setPicked(null);
    setSuggestOpen(false);
    setCategory("certification");
    setIssuer("");
    setIssued("");
    setExpires("");
    setCredentialRef("");
    setCredentialUrl("");
  }

  const showSuggestions = suggestOpen && !picked && rawName.trim().length >= 2;
  const showNoMatchRow =
    showSuggestions && !suggestLoading && suggestions.length === 0;

  function onNameKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") { setSuggestOpen(false); return; }
    if (e.key === "Enter") {
      e.preventDefault();
      if (showSuggestions && suggestions.length > 0) pickSuggestion(suggestions[activeIdx]);
      else commitFreeText();
      return;
    }
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(suggestions.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(0, i - 1)); }
  }

  const dateOrderInvalid = Boolean(issued && expires && expires < issued);
  const urlInvalid = Boolean(
    credentialUrl.trim() && !/^https?:\/\//i.test(credentialUrl.trim()),
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!rawName.trim() || loading) return;
    if (!expanded) { commitFreeText(); return; }
    if (dateOrderInvalid || urlInvalid) return;
    setLoading(true);
    setError(null);
    try {
      const created = await addCredential(token, {
        raw_name: rawName.trim(),
        category,
        issuer: issuer.trim() || null,
        issued_date: issued || null,
        expires_date: expires || null,
        credential_ref: credentialRef.trim() || null,
        credential_url: credentialUrl.trim() || null,
      });
      onAdded(created);
      setLastMatch(created);
      reset();
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

      <div ref={suggestRootRef} className="relative">
        <input
          className="input-cohere w-full"
          placeholder="Add a credential, e.g. OSHA 10, EPA 608, Journeyman Electrician"
          value={rawName}
          role="combobox"
          aria-expanded={showSuggestions}
          aria-controls="credential-suggest-listbox"
          aria-autocomplete="list"
          aria-label="Credential name"
          autoComplete="off"
          onChange={(e) => {
            setRawName(e.target.value);
            setPicked(null);
            setSuggestOpen(true);
          }}
          onFocus={() => { if (!picked) setSuggestOpen(true); }}
          onKeyDown={onNameKeyDown}
        />
        {showSuggestions && (suggestions.length > 0 || suggestLoading || showNoMatchRow) && (
          <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-auto rounded-[10px] border border-hairline bg-white shadow-float">
            {suggestLoading && suggestions.length === 0 ? (
              <div className="px-3 py-2 text-caption text-slate">Searching…</div>
            ) : showNoMatchRow ? (
              /* Typeahead zero-state — free text is a first-class path. */
              <button
                type="button"
                onClick={commitFreeText}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-caption text-slate transition-colors hover:bg-parchment/60 hover:text-cohere-ink"
              >
                <Plus className="h-3.5 w-3.5 shrink-0 text-slate-muted" />
                <span>
                  No match for “{rawName.trim()}”. <span className="font-medium text-cohere-ink">Add it anyway</span> and we&rsquo;ll review it.
                </span>
              </button>
            ) : (
              <ul id="credential-suggest-listbox" role="listbox">
                {suggestions.map((s, i) => (
                  <li key={s.slug} role="option" aria-selected={i === activeIdx}>
                    <button
                      type="button"
                      tabIndex={-1}
                      onMouseEnter={() => setActiveIdx(i)}
                      onClick={() => pickSuggestion(s)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors",
                        i === activeIdx ? "bg-parchment text-cohere-ink" : "text-slate hover:bg-parchment/60 hover:text-cohere-ink",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-caption font-medium text-cohere-ink">{s.name}</span>
                        {s.issuer && (
                          <span className="block truncate text-micro text-slate-muted">{s.issuer}</span>
                        )}
                      </span>
                      <span className="shrink-0 rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">
                        {categoryLabel(s.category)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
      {picked?.validity_note && (
        <p className="mt-1 text-micro text-slate-muted">{picked.validity_note}</p>
      )}

      {/* Detail fields — appear after a pick or free-text commit. */}
      {expanded && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Category">
            <select
              className="input-cohere"
              value={category}
              required
              onChange={(e) => setCategory(e.target.value as CredentialCategory)}
            >
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Issuer (optional)">
            <input
              className="input-cohere"
              placeholder="e.g. EPA, IBEW, state board"
              value={issuer}
              onChange={(e) => setIssuer(e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3 sm:col-span-2 sm:max-w-md">
            <Field label="Issued (optional)">
              <input type="date" className="input-cohere" value={issued} onChange={(e) => setIssued(e.target.value)} />
            </Field>
            <Field label="Expires (optional)">
              <input
                type="date"
                className="input-cohere"
                value={expires}
                min={issued || undefined}
                aria-invalid={dateOrderInvalid || undefined}
                onChange={(e) => setExpires(e.target.value)}
              />
            </Field>
          </div>

          {/* ID + URL live behind a quiet disclosure — rarely needed up front. */}
          <div className="sm:col-span-2">
            <button
              type="button"
              onClick={() => setShowDetails((v) => !v)}
              aria-expanded={showDetails}
              className="inline-flex items-center gap-1 text-caption text-slate transition-colors hover:text-cohere-ink"
            >
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-200", showDetails && "rotate-180")} />
              Add details: certificate number or link
            </button>
            {showDetails && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Credential ID (optional)">
                  <input
                    className="input-cohere"
                    placeholder="e.g. card or certificate number"
                    value={credentialRef}
                    maxLength={120}
                    onChange={(e) => setCredentialRef(e.target.value)}
                  />
                </Field>
                <Field label="Credential URL (optional)">
                  <input
                    type="url"
                    inputMode="url"
                    className="input-cohere"
                    placeholder="https://…"
                    value={credentialUrl}
                    aria-invalid={urlInvalid || undefined}
                    onChange={(e) => setCredentialUrl(e.target.value)}
                  />
                </Field>
              </div>
            )}
          </div>
        </div>
      )}

      {urlInvalid && (
        <p className="mt-3 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
          The credential URL needs to start with http:// or https://.
        </p>
      )}

      {dateOrderInvalid && (
        <p className="mt-3 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
          The expiration date can&apos;t be before the issue date.
        </p>
      )}

      {error && (
        <p className="mt-3 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
          {error}
        </p>
      )}

      {lastMatch && !error && (
        <p className="mt-3 flex items-center gap-2 rounded-sm border border-cohere-green/30 bg-wash-green px-3 py-2 text-caption text-cohere-ink">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-cohere-green" />
          {lastMatch.canonical_name && !lastMatch.needs_review
            ? `Added. Recognized as ${lastMatch.canonical_name}. Attach proof below to get it verified.`
            : "Added. We'll review this one to match it to our credential catalog. You can attach proof below meanwhile."}
        </p>
      )}

      {expanded && (
        <div className="mt-4 flex items-center gap-2">
          <button
            type="submit"
            disabled={loading || !rawName.trim() || dateOrderInvalid || urlInvalid || isViewAs}
            title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
            className="btn-primary disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {loading ? "Adding…" : "Add credential"}
          </button>
          <button type="button" onClick={reset} className="btn-ghost">
            Cancel
          </button>
        </div>
      )}
    </form>
  );
}

function CredentialRow({
  cred,
  token,
  coarse,
  checkrEnabled,
  highlight,
  verifyOpen,
  onToggleVerify,
  onDeleted,
  onVerified,
}: {
  cred: Credential;
  token: string;
  coarse: boolean;
  checkrEnabled: boolean;
  highlight: boolean;
  verifyOpen: boolean;
  onToggleVerify: (open: boolean) => void;
  onDeleted: () => void;
  onVerified: (level: VerificationLevel, badge: string, review: boolean) => void;
}) {
  const { isViewAs } = useViewAs();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Default verify method follows the device: phone-QR on touch, Upload on desktop.
  const [tab, setTab] = useState<VerifyTab>("upload");
  const tabTouched = useRef(false);
  useEffect(() => {
    if (!tabTouched.current) setTab(coarse ? "phone" : "upload");
  }, [coarse]);
  // Badge (Credly / Open Badges)
  const [badgeUrl, setBadgeUrl] = useState("");
  const [badgeBusy, setBadgeBusy] = useState(false);
  const [badgeResult, setBadgeResult] = useState<BadgeVerifyResult | null>(null);
  // Checkr
  const [checkrBusy, setCheckrBusy] = useState(false);
  const [checkrUrl, setCheckrUrl] = useState<string | null>(null);
  const [checkrUnavailable, setCheckrUnavailable] = useState(false);

  const meta = LEVEL_META[cred.verification_level];
  const title = cred.canonical_name ?? cred.raw_name;

  // Date sanity — legacy rows can carry impossible ranges; render those with a
  // quiet attention flag instead of verbatim, and mark expired credentials.
  const impossibleDates = isImpossibleRange(cred.issued_date, cred.expires_date);
  const expired = !impossibleDates && isPastDate(cred.expires_date);

  // Verify-method order matches the device default; the default is the
  // recommendation, so it carries the hint. Plain toggle buttons (aria-pressed),
  // not ARIA tabs — no tabs keyboard contract to half-implement.
  // Checkr is offered only when the server says it's truly configured — never
  // show a method that dead-ends in "not enabled in this environment".
  const methods = useMemo(() => {
    const all: Record<VerifyTab, { id: VerifyTab; label: string }> = {
      upload: { id: "upload", label: "Upload a file" },
      phone: { id: "phone", label: "Take a photo on your phone" },
      badge: { id: "badge", label: "Digital badge" },
      checkr: { id: "checkr", label: "Background check" },
    };
    const order: VerifyTab[] = coarse
      ? ["phone", "upload", "badge", "checkr"]
      : ["upload", "phone", "badge", "checkr"];
    return order
      .filter((id) => id !== "checkr" || checkrEnabled)
      .map((id, i) => ({ ...all[id], hint: i === 0 ? "Recommended" : null }));
  }, [coarse, checkrEnabled]);

  async function runBadge() {
    if (!badgeUrl.trim()) return;
    setBadgeBusy(true);
    setError(null);
    try {
      const r = await verifyBadge(token, cred.id, badgeUrl.trim());
      setBadgeResult(r);
      onVerified(r.new_verification_level, r.new_badge, !r.verified && r.name_matched === false);
    } catch {
      setError("Could not check that badge link. Try again.");
    } finally {
      setBadgeBusy(false);
    }
  }

  async function runCheckr() {
    setCheckrBusy(true);
    setError(null);
    try {
      const r = await createCheckrInvite(token, cred.id);
      if (r.simulated || !r.invitation_url) {
        // Checkr isn't connected in this environment — never open (or even
        // render) an external URL; show the inline not-enabled state instead.
        setCheckrUnavailable(true);
        return;
      }
      setCheckrUrl(r.invitation_url);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setCheckrUnavailable(true);
      } else {
        setError("Could not start the background check. Try again.");
      }
    } finally {
      setCheckrBusy(false);
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
    <li
      id={`credential-${cred.id}`}
      className={cn(
        "scroll-mt-24 rounded-[14px] border bg-white p-5 transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float sm:p-6",
        highlight ? "border-cohere-green/50 shadow-float" : "border-hairline",
      )}
    >
      {/* Stacks below sm: — title full-width, actions in their own row under the meta. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 sm:flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[1.0625rem] font-medium text-cohere-ink">{title}</h3>
            <span className={cn(CHIP_BASE, meta.chip)}>
              <meta.icon className="h-3 w-3" /> {meta.label}
            </span>
            {(cred.needs_review || cred.verification_review_pending) && (
              <span className={cn(CHIP_BASE, STATUS_TONE_CLASSES.progress)}>
                <AlertTriangle className="h-3 w-3" /> In review
              </span>
            )}
            {expired && (
              <span className={cn(CHIP_BASE, STATUS_TONE_CLASSES.muted)}>Expired</span>
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

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-slate">
            {cred.credential_type && <span>{categoryLabel(cred.credential_type)}</span>}
            {cred.issuer && (
              <span className="flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5 text-slate-muted" /> {cred.issuer}
              </span>
            )}
            {(cred.issued_date || cred.expires_date) && (
              <span className="flex flex-wrap items-center gap-1.5">
                <CalendarDays className="h-3.5 w-3.5 text-slate-muted" />
                {impossibleDates ? (
                  <>
                    <span>Issued {formatDate(cred.issued_date)}</span>
                    <span
                      className={cn(CHIP_BASE, STATUS_TONE_CLASSES.attention)}
                      title={`This row's expiry (${formatDate(cred.expires_date)}) is before its issue date (${formatDate(cred.issued_date)}).`}
                    >
                      Check dates
                    </span>
                  </>
                ) : (
                  <span>
                    {cred.issued_date && `Issued ${formatDate(cred.issued_date)}`}
                    {cred.issued_date && cred.expires_date && " · "}
                    {cred.expires_date && `${expired ? "expired" : "expires"} ${formatDate(cred.expires_date)}`}
                  </span>
                )}
              </span>
            )}
          </div>
          {!cred.canonical_name && (
            <p className="mt-1 text-micro text-slate-muted">Entered as “{cred.raw_name}”.</p>
          )}
          {(cred.validity_note || cred.verify_url) && (
            <p className="mt-1 text-micro text-slate-muted">
              {cred.validity_note}
              {cred.verify_url && (
                <>
                  {cred.validity_note ? " · " : ""}
                  <a
                    href={cred.verify_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-cohere-ink"
                  >
                    Issuer registry →
                  </a>
                </>
              )}
            </p>
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

        <div className="flex items-center gap-2 sm:shrink-0">
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
                  onClick={() => onToggleVerify(!verifyOpen)}
                  disabled={isViewAs}
                  title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                  className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2.5 py-1.5 text-micro font-medium text-slate transition-colors hover:border-cohere-green hover:text-cohere-green disabled:opacity-50"
                >
                  <BadgeCheck className="h-3.5 w-3.5" /> Verify: upload or badge
                </button>
              )}
              <button
                onClick={() => setConfirming(true)}
                disabled={isViewAs}
                title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
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
            <MonoLabel>Verify this credential</MonoLabel>
            <button onClick={() => { onToggleVerify(false); setBadgeResult(null); }} aria-label="Close"
              className="text-slate-muted hover:text-cohere-ink"><X className="h-4 w-4" /></button>
          </div>

          {/* Method chooser — plain toggle buttons; the device default leads
              and carries the "Recommended" hint. */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {methods.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={tab === t.id}
                onClick={() => { tabTouched.current = true; setTab(t.id); }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1.5 text-micro font-medium transition-colors",
                  tab === t.id
                    ? "border-cohere-green bg-white text-cohere-green"
                    : "border-hairline text-slate hover:border-slate-muted",
                )}
              >
                {t.label}
                {t.hint && <span className="rounded-sm bg-cohere-green px-1 text-[10px] text-white">{t.hint}</span>}
              </button>
            ))}
          </div>

          {tab === "badge" && (
            <div className="mt-3">
              <p className="text-micro text-slate-muted">
                Earned a digital badge from Credly, NCCER, or another issuer? Paste its share link.
                We confirm it straight with the issuer, the strongest kind of proof, instantly.
              </p>
              <input
                type="url"
                inputMode="url"
                value={badgeUrl}
                onChange={(e) => setBadgeUrl(e.target.value)}
                placeholder="https://www.credly.com/badges/…"
                className="input-cohere mt-2 w-full text-caption"
                aria-label="Badge share link"
              />
              <button onClick={runBadge} disabled={badgeBusy || !badgeUrl.trim()} className="btn-primary mt-2">
                {badgeBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" />}
                Verify badge
              </button>
              {badgeResult && (
                <div className={cn("mt-3 rounded-sm border p-3 text-caption",
                  badgeResult.verified ? "border-cohere-green/30 bg-wash-green text-cohere-ink"
                    : "border-studio-maroon/30 bg-studio-maroon/10 text-cohere-ink")}>
                  <div className="font-semibold">
                    {badgeResult.verified
                      ? `Verified → ${badgeResult.new_badge}`
                      : "Not verified"}
                  </div>
                  <p className="mt-1 text-micro">{badgeResult.detail}</p>
                  {badgeResult.issuer && (
                    <p className="mt-1 text-micro text-slate-muted">
                      {badgeResult.badge_name} · issued by {badgeResult.issuer}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === "upload" && (
            <UploadFilePanel token={token} credentialId={cred.id} onVerified={onVerified} />
          )}

          {tab === "phone" && (
            <PhoneHandoffPanel token={token} credentialId={cred.id} onVerified={onVerified} />
          )}

          {tab === "checkr" && (
            <div className="mt-3">
              <p className="text-micro text-slate-muted">
                Verify licenses, driving records (CDL), or run a background check through Checkr,
                the standard used by major hiring platforms. You&rsquo;ll finish on Checkr&rsquo;s
                secure site in a couple of minutes, then your badge updates automatically.
              </p>
              {checkrUnavailable ? (
                <div className="mt-2 rounded-[10px] border border-hairline bg-white p-3.5 text-caption text-slate">
                  <p className="font-medium text-cohere-ink">
                    Background checks are not enabled in this environment.
                  </p>
                  <p className="mt-1 text-micro text-slate-muted">
                    Nothing was sent. Once Checkr is connected, this button takes you to their
                    secure site to finish in a couple of minutes.
                  </p>
                </div>
              ) : !checkrUrl ? (
                <button onClick={runCheckr} disabled={checkrBusy} className="btn-primary mt-2">
                  {checkrBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  Start Checkr verification
                </button>
              ) : (
                <div className="mt-2 space-y-2">
                  <a href={checkrUrl} target="_blank" rel="noopener noreferrer" className="btn-primary inline-flex">
                    <ShieldCheck className="h-4 w-4" /> Continue on Checkr →
                  </a>
                  <p className="text-micro text-slate-muted">
                    Opens in a new tab. Your credential updates here once Checkr finishes.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-micro text-error-red">{error}</p>}
    </li>
  );
}

function formatBytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

/** Upload a photo or PDF of the certificate — drag-drop or file picker. */
function UploadFilePanel({
  token,
  credentialId,
  onVerified,
}: {
  token: string;
  credentialId: string;
  onVerified: (level: VerificationLevel, badge: string, review: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function pick(f: File | undefined | null) {
    if (!f) return;
    setFile(f);
    setResult(null);
    setError(null);
  }

  async function submit() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await uploadCredentialDocument(token, credentialId, file);
      setResult(r);
      onVerified(r.new_verification_level, r.new_badge, r.status === "needs_review");
    } catch (e) {
      if (e instanceof ApiError && e.status === 413) {
        setError("That file is too large. The limit is 10 MB.");
      } else if (e instanceof ApiError && e.status === 415) {
        setError("That file type isn't supported. Upload a JPG, PNG, WebP, or HEIC photo, or a PDF.");
      } else {
        setError("Could not upload the document. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    const accepted = result.status === "accepted";
    return (
      <div className={cn("mt-3 rounded-[10px] border p-4 text-caption",
        accepted ? "border-cohere-green/30 bg-wash-green text-cohere-ink"
          : "border-hairline bg-white text-cohere-ink")}>
        <div className="flex items-center gap-2 font-semibold">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {accepted ? `Verified → ${result.new_badge}` : "Sent to review"}
        </div>
        <p className="mt-1 text-micro">
          {accepted
            ? result.detail
            : "We'll badge it once confirmed, usually within a business day."}
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <p className="text-micro text-slate-muted">
        Upload a photo or PDF of your certificate, diploma, or license. We read it, check the
        issuer and name, and badge it, or send it to SkillPointe review.
      </p>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files?.[0]); }}
        className={cn(
          "mt-2 flex cursor-pointer flex-col items-center gap-1.5 rounded-[10px] border border-dashed bg-white px-4 py-6 text-center transition-colors",
          dragOver ? "border-cohere-green bg-wash-green" : "border-hairline hover:border-slate-muted",
        )}
      >
        <UploadCloud className="h-5 w-5 text-slate-muted" strokeWidth={1.5} />
        {file ? (
          <p className="text-caption text-cohere-ink">
            {file.name} <span className="text-slate-muted">· {formatBytes(file.size)}</span>
          </p>
        ) : (
          <>
            <p className="text-caption text-cohere-ink">Drop a file here or click to browse</p>
            <p className="text-micro text-slate-muted">JPG, PNG, WebP, HEIC, or PDF, up to 10 MB</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.pdf"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </div>
      <button onClick={submit} disabled={busy || !file} className="btn-primary mt-2">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck2 className="h-4 w-4" />}
        {busy ? "Uploading…" : "Submit document"}
      </button>
      {error && <p className="mt-2 text-micro text-error-red">{error}</p>}
    </div>
  );
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * QR handoff — snap the photo with your phone camera, desktop live-updates.
 *
 * Apple Pay-style reveal: selecting the tab immediately mints the phone link
 * and the QR sheet springs up from the trigger (scale 0.9→1 with a ~12px rise
 * and slight overshoot). Inline anchored sheet — no backdrop, no modal. The
 * app-wide MotionConfig (reducedMotion="user") collapses the spring to a fade
 * for users who prefer reduced motion.
 */
function PhoneHandoffPanel({
  token,
  credentialId,
  onVerified,
}: {
  token: string;
  credentialId: string;
  onVerified: (level: VerificationLevel, badge: string, review: boolean) => void;
}) {
  const [qr, setQr] = useState<string | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [landed, setLanded] = useState(false);
  const [landedBadge, setLandedBadge] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setError(null);
    try {
      const link = await createPhoneLink(token, credentialId);
      const dataUrl = await QRCode.toDataURL(link.url, { width: 240, margin: 1 });
      setQr(dataUrl);
      setLinkUrl(link.url);
      setCopied(false);
      setExpiresAt(link.expires_at ? Date.parse(link.expires_at) : null);
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const s = await getPhoneStatus(token, credentialId);
          if (s.landed) {
            stopPolling();
            setLanded(true);
            setLandedBadge(s.verification_level >= 1 ? s.badge : null);
            onVerified(s.verification_level, s.badge, s.needs_review);
          }
        } catch {
          // transient poll failure — keep trying until the link expires
        }
      }, 4000);
    } catch {
      setError("Could not create the phone link. Try again.");
    } finally {
      busyRef.current = false;
    }
  }, [token, credentialId, onVerified, stopPolling]);

  // Selecting the tab IS the intent — mint the link straight away.
  useEffect(() => {
    start();
    return stopPolling;
  }, [start, stopPolling]);

  useEffect(() => () => { if (copiedTimer.current) clearTimeout(copiedTimer.current); }, []);

  // Subtle expiry countdown while the QR sheet is visible.
  useEffect(() => {
    if (!expiresAt || landed) return;
    const tick = () => {
      setSecondsLeft(Math.max(0, Math.round((expiresAt - Date.now()) / 1000)));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt, landed]);

  const expired = secondsLeft === 0;
  useEffect(() => {
    if (expired) stopPolling();
  }, [expired, stopPolling]);

  async function copyLink() {
    if (!linkUrl) return;
    try {
      await navigator.clipboard.writeText(linkUrl);
      setCopied(true);
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the QR path still works */
    }
  }

  if (landed) {
    return (
      <div className="mt-3 rounded-[10px] border border-cohere-green/30 bg-wash-green p-4 text-caption text-cohere-ink">
        <div className="flex items-center gap-2 font-semibold">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-cohere-green" /> Photo received
        </div>
        <p className="mt-1 text-micro">
          {landedBadge
            ? `Verified → ${landedBadge}`
            : "Sent to SkillPointe review. We'll badge it once confirmed."}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-3">
        <p className="text-micro text-error-red">{error}</p>
        <button onClick={start} className="btn-secondary mt-2">
          <Smartphone className="h-4 w-4" /> Try again
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <p className="text-micro text-slate-muted">
        No file on this computer? Scan the code with your phone camera. It opens a page to
        snap a photo of the document.
      </p>
      {!qr ? (
        <p className="mt-2 flex items-center gap-1.5 text-micro text-slate-muted">
          <Loader2 className="h-3 w-3 animate-spin" /> Preparing your phone link…
        </p>
      ) : (
        <motion.div
          initial={{ opacity: 0, scale: 0.9, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 26, mass: 0.9 }}
          style={{ transformOrigin: "top left" }}
          className="mt-2 flex w-fit items-start gap-4 rounded-[14px] border border-hairline bg-white p-4 shadow-float"
        >
          <div className="shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={qr} alt="QR code that opens the upload page on your phone" className="h-[132px] w-[132px]" />
            {!expired && linkUrl && (
              <button
                type="button"
                onClick={copyLink}
                className="mt-1.5 block w-full text-center text-micro text-slate underline transition-colors hover:text-cohere-ink"
              >
                {copied ? "Copied" : "Can't scan? Copy link"}
              </button>
            )}
          </div>
          <div className="max-w-[26ch] text-caption text-slate">
            <p className="font-medium text-cohere-ink">Scan with your phone camera</p>
            <p className="mt-1 text-micro">
              It opens a page to snap the photo. This page updates automatically once the
              photo lands.
            </p>
            {expired ? (
              <button onClick={start} className="btn-secondary mt-2">
                Get a new code
              </button>
            ) : (
              <>
                <p className="mt-2 flex items-center gap-1.5 text-micro text-slate-muted">
                  <Loader2 className="h-3 w-3 animate-spin" /> Waiting for your phone…
                </p>
                {secondsLeft !== null && (
                  <p className="mt-1 text-micro text-slate-muted tabular-nums">
                    Link expires in {formatCountdown(secondsLeft)}
                  </p>
                )}
              </>
            )}
          </div>
        </motion.div>
      )}
    </div>
  );
}
