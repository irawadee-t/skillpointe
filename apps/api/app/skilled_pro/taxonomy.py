"""
Credential taxonomy + normalization.

A canonical taxonomy of the major U.S. skilled-trades credentials (certs,
licenses, degrees) plus a normalizer that maps free-text strings — from user
input, OCR, SIS feeds, or partner uploads — onto canonical entries.

Design goals
------------
- Deterministic and dependency-free (pure stdlib) so it is fully unit-testable.
- Alias-driven: every canonical entry carries the real-world surface forms we
  see across sources. Matching is exact → alias → token-overlap → fuzzy, so the
  common cases are exact and only the long tail falls back to fuzzy.
- Honest confidence: every match returns a 0..1 confidence so callers can route
  low-confidence matches to the admin review queue rather than trusting them.

This is intentionally a curated seed, not exhaustive. In production it is backed
by (and reconciled against) the Credential Engine CTDL registry and Lightcast /
O*NET skill taxonomies — see docs/skilled-pro/02-credentials-verification.md.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CredentialType(str, Enum):
    LICENSE = "license"
    CERTIFICATION = "certification"
    DEGREE = "degree"
    APPRENTICESHIP = "apprenticeship"
    SAFETY = "safety"


@dataclass(frozen=True)
class CanonicalCredential:
    code: str               # stable machine code, e.g. "EPA_608"
    name: str               # canonical display name
    type: CredentialType
    job_families: tuple[str, ...]  # related trade families (canonical_job_family_code)
    issuer: Optional[str] = None   # typical issuing body, if standardized
    aliases: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Canonical taxonomy (curated seed of major U.S. trade credentials)
# ---------------------------------------------------------------------------

TAXONOMY: tuple[CanonicalCredential, ...] = (
    # ---- Safety / cross-trade ----
    CanonicalCredential(
        "OSHA_10", "OSHA 10-Hour Construction Safety", CredentialType.SAFETY,
        ("construction", "electrical", "welding", "hvac", "manufacturing"),
        "OSHA",
        ("osha 10", "osha-10", "osha 10 hour", "osha 10-hour", "osha10", "osha 10 card"),
    ),
    CanonicalCredential(
        "OSHA_30", "OSHA 30-Hour Construction Safety", CredentialType.SAFETY,
        ("construction", "electrical", "welding", "hvac", "manufacturing"),
        "OSHA",
        ("osha 30", "osha-30", "osha 30 hour", "osha 30-hour", "osha30"),
    ),
    CanonicalCredential(
        "CPR_FIRST_AID", "CPR / First Aid Certification", CredentialType.SAFETY,
        ("construction", "electrical", "hvac", "manufacturing", "healthcare"),
        "American Red Cross / AHA",
        ("cpr", "first aid", "cpr/first aid", "cpr and first aid", "bls", "basic life support", "aed"),
    ),
    CanonicalCredential(
        "FORKLIFT_PIT", "Forklift / Powered Industrial Truck Operator", CredentialType.CERTIFICATION,
        ("manufacturing", "logistics", "construction"),
        "OSHA (employer-certified)",
        ("forklift", "forklift certification", "powered industrial truck", "pit", "lift truck", "forklift operator"),
    ),

    # ---- Electrical ----
    CanonicalCredential(
        "ELEC_APPRENTICE", "Electrical Apprenticeship", CredentialType.APPRENTICESHIP,
        ("electrical",), "DOL / IBEW / IEC",
        ("electrical apprentice", "electrician apprentice", "apprentice electrician", "electrical apprenticeship"),
    ),
    CanonicalCredential(
        "ELEC_JOURNEYMAN", "Journeyman Electrician License", CredentialType.LICENSE,
        ("electrical",), "State licensing board",
        ("journeyman electrician", "journeyman electrical license", "journeyperson electrician",
         "licensed journeyman electrician", "j-man electrician"),
    ),
    CanonicalCredential(
        "ELEC_MASTER", "Master Electrician License", CredentialType.LICENSE,
        ("electrical",), "State licensing board",
        ("master electrician", "master electrical license", "licensed master electrician"),
    ),

    # ---- HVAC ----
    CanonicalCredential(
        "EPA_608", "EPA Section 608 Technician Certification", CredentialType.CERTIFICATION,
        ("hvac",), "EPA",
        ("epa 608", "epa section 608", "608 certification", "epa 608 universal", "section 608",
         "epa universal", "epa refrigerant"),
    ),
    CanonicalCredential(
        "NATE", "NATE (North American Technician Excellence)", CredentialType.CERTIFICATION,
        ("hvac",), "NATE",
        ("nate", "nate certified", "nate certification", "north american technician excellence"),
    ),
    CanonicalCredential(
        "HVAC_EXCELLENCE", "HVAC Excellence Certification", CredentialType.CERTIFICATION,
        ("hvac",), "HVAC Excellence",
        ("hvac excellence", "hvac excellence certified"),
    ),

    # ---- Welding ----
    CanonicalCredential(
        "AWS_CW", "AWS Certified Welder", CredentialType.CERTIFICATION,
        ("welding",), "American Welding Society",
        ("aws certified welder", "certified welder", "aws cw", "aws welding certification", "aws d1.1",
         "aws d1 1", "cwb", "certified welding"),
    ),
    CanonicalCredential(
        "AWS_CWI", "AWS Certified Welding Inspector", CredentialType.CERTIFICATION,
        ("welding",), "American Welding Society",
        ("aws cwi", "certified welding inspector", "cwi", "welding inspector"),
    ),

    # ---- Automotive ----
    CanonicalCredential(
        "ASE", "ASE (Automotive Service Excellence) Certification", CredentialType.CERTIFICATION,
        ("automotive",), "ASE",
        ("ase", "ase certified", "ase certification", "automotive service excellence", "ase master"),
    ),

    # ---- Transportation / logistics ----
    CanonicalCredential(
        "CDL_A", "Commercial Driver's License — Class A", CredentialType.LICENSE,
        ("transportation", "logistics"), "State DMV",
        ("cdl", "cdl a", "cdl-a", "class a cdl", "commercial drivers license", "commercial driver's license",
         "cdl class a"),
    ),
    CanonicalCredential(
        "CDL_B", "Commercial Driver's License — Class B", CredentialType.LICENSE,
        ("transportation", "logistics"), "State DMV",
        ("cdl b", "cdl-b", "class b cdl", "cdl class b"),
    ),

    # ---- Construction / general trades ----
    CanonicalCredential(
        "NCCER", "NCCER Craft Certification", CredentialType.CERTIFICATION,
        ("construction", "electrical", "welding", "hvac"),
        "NCCER",
        ("nccer", "nccer certified", "nccer core", "national center for construction education"),
    ),
    CanonicalCredential(
        "EPA_LEAD_RRP", "EPA Lead RRP (Renovation, Repair & Painting)", CredentialType.CERTIFICATION,
        ("construction",), "EPA",
        ("lead rrp", "epa rrp", "rrp certification", "lead renovator", "renovation repair painting"),
    ),

    # ---- Degrees / generic academic awards ----
    CanonicalCredential(
        "CERT_OF_COMPLETION", "Certificate of Completion", CredentialType.DEGREE,
        (), None,
        ("certificate of completion", "completion certificate", "program certificate", "trade certificate"),
    ),
    CanonicalCredential(
        "DIPLOMA", "Trade / Technical Diploma", CredentialType.DEGREE,
        (), None,
        ("diploma", "technical diploma", "trade diploma", "vocational diploma"),
    ),
    CanonicalCredential(
        "ASSOCIATE", "Associate Degree (AAS/AS/AA)", CredentialType.DEGREE,
        (), None,
        ("associate degree", "associates degree", "associate's degree", "aas", "a.a.s.", "as degree",
         "a.s.", "aa degree", "associate of applied science"),
    ),
)


# Build fast lookup indexes once at import.
_CODE_INDEX: dict[str, CanonicalCredential] = {c.code: c for c in TAXONOMY}
_ALIAS_INDEX: dict[str, CanonicalCredential] = {}
for _c in TAXONOMY:
    _ALIAS_INDEX[_c.name.lower()] = _c
    for _a in _c.aliases:
        _ALIAS_INDEX[_a.lower()] = _c


@dataclass(frozen=True)
class NormalizationResult:
    canonical: Optional[CanonicalCredential]
    confidence: float          # 0..1
    method: str                # "exact" | "alias" | "token" | "fuzzy" | "none"
    raw: str

    @property
    def is_confident(self) -> bool:
        # Threshold above which we trust the mapping without admin review.
        return self.confidence >= 0.82


_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _clean(raw: str) -> str:
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = _NORMALIZE_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def get_by_code(code: str) -> Optional[CanonicalCredential]:
    return _CODE_INDEX.get(code)


def normalize(raw: str) -> NormalizationResult:
    """
    Map a free-text credential string to a canonical taxonomy entry.

    Returns a NormalizationResult with a confidence score and the method used.
    Callers should route results where ``is_confident`` is False to admin review.
    """
    if not raw or not raw.strip():
        return NormalizationResult(None, 0.0, "none", raw)

    cleaned = _clean(raw)
    if not cleaned:
        return NormalizationResult(None, 0.0, "none", raw)

    # 1) Exact canonical-name / alias match.
    hit = _ALIAS_INDEX.get(cleaned)
    if hit is not None:
        return NormalizationResult(hit, 1.0, "alias", raw)

    # 2) Substring containment against aliases (handles "active osha 30 card").
    best_sub: Optional[CanonicalCredential] = None
    best_sub_len = 0
    for alias, cred in _ALIAS_INDEX.items():
        if len(alias) >= 4 and alias in cleaned and len(alias) > best_sub_len:
            best_sub, best_sub_len = cred, len(alias)
    if best_sub is not None:
        # Confidence scales with how much of the input the alias covers.
        coverage = best_sub_len / max(len(cleaned), 1)
        conf = round(min(0.97, 0.80 + coverage * 0.17), 3)
        return NormalizationResult(best_sub, conf, "token", raw)

    # 3) Fuzzy match against all alias surface forms (long tail / typos / OCR noise).
    aliases = list(_ALIAS_INDEX.keys())
    matches = difflib.get_close_matches(cleaned, aliases, n=1, cutoff=0.78)
    if matches:
        alias = matches[0]
        ratio = difflib.SequenceMatcher(None, cleaned, alias).ratio()
        return NormalizationResult(_ALIAS_INDEX[alias], round(ratio, 3), "fuzzy", raw)

    return NormalizationResult(None, 0.0, "none", raw)
