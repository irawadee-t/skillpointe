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
    ("power_plant", [
        # Nuclear/reactor roles are their own canonical family; generic
        # "power plant operator" stays in utilities_energy (test-pinned).
        r"\bnuclear (?:tech|technician|operator)\b",
        r"\breactor operator\b",
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
        r"\bship ?builder\b",     ]),
    ("building_automation", [
        r"\bbuilding automation (?:tech|technician|specialist)\b",
        r"\bbas tech(?:nician)?\b",
        r"\bbuilding controls (?:tech|technician)\b",
        r"\benergy management tech(?:nician)?\b",
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
    ("rail_transit", [
        # Must precede automotive_diesel — "Locomotive Diesel Technician"
        # would otherwise hit the generic diesel pattern.
        # Signal and track titles are NOT listed here: Tasha's taxonomy
        # splits rail into vehicle / signals / track fields, and the
        # taxonomy layer below routes those titles to the finer field.
        r"\blocomotive (?:diesel )?(?:tech|technician|mechanic)\b",
        r"\brail(?:car|road) (?:tech|technician|mechanic)\b",
        r"\bbridge[/\s].*?(?:rail|structure).*?tech(?:nician)?\b",
    ]),
    ("marine", [
        # Must precede automotive_diesel — "Marine Mechanic" would otherwise
        # hit the bare \bmechanic\b pattern.
        r"\bmarine (?:tech|technician|mechanic)\b",
        r"\boutboard (?:tech|technician|mechanic)\b",
        r"\bshipwright\b",
    ]),
    ("field_service", [
        # Must precede automotive_diesel — "Field Service Technician" would
        # otherwise hit the generic "service technician" pattern.
        r"\bfield service (?:tech|technician|specialist|representative)\b",
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
        r"\b(?:equipment|machine|production) maintainer\b", r"\bmaintainer[- ](?:chemical|process|mechanical|electrical|equipment)\b",                      # Ball uses "Maintainer-Chemical Process"
        r"\bchemical (?:operator|technician|tech)\b",
        r"\bstranding (?:operator|helper|associate)\b",
    ]),
    ("civil_survey", [
        r"\bsurvey(?:ing)? (?:and mapping )?tech(?:nician)?\b",
        r"\bcivil engineering tech(?:nician)?\b",
        r"\bland surveyor\b",
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
        r"\b(?:commercial )?truck driver\b",
        r"\bshipping (?:and|&) receiving (?:clerk|associate|tech)\b",
        r"\breceiving (?:clerk|associate|tech|technician)\b",
        r"\binventory (?:specialist|associate|technician)\b",
        r"\bstockroom (?:associate|attendant|clerk)\b",
        r"\btool room (?:attendant|associate|tech)\b",
        r"\bstorekeeper\b",
        r"\bdistribution (?:associate|specialist|operator|supervisor)\b",
    ]),
    # ---- 2026-07 expansion: security, electronics, data center ----
    ("security", [
        r"\b(?:security|fire) alarm (?:tech|technician|installer)\b",
        r"\balarm (?:installer|technician)\b",
    ]),
    ("electronics", [
        r"\belectro[- ]?mechanical tech(?:nician)?\b",
        r"\belectronics? engineering tech(?:nician)?\b",
    ]),
    ("data_center", [
        r"\bdata center (?:tech|technician|specialist|operator)\b",
        r"\bcritical facilities (?:tech|technician)\b",
    ]),
    # ---- 2026-07 expansion: healthcare (SPF definitive job list) ----
    ("healthcare_support", [
        r"\bcertified nursing assistant\b", r"\bcna\b",
        r"\bmedical assistant\b",
        r"\bphlebotomist\b",
        r"\bpatient care (?:tech|technician)\b",
        r"\bhome health aide\b",
    ]),
    ("nursing", [
        r"\blpn\b", r"\blvn\b",
        r"\blicensed (?:practical|vocational) nurse\b",
    ]),
    ("dental", [
        r"\bdental (?:assistant|hygienist)\b",
    ]),
    ("radiology", [
        r"\bradiolog(?:y|ic) tech(?:nologist|nician)?\b",
        r"\bmri tech(?:nician|nologist)?\b",
        r"\bsonographer\b",
        r"\bcardiovascular tech(?:nician|nologist)?\b",
        r"\bx[- ]?ray tech(?:nician)?\b",
        r"\bekg tech(?:nician)?\b",
    ]),
    ("respiratory", [
        r"\brespiratory therapist\b",
    ]),
    ("physical_therapy", [
        r"\b(?:physical|occupational) therap(?:y|ist) (?:assistant|aide)\b",
    ]),
    ("pharmacy", [
        r"\bpharmacy tech(?:nician)?\b",
    ]),
    ("surgical_tech", [
        r"\bsurgical tech(?:nologist|nician)?\b",
        r"\boperating room tech(?:nician)?\b",
        r"\bscrub tech\b",
    ]),
    ("lab_sciences", [
        r"\b(?:medical )?lab(?:oratory)? tech(?:nician|nologist)\b",
    ]),
    ("veterinary", [
        r"\bvet(?:erinary)? tech(?:nician)?\b",
        r"\bveterinary assistant\b",
    ]),
    ("health_information", [
        r"\bhealth information tech(?:nician|nologist)?\b",
        r"\bmedical records\b",
        r"\bmedical (?:coder|coding|billing)\b",
    ]),
    ("dietetics", [
        r"\b(?:registered )?dietitian\b",
        r"\bdietetic tech(?:nician)?\b",
        r"\bnutritionist\b",
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

    # Taxonomy-complete layer: any of Tasha's 116 fields named in the title
    # is a match, deny-list notwithstanding (the taxonomy IS the authorization).
    tax = classify_taxonomy(haystack)
    if tax.is_trade:
        return tax

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


# ===========================================================================
# Taxonomy-complete layer — every field in the SKILLED Nation taxonomy is
# match-eligible. The hand-curated FAMILIES above cover classic trade titles
# with high precision and run first; this layer guarantees COVERAGE: a job
# whose title names any of Tasha's 116 fields (Construction Management,
# Rail Vehicle Maintenance, Cybersecurity, ...) is never rejected as
# "not trades". A taxonomy hit bypasses the deny list by design — the field's
# presence in the taxonomy IS the authorization (2026-08 audit: the deny
# list was vetoing Construction Manager while construction_management held
# 1,894 classified applicants).
# ===========================================================================

# Job-title forms per field code. Derived from the field names, hand-tuned to
# how the titles appear on real postings (management -> manager, nursing ->
# nurse, machining -> machinist, rail vocab, etc.).
_TAXONOMY_PATTERNS: dict[str, list[str]] = {
    "additive_manufacturing": [r"\badditive manufacturing\b", r"\b3d print"],
    "ai_and_machine_learning": [r"\bmachine learning\b", r"\bml engineer\b", r"\bai (?:engineer|specialist)\b"],
    "architectural_drafting_cad": [r"\bdraft(?:er|ing)\b", r"\bcad (?:tech|designer|drafter|operator)\b"],
    "auto_body_collision": [r"\bauto body\b", r"\bcollision (?:repair|tech)\b", r"\bbody shop\b"],
    "automotive_ev_service": [r"\bautomotive (?:tech|technician|mechanic|service)\b", r"\bev (?:tech|technician)\b"],
    "aviation_maintenance": [r"\baircraft\b", r"\bavionics\b", r"\ba&p mechanic\b"],
    "biomedical_equipment_technology": [r"\bbiomedical (?:equipment|tech)\b", r"\bbmet\b"],
    "building_and_facilities_maintenance": [r"\bfacilit(?:y|ies) (?:maintenance|tech)\b", r"\bbuilding maintenance\b", r"\bhandyman\b"],
    "building_automation_controls": [r"\bbuilding automation\b", r"\bbas (?:tech|specialist)\b", r"\bbms\b"],
    "building_construction_technology": [r"\bconstruction (?:tech|technology|worker|laborer|crew)\b", r"\bgeneral laborer\b"],
    "building_energy_management": [r"\benergy management\b", r"\benergy auditor\b"],
    "cardiovascular_sonography": [r"\bcardiovascular sonograph"],
    "cardiovascular_technician": [r"\bcardiovascular tech\b", r"\bekg tech\b", r"\becg tech\b"],
    "carpentry_and_woodworking": [r"\bcarpent(?:er|ry)\b", r"\bwoodwork"],
    "cloud_computing_and_infrastructure": [r"\bcloud (?:engineer|infrastructure|architect|administrator)\b"],
    "cnc_machining": [r"\bcnc\b", r"\bmachinist\b", r"\bprecision machin"],
    "commercial_driving_cdl": [r"\bcdl\b", r"\btruck driver\b", r"\bcommercial driver\b", r"\bdelivery driver\b"],
    "computer_engineering": [r"\bcomputer engineer"],
    "computer_systems_administration": [r"\bsystems? administrator\b", r"\bsysadmin\b"],
    "construction_management": [r"\bconstruction manag(?:er|ement)\b", r"\bsuperintendent\b", r"\bfield manager\b", r"\bproject engineer\b.{0,20}\bconstruction\b", r"\bconstruction project (?:manager|engineer)\b", r"\bfield engineer\b", r"\bassistant construction manager\b", r"\bpreconstruction\b"],
    "cosmetology_esthetician": [r"\bcosmetolog", r"\besthetician\b", r"\bbarber\b"],
    "cybersecurity": [r"\bcyber ?security\b", r"\bsecurity (?:engineer|analyst|architect)\b", r"\binfosec\b"],
    "data_center_operations": [r"\bdata cent(?:er|re) (?:tech|operations|operator)\b"],
    "data_science_and_analytics": [r"\bdata scien", r"\bdata analy"],
    "database_administration": [r"\bdatabase admin", r"\bdba\b"],
    "dental_assistant": [r"\bdental assistant\b"],
    "dental_hygienist": [r"\bdental hygien"],
    "diagnostic_medical_sonography": [r"\bsonograph", r"\bultrasound tech\b"],
    "diesel_service_and_technology": [r"\bdiesel\b", r"\bfleet (?:mechanic|tech)\b"],
    "diet_nutrition": [r"\bdietitian\b", r"\bnutritionist\b"],
    "electrical": [r"\belectrician\b", r"\belectrical (?:tech|technician|apprentice)\b"],
    "electrical_engineering": [r"\belectrical engineer"],
    "emt_paramedic": [r"\bemt\b", r"\bparamedic\b", r"\bemergency medical tech"],
    "energy_storage": [r"\benergy storage\b", r"\bbattery (?:tech|systems)\b"],
    "exercise_science_and_sports_medicine": [r"\bathletic trainer\b", r"\bsports medicine\b"],
    "fiber_optics_technician": [r"\bfiber (?:optic|splic)", r"\bcable tech"],
    "fire_science": [r"\bfirefighter\b", r"\bfire (?:science|marshal|inspector)\b"],
    "gis": [r"\bgis\b", r"\bgeographic information\b"],
    "health_information": [r"\bhealth information\b", r"\bmedical records\b"],
    "healthcare_system_administration": [r"\bhealthcare admin"],
    "heavy_equipment_operation": [r"\bheavy equipment operat", r"\bexcavator operator\b", r"\bcrane operator\b", r"\bdozer\b", r"\bloader operator\b"],
    "heavy_equipment_service_and_technology": [r"\bheavy equipment (?:mechanic|tech|service)\b"],
    "home_and_building_inspection": [r"\b(?:home|building) inspector\b"],
    "hvac_r": [r"\bhvac\b", r"\brefrigeration (?:tech|mechanic)\b"],
    "industrial_electrical_technology": [r"\bindustrial electric"],
    "industrial_maintenance": [r"\bindustrial maintenance\b", r"\bmillwright\b", r"\bmaintenance (?:mechanic|tech)"],
    "instrumentation_automation_controls": [r"\binstrumentation\b", r"\bcontrols tech", r"\bi&c tech\b", r"\bautomation tech"],
    "instrumentation_controls": [r"\binstrument tech"],
    "interior_finishing": [r"\bdrywall\b", r"\bfloor(?:ing)? install", r"\binsulation install", r"\bpainter\b", r"\bglazier\b"],
    "it_network_support": [r"\bit support\b", r"\bhelp ?desk\b", r"\bnetwork support\b", r"\bdesktop support\b"],
    "laboratory_technician": [r"\blab(?:oratory)? tech"],
    "law_enforcement": [r"\bpolice officer\b", r"\bsecurity officer\b", r"\bcorrections officer\b"],
    "lowvoltage_electrical_technology": [r"\blow[- ]voltage\b"],
    "manufacturing_engineering_tech": [r"\bmanufacturing engineer", r"\bindustrial engineer", r"\bprocess engineer"],
    "manufacturing_production": [r"\bproduction (?:operator|tech|associate|worker|supervisor)\b", r"\bmachine operator\b", r"\bassembl(?:er|y)\b", r"\bfabricat", r"\bplant (?:operator|tech)\b", r"\bmanufacturing (?:operator|associate|tech|supervisor)\b", r"\bpackag(?:er|ing operator)\b"],
    "marine_systems_service": [r"\bmarine (?:tech|mechanic|systems)\b", r"\boutboard\b"],
    "marine_welding": [r"\bmarine weld"],
    "masonry_and_concrete": [r"\bmason(?:ry)?\b", r"\bconcrete\b", r"\bcement (?:mason|finisher)\b"],
    "massage_therapy": [r"\bmassage therap"],
    "mechanical_design_cad_cam": [r"\bcad/?cam\b", r"\bmechanical design"],
    "medical_assistant": [r"\bmedical assistant\b"],
    "medical_billing_and_coding": [r"\bmedical (?:billing|coding|coder)\b"],
    "metrology_cmm": [r"\bmetrology\b", r"\bcmm (?:operator|programmer)\b", r"\bquality inspector\b"],
    "mri_technician": [r"\bmri tech"],
    "network_cabling_technician": [r"\bnetwork cabl", r"\bstructured cabling\b"],
    "network_operations": [r"\bnetwork (?:engineer|operations|admin)"],
    "nursing": [r"\b(?:registered )?nurse\b", r"\brn\b", r"\blpn\b", r"\blvn\b"],
    "nursing_assistant": [r"\bcna\b", r"\bnursing assistant\b", r"\bcaregiver\b"],
    "occupational_therapy_assistant": [r"\boccupational therapy assistant\b", r"\bcota\b"],
    "oil_gas_production": [r"\boil (?:and|&) gas\b", r"\broustabout\b", r"\bderrick"],
    "patient_care": [r"\bpatient care\b", r"\bhome health aide\b"],
    "pharmacy_technician": [r"\bpharmacy tech"],
    "phlebotomist": [r"\bphlebotom"],
    "physical_therapy_assistant": [r"\bphysical therap(?:y|ist) assistant\b", r"\bpta\b"],
    "pipefitting_steamfitting": [r"\bpipe ?fitter\b", r"\bsteam ?fitter\b", r"\bpipefitting\b"],
    "pipeline_construction": [r"\bpipeline\b"],
    "pipeline_welding": [r"\bpipeline weld"],
    "plastics_composites": [r"\bplastics\b", r"\bcomposites?\b", r"\binjection mold", r"\bextrusion\b"],
    "plumbing": [r"\bplumb"],
    "power_plant_operation": [r"\bpower plant\b", r"\bplant operator\b", r"\bturbine\b"],
    "powersports_service": [r"\bmotorcycle (?:tech|mechanic)\b", r"\bpowersports\b"],
    "process_technology_and_plant_operations": [r"\bprocess (?:tech|operator)\b", r"\bplant operations\b", r"\bchemical operator\b"],
    "qa_testing_and_automation": [r"\bqa (?:engineer|tester|analyst)\b", r"\btest automation\b"],
    "quality_control_and_quality_assurance": [r"\bquality (?:control|assurance|tech)\b", r"\bqc (?:tech|inspector)\b"],
    "radiology_technician": [r"\bradiolog(?:y|ic) tech", r"\bx-?ray tech"],
    "rail_signals_controls": [r"\bsignal (?:maintainer|tech|apprentice|electrician)\b", r"\brail signal", r"\bc&s (?:tech|maintainer)\b", r"\bcommunications? (?:&|and) signals?\b"],
    "rail_vehicle_maintenance": [r"\bcarman\b", r"\bcar (?:repair|inspector)\b.{0,20}\brail", r"\blocomotive\b", r"\brailcar\b", r"\bfreight car\b", r"\bconductor\b", r"\bbrakeman\b", r"\bswitchman\b", r"\byardmaster\b", r"\btrain(?:man| crew| service)\b"],
    "railway_track_maintenance": [r"\btrack (?:laborer|maintainer|maintenance|foreman|inspector|worker)\b", r"\btrackman\b", r"\bmaintenance of way\b", r"\bmow\b", r"\broadmaster\b"],
    "refrigeration": [r"\brefrigeration\b"],
    "renewable_energy": [r"\brenewable\b", r"\bsolar\b", r"\bwind energy\b"],
    "respiratory_therapy": [r"\brespiratory therap"],
    "robotics_mechatronics": [r"\brobotics?\b", r"\bmechatronic"],
    "security_systems_locksmithing": [r"\blocksmith\b", r"\bsecurity system(?:s)? (?:tech|install)"],
    "sheet_metal_fabrication": [r"\bsheet metal\b"],
    "shipfitting_and_boat_building": [r"\bship ?fitt", r"\bshipwright\b", r"\bboat build", r"\bshipbuild", r"\bhull (?:tech|mechanic)\b", r"\brigger\b"],
    "software_and_web_development": [r"\bsoftware (?:engineer|developer)\b", r"\bweb develop", r"\bfull ?stack\b"],
    "solar_installation": [r"\bsolar install", r"\bpv install"],
    "surgical_technology": [r"\bsurgical tech"],
    "surveying_mapping": [r"\bsurvey(?:or|ing)\b"],
    "telecommunications_technician": [r"\btelecom(?:munications)? tech", r"\bcentral office tech\b"],
    "tool_die_mold": [r"\btool (?:and|&) die\b", r"\btoolmaker\b", r"\bmold maker\b", r"\bdie maker\b"],
    "transmission_linework": [r"\bline(?:man|worker)\b", r"\bpowerline\b", r"\btransmission line\b"],
    "utility_public_works": [r"\butilit(?:y|ies) (?:tech|worker|operator)\b", r"\bpublic works\b", r"\bmeter (?:tech|reader)\b"],
    "veterinary_technician": [r"\bveterinary tech", r"\bvet tech\b"],
    "wastewater_operations": [r"\bwastewater\b", r"\bwater treatment\b"],
    "welding_fabrication": [r"\bweld(?:er|ing)\b"],
    "wind_turbine_technology": [r"\bwind turbine\b", r"\bwind tech"],
}

_TAXONOMY_COMPILED: list[tuple[str, list[re.Pattern[str]]]] = [
    (code, [re.compile(p, re.IGNORECASE) for p in pats])
    for code, pats in _TAXONOMY_PATTERNS.items()
]

# Even taxonomy coverage keeps obvious non-field noise out: a title that is
# ONLY commercial/administrative never becomes a field match by accident.
_TAXONOMY_HARD_DENY = re.compile(
    r"\b(sales|marketing|recruiter|talent acquisition|payroll|accountant|"
    r"accounting|finance|financial|legal|counsel|attorney|intern|internship|"
    r"escrow|mortgage|loan)\b",
    re.IGNORECASE,
)


def classify_taxonomy(title: str) -> TradeMatch:
    """Match a title against the full SKILLED Nation field taxonomy."""
    if not title or _TAXONOMY_HARD_DENY.search(title):
        return TradeMatch(False, reason="taxonomy: denied or empty")
    for code, patterns in _TAXONOMY_COMPILED:
        for pat in patterns:
            m = pat.search(title)
            if m:
                return TradeMatch(True, family=code, matched_term=m.group(0),
                                  reason="taxonomy field match")
    return TradeMatch(False, reason="taxonomy: no field match")
