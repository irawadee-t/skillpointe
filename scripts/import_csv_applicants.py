#!/usr/bin/env python3
"""
Import 335 applicant profiles from the SkillPointe Foundation
Skilled Trades Scholarship CSV into the local Supabase applicants table.

Usage:
    python scripts/import_csv_applicants.py
"""

import csv
import random
import sys
import uuid
from datetime import date, datetime
from typing import List, Optional, Tuple

import psycopg2
import psycopg2.extras

DB_URL = "postgresql://postgres:postgres@localhost:54322/postgres"
CSV_PATH = "Skilled Trades Scholarship Data.csv"
BATCH_SIZE = 50
SEED = 42

# ---------------------------------------------------------------------------
# Name generation — fixed seed for reproducibility
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Aaliyah", "Aaron", "Abigail", "Adam", "Adrian", "Aiden", "Aisha", "Alex",
    "Alexa", "Alexander", "Alexis", "Alicia", "Alyssa", "Amanda", "Amber",
    "Amelia", "Andre", "Andrea", "Andrew", "Angel", "Angela", "Anthony",
    "Antonio", "Aria", "Ariana", "Ashley", "Austin", "Ava", "Avery",
    "Benjamin", "Bianca", "Blake", "Brandon", "Briana", "Brianna", "Brooke",
    "Caleb", "Cameron", "Carlos", "Caroline", "Carter", "Cassandra", "Charles",
    "Charlotte", "Chase", "Chelsea", "Christian", "Christina", "Christopher",
    "Claire", "Cody", "Cole", "Colin", "Connor", "Corey", "Courtney",
    "Crystal", "Dakota", "Dalton", "Daniel", "Daniela", "David", "Deandre",
    "Delaney", "Derek", "Destiny", "Devin", "Diana", "Diego", "Dominic",
    "Dylan", "Eduardo", "Elena", "Eli", "Eliana", "Elijah", "Elizabeth",
    "Ella", "Emily", "Emma", "Eric", "Erica", "Ethan", "Eva", "Evan",
    "Faith", "Felix", "Fernando", "Gabriel", "Gabriella", "Garrett", "Gavin",
    "Genesis", "George", "Giovanni", "Grace", "Grant", "Hailey", "Hannah",
    "Harper", "Hayden", "Henry", "Hunter", "Ian", "Isaac", "Isabel",
    "Isabella", "Isaiah", "Ivy", "Jack", "Jackson", "Jacob", "Jade",
    "Jaime", "Jake", "Jalen", "James", "Jasmine", "Jason", "Javier",
    "Jayden", "Jaylen", "Jennifer", "Jeremiah", "Jesse", "Jessica", "Jesus",
    "Jocelyn", "John", "Jonathan", "Jordan", "Jorge", "Jose", "Joseph",
    "Joshua", "Juan", "Julia", "Julian", "Justin", "Kaitlyn", "Kayla",
    "Kaylee", "Keith", "Kelly", "Kendall", "Kennedy", "Kevin", "Kimberly",
    "Kyle", "Kylie", "Landon", "Lauren", "Leah", "Leonardo", "Leslie",
    "Liam", "Lillian", "Lily", "Logan", "Lucas", "Luis", "Luke", "Luna",
    "Lydia", "Mackenzie", "Madeline", "Madison", "Malik", "Marco", "Marcus",
    "Maria", "Mariah", "Mario", "Mark", "Marley", "Mason", "Mateo",
    "Matthew", "Maya", "Megan", "Melanie", "Melissa", "Mia", "Michael",
    "Michelle", "Miguel", "Mila", "Miles", "Miranda", "Molly", "Morgan",
    "Naomi", "Natalia", "Natalie", "Nathan", "Nathaniel", "Nicholas",
    "Nicole", "Noah", "Nolan", "Nora", "Oliver", "Olivia", "Omar",
    "Oscar", "Owen", "Paige", "Parker", "Patrick", "Paul", "Penelope",
    "Peter", "Peyton", "Preston", "Rachel", "Rafael", "Raymond", "Reagan",
    "Rebecca", "Ricardo", "Riley", "Robert", "Roberto", "Ruby", "Ryan",
    "Rylee", "Sabrina", "Samantha", "Samuel", "Santiago", "Sara", "Sarah",
    "Savannah", "Sean", "Sebastian", "Sergio", "Shelby", "Sierra", "Skylar",
    "Sofia", "Sophia", "Spencer", "Stella", "Stephanie", "Steven", "Sydney",
    "Taylor", "Thomas", "Tiffany", "Timothy", "Travis", "Trenton", "Trevor",
    "Trinity", "Tristan", "Tyler", "Valentina", "Valeria", "Vanessa",
    "Victor", "Victoria", "Vincent", "Wesley", "William", "Wyatt", "Xavier",
    "Zachary", "Zoe",
]

LAST_NAMES = [
    "Adams", "Aguilar", "Ali", "Allen", "Alvarado", "Alvarez", "Anderson",
    "Andrews", "Armstrong", "Arnold", "Bailey", "Baker", "Banks", "Barnes",
    "Barrett", "Bates", "Bell", "Bennett", "Berry", "Bishop", "Black",
    "Boyd", "Bradley", "Brennan", "Brooks", "Brown", "Bryant", "Burke",
    "Burns", "Burton", "Butler", "Campbell", "Carlson", "Carpenter",
    "Carroll", "Carter", "Castillo", "Castro", "Chambers", "Chang", "Chen",
    "Clark", "Clarke", "Coleman", "Collins", "Cook", "Cooper", "Cortez",
    "Cox", "Crawford", "Cruz", "Cunningham", "Daniels", "Davis", "Dawson",
    "Dean", "Delgado", "Diaz", "Dixon", "Dominguez", "Douglas", "Dunn",
    "Edwards", "Ellis", "Espinoza", "Estrada", "Evans", "Ferguson",
    "Fernandez", "Fields", "Fisher", "Fitzgerald", "Fleming", "Fletcher",
    "Flores", "Ford", "Foster", "Fox", "Francis", "Franco", "Freeman",
    "Fuentes", "Garcia", "Gardner", "Garza", "George", "Gibson", "Gomez",
    "Gonzalez", "Gordon", "Graham", "Grant", "Gray", "Green", "Greene",
    "Griffin", "Guerrero", "Gutierrez", "Guzman", "Hale", "Hall",
    "Hamilton", "Hansen", "Harper", "Harris", "Harrison", "Hart", "Harvey",
    "Hayes", "Henderson", "Henry", "Hernandez", "Herrera", "Hicks", "Hill",
    "Hoffman", "Holland", "Holmes", "Hopkins", "Howard", "Howell", "Huang",
    "Hudson", "Hughes", "Hunt", "Hunter", "Jackson", "James", "Jenkins",
    "Jimenez", "Johnson", "Jones", "Jordan", "Keller", "Kelly", "Kennedy",
    "Khan", "Kim", "King", "Knight", "Lam", "Lambert", "Lane", "Lawson",
    "Lee", "Lewis", "Li", "Lin", "Little", "Liu", "Long", "Lopez", "Lowe",
    "Luna", "Lynch", "Maldonado", "Marshall", "Martin", "Martinez", "Mason",
    "Mcdonald", "Mcgee", "Medina", "Mejia", "Mendez", "Mendoza", "Meyer",
    "Miller", "Mills", "Mitchell", "Montgomery", "Moore", "Morales",
    "Morgan", "Morris", "Morrison", "Murphy", "Murray", "Myers", "Navarro",
    "Nelson", "Nguyen", "Nichols", "Norman", "Nunez", "Obrien", "Olson",
    "Ortega", "Ortiz", "Owens", "Padilla", "Palmer", "Park", "Parker",
    "Patterson", "Payne", "Pena", "Perez", "Perry", "Peters", "Peterson",
    "Phillips", "Pierce", "Porter", "Powell", "Price", "Quinn", "Ramirez",
    "Ramos", "Reed", "Reeves", "Reid", "Reyes", "Reynolds", "Rhodes",
    "Rice", "Richardson", "Riley", "Rios", "Rivera", "Roberts", "Robertson",
    "Robinson", "Rodriguez", "Rogers", "Roman", "Romero", "Rosales", "Rose",
    "Ross", "Ruiz", "Russell", "Ryan", "Salazar", "Sanchez", "Sanders",
    "Santiago", "Santos", "Schneider", "Scott", "Shaw", "Silva", "Simmons",
    "Singh", "Smith", "Snyder", "Soto", "Spencer", "Steele", "Stevens",
    "Stewart", "Stone", "Sullivan", "Tate", "Taylor", "Thomas", "Thompson",
    "Torres", "Tran", "Tucker", "Turner", "Valdez", "Valencia", "Vargas",
    "Vasquez", "Vaughn", "Vega", "Walker", "Wallace", "Walsh", "Walters",
    "Wang", "Ward", "Warren", "Washington", "Watson", "Weaver", "Webb",
    "Weber", "Wells", "West", "White", "Williams", "Willis", "Wilson",
    "Wolf", "Wong", "Wood", "Wright", "Wu", "Yang", "Young", "Zamora",
    "Zhang",
]


def generate_names(count: int) -> List[Tuple[str, str]]:
    rng = random.Random(SEED)
    names: List[Tuple[str, str]] = []
    seen: set = set()
    firsts = list(FIRST_NAMES)
    lasts = list(LAST_NAMES)
    while len(names) < count:
        fn = rng.choice(firsts)
        ln = rng.choice(lasts)
        if (fn, ln) not in seen:
            seen.add((fn, ln))
            names.append((fn, ln))
    return names


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------

ENROLLMENT_MAP = {
    "High School (Seniors or Upcoming Seniors eligible only)": "high_school",
    "Community College/Technical School": "community_college",
    "Skilled Trades Certificate/Vocational Program": "vocational_certificate",
    "Apprenticeship Program": "apprenticeship",
    "4 or more year college program (Bachelors, Master's or Graduate Degree)": "bachelors_plus",
    "Early College/High School Dual Enrollment Program": "dual_enrollment",
    "I am not currently attending school.": "not_enrolled",
    "Community College or Trade School": "community_college",
    "Currently Enrolled in a Training Program/Vocational Program": "vocational_certificate",
    "Currently Enrolled in an Apprenticeship": "apprenticeship",
    "4-Year College Student (Major in Skilled Trades)": "bachelors_plus",
}

DEGREE_MAP = {
    "Associate's Degree": "associates",
    "Bachelor's Degree": "bachelors",
    "Skilled Trades Certificate/Vocational Program": "skilled_trades_certificate",
    "Apprenticeship": "apprenticeship",
    "Dual Enrollment": "dual_enrollment",
}

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def strip(val: str) -> str:
    return val.strip() if val else ""


def parse_bool(val: str) -> Optional[bool]:
    v = strip(val).lower()
    if v == "yes":
        return True
    if v == "no":
        return False
    return None


def parse_date(month_str: str, year_str: str) -> Optional[date]:
    m = strip(month_str).lower()
    y = strip(year_str)
    if not m or not y:
        return None
    month_num = MONTH_MAP.get(m)
    if month_num is None:
        return None
    try:
        year_num = int(y)
    except ValueError:
        return None
    if year_num < 1900 or year_num > 2100:
        return None
    return date(year_num, month_num, 1)


def parse_gpa(val: str) -> Optional[float]:
    v = strip(val)
    if not v:
        return None
    try:
        g = float(v)
        if 0 <= g <= 5.0:
            return g
        return None
    except ValueError:
        return None


def parse_state(val: str) -> Optional[str]:
    """Convert 'US-PA' → 'PA'."""
    v = strip(val)
    if not v:
        return None
    if v.startswith("US-"):
        return v[3:]
    return v


def map_enrollment(val: str) -> str:
    v = strip(val)
    return ENROLLMENT_MAP.get(v, "other")


def map_degree(val: str) -> str:
    v = strip(val)
    return DEGREE_MAP.get(v, "other")


def parse_honor_societies(hs_val: str, hs_other: str) -> List[str]:
    result = []
    v = strip(hs_val)
    if v and v.lower() not in ("n/a", "none", ""):
        for item in v.split(","):
            item = item.strip()
            if item:
                result.append(item)
    o = strip(hs_other)
    if o and o.lower() not in ("n/a", "none", ""):
        result.append(o)
    return result


US_REGIONS = {
    "CT": "northeast", "ME": "northeast", "MA": "northeast", "NH": "northeast",
    "RI": "northeast", "VT": "northeast", "NJ": "northeast", "NY": "northeast",
    "PA": "northeast",
    "IL": "midwest", "IN": "midwest", "MI": "midwest", "OH": "midwest",
    "WI": "midwest", "IA": "midwest", "KS": "midwest", "MN": "midwest",
    "MO": "midwest", "NE": "midwest", "ND": "midwest", "SD": "midwest",
    "DE": "south", "FL": "south", "GA": "south", "MD": "south",
    "NC": "south", "SC": "south", "VA": "south", "DC": "south",
    "WV": "south", "AL": "south", "KY": "south", "MS": "south",
    "TN": "south", "AR": "south", "LA": "south", "OK": "south", "TX": "south",
    "AZ": "west", "CO": "west", "ID": "west", "MT": "west",
    "NV": "west", "NM": "west", "UT": "west", "WY": "west",
    "AK": "west", "CA": "west", "HI": "west", "OR": "west", "WA": "west",
}


def state_to_region(state_code: Optional[str]) -> Optional[str]:
    if not state_code:
        return None
    return US_REGIONS.get(state_code.upper())


# ---------------------------------------------------------------------------
# Row → dict
# ---------------------------------------------------------------------------

INSERT_COLS = [
    "first_name", "last_name", "email",
    "program_name_raw", "career_goals_raw", "experience_raw", "bio_raw",
    "city", "state", "region", "country",
    "willing_to_relocate", "willing_to_travel",
    "travel_preference", "relocation_preference",
    "expected_completion_date", "source",
    "enrollment_status", "degree_type",
    "school_name", "school_campus", "school_city", "school_state",
    "career_path", "program_field", "specific_career",
    "program_start_date", "gpa",
    "age_range", "gender", "military_status", "military_dependent",
    "household_income", "current_wages",
    "has_internship", "internship_details",
    "essay_background", "essay_impact",
    "activities", "honor_societies", "remaining_program_costs",
]

INSERT_SQL = f"""
INSERT INTO public.applicants ({', '.join(INSERT_COLS)})
VALUES ({', '.join(['%s'] * len(INSERT_COLS))})
"""


def row_to_values(row: dict, first_name: str, last_name: str) -> tuple:
    """Map a CSV dict row to a tuple of values matching INSERT_COLS."""

    program_raw = strip(row.get("Program/Field Of Study", ""))
    program_other = strip(row.get("Program/Field Of Study - Other", ""))
    if program_other and program_other.lower() not in ("n/a", "none"):
        program_raw = f"{program_raw} ({program_other})" if program_raw else program_other

    essay_bg = strip(row.get("Essay 1 - Background & Driving Passion", ""))
    essay_imp = strip(row.get("Essay 2 - Post-Graduation & Scholarship Impact", ""))
    activities = strip(row.get("Activities/Extracurriculars", ""))
    internship_details = strip(row.get("Internship Details", ""))

    career_goals = essay_imp if essay_imp else None
    experience_parts = []
    if internship_details:
        experience_parts.append(internship_details)
    if activities:
        experience_parts.append(activities)
    experience_raw = "\n\n".join(experience_parts) if experience_parts else None
    bio_raw = essay_bg if essay_bg else None

    state_code = parse_state(row.get("School State:", ""))
    region = state_to_region(state_code)
    city = strip(row.get("School City:", ""))

    completion_date = parse_date(
        row.get("Program Completion Month", ""),
        row.get("Program Completion Year", ""),
    )
    start_date = parse_date(
        row.get("Program Start Month", ""),
        row.get("Program Start Year", ""),
    )

    honor_soc = parse_honor_societies(
        row.get("Honor Society", ""),
        row.get("Honor Society - Other", ""),
    )

    specific_career = strip(row.get("Specific Career/Field Of Study", ""))
    career_path = strip(row.get("Career Path", ""))
    degree_prog = strip(row.get("Degree/Program", ""))

    email = f"{first_name.lower()}.{last_name.lower()}@spf-import.example"

    return (
        first_name,
        last_name,
        email,
        program_raw or None,
        career_goals,
        experience_raw,
        bio_raw,
        city or None,
        state_code,
        region,
        "US",
        False,   # willing_to_relocate
        False,   # willing_to_travel
        "within_region",   # travel_preference
        "within_state",   # relocation_preference
        completion_date,
        "csv_import",
        map_enrollment(row.get("Current Enrollment", "")),
        map_degree(row.get("Degree Type", "")),
        strip(row.get("School Name", "")) or None,
        strip(row.get("Campus Name (If Relevant)", "")) or None,
        city or None,
        state_code,
        career_path or None,
        specific_career or degree_prog or None,
        specific_career or None,
        start_date,
        parse_gpa(row.get("GPA", "")),
        strip(row.get("Age", "")) or None,
        strip(row.get("Gender", "")) or None,
        parse_bool(row.get("Military", "")),
        parse_bool(row.get("Military Spouse/Dependent", "")),
        strip(row.get("Household Income", "")) or None,
        strip(row.get("Current Wages", "")) or None,
        parse_bool(row.get("Internship?", "")) or False,
        internship_details or None,
        essay_bg or None,
        essay_imp or None,
        activities or None,
        honor_soc if honor_soc else None,
        strip(row.get("Remaining Program Costs", "")) or None,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Connecting to database...")
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.matches")
            deleted_matches = cur.rowcount
            cur.execute("DELETE FROM public.applicants")
            deleted_applicants = cur.rowcount
            conn.commit()
            print(f"Cleared {deleted_matches} matches and {deleted_applicants} applicants.")

        print(f"Reading CSV: {CSV_PATH}")
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [h.strip() for h in reader.fieldnames]

            rows = list(reader)
            print(f"CSV rows read: {len(rows)}")

            names = generate_names(len(rows))

            imported = 0
            errors = 0
            batch: List[tuple] = []

            with conn.cursor() as cur:
                for i, row in enumerate(rows):
                    first_name, last_name = names[i]
                    try:
                        values = row_to_values(row, first_name, last_name)
                        batch.append(values)
                    except Exception as e:
                        errors += 1
                        print(f"  [ERROR] Row {i + 1} ({first_name} {last_name}): {e}")
                        continue

                    if len(batch) >= BATCH_SIZE:
                        psycopg2.extras.execute_batch(
                            cur, INSERT_SQL, batch
                        )
                        conn.commit()
                        imported += len(batch)
                        print(f"  Committed batch: {imported} rows so far")
                        batch = []

                if batch:
                    psycopg2.extras.execute_batch(cur, INSERT_SQL, batch)
                    conn.commit()
                    imported += len(batch)

        print(f"\nDone! Imported {imported} applicants. Errors: {errors}")

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.applicants")
            total = cur.fetchone()[0]
            print(f"Total applicants in DB: {total}")

    except Exception as e:
        conn.rollback()
        print(f"Fatal error: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
