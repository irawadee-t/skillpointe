"""
trades.py — Skilled-trades classifier (pure, dependency-free).

Scrapes pull *every* job from a careers site. This module decides which of those
are skilled-trades roles and what family they belong to, so the pipeline can:

  1. Drop irrelevant office/corporate jobs early (skip detail fetch — fast).
  2. Standardize every kept job with a canonical `job_family` field.

Design notes — why not just keyword="technician":
  • "Technician" misses Electrician, Welder, HVAC, Millwright, Pipefitter, etc.
  • A flat keyword list misses compound titles ("Sr. CNC Machinist II — Night").
  • We want a *family*, not just a yes/no.

Approach — small canonical set + regex-anchored synonyms + negative guards:

  • Families cover every blue-collar / skilled-trades role we expect on these
    employer sites (Ball, Delta, GE Vernova, Schneider, Southwire).
  • Each family has a list of *anchored word patterns* so "Electrician" matches
    but "Electrical Engineer" does NOT (engineer is in the deny list).
  • Negative guards (engineer, scientist, analyst, manager-only, director, etc.)
    veto when no positive trade verb is present.

Pure functions; no I/O. Unit-tested in tests/test_trades_classifier.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Canonical trade families
# ---------------------------------------------------------------------------
# Each entry: a family code + the patterns (lower-cased word fragments) that
# qualify. We anchor on word boundaries when the token might be confused with
# something else (e.g. "weld" inside "welder", "welding").

@dataclass(frozen=True)
class TradeMatch:
    is_trade: bool
    family: Optional[str] = None    # canonical_job_families.code
    matched_term: Optional[str] = None
    reason: str = ""


# Families ordered by specificity — more specific first so "instrument electrician"
# resolves to "electrical" rather than a generic "instrumentation".
FAMILIES: list[tuple[str, list[str]]] = [
    # NOTE: order matters. Generic patterns like "mechanic" or "maintenance" sit
    # later so more-specific families (aviation, utilities, industrial maintenance)
    # win first.
    ("aviation_aerospace", [
        r"\baircraft (?:mechanic|technician|tech)\b",
        r"\bavionics (?:tech|technician)\b",
        r"\baviation (?:tech|technician|mechanic)\b",
        r"\baandp (?:mechanic|tech)\b", r"\ba\s?&\s?p (?:mechanic|tech)\b",
        r"\bairframe (?:&|and) powerplant\b",
        r"\bflight line (?:tech|technician|mechanic)\b",
    ]),
    ("utilities_energy", [
        r"\bwind (?:tech|technician|turbine|hub)\b",
        r"\bwind \w+ (?:tech|technician)\b",     # "Wind Hub Technician"
        r"\bsubstation (?:tech|technician|electrician)\b",
        r"\bpower plant (?:tech|technician|operator|mechanic)\b",
        r"\butility (?:worker|tech|technician|operator)\b",
        r"\bgas (?:tech|technician|operator|installer)\b",
        r"\bwater treatment (?:operator|tech)\b",
        r"\bgrid (?:tech|technician|operator)\b",
        r"\bturbine technician\b",
    ]),
    ("industrial_maintenance", [
        r"\bmillwright\b", r"\bmillwrights?\b",
        r"\bindustrial maintenance\b",
        r"\bmaintenance (?:tech|technician|mechanic|electrician|specialist|worker|associate|supervisor|lead|coordinator)\b",
        # "Facility/Facilities Maintenance Mechanical Technician" — broader maintenance
        r"\bfacility (?:tech|technician|mechanic|maintenance)\b",
        r"\bmaintenance\b.*\b(?:tech|technician|mechanic)\b",
        # "Equipment tech/technician" only — "Heavy Equipment Mechanic" stays
        # in automotive_diesel (which is the lived reality of those roles).
        r"\bequipment (?:tech|technician)\b",
        r"\breliability (?:tech|technician|mechanic)\b",
        r"\bfacilities (?:tech|technician|mechanic|maintenance)\b",
        r"\bbuilding (?:tech|technician|engineer)\b",
        r"\bplant (?:tech|technician|mechanic|operator)\b",
        r"\bboiler (?:operator|tech|technician|mechanic)\b",
        r"\bturbine (?:tech|technician|mechanic)\b",
    ]),
    ("electrical", [
        r"\belectrician\b", r"\belectricians?\b",
        r"\bjourneyman electric", r"\bapprentice electric",
        r"\bmaster electrician\b", r"\blineman\b", r"\blineworker\b",
        r"\binstrument(?:ation)? (?:&|and) electric",
        r"\be&i (?:tech|technician)\b",
        r"\bhigh[- ]voltage (?:tech|technician|electrician)\b",
        r"\bsolar (?:installer|technician)\b",
        r"\bwiring technician\b",
        r"\belectronic (?:tech|technician|technologist|assembler)\b",
        r"\belectronics (?:tech|technician|technologist)\b",
        r"\btechnician,?\s+electron",   # "Technician, Electronic"
        r"\belectrical (?:assembly|cell) (?:lead|associate|operator|technician)\b",
        r"\belectrical\b.*\b(?:assembly|cell)\b.*\b(?:lead|associate|operator|technician)\b",
    ]),
    ("welding", [
        r"\bwelder\b", r"\bwelders?\b",
        r"\bwelding (?:operator|technician|tech|inspector|fitter|lead|supervisor|specialist)\b",
        r"\bmig\b.*\bwelder", r"\btig\b.*\bwelder",
        r"\bsmaw\b", r"\bgmaw\b", r"\bfcaw\b", r"\bgtaw\b",
        r"\bcombo welder\b", r"\bpipe welder\b",
        r"\bstructural welder\b",
    ]),
    ("hvac_r", [
        r"\bhvac\b", r"\bhvac/?r\b",
        r"\brefrigeration (?:tech|technician|mechanic)\b",
        r"\b(?:hvac|refrigeration) installer\b",
        r"\bchiller (?:tech|technician|mechanic)\b",
        r"\bcooling (?:tech|technician)\b",
        r"\bcontrols technician\b",
    ]),
    ("plumbing", [
        r"\bplumber\b", r"\bplumbers?\b",
        r"\bpipefitter\b", r"\bpipe[- ]?fitter\b",
        r"\bsteamfitter\b", r"\bgas fitter\b",
    ]),
    ("automotive_diesel", [
        r"\bdiesel (?:tech|technician|mechanic)\b",
        r"\bauto(?:motive)? (?:tech|technician|mechanic)\b",
        r"\bmechanic\b", r"\bmechanics?\b",
        r"\bheavy equipment (?:tech|technician|mechanic|operator)\b",
        r"\bfleet (?:tech|technician|mechanic)\b",
        r"\bservice technician\b", r"\bservice tech\b",
        r"\btrailer (?:tech|technician|mechanic)\b",
    ]),
    ("machining_cnc", [
        r"\bmachinist\b", r"\bmachinists?\b",
        r"\bcnc (?:operator|machinist|programmer|tech|technician|setup)\b",
        r"\btool (?:&|and) die\b",
        r"\btoolmaker\b", r"\btool maker\b",
        r"\bgrinder operator\b",
        r"\blathe operator\b",
        r"\bmill (?:operator|wright)\b",
    ]),
    ("manufacturing_production", [
        r"\bproduction (?:operator|technician|tech|associate|worker|specialist|lead|supervisor|line|helper)\b",
        r"\bmanufacturing (?:operator|technician|tech|associate|specialist)\b",
        r"\bassembler\b", r"\bassemblers?\b",
        r"\bassembly (?:operator|technician|tech|worker|associate|line|lead|specialist)\b",
        r"\bfabricator\b", r"\bfabricators?\b",
        r"\bfabrication (?:associate|operator|technician|tech|specialist|worker)\b",
        r"\bfabrication\b.*\b(?:tech|technician)\b",   # "Fabrication & CAD Technician"
        r"\bmachine operator\b",
        r"\bpress operator\b", r"\bpunch operator\b",
        r"\bextruder operator\b", r"\bextrusion operator\b",
        r"\binjection mold(?:ing)? (?:operator|tech|technician)\b",
        r"\bquality (?:assurance )?(?:inspector|tech|technician|associate)\b",
        r"\bline (?:tech|technician|operator|attendant|lead)\b",
        r"\bprocess (?:operator|technician|tech)\b",
        r"\bblending operator\b", r"\bmixer operator\b",
        r"\bbody maker\b",                     # canning / wire mill
        r"\b(?:test|inspection|ndt) (?:tech|technician|inspector)\b",
        r"\bndt\b",                                    # bare "NDT (Level II)" listings
        r"^\s*inspector\s*$",                          # bare "Inspector" listings
        # Wire-mill / packaging-mill machine operators commonly appear as
        # "Operator, <Machine> I/II/III" or "<Machine> Operator I/II/III".
        r"\boperator,\s+(?:take[- ]?up|drawing|extruder|buncher|armoring|stranding|compound|lift truck|take up)\b",
        r"\b(?:take[- ]?up|drawing|buncher|armoring|stranding|compound|deco|body)\s+operator\b",
        # Bare "Operator" (with optional roman/arabic level suffix) — on these
        # industrial sites it's always a machine operator role.
        r"^\s*operator\s*(?:[-,–]?\s*\w+)?\s*(?:I{1,3}|i{1,3}|\d+)?\s*$",
        r"\bmaintainer\b",                      # Ball uses "Maintainer-Chemical Process"
        r"\bchemical (?:operator|technician|tech)\b",
        r"\bstranding (?:operator|helper|associate)\b",
    ]),
    ("construction_skilled", [
        r"\bcarpenter\b", r"\bcarpenters?\b",
        r"\bmason\b", r"\bmasons?\b", r"\bbrick(?:layer|mason)\b",
        r"\bironworker\b", r"\biron worker\b",
        r"\bsheet metal (?:worker|mechanic|installer)\b",
        r"\bglazier\b",
        r"\broofer\b", r"\broofers?\b",
        r"\bdrywall (?:installer|finisher)\b",
        r"\bpainter\b", r"\bindustrial painter\b",
        r"\bconcrete (?:finisher|worker)\b",
        r"\bequipment operator\b",
        r"\bcrane operator\b",
        r"\bconstruction (?:worker|laborer|technician)\b",
    ]),
    ("logistics_warehouse", [
        r"\bforklift (?:operator|driver)\b",
        r"\bmaterials? handler\b", r"\bmaterials? handling\b",
        r"\bmaterials?,?\s+handler\b",          # "Handler, Materials 2nd"
        r"\bhandler,?\s+materials?\b",          # "Handler, Materials 2nd"
        r"\bmaterials? associate\b",
        r"\bwarehouse (?:associate|operator|specialist|technician|coordinator)\b",
        r"\bcdl driver\b", r"\bclass [ab] driver\b",
        r"\bshipping (?:and|&) receiving (?:clerk|associate|tech)\b",
        r"\breceiving (?:clerk|associate|tech|technician)\b",
        r"\binventory (?:specialist|associate|technician)\b",
        r"\bstockroom (?:associate|attendant|clerk)\b",
        r"\btool room (?:attendant|associate|tech)\b",
        r"\bstorekeeper\b",
        r"\bdistribution (?:associate|specialist|operator|supervisor)\b",
    ]),
]

# Compile once at import time — every classify() call is just a list of
# precompiled regex tests, no per-call compilation cost.
_COMPILED: list[tuple[str, list[re.Pattern[str]]]] = [
    (family, [re.compile(p, re.IGNORECASE) for p in patterns])
    for family, patterns in FAMILIES
]

# Negative guards — titles that contain ONLY these tokens (no positive trade
# match above) are corporate roles, not trades. We veto.
_DENY_TITLES = re.compile(
    r"\b("
    r"engineer|engineering|"
    r"scientist|analyst|"
    r"manager|director|supervisor|coordinator|administrator|"
    r"recruiter|hr |human resources|marketing|sales|"
    r"finance|accountant|accounting|legal|counsel|"
    r"designer|architect|"
    r"vp|vice president|chief|"
    r"intern\b|internship|"
    r"buyer|procurement|"
    r"consultant|"
    r"product (?:manager|owner|designer)|"
    r"data (?:scientist|analyst|engineer)|"
    r"software (?:engineer|developer)|"
    r"devops|sre|cyber|security analyst"
    r")\b",
    re.IGNORECASE,
)

# A few title patterns explicitly stay trades even when a deny token appears
# in the same string (e.g. "Maintenance Supervisor" — the trade dominates).
_TRADE_OVERRIDE = re.compile(
    r"\b("
    r"electrician|welder|machinist|millwright|"
    r"pipefitter|plumber|carpenter|mason|"
    r"ironworker|glazier|roofer|"
    r"lineman|lineworker|"
    r"mechanic|technician|operator|fitter|installer|"
    r"apprentice|journeyman|"
    r"maintenance|production|assembly|machining|"
    r"assembler|fabricator|fabrication|"
    r"maintainer|machinist|millwright|"
    r"inspector|stockroom|storekeeper|handler|"
    r"warehouse|forklift|welder"
    r")\b",
    re.IGNORECASE,
)


def classify(title: str, description: Optional[str] = None) -> TradeMatch:
    """
    Decide whether (title, description) is a skilled-trades job. Returns the
    canonical family code on a positive match, or `is_trade=False` otherwise.

    Two-pass logic — title is authoritative; description is a tie-breaker.
    """
    if not title:
        return TradeMatch(False, reason="empty title")

    haystack = title  # title is the primary signal — fast path
    for family, patterns in _COMPILED:
        for pat in patterns:
            m = pat.search(haystack)
            if m:
                # Strong title hit. Still check the deny list — unless a real
                # trade verb is also present (e.g. "Maintenance Supervisor").
                if _DENY_TITLES.search(haystack) and not _TRADE_OVERRIDE.search(haystack):
                    continue
                return TradeMatch(True, family=family, matched_term=m.group(0),
                                  reason="title match")

    # Title didn't match. If we have a description, try the description as a
    # weaker secondary signal — but ONLY if the title isn't an obvious deny.
    if description and not _DENY_TITLES.search(haystack):
        for family, patterns in _COMPILED:
            for pat in patterns:
                m = pat.search(description)
                if m:
                    return TradeMatch(True, family=family, matched_term=m.group(0),
                                      reason="description match")

    return TradeMatch(False, reason="no trade match")


def is_trade(title: str, description: Optional[str] = None) -> bool:
    """Convenience wrapper — boolean check only."""
    return classify(title, description).is_trade
