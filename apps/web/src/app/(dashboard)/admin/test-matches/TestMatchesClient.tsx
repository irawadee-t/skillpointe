"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search,
  ChevronDown,
  MapPin,
  Briefcase,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  ChevronUp,
  User,
  GraduationCap,
  Calendar,
  Navigation,
  Target,
  Building2,
  Star,
  Wrench,
  FileText,
} from "lucide-react";

import type {
  TestApplicantListItem,
  TestApplicantMatches,
  TestMatchSummary,
} from "@/lib/api/admin";
import { fetchTestApplicantMatches } from "@/lib/api/admin";
import { PageHeader, MonoLabel, Reveal, Stagger, StaggerItem } from "@/components/ui";

interface Props {
  applicants: TestApplicantListItem[];
  fetchError: string | null;
  accessToken: string;
}

export function TestMatchesClient({ applicants, fetchError, accessToken }: Props) {
  const [search, setSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [matchData, setMatchData] = useState<TestApplicantMatches | null>(null);
  const [loading, setLoading] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const filtered = applicants.filter((a) => {
    if (!search) return true;
    const q = search.toLowerCase();
    const name = `${a.first_name ?? ""} ${a.last_name ?? ""}`.toLowerCase();
    return (
      name.includes(q) ||
      (a.state ?? "").toLowerCase().includes(q) ||
      (a.program ?? "").toLowerCase().includes(q) ||
      (a.family_code ?? "").toLowerCase().includes(q)
    );
  });

  const selected = applicants.find((a) => a.id === selectedId);

  const loadMatches = useCallback(
    async (id: string) => {
      setLoading(true);
      setMatchError(null);
      try {
        const data = await fetchTestApplicantMatches(id, accessToken);
        setMatchData(data);
      } catch {
        setMatchError("Failed to load matches for this applicant.");
        setMatchData(null);
      } finally {
        setLoading(false);
      }
    },
    [accessToken],
  );

  const selectApplicant = (id: string) => {
    setSelectedId(id);
    setDropdownOpen(false);
    setSearch("");
    loadMatches(id);
  };

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (fetchError) {
    return (
      <main className="py-8">
        <div className="page-shell">
          <p className="text-body text-studio-maroon">{fetchError}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="py-8">
    <div className="page-shell space-y-6">
      <PageHeader
        eyebrow="Diagnostics"
        title="Test Applicant Matches"
        lead={`Select any applicant to preview their match results. ${applicants.length} applicants available.`}
      />

      {/* Applicant Switcher */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="w-full flex items-center justify-between bg-white border border-border-light rounded-md px-4 py-3 text-left hover:border-cohere-ink/25 transition-colors"
        >
          {selected ? (
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-full bg-wash-blue flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-cohere-blue" />
              </div>
              <div className="min-w-0">
                <div className="text-body font-semibold text-cohere-ink truncate">
                  {selected.first_name} {selected.last_name}
                </div>
                <div className="text-caption text-slate truncate">
                  {selected.state ?? "—"}, {selected.family_code ?? "—"}, {selected.eligible_count} eligible, {selected.near_fit_count} near-fit
                </div>
              </div>
            </div>
          ) : (
            <span className="text-body text-slate">Select an applicant...</span>
          )}
          <ChevronDown className={`w-4 h-4 text-slate-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
        </button>

        {dropdownOpen && (
          <div className="absolute z-50 mt-1 w-full bg-white border border-border-light rounded-md shadow-lg max-h-[420px] overflow-hidden">
            <div className="p-2 border-b border-hairline">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-slate-muted" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, state, program..."
                  className="input-cohere pl-8 pr-3 py-2 text-body"
                  autoFocus
                />
              </div>
            </div>
            <div className="overflow-y-auto max-h-[340px] divide-y divide-hairline">
              {filtered.length === 0 ? (
                <p className="text-body text-slate py-4 text-center">No applicants found</p>
              ) : (
                filtered.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => selectApplicant(a.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-stone/50 transition-colors ${
                      a.id === selectedId ? "bg-wash-blue" : ""
                    }`}
                  >
                    <div className="w-7 h-7 rounded-full bg-stone flex items-center justify-center flex-shrink-0 text-micro font-medium text-slate">
                      {(a.first_name?.[0] ?? "?")}{(a.last_name?.[0] ?? "")}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-caption font-medium text-cohere-ink truncate">
                        {a.first_name} {a.last_name}
                      </div>
                      <div className="text-micro text-slate truncate">
                        {a.state ?? "—"}, {(a.program ?? "").slice(0, 35)}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {a.eligible_count > 0 && (
                        <span className="text-micro px-1.5 py-0.5 rounded-sm bg-wash-green text-cohere-green font-medium tabular-nums">
                          {a.eligible_count}
                        </span>
                      )}
                      <span className="text-micro px-1.5 py-0.5 rounded-sm bg-studio-maroon/10 text-studio-maroon font-medium tabular-nums">
                        {a.near_fit_count}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Match Results */}
      {!selectedId && (
        <div className="text-center py-20 text-slate">
          <Target className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-body">Select an applicant above to see their matches</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-20 gap-2 text-slate">
          <div className="w-5 h-5 border-2 border-hairline border-t-cohere-ink rounded-full animate-spin" />
          <span className="text-body">Loading matches...</span>
        </div>
      )}

      {matchError && (
        <div className="bg-studio-maroon/10 text-cohere-ink px-4 py-3 rounded-md text-caption">{matchError}</div>
      )}

      {matchData && !loading && (
        <div>
          {/* Profile Card — deep-green panel */}
          <Reveal className="card-green p-6 mb-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-feature font-display text-white">
                  {matchData.profile.first_name} {matchData.profile.last_name}
                </h2>
                <p className="text-body text-white/70 mt-0.5">{matchData.profile.program}</p>
              </div>
              <div className="flex items-center gap-4 flex-wrap text-caption text-white/70">
                <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5 text-white/60" />{matchData.profile.city}, {matchData.profile.state}</span>
                <span className="flex items-center gap-1"><Wrench className="w-3.5 h-3.5 text-white/60" />{matchData.profile.family_code ?? "—"}</span>
                <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5 text-white/60" />{matchData.profile.expected_completion_date ?? "—"}</span>
                <span className="flex items-center gap-1"><Navigation className="w-3.5 h-3.5 text-white/60" />Travel: {matchData.profile.travel_preference ?? "—"}</span>
                <span className="flex items-center gap-1">Reloc: {matchData.profile.relocation_preference ?? "—"}</span>
              </div>
            </div>
            <div className="flex gap-3 mt-5 flex-wrap">
              <div className="px-4 py-2.5 bg-white/10 rounded-sm">
                <div className="text-body-lg font-display text-white tabular-nums">{matchData.total_eligible}</div>
                <MonoLabel className="text-white/60">Eligible</MonoLabel>
              </div>
              <div className="px-4 py-2.5 bg-white/10 rounded-sm">
                <div className="text-body-lg font-display text-white tabular-nums">{matchData.total_near_fit}</div>
                <MonoLabel className="text-white/60">Near-fit</MonoLabel>
              </div>
              <div className="px-4 py-2.5 bg-white/10 rounded-sm">
                <div className="text-body-lg font-display text-white tabular-nums">{matchData.total_eligible + matchData.total_near_fit}</div>
                <MonoLabel className="text-white/60">Total actionable</MonoLabel>
              </div>
            </div>
          </Reveal>

          {/* Eligible */}
          {matchData.eligible_matches.length > 0 && (
            <div className="mb-6">
              <h3 className="text-feature font-display text-cohere-ink mb-3 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-cohere-green" />
                Eligible matches ({matchData.total_eligible})
              </h3>
              <Stagger className="space-y-2">
                {matchData.eligible_matches.map((m) => (
                  <StaggerItem key={m.match_id}>
                    <MatchCard match={m} />
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          )}

          {/* Near-fit */}
          {matchData.near_fit_matches.length > 0 && (
            <div>
              <h3 className="text-feature font-display text-cohere-ink mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-studio-maroon" />
                Near-fit matches ({matchData.total_near_fit})
              </h3>
              <Stagger className="space-y-2">
                {matchData.near_fit_matches.map((m) => (
                  <StaggerItem key={m.match_id}>
                    <MatchCard match={m} />
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          )}

          {matchData.total_eligible === 0 && matchData.total_near_fit === 0 && (
            <div className="text-center py-12 text-slate">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-body">No actionable matches for this applicant</p>
            </div>
          )}
        </div>
      )}
    </div>
    </main>
  );
}


function MatchCard({ match: m }: { match: TestMatchSummary }) {
  const [expanded, setExpanded] = useState(false);

  const labelColor: Record<string, string> = {
    strong_fit: "bg-wash-green text-cohere-green border-cohere-green/20",
    good_fit: "bg-wash-blue text-cohere-blue border-cohere-blue/20",
    moderate_fit: "bg-studio-maroon/10 text-studio-maroon border-studio-maroon-soft",
    low_fit: "bg-stone text-slate border-hairline",
  };

  const labelText: Record<string, string> = {
    strong_fit: "Strong fit",
    good_fit: "Good fit",
    moderate_fit: "Moderate fit",
    low_fit: "Low fit",
  };

  return (
    <div className="bg-white border border-border-light rounded-md overflow-hidden transition-colors hover:border-cohere-ink/25">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-stone/40 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-body font-semibold text-cohere-ink truncate">{m.job_title}</span>
              {m.match_label && (
                <span className={`text-micro px-2 py-0.5 rounded-sm border font-medium ${labelColor[m.match_label] ?? "bg-stone text-slate border-hairline"}`}>
                  {labelText[m.match_label] ?? m.match_label}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-caption text-slate mt-1">
              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{m.employer_name}</span>
              <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{m.job_city ?? "—"}, {m.job_state ?? "—"}</span>
              {m.work_setting && <span className="capitalize">{m.work_setting.replace("_", " ")}</span>}
              {m.experience_level && <span className="px-1.5 py-0.5 bg-stone rounded-sm text-slate">{m.experience_level}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
          <span className="inline-flex items-center justify-center min-w-[3rem] rounded-sm bg-cohere-green px-2.5 py-1.5 text-body font-display text-white tabular-nums">
            {m.policy_adjusted_score?.toFixed(1) ?? "—"}
          </span>
          {expanded ? <ChevronUp className="w-4 h-4 text-slate" /> : <ChevronDown className="w-4 h-4 text-slate" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-hairline px-4 py-3 bg-stone/40">
          <div className="grid grid-cols-2 gap-4 text-micro">
            {/* Strengths */}
            {m.top_strengths.length > 0 && (
              <div>
                <h4 className="font-medium text-cohere-green mb-1 flex items-center gap-1">
                  <Star className="w-3 h-3" /> Strengths
                </h4>
                <ul className="space-y-0.5 text-slate">
                  {m.top_strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Gaps */}
            {m.top_gaps.length > 0 && (
              <div>
                <h4 className="font-medium text-studio-maroon mb-1 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Gaps
                </h4>
                <ul className="space-y-0.5 text-slate">
                  {m.top_gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {m.recommended_next_step && (
            <div className="mt-3 text-micro text-slate">
              <span className="font-medium text-ink">Next step: </span>{m.recommended_next_step}
            </div>
          )}

          {/* Job description */}
          {m.description_raw && (
            <details className="mt-3">
              <summary className="text-micro font-medium text-slate cursor-pointer hover:text-ink flex items-center gap-1">
                <FileText className="w-3 h-3" /> Job description
              </summary>
              <div className="mt-2 text-micro text-slate whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto bg-white p-3 rounded-sm border border-hairline">
                {m.description_raw}
              </div>
            </details>
          )}

          {m.source_url && (
            <div className="mt-3">
              <a
                href={m.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-micro text-cohere-blue hover:underline"
              >
                View original posting <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
