"use client";

import { useState } from "react";
import Link from "next/link";
import { Eye, Cpu, Share2, Check, Loader2 } from "lucide-react";

import {
  ConsentSetting,
  DATA_CATEGORIES,
  DATA_CATEGORY_LABELS,
  REQUESTER_CATEGORIES,
  REQUESTER_LABELS,
  updateConsent,
} from "@/lib/api/consent";
import { PageHeader, MonoLabel, Breadcrumb } from "@/components/ui";
import { cn } from "@/lib/utils";

type SaveState = "idle" | "saving" | "saved" | "error";

export function ConsentClient({
  initial,
  token,
}: {
  initial: ConsentSetting[];
  token: string;
}) {
  // Index by category so ordering follows DATA_CATEGORIES regardless of API order.
  const byCat = new Map(initial.map((s) => [s.data_category, s]));
  const [settings, setSettings] = useState<Record<string, ConsentSetting>>(
    Object.fromEntries(
      DATA_CATEGORIES.map((c) => [
        c,
        byCat.get(c) ?? { data_category: c, display: false, internal_use: true, external_sharing: [] },
      ]),
    ),
  );
  const [save, setSave] = useState<Record<string, SaveState>>({});

  async function persist(cat: string, next: ConsentSetting) {
    const prev = settings[cat];
    setSettings((s) => ({ ...s, [cat]: next }));         // optimistic
    setSave((s) => ({ ...s, [cat]: "saving" }));
    try {
      const saved = await updateConsent(token, cat, {
        display: next.display,
        internal_use: next.internal_use,
        external_sharing: next.external_sharing,
      });
      setSettings((s) => ({ ...s, [cat]: saved }));
      setSave((s) => ({ ...s, [cat]: "saved" }));
      setTimeout(() => setSave((s) => (s[cat] === "saved" ? { ...s, [cat]: "idle" } : s)), 1800);
    } catch {
      setSettings((s) => ({ ...s, [cat]: prev }));        // revert
      setSave((s) => ({ ...s, [cat]: "error" }));
    }
  }

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-4xl px-5 space-y-6">
        <Breadcrumb items={[
          { label: "Credentials", href: "/applicant/credentials" },
          { label: "Data sharing" },
        ]} />
        <PageHeader
          eyebrow="Your data"
          title="Data sharing & consent"
          lead="You decide what's shown, what SKILLED Nation can use, and who receives each part of your profile. Nothing goes out unless you turn it on. Every change is recorded."
        />

        {/* Scope legend */}
        <div className="rounded-md bg-stone p-5">
          <MonoLabel className="mb-3 block">The three controls</MonoLabel>
          <div className="grid gap-3 sm:grid-cols-3">
            <Legend icon={Eye} title="Display" body="Show this on your public SKILLED profile." />
            <Legend icon={Cpu} title="Platform use" body="Let SKILLED use it for matching & insights." />
            <Legend icon={Share2} title="External sharing" body="Choose which kinds of organizations may receive it." />
          </div>
        </div>

        {/* Per-category cards */}
        <div className="space-y-3">
          {DATA_CATEGORIES.map((cat) => (
            <CategoryCard
              key={cat}
              setting={settings[cat]}
              saveState={save[cat] ?? "idle"}
              onChange={(next) => persist(cat, next)}
            />
          ))}
        </div>

        <p className="text-caption text-slate-muted">
          External sharing is gated per organization type.
          Consent changes are written to a signed, append-only record for your protection.
        </p>
      </div>
    </main>
  );
}

function Legend({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Eye;
  title: string;
  body: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-cohere-green" strokeWidth={1.75} />
      <div>
        <div className="text-body font-medium text-cohere-ink">{title}</div>
        <div className="text-caption text-slate">{body}</div>
      </div>
    </div>
  );
}

function CategoryCard({
  setting,
  saveState,
  onChange,
}: {
  setting: ConsentSetting;
  saveState: SaveState;
  onChange: (next: ConsentSetting) => void;
}) {
  const busy = saveState === "saving";
  const cat = setting.data_category;
  const sharingOn = setting.external_sharing.length > 0;

  function toggleRequester(req: string) {
    const has = setting.external_sharing.includes(req);
    onChange({
      ...setting,
      external_sharing: has
        ? setting.external_sharing.filter((r) => r !== req)
        : [...setting.external_sharing, req],
    });
  }

  return (
    <div className="rounded-md border border-border-light bg-white p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
          {DATA_CATEGORY_LABELS[cat] ?? cat}
        </h3>
        <SaveBadge state={saveState} />
      </div>

      <div className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
        <Switch
          label="Show on profile"
          checked={setting.display}
          disabled={busy}
          onChange={(v) => onChange({ ...setting, display: v })}
        />
        <Switch
          label="Allow platform use"
          checked={setting.internal_use}
          disabled={busy}
          onChange={(v) => onChange({ ...setting, internal_use: v })}
        />
      </div>

      <div className="mt-4 border-t border-hairline pt-4">
        <div className="flex items-center gap-2">
          <Share2 className="h-3.5 w-3.5 text-slate-muted" />
          <span className="text-caption font-medium text-ink">Share externally with</span>
          {!sharingOn && <span className="text-micro text-slate-muted">· off (private)</span>}
        </div>
        <div className="mt-2.5 flex flex-wrap gap-2">
          {REQUESTER_CATEGORIES.map((req) => {
            const on = setting.external_sharing.includes(req);
            return (
              <button
                key={req}
                type="button"
                disabled={busy}
                onClick={() => toggleRequester(req)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-caption transition-colors disabled:opacity-50",
                  on
                    ? "border-cohere-green bg-cohere-green text-white"
                    : "border-hairline bg-transparent text-ink hover:border-cohere-ink",
                )}
              >
                {on && <Check className="h-3 w-3" />}
                {REQUESTER_LABELS[req] ?? req}
              </button>
            );
          })}
        </div>
      </div>

      {saveState === "error" && (
        <p className="mt-3 text-micro text-error-red">Couldn&apos;t save that change. Please retry.</p>
      )}
    </div>
  );
}

function Switch({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="group flex items-center gap-2.5 disabled:opacity-50"
    >
      <span
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200",
          checked ? "bg-cohere-green" : "bg-hairline",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform duration-200",
            checked ? "translate-x-[18px]" : "translate-x-0.5",
          )}
        />
      </span>
      <span className="text-caption text-ink">{label}</span>
    </button>
  );
}

function SaveBadge({ state }: { state: SaveState }) {
  if (state === "saving")
    return (
      <span className="inline-flex items-center gap-1 text-micro text-slate-muted">
        <Loader2 className="h-3 w-3 animate-spin" /> Saving…
      </span>
    );
  if (state === "saved")
    return (
      <span className="inline-flex items-center gap-1 text-micro text-cohere-green">
        <Check className="h-3 w-3" /> Saved
      </span>
    );
  return null;
}
