"""In-pipeline job enrichment — every job gets the full ontology, automatically.

This is the stage that makes new partners translate: whatever the source
(career-page pull, employer form, bulk import, adapter scrape), a job that
reaches the jobs table passes through here and comes out carrying:

  * canonical career field + sector (trades classifier over title/description,
    resolved through the SKILLED Nation taxonomy bridge)
  * seniority level with evidence, years asked, entry_friendly
    (packages/matching/seniority.py — O*NET-derived, deterministic)
  * canonical credentials with required/preferred/mentioned grading
  * practical signals: shift, apprenticeship, veteran-friendly

Everything is pure-Python deterministic extraction; no LLM required. The
caller is responsible for triggering match recompute AFTER enrichment so the
gates see the enriched fields (entry_friendly, credentials, years).

scripts/extract_job_ontology.py delegates to this module so the batch script
and the live pipeline can never drift.
"""
from __future__ import annotations

import logging
import re
import sys
from functools import lru_cache
from pathlib import Path

# packages/ import path — walk only existing parents (deploy layouts differ).
for _parent in Path(__file__).resolve().parents:
    _pkg = _parent / "packages"
    if _pkg.is_dir():
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        break

from matching import sn_taxonomy  # noqa: E402
from matching.seniority import classify_seniority  # noqa: E402

from app.skilled_pro.taxonomy import all_definitions  # noqa: E402

logger = logging.getLogger(__name__)

try:
    from scraper.trades import classify as classify_trade  # noqa: E402
    _TRADES_AVAILABLE = True
except ImportError:  # pragma: no cover - deploy-layout dependent
    classify_trade = None  # type: ignore[assignment]
    _TRADES_AVAILABLE = False

# --- Credential extraction (canonical registry, alias-indexed) --------------

_PREFERRED_CTX = re.compile(
    r"(preferred|a plus|nice to have|bonus|is desirable|would be an asset|"
    r"not required|helpful but)", re.IGNORECASE,
)
_REQUIRED_CTX = re.compile(
    r"(required|must (have|hold|possess)|need to (have|hold)|valid|current|"
    r"active|requirement)", re.IGNORECASE,
)
_SHIFT_PATTERNS = [
    ("night",    re.compile(r"\b(3rd|third|night|overnight|graveyard)[\s-]*shift\b|\bnights?\b.{0,12}\bshift", re.IGNORECASE)),
    ("evening",  re.compile(r"\b(2nd|second|evening|swing)[\s-]*shift\b", re.IGNORECASE)),
    ("rotating", re.compile(r"\brotat(ing|ional)[\s-]*(shift|schedule)\b|\bshift rotation\b", re.IGNORECASE)),
    ("weekend",  re.compile(r"\bweekends?[\s-]*(required|shift|work)\b", re.IGNORECASE)),
    ("day",      re.compile(r"\b(1st|first|day)[\s-]*shift\b", re.IGNORECASE)),
]
_APPRENTICESHIP = re.compile(
    r"\bapprentice(ship)?\b|\bearn while you learn\b|\bregistered apprenticeship\b",
    re.IGNORECASE,
)
_VETERAN = re.compile(
    r"\bveterans?\b.{0,40}\b(welcome|encouraged|preferred|hiring)\b|"
    r"\bmilitary\b.{0,30}\b(welcome|encouraged|friendly|experience a plus)\b|"
    r"\btransitioning service members?\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _alias_index():
    """[(compiled_pattern, alias, definition)] longest alias first."""
    entries = []
    for d in all_definitions():
        for alias in {d.name, *d.aliases}:
            a = alias.strip()
            if len(a) < 3:
                continue
            flags = 0 if (a.isupper() and " " not in a) else re.IGNORECASE
            entries.append((re.compile(rf"(?<![\w-]){re.escape(a)}(?![\w-])", flags), a, d))
    entries.sort(key=lambda t: -len(t[1]))
    return entries


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?:;])\s+|\n+", text)


def extract_credentials(*texts: str | None) -> list[dict]:
    found: dict[str, dict] = {}
    rank = {"required": 2, "preferred": 1, "mentioned": 0}
    for text in texts:
        if not text:
            continue
        for sent in _sentences(text):
            consumed: list[tuple[int, int]] = []
            for pat, alias, d in _alias_index():
                m = pat.search(sent)
                if not m:
                    continue
                span = (m.start(), m.end())
                if any(s <= span[0] and span[1] <= e for s, e in consumed):
                    continue
                consumed.append(span)
                requirement = (
                    "preferred" if _PREFERRED_CTX.search(sent)
                    else "required" if _REQUIRED_CTX.search(sent)
                    else "mentioned"
                )
                prev = found.get(d.code)
                if prev is None or rank[requirement] > rank[prev["requirement"]]:
                    found[d.code] = {
                        "raw": alias, "slug": d.code.lower(), "name": d.name,
                        "confidence": 0.95, "confident": True,
                        "requirement": requirement,
                    }
    return list(found.values())


def extract_practical_signals(title: str | None, *texts: str | None) -> dict:
    joined = " ".join(t for t in (title, *texts) if t)
    shift = next((label for label, pat in _SHIFT_PATTERNS if pat.search(joined)), None)
    return {
        "shift": shift,
        "is_apprenticeship": bool(_APPRENTICESHIP.search(title or "")
                                  or _APPRENTICESHIP.search(joined)),
        "veteran_friendly": bool(_VETERAN.search(joined)),
    }


# --- The pipeline stage -----------------------------------------------------

async def enrich_jobs(conn, job_ids: list[str], *, preserve_level: bool = False) -> dict:
    """Run the full ontology over the given jobs and persist it.

    Family/sector are only FILLED when missing — an admin- or employer-set
    field is never overwritten by the classifier. With preserve_level=True
    (employer-authored jobs), an explicitly chosen experience_level also
    stands; the classifier only fills gaps. Everything else is recomputed
    from the current posting text (idempotent).
    Returns an audit dict. Does NOT trigger recompute; callers do that after.
    """
    audit = {"enriched": 0, "family_stamped": 0, "no_trade_match": 0}
    if not job_ids:
        return audit

    fam_rows = await conn.fetch(
        "SELECT code, id FROM public.canonical_job_families WHERE is_active")
    fam_ids = {r["code"]: r["id"] for r in fam_rows}

    rows = await conn.fetch(
        """SELECT j.id, j.title_raw, j.description_raw, j.requirements_raw,
                  j.experience_level, j.canonical_job_family_id, j.sector_code
             FROM public.jobs j WHERE j.id = ANY($1::uuid[])""",
        job_ids,
    )
    for r in rows:
        title, desc, reqs = r["title_raw"], r["description_raw"], r["requirements_raw"]

        family_id, sector = r["canonical_job_family_id"], r["sector_code"]
        if family_id is None and _TRADES_AVAILABLE:
            m = classify_trade(title or "", desc)
            code = sn_taxonomy.resolve_field_code(m.family) if (m.is_trade and m.family) else None
            if code and code in fam_ids:
                family_id = fam_ids[code]
                sector = sector or sn_taxonomy.FIELDS[code]["sectors"][0]
                audit["family_stamped"] += 1
            else:
                audit["no_trade_match"] += 1

        sen = classify_seniority(title, desc, reqs)
        _CLEAN_LEVELS = {"entry", "mid", "senior", "management"}
        level = (
            r["experience_level"]
            if preserve_level and (r["experience_level"] or "") in _CLEAN_LEVELS
            else sen.level
        )
        creds = extract_credentials(title, desc, reqs)
        practical = extract_practical_signals(title, desc, reqs)
        names = [c["name"] for c in creds if c["requirement"] != "preferred"]

        await conn.execute(
            """UPDATE public.jobs SET
                   canonical_job_family_id = $2,
                   sector_code = $3,
                   experience_level = $4,
                   years_experience_required = $5,
                   entry_friendly = $6,
                   seniority_evidence = $7::jsonb,
                   required_credentials = $8,
                   required_credentials_canonical = $9::jsonb,
                   shift = $10,
                   is_apprenticeship = $11,
                   veteran_friendly = $12,
                   updated_at = NOW()
                 WHERE id = $1""",
            # The app's asyncpg pool registers a jsonb codec that dumps
            # Python values itself — pass OBJECTS, never pre-dumped strings
            # (that double-encodes). Callers with a bare connection must set
            # the same codec (scripts/extract_job_ontology.py does).
            r["id"], family_id, sector,
            level, sen.years_required, sen.entry_friendly,
            {"job_zone": sen.job_zone, "evidence": sen.evidence,
             "previous_label": r["experience_level"]},
            names, creds,
            practical["shift"], practical["is_apprenticeship"],
            practical["veteran_friendly"],
        )
        audit["enriched"] += 1

    logger.info("Job enrichment: %s", audit)
    return audit
