"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Search,
  ChevronDown,
  MapPin,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  ChevronUp,
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
import { PageHeader, Reveal, Stagger, StaggerItem } from "@/components/ui";
import { MatchLabel } from "@/components/matches/MatchLabel";
import {
  RELOCATION_LABELS, TRAVEL_LABELS, WORK_SETTING_LABELS, humanizeEnum,
} from "@/lib/humanize";

interface Props {
  applicants: TestApplicantListItem[];
  fetchError: string | null;
  accessToken: string;
}

/** "City, ST" with honest fallbacks — never "—, —". */
function place(city?: string | null, state?: string | null): string {
  const s = [city, state].filter(Boolean).join(", ");
  return s || "Location not set";
}

export function TestMatchesClient({ applicants, fetchError, accessToken }: Props) {
  const [search, setSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);
  const [matchData, setMatchData] = useState<TestApplicantMatches | null>(null);
  const [loading, setLoading] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => { setActiveIdx(0); }, [search, dropdownOpen]);

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

  // Listbox keyboard contract: arrows move the active option, Enter selects,
  // Escape closes and returns focus to the trigger.
  function onListKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = filtered[activeIdx];
      if (hit) selectApplicant(hit.id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setDropdownOpen(false);
    }
  }

  useEffect(() => {
    // Keep the active option in view while arrowing.
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${activeIdx}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

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
        title="Test matches"
        lead={`Select any applicant to preview their match results. ${applicants.length} applicants available.`}
      />

      {/* Applicant switcher — combobox with listbox semantics */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          aria-haspopup="listbox"
          aria-expanded={dropdownOpen}
          className="w-full flex items-center justify-between bg-white border border-border-light rounded-md px-4 py-3 text-left hover:border-cohere-ink/25 transition-colors"
        >
          {selected ? (
            <div className="flex items-center gap-3 min-w-0">
              <div className="min-w-0">
                <div className="text-body font-semibold text-cohere-ink truncate">
                  {selected.first_name} {selected.last_name}
                </div>
                <div className="text-caption text-slate truncate">
                  {[selected.state, selected.family_code].filter(Boolean).join(", ") || "No state or trade set"}
                  {" · "}{selected.eligible_count} eligible · {selected.near_fit_count} near fit
                </div>
              </div>
            </div>
          ) : (
            <span className="text-body text-slate">Select an applicant…</span>
          )}
          <ChevronDown className={`w-4 h-4 text-slate-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`} aria-hidden />
        </button>

        {dropdownOpen && (
          <div className="absolute z-50 mt-1 w-full bg-white border border-border-light rounded-md shadow-float max-h-[420px] overflow-hidden">
            <div className="p-2 border-b border-hairline">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-slate-muted" aria-hidden />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={onListKeyDown}
                  placeholder="Search by name, state, program…"
                  role="combobox"
                  aria-expanded={dropdownOpen}
                  aria-controls="applicant-listbox"
                  aria-activedescendant={filtered[activeIdx] ? `applicant-opt-${filtered[activeIdx].id}` : undefined}
                  className="input-cohere pl-8 pr-3 py-2 text-body"
                  autoFocus
                />
              </div>
            </div>
            <div
              id="applicant-listbox"
              role="listbox"
              aria-label="Applicants"
              ref={listRef}
              className="overflow-y-auto max-h-[340px] divide-y divide-hairline"
            >
              {filtered.length === 0 ? (
                <p className="text-body text-slate py-4 text-center">
                  {search ? <>No results for &ldquo;{search}&rdquo;</> : "No applicants found"}
                </p>
              ) : (
                filtered.map((a, idx) => (
                  <button
                    key={a.id}
                    id={`applicant-opt-${a.id}`}
                    role="option"
                    aria-selected={a.id === selectedId}
                    data-idx={idx}
                    onClick={() => selectApplicant(a.id)}
                    onMouseEnter={() => setActiveIdx(idx)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                      idx === activeIdx ? "bg-stone/60" : a.id === selectedId ? "bg-wash-blue" : "hover:bg-stone/50"
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
                        {[a.state, (a.program ?? "").slice(0, 35)].filter(Boolean).join(", ") || "No profile details"}
                      </div>
                    </div>
                    {/* Labeled count pills — no bare mystery numbers. */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {a.eligible_count > 0 && (
                        <span className="text-micro px-1.5 py-0.5 rounded-sm bg-cohere-green text-white font-medium tabular-nums">
                          {a.eligible_count} eligible
                        </span>
                      )}
                      <span className="text-micro px-1.5 py-0.5 rounded-sm bg-studio-maroon text-white font-medium tabular-nums">
                        {a.near_fit_count} near fit
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
          {/* Profile Card — white sheet */}
          <Reveal className="rounded-[14px] border border-hairline bg-white p-6 mb-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="font-display text-[1.25rem] text-ink">
                  {matchData.profile.first_name} {matchData.profile.last_name}
                </h2>
                <p className="text-body text-slate mt-0.5">{matchData.profile.program}</p>
              </div>
              <div className="flex items-center gap-4 flex-wrap text-caption text-slate">
                <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5 text-slate-muted" aria-hidden />{place(matchData.profile.city, matchData.profile.state)}</span>
                <span className="flex items-center gap-1"><Wrench className="w-3.5 h-3.5 text-slate-muted" aria-hidden />{matchData.profile.family_code ?? "No trade set"}</span>
                <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5 text-slate-muted" aria-hidden />{matchData.profile.expected_completion_date ?? "No completion date"}</span>
                <span className="flex items-center gap-1"><Navigation className="w-3.5 h-3.5 text-slate-muted" aria-hidden />{humanizeEnum(matchData.profile.travel_preference ?? "unknown", TRAVEL_LABELS)}</span>
                <span className="flex items-center gap-1">{humanizeEnum(matchData.profile.relocation_preference ?? "unknown", RELOCATION_LABELS)}</span>
              </div>
            </div>
            <p className="mt-5 text-body text-slate">
              <span className="font-medium text-ink tabular-nums">{matchData.total_eligible}</span> eligible
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium text-ink tabular-nums">{matchData.total_near_fit}</span> near fit
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium text-ink tabular-nums">{matchData.total_eligible + matchData.total_near_fit}</span> actionable in total
            </p>
          </Reveal>

          {/* Eligible */}
          {matchData.eligible_matches.length > 0 && (
            <div className="mb-6">
              <h3 className="text-feature font-display text-cohere-ink mb-3 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-cohere-green" aria-hidden />
                Eligible matches ({matchData.total_eligible})
              </h3>
              <MatchList matches={matchData.eligible_matches} />
            </div>
          )}

          {/* Near-fit */}
          {matchData.near_fit_matches.length > 0 && (
            <div>
              <h3 className="text-feature font-display text-cohere-ink mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-studio-maroon" aria-hidden />
                Near-fit matches ({matchData.total_near_fit})
              </h3>
              <MatchList matches={matchData.near_fit_matches} />
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

/**
 * Dedupe visually-identical rows (same title + employer + location): the
 * highest-scoring copy renders once with an "×N postings" affix instead of
 * N indistinguishable cards.
 */
function MatchList({ matches }: { matches: TestMatchSummary[] }) {
  const deduped = useMemo(() => {
    const seen = new Map<string, { match: TestMatchSummary; copies: number }>();
    for (const m of matches) {
      const key = [m.job_title, m.employer_name, m.job_city, m.job_state].join("|");
      const hit = seen.get(key);
      if (hit) hit.copies += 1;
      else seen.set(key, { match: m, copies: 1 });
    }
    return Array.from(seen.values());
  }, [matches]);

  return (
    <Stagger className="space-y-2">
      {deduped.map(({ match, copies }) => (
        <StaggerItem key={match.match_id}>
          <MatchCard match={match} copies={copies} />
        </StaggerItem>
      ))}
    </Stagger>
  );
}

function MatchCard({ match: m, copies = 1 }: { match: TestMatchSummary; copies?: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white border border-border-light rounded-md overflow-hidden transition-colors hover:border-cohere-ink/25">
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-stone/40 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-body font-semibold text-cohere-ink truncate">{m.job_title}</span>
              {m.match_label && <MatchLabel label={m.match_label} />}
              {copies > 1 && (
                <span className="text-micro text-slate-muted" title="Identical postings collapsed">
                  ×{copies} postings
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-caption text-slate mt-1">
              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" aria-hidden />{m.employer_name}</span>
              <span className="flex items-center gap-1"><MapPin className="w-3 h-3" aria-hidden />{place(m.job_city, m.job_state)}</span>
              {m.work_setting && <span>{humanizeEnum(m.work_setting, WORK_SETTING_LABELS)}</span>}
              {m.experience_level && <span className="px-1.5 py-0.5 bg-stone rounded-sm text-slate">{humanizeEnum(m.experience_level)}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
          <span className="inline-flex items-center justify-center min-w-[3rem] rounded-sm bg-cohere-green px-2.5 py-1.5 text-body font-display text-white tabular-nums" title="Policy-adjusted score">
            {m.policy_adjusted_score?.toFixed(1) ?? "—"}
          </span>
          {expanded ? <ChevronUp className="w-4 h-4 text-slate" aria-hidden /> : <ChevronDown className="w-4 h-4 text-slate" aria-hidden />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-hairline px-4 py-3 bg-stone/40">
          <div className="grid grid-cols-2 gap-4 text-micro">
            {/* Strengths */}
            {m.top_strengths.length > 0 && (
              <div>
                <h4 className="font-medium text-cohere-green mb-1 flex items-center gap-1">
                  <Star className="w-3 h-3" aria-hidden /> Strengths
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
                  <AlertTriangle className="w-3 h-3" aria-hidden /> Gaps
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
                <FileText className="w-3 h-3" aria-hidden /> Job description
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
                View original posting <ExternalLink className="w-3 h-3" aria-hidden />
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
