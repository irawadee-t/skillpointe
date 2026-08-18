#!/usr/bin/env python3
"""
map_onet.py — deterministic job-title → O*NET-SOC occupation mapper.

Gives the platform's hand-rolled taxonomy an external ground truth by
mapping every active job posting's raw title to an O*NET-SOC code using
the official O*NET database text distribution (Occupation Data +
Alternate Titles + Job Zones). Pure deterministic string matching — no
LLM calls, no network calls, no new dependencies.

Matching tiers (recorded per job as match_tier):
  exact    — the whole normalized title is in the O*NET title index
             (includes a light depluralized/stemmed key, since O*NET
             primary titles are plural: "Electricians" vs "Electrician")
  segment  — the title is split on delimiters (" - ", "—", "(", ",", …)
             and contiguous segment subsequences are tried longest-first;
             drops company/location/program suffixes like
             "Skilled Trade - Electrician - Cleveland Engine Plant"
  fuzzy    — highest token-set Jaccard overlap (>= 0.6) against all
             O*NET titles; lower confidence, flagged as such
  unmapped — no tier produced a match

Prerequisites:
  O*NET text files under audit/onet/db_*_text/ (newest dir wins):
    Occupation Data.txt, Alternate Titles.txt, Job Zones.txt
  Download: https://www.onetcenter.org/dl_files/database/db_30_2_text.zip

Usage (repo root, API venv active):
  python scripts/map_onet.py                 # map + write CSV
  python scripts/map_onet.py --audit         # also write audit/onet/onet_audit.md
  python scripts/map_onet.py --write-db      # also persist soc code + tier to jobs
  python scripts/map_onet.py --onet-dir PATH # explicit O*NET text dir

Outputs:
  audit/onet/job_soc_mapping.csv
  audit/onet/onet_audit.md          (with --audit)
  jobs.onet_soc_code / jobs.onet_match_tier   (with --write-db)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

AUDIT_DIR = REPO_ROOT / "audit" / "onet"
CSV_PATH = AUDIT_DIR / "job_soc_mapping.csv"
AUDIT_MD_PATH = AUDIT_DIR / "onet_audit.md"

JACCARD_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# Title normalization
# ---------------------------------------------------------------------------

# Multi-word noise phrases removed before tokenization.
_NOISE_PHRASES = [
    r"\bentry[\s-]*level\b",
    r"\bpart[\s-]*time\b",
    r"\bfull[\s-]*time\b",
    r"\b(1st|2nd|3rd|first|second|third|day|night|swing|weekend|overnight)\s+shift\b",
    r"\bshift\s+(1st|2nd|3rd|first|second|third|a|b|c|d|\d)\b",
    r"\blevel\s+(i{1,3}v?|v|\d)\b",
    r"\bsign[\s-]*on\s+bonus\b",
]

# Single-token noise: seniority, shift, level markers, employment type.
_NOISE_TOKENS = {
    # seniority
    "senior", "sr", "jr", "junior", "lead", "principal", "experienced",
    "entry",
    # level suffixes (roman numerals + bare digits)
    "i", "ii", "iii", "iv", "v", "1", "2", "3", "4", "5", "level",
    # shift / schedule
    "shift", "shifts", "night", "nights", "day", "days", "weekend",
    "weekends", "swing", "overnight", "am", "pm",
    # employment type
    "parttime", "fulltime", "temporary", "temp", "seasonal", "prn",
    "hourly", "onsite", "remote", "hybrid",
    # generic stopwords (O*NET titles drop these too after normalization)
    "and", "or", "the", "of", "for", "a", "an", "with", "in", "at", "to",
}

_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation and seniority/shift/level noise tokens,
    collapse whitespace. Deterministic."""
    s = title.lower()
    for pat in _NOISE_PHRASES:
        s = re.sub(pat, " ", s)
    s = _PUNCT_RE.sub(" ", s)
    toks = [t for t in s.split() if t not in _NOISE_TOKENS]
    return _WS_RE.sub(" ", " ".join(toks)).strip()


def stem_token(tok: str) -> str:
    """Very light depluralization: electricians -> electrician,
    branches -> branch. Never touches short tokens (hvac, gas, bus)."""
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith("es") and not tok.endswith("ses"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def stem_key(normalized: str) -> str:
    return " ".join(stem_token(t) for t in normalized.split())


def token_set(normalized: str) -> frozenset:
    return frozenset(stem_token(t) for t in normalized.split())


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Delimiters that separate a core title from company/location/shift
# qualifiers. Hyphens split only when a space is adjacent on either side
# ("Technician -TX 12" splits; "Electro-Mechanical" does not).
_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:\s-|-\s|--+|[–—|,:;/()])\s*")


def title_segments(title_raw: str) -> list[str]:
    """Split a raw title into qualifier segments (before normalization)."""
    parts = _SEGMENT_SPLIT_RE.split(title_raw)
    return [p for p in (part.strip() for part in parts) if p]


def segment_candidates(title_raw: str) -> list[str]:
    """Normalized contiguous segment subsequences, longest first (by
    segment count then by position), excluding the full title (tier a
    already tried it). Deterministic ordering."""
    segs = [normalize_title(s) for s in title_segments(title_raw)]
    segs = [s for s in segs if s]
    n = len(segs)
    if n <= 1:
        return []
    out, seen = [], set()
    full = normalize_title(title_raw)
    for length in range(n, 0, -1):
        for start in range(0, n - length + 1):
            cand = " ".join(segs[start:start + length])
            if cand and cand != full and cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


# ---------------------------------------------------------------------------
# O*NET index
# ---------------------------------------------------------------------------

class OnetIndex:
    """Normalized-title → SOC index built from Occupation Data (primary
    titles) and Alternate Titles.

    Many alternate titles are ambiguous ("Machinist", "Material Handler",
    "Field Service Representative" each appear under 2–8 SOC codes).
    Collisions resolve deterministically by:
      1. primary occupation titles beat alternate titles
      2. highest containment of the looked-up title's tokens in the
         candidate SOC's *primary* title ("material handler" prefers
         "Laborers and ... Material Movers, Hand" over "Hoist and Winch
         Operators")
      3. highest Jaccard vs the candidate SOC's primary title
      4. smallest SOC code
    """

    def __init__(self):
        # key -> list of (priority, soc_code, onet_title); 0=primary, 1=alt
        self._exact: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
        self._stemmed: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
        # fuzzy corpus: (token_set, onet_title, soc_code)
        self._fuzzy: list[tuple[frozenset, str, str]] = []
        self.soc_titles: dict[str, str] = {}   # soc -> primary title
        self.job_zones: dict[str, str] = {}    # soc -> job zone
        self._soc_tokens: dict[str, frozenset] = {}  # soc -> primary tokens

    def add_title(self, soc: str, title: str, primary: bool):
        norm = normalize_title(title)
        if not norm:
            return
        entry = (0 if primary else 1, soc, title)
        self._exact[norm].append(entry)
        self._stemmed[stem_key(norm)].append(entry)
        self._fuzzy.append((token_set(norm), title, soc))
        if primary:
            self._soc_tokens[soc] = token_set(norm)

    def finalize(self):
        # Deterministic fuzzy ordering: title asc, soc asc.
        self._fuzzy.sort(key=lambda e: (e[1].lower(), e[2]))

    def _resolve(self, normalized: str,
                 candidates: list[tuple[int, str, str]]) -> tuple[str, str]:
        toks = token_set(normalized)

        def rank(entry):
            priority, soc, _title = entry
            primary_toks = self._soc_tokens.get(soc, frozenset())
            containment = (len(toks & primary_toks) / len(toks)) if toks else 0.0
            return (priority, -containment, -jaccard(toks, primary_toks), soc)

        best = min(candidates, key=rank)
        return best[1], best[2]

    def lookup_exact(self, normalized: str) -> tuple[str, str] | None:
        """Return (soc, onet_title) for an exact or stemmed key hit."""
        candidates = list(self._exact.get(normalized, []))
        candidates += self._stemmed.get(stem_key(normalized), [])
        if not candidates:
            return None
        # De-dupe (a title indexes into both tables under the same key).
        candidates = sorted(set(candidates))
        return self._resolve(normalized, candidates)

    def lookup_fuzzy(self, normalized: str) -> tuple[str, str, float] | None:
        """Best Jaccard >= threshold match: (soc, onet_title, score)."""
        toks = token_set(normalized)
        if not toks:
            return None
        best = None  # (-score, title_lower, soc, title)
        for cand_toks, title, soc in self._fuzzy:
            score = jaccard(toks, cand_toks)
            if score >= JACCARD_THRESHOLD:
                key = (-score, title.lower(), soc)
                if best is None or key < best[0]:
                    best = (key, title, soc, score)
        if best is None:
            return None
        return best[2], best[1], best[3]


def load_onet_index(onet_dir: Path) -> OnetIndex:
    idx = OnetIndex()
    occ_path = onet_dir / "Occupation Data.txt"
    alt_path = onet_dir / "Alternate Titles.txt"
    zone_path = onet_dir / "Job Zones.txt"
    for p in (occ_path, alt_path, zone_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing O*NET file: {p}")

    with occ_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            soc, title = row["O*NET-SOC Code"], row["Title"]
            idx.soc_titles[soc] = title
            idx.add_title(soc, title, primary=True)

    with alt_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            soc, alt = row["O*NET-SOC Code"], row["Alternate Title"]
            idx.add_title(soc, alt, primary=False)
            # Many alt titles carry a parenthetical expansion:
            # "CNC Machinist (Computer Numerical Control Machinist)".
            # Index the acronym part on its own too.
            if "(" in alt:
                head = alt.split("(", 1)[0].strip()
                if head:
                    idx.add_title(soc, head, primary=False)
            short = (row.get("Short Title") or "").strip()
            if short and short.lower() != "n/a":
                idx.add_title(soc, short, primary=False)

    with zone_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            idx.job_zones[row["O*NET-SOC Code"]] = row["Job Zone"]

    idx.finalize()
    return idx


def find_onet_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = sorted(AUDIT_DIR.glob("db_*_text"), reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No db_*_text directory under {AUDIT_DIR}. Download the O*NET "
            "text distribution first (see module docstring)."
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_title(title_raw: str, idx: OnetIndex):
    """Map one raw title. Returns (soc, onet_title, tier) with tier in
    {'exact', 'segment', 'fuzzy'} or (None, None, 'unmapped')."""
    norm = normalize_title(title_raw)

    hit = idx.lookup_exact(norm)
    if hit:
        return hit[0], hit[1], "exact"

    for cand in segment_candidates(title_raw):
        hit = idx.lookup_exact(cand)
        if hit:
            return hit[0], hit[1], "segment"

    fz = idx.lookup_fuzzy(norm)
    if fz is None:
        # Retry fuzzy on the longest segment candidate (company/location
        # tokens dilute Jaccard badly).
        for cand in segment_candidates(title_raw):
            fz = idx.lookup_fuzzy(cand)
            if fz:
                break
    if fz:
        return fz[0], fz[1], "fuzzy"

    return None, None, "unmapped"


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------

JOBS_SQL = """
    SELECT j.id::text,
           j.title_raw,
           COALESCE(f.code, '')       AS family_code,
           COALESCE(j.sector_code,'') AS sector_code,
           COALESCE(j.experience_level,'') AS experience_level,
           COALESCE(j.source,'')      AS source,
           COALESCE(e.name,'')        AS employer_name
    FROM public.jobs j
    LEFT JOIN public.canonical_job_families f ON f.id = j.canonical_job_family_id
    LEFT JOIN public.employers e ON e.id = j.employer_id
    WHERE j.status = 'active'
    ORDER BY j.title_raw, j.id
"""


def fetch_active_jobs(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(JOBS_SQL)
        cols = ["job_id", "title_raw", "family_code", "sector_code",
                "experience_level", "source", "employer_name"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def write_db(conn, rows: list[dict]) -> int:
    """Persist soc code + tier onto jobs. Adds columns if absent."""
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE public.jobs "
            "ADD COLUMN IF NOT EXISTS onet_soc_code text, "
            "ADD COLUMN IF NOT EXISTS onet_match_tier text"
        )
        mapped = [(r["job_id"], r["soc_code"], r["match_tier"])
                  for r in rows if r["soc_code"]]
        execute_values(
            cur,
            """
            UPDATE public.jobs AS j
            SET onet_soc_code = v.soc, onet_match_tier = v.tier
            FROM (VALUES %s) AS v(id, soc, tier)
            WHERE j.id = v.id::uuid
            """,
            mapped,
        )
        # Mark explicitly-unmapped so a rerun clears stale codes.
        unmapped = [(r["job_id"],) for r in rows if not r["soc_code"]]
        if unmapped:
            execute_values(
                cur,
                """
                UPDATE public.jobs AS j
                SET onet_soc_code = NULL, onet_match_tier = 'unmapped'
                FROM (VALUES %s) AS v(id)
                WHERE j.id = v.id::uuid
                """,
                unmapped,
            )
    conn.commit()
    return len([r for r in rows if r["soc_code"]])


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------

def soc_major_group(soc: str) -> str:
    return soc[:2] if soc else ""


# SOC major group names (2018 SOC), for readable audit output.
SOC_MAJOR_NAMES = {
    "11": "Management", "13": "Business & Financial", "15": "Computer & Math",
    "17": "Architecture & Engineering", "19": "Life/Physical/Social Science",
    "21": "Community & Social Service", "23": "Legal", "25": "Education",
    "27": "Arts/Design/Media", "29": "Healthcare Practitioners",
    "31": "Healthcare Support", "33": "Protective Service",
    "35": "Food Prep & Serving", "37": "Building & Grounds",
    "39": "Personal Care", "41": "Sales", "43": "Office & Admin Support",
    "45": "Farming/Fishing/Forestry", "47": "Construction & Extraction",
    "49": "Installation/Maintenance/Repair", "51": "Production",
    "53": "Transportation & Material Moving", "55": "Military",
}


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def build_audit_md(rows: list[dict], onet_dir: Path) -> str:
    total = len(rows)
    tier_counts = Counter(r["match_tier"] for r in rows)
    mapped_rows = [r for r in rows if r["soc_code"]]
    unmapped_rows = [r for r in rows if not r["soc_code"]]

    lines: list[str] = []
    lines.append("# O*NET-SOC Mapping Audit")
    lines.append("")
    lines.append(f"Generated by `scripts/map_onet.py` against O*NET data in "
                 f"`{onet_dir.name}` (deterministic; no LLM calls).")
    lines.append(f"Scope: **{total} active jobs**.")
    lines.append("")
    lines.append("**How to read this:** the mapper is title-string only. "
                 "`exact`/`segment` tiers are reliable for distinctive titles "
                 "but generic titles (\"Operator\", \"Production Technician\", "
                 "\"Maintenance Supervisor\") are ambiguous inside O*NET "
                 "itself — they appear as alternate titles under many SOC "
                 "codes, and the deterministic tie-break (primary-title "
                 "token overlap, then smallest SOC) can land on an "
                 "off-domain occupation. `fuzzy` is flagged lower "
                 "confidence by construction. Treat single-title "
                 "disagreements as leads to inspect, not verdicts; treat "
                 "*clusters* of disagreeing titles as real segmentation "
                 "signal.")
    lines.append("")

    # -- 1. Coverage -------------------------------------------------------
    lines.append("## 1. Mapping coverage")
    lines.append("")
    lines.append("| Tier | Jobs | % of active |")
    lines.append("|------|-----:|------------:|")
    for tier in ("exact", "segment", "fuzzy", "unmapped"):
        c = tier_counts.get(tier, 0)
        lines.append(f"| {tier} | {c} | {pct(c, total)} |")
    lines.append(f"| **mapped total** | **{len(mapped_rows)}** | "
                 f"**{pct(len(mapped_rows), total)}** |")
    lines.append("")
    if unmapped_rows:
        lines.append("Sample unmapped titles (up to 20 distinct):")
        lines.append("")
        seen = set()
        shown = 0
        for r in unmapped_rows:
            if r["title_raw"] in seen:
                continue
            seen.add(r["title_raw"])
            lines.append(f"- {r['title_raw']}  (family: {r['family_code'] or '—'})")
            shown += 1
            if shown >= 20:
                break
        lines.append("")

    # -- 2. Agreement matrix ----------------------------------------------
    lines.append("## 2. Our family vs SOC major group (agreement matrix)")
    lines.append("")
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in mapped_rows:
        by_family[r["family_code"] or "(none)"].append(r)

    lines.append("Families with >= 5 mapped jobs. 'Agreement' = share of the "
                 "family's mapped jobs whose SOC code falls in the dominant "
                 "SOC major group.")
    lines.append("")
    lines.append("| Our family | Mapped jobs | Dominant SOC major group | Agreement | Impure (<70%)? |")
    lines.append("|------------|------------:|--------------------------|----------:|:--:|")
    impure: list[tuple[str, list[dict], str, float]] = []
    for fam in sorted(by_family, key=lambda f: -len(by_family[f])):
        rs = by_family[fam]
        if len(rs) < 5:
            continue
        groups = Counter(soc_major_group(r["soc_code"]) for r in rs)
        dom, dom_n = groups.most_common(1)[0]
        agree = dom_n / len(rs)
        name = SOC_MAJOR_NAMES.get(dom, "?")
        flag = "**YES**" if agree < 0.70 else ""
        lines.append(f"| {fam} | {len(rs)} | {dom} — {name} | "
                     f"{agree * 100:.1f}% | {flag} |")
        if agree < 0.70:
            impure.append((fam, rs, dom, agree))
    lines.append("")

    if impure:
        lines.append("### Impure families (<70% SOC major-group agreement)")
        lines.append("")
        for fam, rs, dom, agree in impure:
            lines.append(f"**{fam}** — dominant group {dom} "
                         f"({SOC_MAJOR_NAMES.get(dom, '?')}), "
                         f"{agree * 100:.1f}% agreement. Disagreeing jobs:")
            lines.append("")
            for r in rs:
                g = soc_major_group(r["soc_code"])
                if g != dom:
                    lines.append(
                        f"- {r['title_raw']} → {r['soc_code']} "
                        f"({r['soc_title']}) [group {g} — "
                        f"{SOC_MAJOR_NAMES.get(g, '?')}] tier={r['match_tier']}")
            lines.append("")
    else:
        lines.append("No family with >= 5 mapped jobs fell below 70% "
                     "SOC major-group agreement.")
        lines.append("")

    # -- 3. Cross-source consistency --------------------------------------
    lines.append("## 3. Cross-source consistency")
    lines.append("")
    lines.append("Normalized titles appearing under 2+ employers/sources — "
                 "do we put them in the same family?")
    lines.append("")
    by_norm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        n = normalize_title(r["title_raw"])
        if n:
            by_norm[n].append(r)
    multi = 0
    divergent: list[tuple[str, list[dict]]] = []
    for n, rs in sorted(by_norm.items()):
        origins = {(r["employer_name"], r["source"]) for r in rs}
        employers = {r["employer_name"] for r in rs}
        sources = {r["source"] for r in rs}
        if len(employers) < 2 and len(sources) < 2:
            continue
        multi += 1
        fams = {r["family_code"] for r in rs}
        if len(fams) > 1:
            divergent.append((n, rs))
        _ = origins
    lines.append(f"- Normalized titles seen under 2+ employers or sources: "
                 f"**{multi}**")
    lines.append(f"- Of those, titles assigned to **different families**: "
                 f"**{len(divergent)}** ({pct(len(divergent), multi)})")
    lines.append("")
    if divergent:
        lines.append("Divergences:")
        lines.append("")
        for n, rs in divergent:
            lines.append(f"**\"{n}\"**")
            for r in rs:
                lines.append(f"- {r['title_raw']} — {r['employer_name']} "
                             f"[{r['source']}] → family `{r['family_code'] or '—'}`")
            lines.append("")

    # -- 4. Job Zone vs experience level ----------------------------------
    lines.append("## 4. O*NET Job Zone vs our experience_level")
    lines.append("")
    lines.append("Job Zone 1 = little/no preparation … Job Zone 5 = extensive "
                 "preparation. Crosstab over mapped jobs with a known zone:")
    lines.append("")
    zoned = [r for r in mapped_rows if r["job_zone"]]
    levels = ["entry", "mid", "senior", "management", ""]
    zones = sorted({r["job_zone"] for r in zoned})
    ct: dict[tuple[str, str], int] = Counter(
        (r["experience_level"], r["job_zone"]) for r in zoned)
    header = "| our level \\ zone | " + " | ".join(zones) + " | total |"
    lines.append(header)
    lines.append("|---" * (len(zones) + 2) + "|")
    for lvl in levels:
        row_total = sum(ct.get((lvl, z), 0) for z in zones)
        if row_total == 0:
            continue
        label = lvl or "(none)"
        cells = " | ".join(str(ct.get((lvl, z), 0)) for z in zones)
        lines.append(f"| {label} | {cells} | {row_total} |")
    lines.append("")

    entry_rows = [r for r in zoned if r["experience_level"] == "entry"]
    entry_hi = [r for r in entry_rows if r["job_zone"] in ("4", "5")]
    senior_rows = [r for r in zoned if r["experience_level"] == "senior"]
    senior_lo = [r for r in senior_rows if r["job_zone"] in ("1", "2")]
    lines.append(f"- Our **entry** jobs landing in Job Zone 4–5 (suspicious): "
                 f"**{len(entry_hi)} / {len(entry_rows)}** "
                 f"({pct(len(entry_hi), len(entry_rows))})")
    for r in entry_hi[:10]:
        lines.append(f"  - {r['title_raw']} → {r['soc_code']} "
                     f"({r['soc_title']}), zone {r['job_zone']}")
    lines.append(f"- Our **senior** jobs landing in Job Zone 1–2 (suspicious): "
                 f"**{len(senior_lo)} / {len(senior_rows)}** "
                 f"({pct(len(senior_lo), len(senior_rows))})")
    for r in senior_lo[:10]:
        lines.append(f"  - {r['title_raw']} → {r['soc_code']} "
                     f"({r['soc_title']}), zone {r['job_zone']}")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CSV_FIELDS = ["job_id", "title_raw", "our_family_code", "our_sector",
              "soc_code", "soc_title", "match_tier", "matched_onet_title",
              "job_zone"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map active job titles to O*NET-SOC codes")
    parser.add_argument("--onet-dir", default=None,
                        help="Path to the O*NET db_*_text directory")
    parser.add_argument("--audit", action="store_true",
                        help="Also write audit/onet/onet_audit.md")
    parser.add_argument("--write-db", action="store_true",
                        help="Persist onet_soc_code + onet_match_tier to jobs")
    args = parser.parse_args()

    onet_dir = find_onet_dir(args.onet_dir)
    print(f"Loading O*NET index from {onet_dir} ...")
    idx = load_onet_index(onet_dir)
    print(f"  {len(idx.soc_titles)} occupations, "
          f"{len(idx._fuzzy)} title entries, "
          f"{len(idx.job_zones)} job zones")

    from etl.db import get_connection
    conn = get_connection()
    try:
        jobs = fetch_active_jobs(conn)
        print(f"Mapping {len(jobs)} active jobs ...")

        rows: list[dict] = []
        for j in jobs:
            soc, onet_title, tier = match_title(j["title_raw"], idx)
            rows.append({
                **j,
                "soc_code": soc or "",
                "soc_title": idx.soc_titles.get(soc, "") if soc else "",
                "match_tier": tier,
                "matched_onet_title": onet_title or "",
                "job_zone": idx.job_zones.get(soc, "") if soc else "",
            })

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({
                    "job_id": r["job_id"],
                    "title_raw": r["title_raw"],
                    "our_family_code": r["family_code"],
                    "our_sector": r["sector_code"],
                    "soc_code": r["soc_code"],
                    "soc_title": r["soc_title"],
                    "match_tier": r["match_tier"],
                    "matched_onet_title": r["matched_onet_title"],
                    "job_zone": r["job_zone"],
                })
        print(f"Wrote {CSV_PATH}")

        tiers = Counter(r["match_tier"] for r in rows)
        total = len(rows)
        for t in ("exact", "segment", "fuzzy", "unmapped"):
            print(f"  {t:>8}: {tiers.get(t, 0):4d}  "
                  f"({100.0 * tiers.get(t, 0) / total:.1f}%)" if total else "")

        if args.audit:
            AUDIT_MD_PATH.write_text(build_audit_md(rows, onet_dir),
                                     encoding="utf-8")
            print(f"Wrote {AUDIT_MD_PATH}")

        if args.write_db:
            n = write_db(conn, rows)
            print(f"Persisted onet_soc_code for {n} jobs "
                  f"(+ tier for all {total}).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
