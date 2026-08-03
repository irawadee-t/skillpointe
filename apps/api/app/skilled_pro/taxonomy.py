"""
Credential taxonomy + normalization.

A canonical taxonomy of the major U.S. skilled-trades credentials (certs,
licenses, degrees) plus a normalizer that maps free-text strings — from user
input, OCR, SIS feeds, résumé parsing, or partner uploads — onto canonical
entries.

Design goals
------------
- Deterministic and dependency-free (pure stdlib) so it is fully unit-testable.
- Alias-driven: every canonical entry carries the real-world surface forms we
  see across sources. Matching is exact → longest word-boundary alias →
  fuzzy, so the common cases are exact and only the long tail falls back to
  fuzzy. Longest-alias-wins guarantees "CDL A" beats "CDL" — specificity
  ordering, never first-match-wins.
- Honest confidence: every match returns a 0..1 confidence so callers can route
  low-confidence matches to the admin review queue rather than trusting them.
- Ambiguity is surfaced, not guessed: a bare "CDA" (dental assistant vs child
  development associate) deliberately has no alias and falls to review.

The registry is mirrored into the ``credential_definitions`` table (see
supabase/migrations/*credential_taxonomy_registry*.sql — generated from this
module by scripts/gen_credential_definitions_sql.py). ``code`` here is the
stable machine key; ``slug`` (= code lowercased) is what the DB stores in
``credential_definitions.canonical_code`` and what the matching layer meets on.

Grounding sources for validity/verification facts: OSHA outreach-card policy,
EPA 608 (lifetime, 40 CFR 82), ASE (5-year recert), NATE (2-year/16 CEH),
NCCCO (5-year), MSSC (5-year/100 pts), AWS CW (6-month maintenance forms),
CompTIA CE (3-year), NCCER Registry, Nursys, PTCB, BACB, FAA Airmen Inquiry.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CredentialType(str, Enum):
    """Trades-appropriate credential categories.

    Grounded in the Credential Engine CTDL credential-type vocabulary
    (Certification, License, Degree/Diploma, ApprenticeshipCertificate, …) and
    the fields LinkedIn's licenses-and-certifications form collects, collapsed
    to the set that matters for skilled-trades hiring.
    """
    LICENSE = "license"
    CERTIFICATION = "certification"
    DEGREE = "degree"                  # degree or diploma
    APPRENTICESHIP = "apprenticeship"
    SAFETY = "safety"                  # safety training (OSHA, CPR, …)
    UNION = "union"                    # union membership
    OTHER = "other"


@dataclass(frozen=True)
class CanonicalCredential:
    code: str               # stable machine code, e.g. "EPA_608"
    name: str               # canonical display name
    type: CredentialType
    job_families: tuple[str, ...]  # related trade families (canonical_job_families.code)
    issuer: Optional[str] = None   # typical issuing body, if standardized
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Typical validity / renewal cadence, phrased for humans. None = unknown.
    validity: Optional[str] = None
    # Public registry where a holder can be looked up, when one exists.
    verify_url: Optional[str] = None

    @property
    def slug(self) -> str:
        """DB-facing key (credential_definitions.canonical_code)."""
        return self.code.lower()


_C = CanonicalCredential
_T = CredentialType

# ---------------------------------------------------------------------------
# Canonical taxonomy — major U.S. trade certs, licenses, and degrees.
# Aliases are matched case/punctuation-insensitively at word boundaries.
# Never put a genuinely ambiguous bare token (e.g. "CDA") on any entry.
# ---------------------------------------------------------------------------

TAXONOMY: tuple[CanonicalCredential, ...] = (
    # =================== Safety / cross-trade ===================
    _C("OSHA_10", "OSHA 10-Hour Safety Card", _T.SAFETY,
       ("construction", "electrical", "welding", "hvac", "manufacturing", "logistics"),
       "OSHA-authorized trainer",
       ("osha 10", "osha10", "osha 10 hour", "10 hour osha", "osha 10 card",
        "10 hour card", "osha 10 construction", "osha 10 general industry"),
       "No federal expiration; many employers and some state laws want completion within the last 5 years"),
    _C("OSHA_30", "OSHA 30-Hour Safety Card", _T.SAFETY,
       ("construction", "electrical", "welding", "hvac", "manufacturing", "construction_mgmt"),
       "OSHA-authorized trainer",
       ("osha 30", "osha30", "osha 30 hour", "30 hour osha", "osha 30 card",
        "osha 30 construction", "osha 30 general industry"),
       "No federal expiration; many employers and some state laws want completion within the last 5 years"),
    _C("HAZWOPER_40", "OSHA HAZWOPER 40-Hour", _T.SAFETY,
       ("construction", "manufacturing", "industrial_maintenance"),
       "OSHA-authorized trainer",
       ("hazwoper", "hazwoper 40", "40 hour hazwoper", "hazwoper certification"),
       "8-hour refresher required annually"),
    _C("NFPA_70E", "NFPA 70E Arc Flash / Electrical Safety Training", _T.SAFETY,
       ("electrical", "energy_lineman", "building_automation", "industrial_maintenance"),
       "NFPA-aligned trainer",
       ("nfpa 70e", "70e", "arc flash", "arc flash training", "electrical safety training"),
       "Retraining at least every 3 years"),
    _C("CONFINED_SPACE", "Confined Space Entry Training", _T.SAFETY,
       ("construction", "manufacturing", "industrial_maintenance"),
       None,
       ("confined space", "confined space entry", "confined space training")),
    _C("FALL_PROTECTION", "Fall Protection Training", _T.SAFETY,
       ("construction", "wind_energy", "energy_lineman"),
       None,
       ("fall protection", "fall arrest", "fall protection training"),
       "Employers commonly require refresh every 2 years"),
    _C("LOTO", "Lockout/Tagout (LOTO) Training", _T.SAFETY,
       ("manufacturing", "industrial_maintenance", "power_plant"),
       None,
       ("lockout tagout", "loto", "lock out tag out"),
       "Employer retraining on procedure change; annual review is common"),
    _C("CPR_FIRST_AID", "CPR / First Aid / AED", _T.SAFETY,
       ("construction", "manufacturing", "healthcare_support", "childcare_education", "security"),
       "American Red Cross / American Heart Association",
       ("cpr", "first aid", "cpr first aid", "cpr and first aid", "aed", "cpr aed"),
       "Renew every 2 years"),
    _C("BLS", "Basic Life Support (BLS) Provider", _T.SAFETY,
       ("nursing", "healthcare_support", "surgical_tech", "respiratory", "radiology",
        "dental", "pharmacy"),
       "American Heart Association",
       ("bls", "basic life support", "bls provider", "bls cpr", "bls certification"),
       "Renew every 2 years"),
    _C("ACLS", "Advanced Cardiovascular Life Support (ACLS)", _T.SAFETY,
       ("nursing", "respiratory"),
       "American Heart Association",
       ("acls", "advanced cardiac life support", "advanced cardiovascular life support"),
       "Renew every 2 years"),
    _C("GWO_BST", "GWO Basic Safety Training", _T.SAFETY,
       ("wind_energy",),
       "Global Wind Organisation",
       ("gwo", "gwo bst", "gwo basic safety training", "winda"),
       "Valid 2 years; refresh modules required",
       "https://winda.globalwindsafety.org"),
    _C("TWIC", "TWIC — Transportation Worker Identification Credential", _T.LICENSE,
       ("logistics", "marine", "rail_transit"),
       "TSA",
       ("twic", "twic card", "transportation worker identification credential"),
       "Valid 5 years"),
    _C("DOT_MEDICAL", "DOT Medical Examiner's Certificate", _T.OTHER,
       ("logistics", "heavy_equipment"),
       "FMCSA-certified medical examiner",
       ("dot medical card", "dot physical", "dot med card", "medical examiners certificate"),
       "Valid up to 2 years"),

    # =================== Construction / general trades ===================
    _C("FORKLIFT_PIT", "Forklift / Powered Industrial Truck Operator", _T.CERTIFICATION,
       ("manufacturing", "logistics", "construction"),
       "OSHA (employer-certified)",
       ("forklift", "forklift certification", "forklift license", "forklift operator",
        "powered industrial truck", "lift truck"),
       "Employer re-evaluation at least every 3 years"),
    _C("NCCER_CORE", "NCCER Core", _T.CERTIFICATION,
       ("construction",),
       "NCCER",
       ("nccer", "nccer core", "nccer certified", "core curriculum",
        "national center for construction education"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_ELECTRICAL", "NCCER Electrical (Craft Level)", _T.CERTIFICATION,
       ("electrical",), "NCCER",
       ("nccer electrical", "nccer electrician", "electrical levels 1 4"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_WELDING", "NCCER Welding (Craft Level)", _T.CERTIFICATION,
       ("welding",), "NCCER",
       ("nccer welding", "nccer welder"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_HVAC", "NCCER HVAC (Craft Level)", _T.CERTIFICATION,
       ("hvac",), "NCCER",
       ("nccer hvac", "nccer hvac r"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_PLUMBING", "NCCER Plumbing (Craft Level)", _T.CERTIFICATION,
       ("plumbing",), "NCCER",
       ("nccer plumbing", "nccer plumber"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_PIPEFITTING", "NCCER Pipefitting (Craft Level)", _T.CERTIFICATION,
       ("plumbing", "construction"), "NCCER",
       ("nccer pipefitting", "nccer pipefitter", "pipefitter certification"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_CARPENTRY", "NCCER Carpentry (Craft Level)", _T.CERTIFICATION,
       ("construction",), "NCCER",
       ("nccer carpentry", "nccer carpenter", "carpentry certification"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_MILLWRIGHT", "NCCER Millwright (Craft Level)", _T.CERTIFICATION,
       ("industrial_maintenance", "manufacturing"), "NCCER",
       ("nccer millwright", "millwright certification"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_INDUSTRIAL_MAINT", "NCCER Industrial Maintenance", _T.CERTIFICATION,
       ("industrial_maintenance",), "NCCER",
       ("nccer industrial maintenance", "industrial maintenance craft"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("NCCER_HEAVY_EQUIP", "NCCER Heavy Equipment Operations", _T.CERTIFICATION,
       ("heavy_equipment",), "NCCER",
       ("nccer heavy equipment", "nccer heavy equipment operations"),
       "Does not expire; recorded in the NCCER Registry",
       "https://registry.nccer.org"),
    _C("HEAVY_EQUIP_CERT", "Heavy Equipment Operator Certification", _T.CERTIFICATION,
       ("heavy_equipment", "construction"),
       "NCCER / IUOE / trade school",
       ("heavy equipment operator", "heavy equipment certification",
        "heavy equipment operator certification", "equipment operator certification")),
    _C("EPA_LEAD_RRP", "EPA Lead RRP (Renovation, Repair & Painting)", _T.CERTIFICATION,
       ("construction",), "EPA",
       ("lead rrp", "epa rrp", "rrp", "rrp certification", "lead renovator",
        "renovation repair and painting", "renovation repair painting"),
       "Valid 5 years"),
    _C("NCCCO_CRANE", "NCCCO Certified Crane Operator", _T.CERTIFICATION,
       ("heavy_equipment", "construction"),
       "NCCCO",
       ("nccco", "cco", "crane operator certification", "certified crane operator",
        "nccco crane", "crane certification"),
       "Valid 5 years; recertify in the final 12 months",
       "https://www.nccco.org/nccco/verify-cco"),
    _C("NCCCO_RIGGER", "NCCCO Rigger / Signalperson", _T.CERTIFICATION,
       ("construction", "heavy_equipment"),
       "NCCCO",
       ("rigger certification", "signalperson", "rigger signalperson", "qualified rigger",
        "certified rigger"),
       "Valid 5 years",
       "https://www.nccco.org/nccco/verify-cco"),
    _C("AERIAL_LIFT", "Aerial Lift / MEWP Operator Training", _T.CERTIFICATION,
       ("construction", "field_service"),
       None,
       ("aerial lift", "mewp", "boom lift certification", "scissor lift certification",
        "aerial lift certification"),
       "Re-evaluation every 3 years is standard (ANSI A92)"),
    _C("CONTRACTOR_LICENSE", "State Contractor License", _T.LICENSE,
       ("construction", "construction_mgmt"),
       "State contractor licensing board",
       ("contractor license", "general contractor license", "licensed contractor",
        "gc license"),
       "State license; renewal cycle varies by state (search your state's contractor license lookup)"),
    _C("LEED_GA", "LEED Green Associate", _T.CERTIFICATION,
       ("construction_mgmt",),
       "GBCI / USGBC",
       ("leed", "leed green associate", "leed ap"),
       "2-year continuing-education cycle"),

    # =================== Electrical / energy ===================
    _C("ELEC_APPRENTICE", "Electrical Apprenticeship", _T.APPRENTICESHIP,
       ("electrical",), "DOL / IBEW / IEC",
       ("electrical apprentice", "electrician apprentice", "apprentice electrician",
        "electrical apprenticeship")),
    _C("ELEC_JOURNEYMAN", "Journeyman Electrician License", _T.LICENSE,
       ("electrical",), "State licensing board",
       ("journeyman electrician", "journeyman electrical license", "journeyperson electrician",
        "licensed journeyman electrician", "j man electrician", "journeyman electrician license"),
       "State license; typically renews every 1–3 years with continuing education (verify via your state's license lookup)"),
    _C("ELEC_MASTER", "Master Electrician License", _T.LICENSE,
       ("electrical",), "State licensing board",
       ("master electrician", "master electrical license", "licensed master electrician"),
       "State license; typically renews every 1–3 years (verify via your state's license lookup)"),
    _C("LOW_VOLTAGE", "Low-Voltage / Limited Energy Technician License", _T.LICENSE,
       ("electrical", "building_automation", "electronics"),
       "State licensing board",
       ("low voltage license", "low voltage technician", "limited energy", "low voltage")),
    _C("LINEMAN_JOURNEY", "Journeyman Lineman", _T.APPRENTICESHIP,
       ("energy_lineman",), "DOL / IBEW",
       ("journeyman lineman", "journeyman lineworker", "lineman", "lineworker")),
    _C("NABCEP_PV", "NABCEP PV Installation Professional", _T.CERTIFICATION,
       ("solar_energy", "electrical"),
       "NABCEP",
       ("nabcep", "nabcep pv", "pv installation professional", "solar installer certification",
        "solar certification"),
       "Valid 3 years",
       "https://www.nabcep.com/certification-verification"),
    _C("BOILER_OPERATOR", "Stationary Engineer / Boiler Operator License", _T.LICENSE,
       ("power_plant", "industrial_maintenance"),
       "City/state licensing authority",
       ("boiler operator", "stationary engineer", "boiler license",
        "high pressure boiler operator")),

    # =================== HVAC ===================
    _C("EPA_608", "EPA Section 608 Technician Certification", _T.CERTIFICATION,
       ("hvac", "field_service"), "EPA",
       ("epa 608", "epa section 608", "section 608", "608 certification",
        "epa universal", "universal epa", "epa 608 universal", "608 universal",
        "epa refrigerant", "refrigerant certification", "universal refrigerant",
        "epa 608 type i", "epa 608 type ii", "epa 608 type iii"),
       "Lifetime — does not expire under 40 CFR Part 82"),
    _C("EPA_609", "EPA Section 609 MVAC Certification", _T.CERTIFICATION,
       ("automotive", "hvac"), "EPA",
       ("epa 609", "section 609", "mvac", "mvac certification", "609 certification"),
       "Lifetime — does not expire"),
    _C("NATE", "NATE (North American Technician Excellence)", _T.CERTIFICATION,
       ("hvac",), "NATE",
       ("nate", "nate certified", "nate certification", "north american technician excellence"),
       "Valid 2 years; renew with 16 CEHs or by retesting"),
    _C("HVAC_EXCELLENCE", "HVAC Excellence Certification", _T.CERTIFICATION,
       ("hvac",), "HVAC Excellence",
       ("hvac excellence", "hvac excellence certified")),
    _C("HVAC_LICENSE", "State HVAC Contractor / Technician License", _T.LICENSE,
       ("hvac",), "State licensing board",
       ("hvac license", "hvac contractor license", "hvac technician license",
        "licensed hvac technician"),
       "State license; renewal cycle varies by state (verify via your state's license lookup)"),

    # =================== Plumbing ===================
    _C("PLUMB_APPRENTICE", "Plumbing Apprenticeship", _T.APPRENTICESHIP,
       ("plumbing",), "DOL / UA",
       ("plumbing apprentice", "apprentice plumber", "plumbing apprenticeship")),
    _C("PLUMB_JOURNEYMAN", "Journeyman Plumber License", _T.LICENSE,
       ("plumbing",), "State licensing board",
       ("journeyman plumber", "journeyman plumbing license", "licensed journeyman plumber",
        "journeyman plumber license"),
       "State license; typically renews every 1–3 years (verify via your state's license lookup)"),
    _C("PLUMB_MASTER", "Master Plumber License", _T.LICENSE,
       ("plumbing",), "State licensing board",
       ("master plumber", "master plumbing license", "licensed master plumber"),
       "State license; typically renews every 1–3 years (verify via your state's license lookup)"),
    _C("BACKFLOW", "Backflow Prevention Assembly Tester", _T.CERTIFICATION,
       ("plumbing",), "ASSE / state program",
       ("backflow", "backflow tester", "backflow prevention", "asse 5110",
        "backflow certification"),
       "Typically valid 3 years"),
    _C("MED_GAS", "Medical Gas Installer (ASSE 6010)", _T.CERTIFICATION,
       ("plumbing",), "ASSE",
       ("medical gas", "med gas", "asse 6010", "medical gas installer"),
       "Valid 3 years"),

    # =================== Welding ===================
    _C("AWS_CW", "AWS Certified Welder", _T.CERTIFICATION,
       ("welding",), "American Welding Society",
       ("aws certified welder", "certified welder", "aws cw", "aws welding certification",
        "certified welding"),
       "Stays active with a maintenance form every 6 months confirming continued use of the process"),
    _C("AWS_CWI", "AWS Certified Welding Inspector", _T.CERTIFICATION,
       ("welding",), "American Welding Society",
       ("aws cwi", "cwi", "certified welding inspector", "welding inspector"),
       "Renew every 3 years; full recertification every 9 years"),
    _C("AWS_D1_1", "AWS D1.1 Structural Steel Qualification", _T.CERTIFICATION,
       ("welding",), "American Welding Society",
       ("aws d1 1", "d1 1", "structural welding certification", "structural steel welding"),
       "Code qualification; continuity typically required every 6 months"),
    _C("WELDER_QUAL", "Welder Performance Qualification (process-specific)", _T.CERTIFICATION,
       ("welding", "manufacturing"),
       "Employer / accredited test facility (AWS, ASME)",
       ("welder qualification", "welding qualification", "wpq",
        "tig certification", "mig certification", "stick certification",
        "gtaw certification", "gmaw certification", "smaw certification",
        "fcaw certification", "certified tig welder", "certified mig welder",
        "tig certified", "mig certified"),
       "Continuity typically required every 6 months per code"),
    _C("ASME_IX", "ASME Section IX Welder Qualification", _T.CERTIFICATION,
       ("welding", "manufacturing", "power_plant"),
       "ASME-accredited test facility",
       ("asme section ix", "asme ix", "asme welding", "pressure vessel welding"),
       "Continuity typically required every 6 months"),
    _C("API_1104", "API 1104 Pipeline Welding Qualification", _T.CERTIFICATION,
       ("welding",), "API-accredited test facility",
       ("api 1104", "pipeline welding", "pipeline welding qualification"),
       "Continuity typically required every 6 months"),

    # =================== Manufacturing / industrial / electronics ===================
    _C("MSSC_CPT", "MSSC Certified Production Technician", _T.CERTIFICATION,
       ("manufacturing",), "MSSC",
       ("cpt", "mssc cpt", "mssc", "certified production technician"),
       "Valid 5 years; 100 recertification points to renew"),
    _C("MSSC_CLT", "MSSC Certified Logistics Technician", _T.CERTIFICATION,
       ("logistics",), "MSSC",
       ("clt", "mssc clt", "certified logistics technician"),
       "Valid 5 years"),
    _C("NIMS_MACHINING", "NIMS Machining Credential", _T.CERTIFICATION,
       ("manufacturing",), "NIMS",
       ("nims", "nims machining", "nims credential", "nims certified"),
       "Does not expire"),
    _C("CMRT", "SMRP Certified Maintenance & Reliability Technician", _T.CERTIFICATION,
       ("industrial_maintenance",), "SMRP",
       ("cmrt", "certified maintenance and reliability technician"),
       "Valid 3 years"),
    _C("LEAN_SIX_SIGMA", "Lean Six Sigma Belt", _T.CERTIFICATION,
       ("manufacturing", "construction_mgmt", "administrative"),
       "Varies (ASQ, IASSC, employer programs)",
       ("six sigma", "lean six sigma", "six sigma green belt", "six sigma black belt",
        "lean manufacturing certification", "green belt", "yellow belt")),
    _C("FANUC_ROBOT", "FANUC Robot Operations & Programming Certificate", _T.CERTIFICATION,
       ("robotics", "manufacturing"), "FANUC",
       ("fanuc", "fanuc certified", "robot programming certificate", "fanuc robot")),
    _C("IPC_610", "IPC-A-610 Certified (Electronics Assembly)", _T.CERTIFICATION,
       ("electronics", "manufacturing"), "IPC",
       ("ipc a 610", "ipc 610", "ipc certified"),
       "Valid 2 years"),
    _C("J_STD_001", "IPC J-STD-001 Soldering Certification", _T.CERTIFICATION,
       ("electronics",), "IPC",
       ("j std 001", "ipc j std", "soldering certification"),
       "Valid 2 years"),

    # =================== Automotive / collision ===================
    _C("ASE", "ASE (Automotive Service Excellence) Certification", _T.CERTIFICATION,
       ("automotive",), "ASE",
       ("ase", "ase certified", "ase certification", "automotive service excellence",
        "ase master", "ase master technician", "ase a series"),
       "Valid 5 years; recertification test (or ASE renewal app) to maintain"),
    _C("ICAR", "I-CAR Training (Collision Repair)", _T.CERTIFICATION,
       ("auto_body",), "I-CAR",
       ("i car", "icar", "i car platinum", "i car gold"),
       "Platinum recognition renews annually"),

    # =================== Aviation / marine / rail ===================
    _C("FAA_AP", "FAA Airframe & Powerplant (A&P) Mechanic Certificate", _T.LICENSE,
       ("aviation",), "FAA",
       ("a p license", "a p mechanic", "faa a p", "ap mechanic",
        "airframe and powerplant", "airframe powerplant", "powerplant mechanic"),
       "Does not expire; FAA recent-experience requirements apply",
       "https://amsrvs.registry.faa.gov/airmeninquiry/"),
    _C("FAA_107", "FAA Part 107 Remote Pilot Certificate", _T.LICENSE,
       ("aviation", "civil_survey", "field_service"), "FAA",
       ("part 107", "faa part 107", "remote pilot", "drone license",
        "drone pilot certificate", "remote pilot certificate"),
       "Recurrent online training every 24 months",
       "https://amsrvs.registry.faa.gov/airmeninquiry/"),
    _C("ABYC", "ABYC Marine Technician Certification", _T.CERTIFICATION,
       ("marine",), "ABYC",
       ("abyc", "abyc certified", "marine technician certification"),
       "Valid 5 years"),
    _C("USCG_MMC", "USCG Merchant Mariner Credential", _T.LICENSE,
       ("marine",), "U.S. Coast Guard",
       ("mmc", "merchant mariner", "merchant mariner credential", "uscg mmc"),
       "Valid 5 years"),

    # =================== Transportation / logistics ===================
    _C("CDL_A", "Commercial Driver's License — Class A", _T.LICENSE,
       ("logistics", "heavy_equipment"), "State DMV",
       ("cdl a", "class a cdl", "cdl class a", "class a commercial drivers license",
        "class a license"),
       "Renews on the state driver's-license cycle (typically 4–8 years); verify via the issuing state DMV"),
    _C("CDL_B", "Commercial Driver's License — Class B", _T.LICENSE,
       ("logistics", "rail_transit", "heavy_equipment"), "State DMV",
       ("cdl b", "class b cdl", "cdl class b", "class b license"),
       "Renews on the state driver's-license cycle; verify via the issuing state DMV"),
    _C("CDL_C", "Commercial Driver's License — Class C", _T.LICENSE,
       ("logistics",), "State DMV",
       ("cdl c", "class c cdl", "cdl class c"),
       "Renews on the state driver's-license cycle; verify via the issuing state DMV"),
    _C("CDL_UNSPEC", "Commercial Driver's License (CDL)", _T.LICENSE,
       ("logistics", "heavy_equipment"), "State DMV",
       ("cdl", "commercial drivers license", "commercial driver license",
        "commercial license"),
       "Class unspecified — ask which class (A/B/C); renews on the state cycle"),
    _C("CDL_HAZMAT", "CDL Hazmat Endorsement (H)", _T.LICENSE,
       ("logistics",), "State DMV + TSA",
       ("hazmat endorsement", "hazmat", "h endorsement", "cdl hazmat"),
       "TSA security threat assessment renews every 5 years"),
    _C("CDL_TANKER", "CDL Tanker Endorsement (N)", _T.LICENSE,
       ("logistics",), "State DMV",
       ("tanker endorsement", "n endorsement", "tanker")),
    _C("CDL_DOUBLES", "CDL Doubles/Triples Endorsement (T)", _T.LICENSE,
       ("logistics",), "State DMV",
       ("doubles triples", "t endorsement", "doubles triples endorsement")),
    _C("CDL_PASSENGER", "CDL Passenger Endorsement (P)", _T.LICENSE,
       ("logistics", "rail_transit"), "State DMV",
       ("passenger endorsement", "p endorsement")),
    _C("CDL_SCHOOL_BUS", "CDL School Bus Endorsement (S)", _T.LICENSE,
       ("logistics", "childcare_education"), "State DMV",
       ("school bus endorsement", "s endorsement", "school bus certificate")),

    # =================== Healthcare ===================
    _C("CNA", "Certified Nursing Assistant (CNA)", _T.CERTIFICATION,
       ("nursing", "healthcare_support"),
       "State nurse aide registry",
       ("cna", "certified nursing assistant", "nurse aide", "nursing assistant",
        "state tested nursing assistant", "stna"),
       "2-year renewal with paid work requirement; verify via the state nurse aide registry"),
    _C("LPN_LVN", "Licensed Practical / Vocational Nurse (LPN/LVN)", _T.LICENSE,
       ("nursing",), "State board of nursing",
       ("lpn", "lvn", "licensed practical nurse", "licensed vocational nurse",
        "practical nurse"),
       "State license; typically renews every 2 years",
       "https://www.nursys.com"),
    _C("RN", "Registered Nurse (RN) License", _T.LICENSE,
       ("nursing",), "State board of nursing",
       ("rn", "registered nurse", "rn license", "registered nurse license"),
       "State license; typically renews every 2 years",
       "https://www.nursys.com"),
    _C("CMA", "Certified Medical Assistant (CMA/CCMA/RMA)", _T.CERTIFICATION,
       ("healthcare_support", "administrative"),
       "AAMA / NHA / AMT",
       ("cma", "ccma", "rma", "certified medical assistant", "medical assistant certification",
        "registered medical assistant", "certified clinical medical assistant"),
       "Typically 2–5 year renewal depending on issuer"),
    _C("PHLEBOTOMY", "Certified Phlebotomy Technician", _T.CERTIFICATION,
       ("lab_sciences", "healthcare_support"),
       "NHA / ASCP / NCCT",
       ("phlebotomy", "phlebotomy certification", "certified phlebotomy technician",
        "cpt phlebotomy", "pbt", "phlebotomist"),
       "Typically valid 2 years"),
    _C("EKG_TECH", "Certified EKG Technician (CET)", _T.CERTIFICATION,
       ("healthcare_support",), "NHA",
       ("cet", "ekg technician", "ekg certification", "ecg technician",
        "certified ekg technician"),
       "Valid 2 years"),
    _C("PTCB_CPHT", "Certified Pharmacy Technician (CPhT)", _T.CERTIFICATION,
       ("pharmacy",), "PTCB",
       ("cpht", "ptcb", "pharmacy technician certification", "certified pharmacy technician",
        "pharmacy technician license"),
       "Renew every 2 years with 20 CE hours",
       "https://www.ptcb.org"),
    _C("RBT", "Registered Behavior Technician (RBT)", _T.CERTIFICATION,
       ("healthcare_support", "childcare_education"), "BACB",
       ("rbt", "registered behavior technician", "behavior technician"),
       "Annual renewal",
       "https://www.bacb.com"),
    _C("CST", "Certified Surgical Technologist (CST)", _T.CERTIFICATION,
       ("surgical_tech",), "NBSTSA",
       ("cst", "certified surgical technologist", "surgical tech certification",
        "surgical technologist"),
       "Valid 4 years (CE or retest)",
       "https://www.nbstsa.org"),
    _C("ARRT", "ARRT Registered Technologist (Radiography)", _T.CERTIFICATION,
       ("radiology",), "ARRT",
       ("arrt", "registered radiologic technologist", "radiologic technologist",
        "rad tech certification", "rt r"),
       "Annual registration + 24 CE credits every 2 years; most states also require a license",
       "https://www.arrt.org/pages/verify-credentials"),
    _C("NBRC_RRT", "Registered Respiratory Therapist (RRT)", _T.CERTIFICATION,
       ("respiratory",), "NBRC",
       ("rrt", "crt", "registered respiratory therapist", "certified respiratory therapist",
        "respiratory therapist"),
       "NBRC credential + state RT license; renewal cycles vary"),
    _C("PTA_LICENSE", "Physical Therapist Assistant (PTA) License", _T.LICENSE,
       ("physical_therapy",), "State licensing board",
       ("pta", "physical therapist assistant", "pta license",
        "licensed physical therapist assistant"),
       "State license; typically renews every 2 years"),
    _C("DANB_CDA", "DANB Certified Dental Assistant", _T.CERTIFICATION,
       ("dental",), "DANB",
       ("certified dental assistant", "danb", "danb cda", "dental assistant certification"),
       "Annual renewal with CE"),
    _C("RDH", "Registered Dental Hygienist (RDH) License", _T.LICENSE,
       ("dental",), "State dental board",
       ("rdh", "dental hygienist", "registered dental hygienist", "dental hygiene license"),
       "State license; typically renews every 1–2 years"),
    _C("HHA", "Home Health Aide (HHA) Certificate", _T.CERTIFICATION,
       ("healthcare_support",), "State-approved program",
       ("hha", "home health aide", "home care aide"),
       "State renewal with in-service hours (12/yr federal minimum)"),
    _C("CPC", "Certified Professional Coder (CPC)", _T.CERTIFICATION,
       ("health_information", "administrative"), "AAPC",
       ("cpc", "certified professional coder", "medical coding certification",
        "medical coder"),
       "Annual membership + 36 CEUs per 2 years"),
    _C("RHIT", "Registered Health Information Technician (RHIT)", _T.CERTIFICATION,
       ("health_information",), "AHIMA",
       ("rhit", "health information technician"),
       "CE-based renewal every 2 years"),
    _C("CVT", "Credentialed Veterinary Technician (CVT/RVT/LVT)", _T.LICENSE,
       ("veterinary",), "State veterinary board",
       ("cvt", "rvt", "lvt", "veterinary technician", "vet tech license",
        "credentialed veterinary technician", "vet tech"),
       "State credential; typically renews every 1–3 years"),
    _C("CDM", "Certified Dietary Manager (CDM, CFPP)", _T.CERTIFICATION,
       ("dietetics", "culinary"), "ANFP",
       ("cdm", "certified dietary manager", "dietary manager"),
       "45 CE hours every 3 years"),
    _C("MLT", "Medical Laboratory Technician (MLT) Certification", _T.CERTIFICATION,
       ("lab_sciences",), "ASCP",
       ("mlt", "medical laboratory technician", "lab technician certification",
        "ascp mlt"),
       "3-year Credential Maintenance Program cycle"),

    # =================== Personal services / culinary / security ===================
    _C("COSMETOLOGY_LIC", "Cosmetology License", _T.LICENSE,
       ("cosmetology",), "State board of cosmetology",
       ("cosmetology license", "licensed cosmetologist", "cosmetologist"),
       "State license; typically renews every 1–2 years"),
    _C("BARBER_LIC", "Barber License", _T.LICENSE,
       ("cosmetology",), "State barbering board",
       ("barber license", "licensed barber", "barbering license"),
       "State license; typically renews every 1–2 years"),
    _C("ESTHETICIAN_LIC", "Esthetician License", _T.LICENSE,
       ("cosmetology",), "State board of cosmetology",
       ("esthetician license", "esthetician", "aesthetician license"),
       "State license; typically renews every 1–2 years"),
    _C("NAIL_TECH_LIC", "Nail Technician License", _T.LICENSE,
       ("cosmetology",), "State board of cosmetology",
       ("nail technician license", "nail tech", "manicurist license"),
       "State license; typically renews every 1–2 years"),
    _C("SERVSAFE_MGR", "ServSafe Food Protection Manager", _T.CERTIFICATION,
       ("culinary", "dietetics"), "National Restaurant Association",
       ("servsafe", "servsafe manager", "food protection manager", "food safety manager"),
       "Valid 5 years"),
    _C("FOOD_HANDLER", "Food Handler Card", _T.CERTIFICATION,
       ("culinary",), "ServSafe / state program",
       ("food handler", "food handlers card", "food handler certificate", "food handler card"),
       "Typically 2–3 years, set by state/county"),
    _C("ACF_CC", "ACF Certified Culinarian", _T.CERTIFICATION,
       ("culinary",), "American Culinary Federation",
       ("certified culinarian", "acf certified", "acf certification")),
    _C("GUARD_CARD", "State Security Guard License / Registration", _T.LICENSE,
       ("security",), "State licensing authority",
       ("guard card", "security guard license", "security license", "unarmed guard",
        "armed guard license", "security guard card"),
       "State registration; typically renews every 1–2 years"),

    # =================== Childcare / education ===================
    _C("CDA_CREDENTIAL", "Child Development Associate (CDA) Credential", _T.CERTIFICATION,
       ("childcare_education",), "Council for Professional Recognition",
       ("cda credential", "child development associate"),
       "Valid 3 years"),

    # =================== IT / building tech ===================
    _C("COMPTIA_A", "CompTIA A+", _T.CERTIFICATION,
       ("it_support", "field_service", "data_center"), "CompTIA",
       ("comptia a", "comptia a plus", "a plus certification"),
       "Valid 3 years (Continuing Education program)"),
    _C("COMPTIA_NET", "CompTIA Network+", _T.CERTIFICATION,
       ("it_support", "data_center"), "CompTIA",
       ("comptia network", "network plus", "comptia network plus"),
       "Valid 3 years (Continuing Education program)"),
    _C("COMPTIA_SEC", "CompTIA Security+", _T.CERTIFICATION,
       ("it_support", "data_center", "security"), "CompTIA",
       ("comptia security", "security plus", "comptia security plus"),
       "Valid 3 years (Continuing Education program)"),
    _C("CCNA", "Cisco CCNA", _T.CERTIFICATION,
       ("it_support", "data_center"), "Cisco",
       ("ccna", "cisco certified network associate"),
       "Valid 3 years"),
    _C("BICSI", "BICSI Installer / Technician", _T.CERTIFICATION,
       ("data_center", "building_automation", "electronics"), "BICSI",
       ("bicsi", "bicsi installer", "bicsi technician"),
       "Valid 3 years with CE"),
    _C("NICET", "NICET Certification (Fire Alarm / Low Voltage)", _T.CERTIFICATION,
       ("building_automation", "electrical"), "NICET",
       ("nicet", "nicet ii", "nicet certification", "fire alarm certification"),
       "Recertify every 3 years with CPD points"),
    _C("CFOT", "FOA Certified Fiber Optic Technician (CFOT)", _T.CERTIFICATION,
       ("electronics", "data_center"), "Fiber Optic Association",
       ("cfot", "fiber optic technician", "fiber optics certification", "fiber optic certification")),
    _C("NIAGARA", "Tridium Niagara 4 Certification", _T.CERTIFICATION,
       ("building_automation",), "Tridium",
       ("niagara", "tridium", "niagara 4")),
    _C("AUTOCAD_CERT", "Autodesk Certified User (AutoCAD / Revit)", _T.CERTIFICATION,
       ("drafting",), "Autodesk",
       ("autocad certification", "autodesk certified", "autocad certified user",
        "revit certification", "revit certified")),
    _C("MOS", "Microsoft Office Specialist", _T.CERTIFICATION,
       ("administrative", "it_support"), "Microsoft",
       ("microsoft office specialist", "mos certification")),

    # =================== Civil / survey ===================
    _C("PLS", "Professional Land Surveyor (PLS) License", _T.LICENSE,
       ("civil_survey",), "State licensing board",
       ("pls", "professional land surveyor", "land surveyor license", "licensed surveyor"),
       "State license; typically renews every 2 years"),

    # =================== Apprenticeship / union / degrees ===================
    _C("DOL_JOURNEYWORKER", "DOL Registered Apprenticeship — Journeyworker", _T.APPRENTICESHIP,
       ("electrical", "plumbing", "hvac", "welding", "construction", "manufacturing",
        "energy_lineman"),
       "DOL Office of Apprenticeship",
       ("journeyman", "journeyworker", "journeyman card", "journeyman certificate",
        "registered apprenticeship", "dol apprenticeship"),
       "Completion credential — does not expire"),
    _C("UNION_MEMBER", "Union Membership", _T.UNION,
       (), "Local union",
       ("union member", "union membership", "ibew member", "ua member", "uaw member",
        "ibew", "teamsters")),
    _C("HS_DIPLOMA", "High School Diploma", _T.DEGREE,
       (), None,
       ("high school diploma", "hs diploma", "high school graduate", "highschool diploma")),
    _C("GED", "GED / High School Equivalency", _T.DEGREE,
       (), "GED Testing Service / state equivalency program",
       ("ged", "hiset", "high school equivalency", "tasc")),
    _C("CERT_OF_COMPLETION", "Certificate of Completion", _T.DEGREE,
       (), None,
       ("certificate of completion", "completion certificate", "program certificate",
        "trade certificate")),
    _C("DIPLOMA", "Trade / Technical Diploma", _T.DEGREE,
       (), None,
       ("diploma", "technical diploma", "trade diploma", "vocational diploma")),
    _C("ASSOCIATE", "Associate Degree", _T.DEGREE,
       (), None,
       ("associate degree", "associates degree", "associate's degree", "aa degree",
        "associate of arts")),
    _C("ASSOCIATE_SCIENCE", "Associate of Science (AS)", _T.DEGREE,
       (), None,
       ("as degree", "a.s.", "associate of science", "associate in science")),
    _C("ASSOCIATE_APPLIED_SCIENCE", "Associate of Applied Science (AAS)", _T.DEGREE,
       (), None,
       ("aas", "a.a.s.", "aas degree", "associate of applied science",
        "applied science degree")),
    _C("BACHELOR", "Bachelor's Degree", _T.DEGREE,
       (), None,
       ("bachelors degree", "bachelor's degree", "bachelors", "bachelor of science",
        "bachelor of arts", "bs degree", "ba degree")),
)


# ---------------------------------------------------------------------------
# Index construction (import-time; collisions fail loudly)
# ---------------------------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _clean(raw: str) -> str:
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = _NORMALIZE_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


_CODE_INDEX: dict[str, CanonicalCredential] = {}
_SLUG_INDEX: dict[str, CanonicalCredential] = {}
# alias (cleaned) -> credential. Aliases must be globally unambiguous; a
# collision across entries is a taxonomy bug and raises at import.
_ALIAS_INDEX: dict[str, CanonicalCredential] = {}

for _c in TAXONOMY:
    if _c.code in _CODE_INDEX:
        raise ValueError(f"Duplicate taxonomy code: {_c.code}")
    _CODE_INDEX[_c.code] = _c
    _SLUG_INDEX[_c.slug] = _c
    for _a in (_c.name, *_c.aliases):
        _key = _clean(_a)
        if not _key:
            continue
        _existing = _ALIAS_INDEX.get(_key)
        if _existing is not None and _existing.code != _c.code:
            raise ValueError(
                f"Ambiguous alias {_key!r} on both {_existing.code} and {_c.code} — "
                "resolve by removing it or making it more specific"
            )
        _ALIAS_INDEX[_key] = _c

# Aliases sorted longest-first for the containment stage: specificity ordering
# means "cdl class a" always beats "cdl", never first-match-wins.
_ALIASES_BY_LENGTH: list[tuple[str, "re.Pattern[str]", CanonicalCredential]] = [
    (alias, re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"), cred)
    for alias, cred in sorted(
        _ALIAS_INDEX.items(), key=lambda kv: (-len(kv[0]), kv[0])
    )
    if len(alias) >= 3
]


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

    @property
    def slug(self) -> Optional[str]:
        return self.canonical.slug if self.canonical else None


def get_by_code(code: str) -> Optional[CanonicalCredential]:
    return _CODE_INDEX.get(code)


def get_by_slug(slug: str) -> Optional[CanonicalCredential]:
    """Lookup by DB-facing key; tolerant of legacy uppercase codes."""
    if not slug:
        return None
    return _SLUG_INDEX.get(slug.lower())


def all_definitions() -> tuple[CanonicalCredential, ...]:
    return TAXONOMY


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

    # 2) Word-boundary containment, longest alias first (handles
    #    "active osha 30 card"). Word boundaries mean the alias "cdl" cannot
    #    fire inside "cdlx", and the longest-first ordering means "class a cdl"
    #    is chosen over "cdl" when both are present.
    for alias, pattern, cred in _ALIASES_BY_LENGTH:
        if pattern.search(cleaned):
            # Confidence scales with how much of the input the alias covers.
            coverage = len(alias) / max(len(cleaned), 1)
            conf = round(min(0.97, 0.80 + coverage * 0.17), 3)
            return NormalizationResult(cred, conf, "token", raw)

    # 3) Fuzzy match against all alias surface forms (long tail / typos / OCR noise).
    aliases = [a for a, _p, _c in _ALIASES_BY_LENGTH]
    matches = difflib.get_close_matches(cleaned, aliases, n=1, cutoff=0.78)
    if matches:
        alias = matches[0]
        ratio = difflib.SequenceMatcher(None, cleaned, alias).ratio()
        return NormalizationResult(_ALIAS_INDEX[alias], round(ratio, 3), "fuzzy", raw)

    return NormalizationResult(None, 0.0, "none", raw)


def suggest(query: str, limit: int = 8) -> list[CanonicalCredential]:
    """
    Type-ahead suggestions for a partial credential name.

    Ranking: exact alias/name prefix beats word-boundary containment beats
    fuzzy; within a band, shorter canonical names first (more specific pages
    like "OSHA 10" before "OSHA 10-Hour ... General Industry" variants).
    Deterministic and DB-free — safe on the request path.
    """
    cleaned = _clean(query or "")
    if len(cleaned) < 2:
        return []

    scored: dict[str, tuple[int, int, str]] = {}  # code -> (band, name_len, name)

    def _offer(cred: CanonicalCredential, band: int) -> None:
        cur = scored.get(cred.code)
        cand = (band, len(cred.name), cred.name)
        if cur is None or cand < cur:
            scored[cred.code] = cand

    for alias, cred in _ALIAS_INDEX.items():
        if alias.startswith(cleaned):
            _offer(cred, 0)
        elif cleaned in alias:
            _offer(cred, 1)

    if len(scored) < limit and len(cleaned) >= 4:
        # Fuzzy fill for typos ("oshaa 10") — skipped for very short queries
        # where edit-distance neighbours are mostly noise.
        close = difflib.get_close_matches(cleaned, list(_ALIAS_INDEX.keys()), n=limit, cutoff=0.8)
        for alias in close:
            _offer(_ALIAS_INDEX[alias], 2)

    ranked = sorted(scored.items(), key=lambda kv: kv[1])
    return [_CODE_INDEX[code] for code, _ in ranked[:limit]]
