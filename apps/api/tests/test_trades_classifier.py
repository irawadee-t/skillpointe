"""Tests for the trades classifier — the bar is broad coverage with zero corporate creep."""
from __future__ import annotations

import sys
from pathlib import Path

# packages/ is added at runtime by scripts; mirror it here for tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from scraper.trades import classify, is_trade  # noqa: E402

# ---------------------------------------------------------------------------
# Should match — every common trade title shape the user might miss
# ---------------------------------------------------------------------------

POSITIVE = [
    # Electrical
    ("Industrial Electrician — Carrollton, GA", "electrical"),
    ("Journeyman Electrician (Apprentice OK)", "electrical"),
    ("Lineman I", "electrical"),
    ("Substation Technician", "utilities_energy"),
    ("E&I Technician — Night Shift", "electrical"),

    # Welding
    ("Welder II", "welding"),
    ("Pipe Welder — TIG", "welding"),
    ("Structural Welder (1st shift)", "welding"),
    ("Welding Inspector", "welding"),

    # HVAC / refrigeration
    ("HVAC Technician", "hvac_r"),
    ("Refrigeration Mechanic — Atlanta", "hvac_r"),
    ("Chiller Technician", "hvac_r"),
    ("HVAC/R Installer", "hvac_r"),

    # Plumbing / piping
    ("Plumber Journeyman", "plumbing"),
    ("Pipefitter — Industrial", "plumbing"),
    ("Steamfitter Apprentice", "plumbing"),

    # Auto / diesel
    ("Diesel Mechanic", "automotive_diesel"),
    ("Heavy Equipment Mechanic", "automotive_diesel"),
    ("Service Technician — Fleet", "automotive_diesel"),

    # Machining
    ("CNC Machinist — Night Shift", "machining_cnc"),
    ("Tool & Die Maker", "machining_cnc"),
    ("CNC Operator I", "machining_cnc"),

    # Production / manufacturing operators
    ("Production Operator", "manufacturing_production"),
    ("Machine Operator (1st shift)", "manufacturing_production"),
    ("Assembler I — Aerospace", "manufacturing_production"),
    ("Injection Molding Technician", "manufacturing_production"),
    ("Press Operator — 12 hr nights", "manufacturing_production"),

    # Industrial maintenance
    ("Millwright", "industrial_maintenance"),
    ("Maintenance Technician — Plant 2", "industrial_maintenance"),
    ("Industrial Maintenance Mechanic", "industrial_maintenance"),
    ("Reliability Technician", "industrial_maintenance"),

    # Construction
    ("Carpenter", "construction_skilled"),
    ("Ironworker — Bridges", "construction_skilled"),
    ("Sheet Metal Worker", "construction_skilled"),
    ("Industrial Painter", "construction_skilled"),
    ("Crane Operator", "construction_skilled"),

    # Aviation
    ("Aircraft Mechanic — A&P", "aviation_aerospace"),
    ("Avionics Technician", "aviation_aerospace"),

    # Logistics
    ("Forklift Operator — 2nd shift", "logistics_warehouse"),
    ("Material Handler", "logistics_warehouse"),

    # Utilities / energy
    ("Wind Turbine Technician", "utilities_energy"),
    ("Power Plant Operator", "utilities_energy"),
]


def test_positive_titles_match_expected_family():
    misses = []
    for title, expected in POSITIVE:
        result = classify(title)
        if not result.is_trade:
            misses.append((title, "MISS — not a trade"))
        elif result.family != expected:
            misses.append((title, f"family={result.family}, expected={expected}"))
    assert not misses, f"{len(misses)} miscategorized: {misses[:8]}"


# ---------------------------------------------------------------------------
# Should NOT match — corporate / office / engineering roles
# ---------------------------------------------------------------------------

NEGATIVE = [
    "Electrical Engineer",
    "Manufacturing Engineer II",
    "Senior Software Engineer",
    "Data Analyst",
    "Marketing Manager",
    "Director of HR",
    "Plant Manager",            # manager-only, no trade verb
    "Recruiter",
    "Procurement Buyer",
    "Product Designer",
    "Sales Account Executive",
    "Engineering Intern",
    "Accountant",
    "Cybersecurity Analyst",
]


def test_negative_titles_are_filtered_out():
    false_positives = [t for t in NEGATIVE if is_trade(t)]
    assert not false_positives, f"corporate jobs leaking through: {false_positives}"


# ---------------------------------------------------------------------------
# Override — "Maintenance Supervisor" has 'supervisor' (deny) but 'maintenance'
# (trade) — should still classify as trade.
# ---------------------------------------------------------------------------

def test_trade_override_beats_deny_when_trade_verb_present():
    assert is_trade("Maintenance Supervisor")
    assert is_trade("Welding Lead")
    assert is_trade("Lead Electrician")
    # But a corporate-only role with the same suffix should NOT match.
    assert not is_trade("Marketing Lead")
    assert not is_trade("Engineering Manager")


def test_empty_input_is_not_a_trade():
    assert not is_trade("")
    assert not is_trade("   ")  # whitespace title


def test_description_fallback_catches_trade_when_title_is_generic():
    # Some sites have generic role titles like "Field Service Role" — the
    # description gives it away.
    title = "Field Role — Day Shift"
    desc = "You will operate CNC machinery and act as a machine operator."
    assert is_trade(title, desc)


def test_real_miss_coverage_from_live_spot_check():
    """Every title here was previously dropped by the classifier during a real
    spot-check across Ball, GE Vernova, Schneider, and Southwire. They are all
    legitimate skilled-trades roles — must be classified True."""
    real_misses = [
        # Southwire wire-mill machine operators
        "Operator, Take Up III",
        "Operator, Drawing I",
        "Operator, Extruder II",
        "Operator, Buncher II",
        "Operator, Armoring Machine",
        "Operator, Compound Equip I",
        "Operator, Lift Truck",
        "Drawing Operator III",
        "Stranding Helper-EG",
        "Operator - EG",
        "Operator",
        # Ball
        "Electronic Technician",
        "Maintainer-Chemical Process",
        "Maintainer - Deco Operator",
        "Chemical Operator",
        "Quality Assurance Technician",
        "Body Maker I",
        "Storekeeper",
        # GE Vernova
        "Wind Hub Technician- SD2 (Highmore, SD)",
        "Wind Hub Technician - ND1 (Glen Ullin, ND)",
        "Fabrication & CAD Technician",
        "Test Technician - Capacitor Voltage Transformers (2nd Shift)",
        "Facility Maintenance Mechanical Technician",
        "Receiving Clerk - 2nd Shift",
        "NDT (Level II) Quality Assurance 2nd shift",
        "Inspector",
        # Schneider
        "Fabrication Associate I",
        "Fabrication Associate II",
        "Materials Associate I",
        "Material Associate - Forklift",
        "Electrical Assembly Cell Lead",
        "Tool Room Attendant",
        "Warehouse Coordinator",
        # Southwire (additional)
        "Technician, Electronic",
        "Handler, Materials 2nd",
    ]
    misses = [t for t in real_misses if not is_trade(t)]
    assert not misses, f"{len(misses)}/{len(real_misses)} still missed: {misses[:8]}"


def test_description_does_not_override_corporate_title():
    # A "Marketing Manager" job whose description happens to mention a welder
    # in passing must NOT be classified as a trade.
    assert not is_trade("Marketing Manager",
                        "You will coordinate campaigns about welders and machinists.")
