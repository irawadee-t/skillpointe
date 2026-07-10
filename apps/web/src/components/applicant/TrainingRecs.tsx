"use client";

import { useEffect, useState } from "react";
import { GraduationCap, ExternalLink, Loader2 } from "lucide-react";

import { MatchTraining, trainingForMatch } from "@/lib/api/robustness";
import { MonoLabel } from "@/components/ui";

export function TrainingRecs({ token, matchId }: { token: string; matchId: string }) {
  const [data, setData] = useState<MatchTraining | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    trainingForMatch(token, matchId).then(setData).catch((e: Error) => setErr(e.message));
  }, [token, matchId]);

  if (err) return null;
  if (!data) return (
    <div className="flex items-center gap-2 text-caption text-slate-muted">
      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking for training pathways…
    </div>
  );
  if (!data.recommendations.length) return null;

  return (
    <section className="rounded-xl border border-cohere-blue/30 bg-wash-blue p-6">
      <div className="flex items-center gap-2">
        <GraduationCap className="h-5 w-5 text-cohere-blue" strokeWidth={1.75} />
        <h3 className="font-display text-feature text-cohere-ink">One credential away</h3>
      </div>
      <p className="mt-2 text-body text-slate">
        {data.recommendations.length === 1
          ? "This program at a partner school gets you the missing credential"
          : `These ${data.recommendations.length} partner-school programs get you the missing credential`}
        {data.missing_credentials.length ? ` (${data.missing_credentials.join(", ").replace(/_/g, " ")})` : ""}.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {data.recommendations.map((p) => (
          <a key={p.id} href={p.url ?? p.provider_url ?? "#"}
             target={p.url || p.provider_url ? "_blank" : undefined}
             rel="noopener noreferrer"
             className="group rounded-lg border border-hairline bg-white p-4 transition-shadow hover:shadow-[0_6px_20px_-10px_rgba(12,10,9,0.14)]">
            <MonoLabel className="text-cohere-blue">{p.credential_key.replace(/_/g, " ")}</MonoLabel>
            <div className="mt-1 font-medium text-cohere-ink">{p.name}</div>
            <div className="mt-0.5 text-caption text-slate">{p.provider_name}</div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-micro text-slate">
              {p.duration_weeks && <span>{p.duration_weeks} weeks</span>}
              {p.cost_range && <span>{p.cost_range}</span>}
              {p.format && <span>{p.format.replace("_", "-")}</span>}
              {(p.city || p.state) && <span>{[p.city, p.state].filter(Boolean).join(", ")}</span>}
            </div>
            {(p.url || p.provider_url) && (
              <div className="mt-2 inline-flex items-center gap-1 text-caption text-cohere-blue">
                Program details <ExternalLink className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
              </div>
            )}
          </a>
        ))}
      </div>
    </section>
  );
}
