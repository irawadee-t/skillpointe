"""SKILLED Nation career taxonomy — GENERATED, do not edit by hand.

Source: Industry & Career List Revisions v2 (Tasha). Regenerate with
scripts/gen_taxonomy.py. Pure data + derived adjacency; no I/O.
"""
from __future__ import annotations

SECTORS: dict[str, dict] = {
    "construction": {"name": 'Construction & Building Trades', "full_name": 'Construction & Building Trades',
        "description": 'Building, renovating, and repairing homes, commercial buildings, roads, bridges, and other structures.',
        "examples": 'Carpenter, electrician, plumber, HVAC technician, mason, roofer, welder, heavy equipment operator'},
    "manufacturing": {"name": 'Manufacturing', "full_name": 'Manufacturing',
        "description": 'Making physical products using machinery, tools, robotics, automation, machining, and quality-control systems. Includes traditional factory work as well as high-tech production.',
        "examples": 'CNC machinist, industrial maintenance technician, welder/fabricator, tool-and-die maker, mechatronics technician, robotics technician'},
    "energy": {"name": 'Energy & Utilities', "full_name": 'Energy & Utilities',
        "description": 'Producing, transmitting, distributing, and maintaining energy, water, gas, and related utility systems. This includes both traditional utilities and clean-energy pathways.',
        "examples": 'Lineworker, power plant operator, solar PV installer, wind turbine technician, substation technician, natural gas technician'},
    "transportation": {"name": 'Transportation', "full_name": 'Transportation (Automotive, Diesel, Aviation, Marine, Rail, and Related Logistics)',
        "description": 'Maintaining and repairing cars, trucks, buses, construction equipment, farm equipment, aircraft, rail and railcars, boats and marine craft, and other motorized systems.',
        "examples": 'Auto technician, diesel mechanic, collision repair technician, small engine mechanic, heavy equipment mechanic, aircraft mechanic, avionics technician, marine technician, shipfitter, rail signal maintainer, locomotive technician'},
    "healthcare": {"name": 'Healthcare', "full_name": 'Healthcare',
        "description": 'Hands-on clinical, technical, and patient-support roles that typically require certificates, licenses, or associate-level training rather than a four-year degree',
        "examples": 'Medical assistant, nurse, surgical technologist, dental assistant, pharmacy technician, phlebotomist, radiologic technologist, sterile processing technician; cosmetology'},
    "data_it": {"name": 'Data & Information Technology', "full_name": 'Data & Information Technology',
        "description": 'Building, maintaining, and repairing infrastructure, hardware, and software related to information technology and data storage. Primarily focused on non-4 year and advanced degrees.',
        "examples": 'Database administrators, network and IT support specialist, network and computer systems administrator,'},
    "telecom": {"name": 'Telecommunications', "full_name": 'Telecommunications',
        "description": 'Installing, maintaining, and troubleshooting the physical systems that support internet, phone, security, data, and connected-building technologies. This overlaps with construction, utilities, and IT.',
        "examples": 'Fiber optic technician, cable installer, low-voltage electrical technician, security systems installer, network cabling technician'},
    "public_safety": {"name": 'Public & Emergency Service', "full_name": 'Public & Emergency Service',
        "description": 'Careers focused on protecting people, property, and communities. Not all public safety jobs are “trades” in the traditional sense, but many are hands-on, skill-based, credentialed career paths.',
        "examples": 'Firefighter, EMT/paramedic, fire alarm technician, emergency vehicle technician, public safety communications technician, various municipal and civil service positions'},
}

FIELDS: dict[str, dict] = {
    "ai_and_machine_learning": {"name": 'AI and Machine Learning', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "additive_manufacturing": {"name": 'Additive Manufacturing & 3D Printing', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "aviation_maintenance": {"name": 'Aircraft/Aviation Maintenance (including A&P Mechanic)', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "architectural_drafting_cad": {"name": 'Architectural Drafting/CAD', "sectors": ['construction'], "is_other": False, "aliases": []},
    "auto_body_collision": {"name": 'Auto Body / Collision Repair', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "automotive_ev_service": {"name": 'Automotive and EV Service & Technology', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "biomedical_equipment_technology": {"name": 'Biomedical Equipment Technology', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "building_and_facilities_maintenance": {"name": 'Building & Facilities Maintenance', "sectors": ['construction'], "is_other": False, "aliases": []},
    "building_automation_controls": {"name": 'Building Automation & Controls', "sectors": ['construction'], "is_other": False, "aliases": []},
    "building_construction_technology": {"name": 'Building Construction Technology', "sectors": ['construction'], "is_other": False, "aliases": []},
    "building_energy_management": {"name": 'Building Energy Management', "sectors": ['construction'], "is_other": False, "aliases": []},
    "cnc_machining": {"name": 'CNC Machining & Precision Machining', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "fiber_optics_technician": {"name": 'Cable/Fiber Optics Technician', "sectors": ['telecom'], "is_other": False, "aliases": []},
    "cardiovascular_sonography": {"name": 'Cardiovascular Sonography', "sectors": ['healthcare'], "is_other": False, "aliases": ['Cardovascular Sonography']},
    "cardiovascular_technician": {"name": 'Cardiovascular Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "carpentry_and_woodworking": {"name": 'Carpentry & Woodworking', "sectors": ['construction'], "is_other": False, "aliases": []},
    "cloud_computing_and_infrastructure": {"name": 'Cloud Computing & Infrastructure', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "commercial_driving_cdl": {"name": 'Commercial Driving (CDL)', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "computer_engineering": {"name": 'Computer Engineering', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "computer_systems_administration": {"name": 'Computer Systems Administration', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "construction_management": {"name": 'Construction Management', "sectors": ['construction'], "is_other": False, "aliases": []},
    "cosmetology_esthetician": {"name": 'Cosmetology / Esthetician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "cybersecurity": {"name": 'Cybersecurity', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "data_center_operations": {"name": 'Data Center Operations', "sectors": ['data_it', 'telecom'], "is_other": False, "aliases": []},
    "data_science_and_analytics": {"name": 'Data Science & Analytics', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "database_administration": {"name": 'Database Administration', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "dental_assistant": {"name": 'Dental Assistant', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "dental_hygienist": {"name": 'Dental Hygienist', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "diagnostic_medical_sonography": {"name": 'Diagnostic Medical Sonography', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "diesel_service_and_technology": {"name": 'Diesel Service & Technology', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "diet_nutrition": {"name": 'Diet & Nutrition', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "emt_paramedic": {"name": 'EMT / Paramedic', "sectors": ['healthcare', 'public_safety'], "is_other": False, "aliases": []},
    "electrical": {"name": 'Electrical (Residential or Commercial)', "sectors": ['construction', 'energy'], "is_other": False, "aliases": []},
    "electrical_engineering": {"name": 'Electrical Engineering', "sectors": ['energy'], "is_other": False, "aliases": []},
    "transmission_linework": {"name": 'Electrical/Transmission Linework', "sectors": ['energy'], "is_other": False, "aliases": []},
    "energy_storage": {"name": 'Energy Storage', "sectors": ['energy'], "is_other": False, "aliases": []},
    "exercise_science_and_sports_medicine": {"name": 'Exercise Science & Sports Medicine', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "fire_science": {"name": 'Fire Science', "sectors": ['public_safety'], "is_other": False, "aliases": []},
    "gis": {"name": 'Geographic Information Systems (GIS)', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "hvac_r": {"name": 'HVAC/R', "sectors": ['construction'], "is_other": False, "aliases": []},
    "healthcare_system_administration": {"name": 'Healthcare System Administration', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "heavy_equipment_operation": {"name": 'Heavy Equipment Operation', "sectors": ['construction', 'energy', 'transportation'], "is_other": False, "aliases": []},
    "heavy_equipment_service_and_technology": {"name": 'Heavy Equipment Service & Technology', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "home_and_building_inspection": {"name": 'Home & Building Inspection', "sectors": ['construction'], "is_other": False, "aliases": []},
    "it_network_support": {"name": 'IT & Network Support', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "industrial_electrical_technology": {"name": 'Industrial Electrical Technology', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "industrial_maintenance": {"name": 'Industrial Maintenance, Millwright & Mechanical Systems', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "metrology_cmm": {"name": 'Inspection, Metrology & CMM Operation', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "instrumentation_controls": {"name": 'Instrumentation and Controls', "sectors": ['energy'], "is_other": False, "aliases": []},
    "instrumentation_automation_controls": {"name": 'Instrumentation, Automation, & Controls', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "interior_finishing": {"name": 'Interior Finishing (e.g., Flooring, Drywall, Insulation, Painting, Interior Design)', "sectors": ['construction'], "is_other": False, "aliases": []},
    "laboratory_technician": {"name": 'Laboratory Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "law_enforcement": {"name": 'Law Enforcement / Criminology', "sectors": ['public_safety'], "is_other": False, "aliases": []},
    "lowvoltage_electrical_technology": {"name": 'Low-Voltage Electrical Technology', "sectors": ['construction', 'energy', 'telecom'], "is_other": False, "aliases": []},
    "mri_technician": {"name": 'MRI Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "manufacturing_engineering_tech": {"name": 'Manufacturing Engineering Technology & Industrial Technology', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "manufacturing_production": {"name": 'Manufacturing Production & Machine Operation', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "marine_systems_service": {"name": 'Marine Systems Service & Technology', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "marine_welding": {"name": 'Marine Welding', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "masonry_and_concrete": {"name": 'Masonry and Concrete', "sectors": ['construction'], "is_other": False, "aliases": []},
    "massage_therapy": {"name": 'Massage Therapy', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "materials_ndt": {"name": 'Materials Testing & Nondestructive Testing', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "mechanical_design_cad_cam": {"name": 'Mechanical Design, CAD/CAM & Drafting', "sectors": ['manufacturing'], "is_other": False, "aliases": ['Mechancial Design, CAD/CAM & Drafting']},
    "medical_assistant": {"name": 'Medical Assistant', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "medical_billing_and_coding": {"name": 'Medical Billing and Coding', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "health_information": {"name": 'Medical Records and Health Information', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "powersports_service": {"name": 'Motorcycle / Powersports Service & Technology', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "network_cabling_technician": {"name": 'Network Cabling Technician', "sectors": ['telecom'], "is_other": False, "aliases": []},
    "network_operations": {"name": 'Network Operations', "sectors": ['telecom'], "is_other": False, "aliases": []},
    "nursing": {"name": 'Nursing (LPN/LVN, ADN, RN)', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "nursing_assistant": {"name": 'Nursing Assistant (CNA)', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "occupational_therapy_assistant": {"name": 'Occupational Therapy Assistant', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "oil_gas_production": {"name": 'Oil / Natural Gas Production Technology', "sectors": ['energy'], "is_other": False, "aliases": []},
    "patient_care": {"name": 'Patient Care', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "pharmacy_technician": {"name": 'Pharmacy Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "phlebotomist": {"name": 'Phlebotomist', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "physical_therapy_assistant": {"name": 'Physical Therapy Assistant', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "pipefitting_steamfitting": {"name": 'Pipefitting / Steamfitting', "sectors": ['construction'], "is_other": False, "aliases": []},
    "pipeline_construction": {"name": 'Pipeline Construction and Operation', "sectors": ['energy'], "is_other": False, "aliases": []},
    "pipeline_welding": {"name": 'Pipeline Welding', "sectors": ['energy'], "is_other": False, "aliases": []},
    "plastics_composites": {"name": 'Plastics, Polymers & Composites Manufacturing', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "plumbing": {"name": 'Plumbing', "sectors": ['construction'], "is_other": False, "aliases": []},
    "power_plant_operation": {"name": 'Power Plant Technology/Operation', "sectors": ['energy'], "is_other": False, "aliases": []},
    "process_technology_and_plant_operations": {"name": 'Process Technology & Plant Operations', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "qa_testing_and_automation": {"name": 'QA Testing and Automation', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "quality_control_and_quality_assurance": {"name": 'Quality Control & Quality Assurance', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "radiology_technician": {"name": 'Radiology Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "rail_signals_controls": {"name": 'Rail Signals, Communications, and Controls', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "rail_vehicle_maintenance": {"name": 'Rail Vehicle Maintenance', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "railway_track_maintenance": {"name": 'Railway Track Construction and Maintenance', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "refrigeration": {"name": 'Refrigeration', "sectors": ['construction'], "is_other": False, "aliases": []},
    "respiratory_therapy": {"name": 'Respiratory Therapy', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "robotics_mechatronics": {"name": 'Robotics & Mechatronics', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "security_systems_locksmithing": {"name": 'Security System Technology / Locksmithing', "sectors": ['construction'], "is_other": False, "aliases": []},
    "sheet_metal_fabrication": {"name": 'Sheet Metal Fabrication', "sectors": ['construction', 'manufacturing', 'transportation'], "is_other": False, "aliases": []},
    "shipfitting_and_boat_building": {"name": 'Shipfitting and Boat Building', "sectors": ['transportation'], "is_other": False, "aliases": []},
    "software_and_web_development": {"name": 'Software & Web Development', "sectors": ['data_it'], "is_other": False, "aliases": []},
    "solar_installation": {"name": 'Solar Installation and Maintenance', "sectors": ['energy'], "is_other": False, "aliases": []},
    "surgical_technology": {"name": 'Surgical Technology', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "surveying_mapping": {"name": 'Surveying and Mapping', "sectors": ['construction'], "is_other": False, "aliases": []},
    "renewable_energy": {"name": 'Sustainable/Renewable Energy', "sectors": ['energy'], "is_other": False, "aliases": []},
    "telecommunications_technician": {"name": 'Telecommunications Technician', "sectors": ['telecom'], "is_other": False, "aliases": []},
    "tool_die_mold": {"name": 'Tool, Die, Mold & Fixture Making', "sectors": ['manufacturing'], "is_other": False, "aliases": []},
    "utility_public_works": {"name": 'Utility/Public Works', "sectors": ['public_safety'], "is_other": False, "aliases": []},
    "veterinary_technician": {"name": 'Veterinary Technician', "sectors": ['healthcare'], "is_other": False, "aliases": []},
    "wastewater_operations": {"name": 'Waste/Wastewater Operations', "sectors": ['public_safety'], "is_other": False, "aliases": []},
    "welding_fabrication": {"name": 'Welding and Fabrication', "sectors": ['construction', 'manufacturing', 'transportation'], "is_other": False, "aliases": ['Welding & Fabricating']},
    "wind_turbine_technology": {"name": 'Wind Turbine Technology', "sectors": ['energy'], "is_other": False, "aliases": []},
    "other_construction": {"name": 'Other Construction-related field', "sectors": ['construction'], "is_other": True, "aliases": []},
    "other_manufacturing": {"name": 'Other Manufacturing-related field', "sectors": ['manufacturing'], "is_other": True, "aliases": []},
    "other_energy": {"name": 'Other Energy/Utilities-related field', "sectors": ['energy'], "is_other": True, "aliases": []},
    "other_transportation": {"name": 'Other Transportation-related field', "sectors": ['transportation'], "is_other": True, "aliases": []},
    "other_healthcare": {"name": 'Other Healthcare-related field', "sectors": ['healthcare'], "is_other": True, "aliases": []},
    "other_data_it": {"name": 'Other Data/IT-related field', "sectors": ['data_it'], "is_other": True, "aliases": []},
    "other_telecom": {"name": 'Other Telecommunications-related field', "sectors": ['telecom'], "is_other": True, "aliases": []},
    "other_public_safety": {"name": 'Other Public & Emergency Services-related field', "sectors": ['public_safety'], "is_other": True, "aliases": []},
}

LEGACY_FAMILY_BRIDGE: dict[str, str | None] = {
    "electrical": 'electrical',
    "plumbing": 'plumbing',
    "hvac": 'hvac_r',
    "construction": 'building_construction_technology',
    "welding": 'welding_fabrication',
    "automotive": 'automotive_ev_service',
    "manufacturing": 'manufacturing_production',
    "logistics": 'other_transportation',
    "heavy_equipment": 'heavy_equipment_operation',
    "security": 'security_systems_locksmithing',
    "drafting": 'architectural_drafting_cad',
    "aviation": 'aviation_maintenance',
    "auto_body": 'auto_body_collision',
    "aviation_aerospace": 'aviation_maintenance',
    "energy_lineman": 'transmission_linework',
    "solar_energy": 'solar_installation',
    "wind_energy": 'wind_turbine_technology',
    "robotics": 'robotics_mechatronics',
    "construction_mgmt": 'construction_management',
    "healthcare_support": 'patient_care',
    "dental": 'dental_assistant',
    "nursing": 'nursing',
    "radiology": 'radiology_technician',
    "respiratory": 'respiratory_therapy',
    "physical_therapy": 'physical_therapy_assistant',
    "pharmacy": 'pharmacy_technician',
    "surgical_tech": 'surgical_technology',
    "veterinary": 'veterinary_technician',
    "lab_sciences": 'laboratory_technician',
    "health_information": 'health_information',
    "dietetics": 'diet_nutrition',
    "civil_survey": 'surveying_mapping',
    "field_service": 'industrial_maintenance',
    "rail_transit": 'rail_vehicle_maintenance',
    "marine": 'marine_systems_service',
    "power_plant": 'power_plant_operation',
    "building_automation": 'building_automation_controls',
    "data_center": 'data_center_operations',
    "industrial_maintenance": 'industrial_maintenance',
    "electronics": 'industrial_electrical_technology',
    "it_support": 'it_network_support',
    "administrative": None,
    "utilities_energy": 'utility_public_works',
    "logistics_warehouse": 'other_transportation',
    "automotive_diesel": 'diesel_service_and_technology',
    "machining_cnc": 'cnc_machining',
    "construction_skilled": 'building_construction_technology',
}



def resolve_field_code(code: str | None) -> str | None:
    """Map any known code (new or legacy) to a current field code."""
    if code is None:
        return None
    if code in FIELDS:
        return code
    return LEGACY_FAMILY_BRIDGE.get(code)


def field_sectors(code: str | None) -> set[str]:
    f = FIELDS.get(resolve_field_code(code) or "")
    return set(f["sectors"]) if f else set()


def fields_share_sector(a: str | None, b: str | None) -> bool:
    return bool(field_sectors(a) & field_sectors(b))


def relate(a: str | None, b: str | None) -> str:
    """Relationship between two field codes (legacy codes resolve first).

    "same"      — identical named field (an "Other X" pair never counts as
                  same: it carries sector-level signal only)
    "adjacent"  — distinct fields sharing at least one sector
    "unrelated" — no shared sector
    "unknown"   — either side missing or not in the taxonomy
    """
    ra, rb = resolve_field_code(a), resolve_field_code(b)
    if ra is None or rb is None:
        return "unknown"
    if ra == rb and not FIELDS[ra]["is_other"]:
        return "same"
    if set(FIELDS[ra]["sectors"]) & set(FIELDS[rb]["sectors"]):
        return "adjacent"
    return "unrelated"


# Derived adjacency: two distinct fields are adjacent iff they share a sector.
# "Other" fields are adjacent to everything in their sector by construction.
FIELD_ADJACENCY: dict[str, set[str]] = {}
for _code, _f in FIELDS.items():
    FIELD_ADJACENCY[_code] = {
        _c for _c, _g in FIELDS.items()
        if _c != _code and set(_g["sectors"]) & set(_f["sectors"])
    }
