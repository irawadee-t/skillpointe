"use client";

import { useEffect, useState } from "react";
import { Mail, MessageSquare, Globe, Loader2, Check } from "lucide-react";

import { Preferences, getPreferences, patchPreferences } from "@/lib/api/robustness";
import { MonoLabel } from "@/components/ui";

export function PreferencesPanel({ token }: { token: string }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPreferences(token).then(setPrefs).catch((e: Error) => setErr(e.message));
  }, [token]);

  async function toggle<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    if (!prefs) return;
    setSaving(String(key)); setErr(null); setSaved(false);
    try {
      const next = await patchPreferences(token, { [key]: value } as Partial<Preferences>);
      setPrefs(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(null);
    }
  }

  if (!prefs) {
    return <div className="text-caption text-slate-muted">Loading preferences…</div>;
  }

  return (
    <div className="space-y-4">
      {err && <p className="text-caption text-studio-maroon">{err}</p>}

      <Row
        icon={Mail}
        label="Email: new matches and messages"
        sub="Short digest, never every event."
        on={prefs.email_opt_in}
        saving={saving === "email_opt_in"}
        onChange={(v) => toggle("email_opt_in", v)}
      />
      <Row
        icon={MessageSquare}
        label="Text: time-sensitive things only"
        sub="Interview times, employer messages, new match near you. Standard message rates apply."
        on={prefs.sms_opt_in}
        saving={saving === "sms_opt_in"}
        onChange={(v) => toggle("sms_opt_in", v)}
      />

      <div className="rounded-xl border border-hairline bg-white p-4">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-slate-muted" />
          <MonoLabel>Language / Idioma</MonoLabel>
        </div>
        <div className="mt-3 inline-flex overflow-hidden rounded-full border border-hairline">
          {(["en", "es"] as const).map((locale) => (
            <button
              key={locale}
              onClick={() => toggle("preferred_locale", locale)}
              disabled={saving === "preferred_locale"}
              className={`px-4 py-1.5 text-caption font-medium transition-colors ${
                prefs.preferred_locale === locale
                  ? "bg-ink text-canvas"
                  : "text-slate hover:text-cohere-ink"
              }`}
            >
              {locale === "en" ? "English" : "Español"}
            </button>
          ))}
        </div>
      </div>

      {saved && (
        <div className="inline-flex items-center gap-1 text-caption text-cohere-green">
          <Check className="h-3.5 w-3.5" /> Saved
        </div>
      )}
    </div>
  );
}

function Row({
  icon: Icon, label, sub, on, saving, onChange,
}: {
  icon: typeof Mail; label: string; sub: string; on: boolean; saving: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-hairline bg-white p-4">
      <Icon className="mt-0.5 h-4 w-4 text-slate-muted" strokeWidth={1.75} />
      <div className="flex-1">
        <div className="font-medium text-cohere-ink">{label}</div>
        <div className="mt-0.5 text-caption text-slate">{sub}</div>
      </div>
      <div className="relative">
        <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" disabled={saving} />
        <div className="h-5 w-9 rounded-full bg-stone transition-colors peer-checked:bg-cohere-green" />
        <div className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${on ? "translate-x-4" : ""}`} />
        {saving && <Loader2 className="absolute -right-6 top-0.5 h-4 w-4 animate-spin text-slate-muted" />}
      </div>
    </label>
  );
}
