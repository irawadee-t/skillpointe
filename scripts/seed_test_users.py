#!/usr/bin/env python3
"""
seed_test_users.py — Create all three test users with sample data.

Creates (idempotent — safe to re-run, skips existing users):

  admin@test.local      / Test1234!  — admin role
  applicant@test.local  / Test1234!  — applicant role
                                        with profile + 2 sample matches
  employer@test.local   / Test1234!  — employer role
                                        with company + 2 jobs + 2 sample matches

Usage:
    cd apps/api && source .venv/bin/activate
    python ../../scripts/seed_test_users.py

Requirements:
    pip install supabase psycopg2-binary python-dotenv
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

# Load apps/api/.env
env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"Loaded env from {env_file}")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://localhost:54321")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres")

PASSWORD = "Test1234!"

USERS = [
    {"email": "admin@test.local",     "role": "admin"},
    {"email": "applicant@test.local", "role": "applicant"},
    {"email": "employer@test.local",  "role": "employer"},
]


def _create_auth_user(client, email: str, role: str) -> str | None:
    """Create Supabase Auth user. Returns user_id or None if already exists."""
    try:
        resp = client.auth.admin.create_user({
            "email": email,
            "password": PASSWORD,
            "email_confirm": True,
            "app_metadata": {"role": role},
        })
        uid = resp.user.id
        print(f"  ✓ Auth user created: {uid}")
        return uid
    except Exception as exc:
        msg = str(exc)
        if "already been registered" in msg or "already exists" in msg or "duplicate" in msg.lower():
            # Look up existing user
            try:
                users = client.auth.admin.list_users()
                for u in users:
                    if u.email == email:
                        print(f"  → Auth user already exists: {u.id}")
                        return u.id
            except Exception:
                pass
        print(f"  ✗ Auth error for {email}: {exc}")
        return None


def _upsert_user_profile(conn, user_id: str, role: str) -> None:
    conn.execute(
        """
        INSERT INTO public.user_profiles (user_id, role, onboarding_complete)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, role),
    )


def seed(conn, client) -> None:
    ids: dict[str, str] = {}  # email → user_id

    # ---------------------------------------------------------------
    # Step 1: Create auth users + user_profiles
    # ---------------------------------------------------------------
    print("\n── Creating auth users ──")
    for u in USERS:
        print(f"\n{u['email']} ({u['role']})")
        uid = _create_auth_user(client, u["email"], u["role"])
        if not uid:
            print(f"  Skipping DB setup for {u['email']} — could not get user_id")
            continue
        ids[u["email"]] = uid
        _upsert_user_profile(conn, uid, u["role"])
        print(f"  ✓ user_profiles row ({u['role']})")

    applicant_uid = ids.get("applicant@test.local")
    employer_uid = ids.get("employer@test.local")

    # ---------------------------------------------------------------
    # Step 2: Resolve canonical_job_family_id for 'welding'
    # ---------------------------------------------------------------
    conn.execute("SELECT id FROM public.canonical_job_families WHERE code = 'welding' LIMIT 1")
    row = conn.fetchone()
    if not row:
        print("\n⚠  canonical_job_families not seeded yet — run `supabase db reset` first.")
        return
    welding_family_id = row[0]

    # ---------------------------------------------------------------
    # Step 3: Applicant profile
    # ---------------------------------------------------------------
    if applicant_uid:
        print("\n── Applicant profile ──")
        conn.execute(
            """
            INSERT INTO public.applicants (
                user_id, first_name, last_name,
                program_name_raw, canonical_job_family_id,
                city, state, region,
                willing_to_relocate, willing_to_travel,
                expected_completion_date, available_from_date,
                onboarding_complete, source
            ) VALUES (
                %s, 'Jane', 'Smith',
                'Welding Technology — Associate Degree', %s,
                'Austin', 'TX', 'southwest',
                TRUE, FALSE,
                '2026-05-15', '2026-06-01',
                TRUE, 'seed'
            )
            ON CONFLICT (user_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name
            RETURNING id
            """,
            (applicant_uid, welding_family_id),
        )
        row = conn.fetchone()
        applicant_id = row[0]
        print(f"  ✓ applicants row: {applicant_id}")
    else:
        applicant_id = None
        print("\n── Skipping applicant profile (no user_id) ──")

    # ---------------------------------------------------------------
    # Step 4: Employer + employer_contacts
    # ---------------------------------------------------------------
    if employer_uid:
        print("\n── Employer ──")

        # Employer company
        conn.execute(
            """
            INSERT INTO public.employers (name, industry, city, state, region, is_partner, source)
            VALUES ('Acme Industrial', 'Manufacturing', 'Austin', 'TX', 'southwest', TRUE, 'seed')
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
        )
        row = conn.fetchone()
        if row:
            employer_id = row[0]
            print(f"  ✓ employers row: {employer_id}")
        else:
            conn.execute(
                "SELECT id FROM public.employers WHERE name = 'Acme Industrial' LIMIT 1"
            )
            employer_id = conn.fetchone()[0]
            print(f"  → employer already exists: {employer_id}")

        # Link employer user → company
        conn.execute(
            """
            INSERT INTO public.employer_contacts (user_id, employer_id, is_primary, title)
            VALUES (%s, %s, TRUE, 'Hiring Manager')
            ON CONFLICT (user_id) DO NOTHING
            """,
            (employer_uid, employer_id),
        )
        print(f"  ✓ employer_contacts row")

        # Job 1 — eligible match target
        conn.execute(
            """
            INSERT INTO public.jobs (
                employer_id, title_raw, title_normalized,
                canonical_job_family_id,
                city, state, region,
                work_setting, travel_requirement,
                pay_min, pay_max, pay_type,
                description_raw, requirements_raw,
                experience_level, is_active, source
            ) VALUES (
                %s,
                'Welder — Entry Level',
                'Welder',
                %s,
                'Austin', 'TX', 'southwest',
                'on_site', 'none',
                22.00, 28.00, 'hourly',
                'Join our welding team. MIG/TIG work on industrial equipment.',
                'Welding Technology program graduate or equivalent trade experience. No license required for entry level.',
                'entry', TRUE, 'seed'
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (employer_id, welding_family_id),
        )
        row = conn.fetchone()
        if row:
            job1_id = row[0]
            print(f"  ✓ job 1 (Welder — Entry Level): {job1_id}")
        else:
            conn.execute(
                "SELECT id FROM public.jobs WHERE title_raw = 'Welder — Entry Level' AND employer_id = %s LIMIT 1",
                (employer_id,)
            )
            job1_id = conn.fetchone()[0]
            print(f"  → job 1 already exists: {job1_id}")

        # Job 2 — near_fit match target
        conn.execute(
            """
            INSERT INTO public.jobs (
                employer_id, title_raw, title_normalized,
                canonical_job_family_id,
                city, state, region,
                work_setting, travel_requirement,
                pay_min, pay_max, pay_type,
                description_raw, requirements_raw,
                experience_level, is_active, source
            ) VALUES (
                %s,
                'Metal Fabricator — Mid Level',
                'Metal Fabricator',
                %s,
                'Austin', 'TX', 'southwest',
                'on_site', 'light',
                26.00, 34.00, 'hourly',
                'Fabrication and assembly of structural steel components.',
                'Minimum 2 years fabrication experience. AWS certification preferred.',
                'mid', TRUE, 'seed'
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (employer_id, welding_family_id),
        )
        row = conn.fetchone()
        if row:
            job2_id = row[0]
            print(f"  ✓ job 2 (Metal Fabricator — Mid Level): {job2_id}")
        else:
            conn.execute(
                "SELECT id FROM public.jobs WHERE title_raw = 'Metal Fabricator — Mid Level' AND employer_id = %s LIMIT 1",
                (employer_id,)
            )
            job2_id = conn.fetchone()[0]
            print(f"  → job 2 already exists: {job2_id}")

    else:
        employer_id = job1_id = job2_id = None
        print("\n── Skipping employer setup (no user_id) ──")

    # ---------------------------------------------------------------
    # Step 5: Sample matches (applicant ↔ both jobs)
    # ---------------------------------------------------------------
    if applicant_id and job1_id and job2_id:
        print("\n── Sample matches ──")

        _upsert_match(
            conn,
            applicant_id=applicant_id,
            job_id=job1_id,
            eligibility_status="eligible",
            base_fit_score=79.5,
            weighted_structured_score=81.0,
            semantic_score=74.0,
            policy_adjusted_score=84.5,
            match_label="strong_fit",
            top_strengths=[
                "Trade alignment: Welding Technology maps directly to job family",
                "Geography: Austin TX — same city as job location",
                "Timing: Available June 2026, within hiring window",
            ],
            top_gaps=[
                "Experience: Limited documented internship hours",
            ],
            required_missing_items=[
                "1 year of documented welding experience preferred (not required for entry level)",
            ],
            recommended_next_step="Apply directly — you meet all key requirements for this entry-level role.",
            confidence_level="high",
            hard_gate_rationale={
                "job_family":       {"result": "pass",     "reason": "Welding Technology aligns directly with Welder job family", "severity": None},
                "geography":        {"result": "pass",     "reason": "Austin TX matches job location", "severity": None},
                "timing_readiness": {"result": "pass",     "reason": "Available from June 2026 — within window", "severity": None},
                "credential":       {"result": "pass",     "reason": "No hard credential requirements for entry level", "severity": None},
                "explicit_minimum": {"result": "pass",     "reason": "No explicit minimum stated beyond trade program", "severity": None},
            },
            policy_modifiers=[
                {"policy": "partner_employer_preference", "value": 5,  "reason": "Acme Industrial is a SkillPointe partner employer"},
                {"policy": "readiness_preference",        "value": 3,  "reason": "Applicant completing program in < 3 months"},
            ],
            dimension_scores=[
                ("trade_program_alignment",       25, 90, 22.50, "Welding Technology maps directly to Welding & Metal Fabrication family", False),
                ("geography_alignment",           20, 96, 19.20, "Austin TX → Austin TX — same city", False),
                ("credential_readiness",          15, 72, 10.80, "No hard credentials required; completion date within window", False),
                ("timing_readiness",              10, 80,  8.00, "Available June 2026 — within acceptable hiring window", False),
                ("experience_internship_alignment",10, 50,  5.00, "Limited documented experience — typical for program graduate", True),
                ("industry_alignment",             5, 85,  4.25, "Manufacturing/industrial sector aligns", False),
                ("compensation_alignment",         5, 75,  3.75, "Pay range $22–$28/hr consistent with entry-level expectations", False),
                ("work_style_signal_alignment",    5, 78,  3.90, "On-site role — applicant is local, no remote preference detected", False),
                ("employer_soft_pref_alignment",   5, 50,  2.50, "No soft preferences specified by employer", True),
            ],
        )

        _upsert_match(
            conn,
            applicant_id=applicant_id,
            job_id=job2_id,
            eligibility_status="near_fit",
            base_fit_score=55.5,
            weighted_structured_score=62.0,
            semantic_score=58.0,
            policy_adjusted_score=58.5,
            match_label="moderate_fit",
            top_strengths=[
                "Trade alignment: Welding background relevant to metal fabrication",
                "Geography: Austin TX — same city",
            ],
            top_gaps=[
                "Experience gap: 2 years required, applicant has limited logged hours",
                "Certification gap: AWS certification preferred but not held",
            ],
            required_missing_items=[
                "Minimum 2 years fabrication experience (required — near fit)",
                "AWS D1.1 certification preferred by employer",
            ],
            recommended_next_step=(
                "Build experience in entry-level welding roles first, "
                "then pursue AWS certification. Re-evaluate in 12–18 months."
            ),
            confidence_level="medium",
            hard_gate_rationale={
                "job_family":       {"result": "pass",     "reason": "Welding background adjacent to fabrication", "severity": None},
                "geography":        {"result": "pass",     "reason": "Austin TX matches job location", "severity": None},
                "timing_readiness": {"result": "pass",     "reason": "Available from June 2026", "severity": None},
                "credential":       {"result": "near_fit", "reason": "AWS cert preferred — applicant does not hold it", "severity": "moderate"},
                "explicit_minimum": {"result": "near_fit", "reason": "2 years experience required; applicant is entry level", "severity": "high"},
            },
            policy_modifiers=[
                {"policy": "partner_employer_preference", "value": 5,   "reason": "Acme Industrial is a SkillPointe partner employer"},
                {"policy": "missing_critical_requirement", "value": -12, "reason": "2-year experience requirement not met (near_fit gate)"},
            ],
            dimension_scores=[
                ("trade_program_alignment",        25, 75, 18.75, "Welding background is adjacent but fabrication is distinct specialisation", False),
                ("geography_alignment",            20, 96, 19.20, "Austin TX → Austin TX — same city", False),
                ("credential_readiness",           15, 35,  5.25, "AWS certification preferred; not held by applicant", False),
                ("timing_readiness",               10, 80,  8.00, "Available June 2026 — within window", False),
                ("experience_internship_alignment", 10, 30,  3.00, "Entry-level applicant vs 2-year requirement — significant gap", False),
                ("industry_alignment",              5, 80,  4.00, "Manufacturing sector aligns", False),
                ("compensation_alignment",          5, 60,  3.00, "Pay range higher than entry level — partially compatible", False),
                ("work_style_signal_alignment",     5, 70,  3.50, "On-site, light travel — applicant local, no travel preference noted", True),
                ("employer_soft_pref_alignment",    5, 50,  2.50, "No soft preferences specified by employer", True),
            ],
        )

        print("\n  ✓ 2 sample matches created")


def _upsert_match(
    conn,
    *,
    applicant_id,
    job_id,
    eligibility_status: str,
    base_fit_score: float,
    weighted_structured_score: float,
    semantic_score: float,
    policy_adjusted_score: float,
    match_label: str,
    top_strengths: list[str],
    top_gaps: list[str],
    required_missing_items: list[str],
    recommended_next_step: str,
    confidence_level: str,
    hard_gate_rationale: dict,
    policy_modifiers: list[dict],
    dimension_scores: list[tuple],
) -> None:
    conn.execute(
        """
        INSERT INTO public.matches (
            applicant_id, job_id,
            eligibility_status, hard_gate_cap,
            base_fit_score, weighted_structured_score, semantic_score,
            policy_adjusted_score, match_label,
            top_strengths, top_gaps,
            required_missing_items, recommended_next_step,
            confidence_level, requires_review,
            hard_gate_rationale, policy_modifiers,
            is_visible_to_applicant, is_visible_to_employer,
            policy_version
        ) VALUES (
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, FALSE,
            %s, %s,
            TRUE, TRUE,
            'v1'
        )
        ON CONFLICT (applicant_id, job_id) DO UPDATE SET
            policy_adjusted_score = EXCLUDED.policy_adjusted_score,
            match_label           = EXCLUDED.match_label
        RETURNING id
        """,
        (
            applicant_id, job_id,
            eligibility_status,
            1.0 if eligibility_status == "eligible" else 0.75,
            base_fit_score, weighted_structured_score, semantic_score,
            policy_adjusted_score, match_label,
            json.dumps(top_strengths), json.dumps(top_gaps),
            json.dumps(required_missing_items), recommended_next_step,
            confidence_level,
            json.dumps(hard_gate_rationale), json.dumps(policy_modifiers),
        ),
    )
    match_row = conn.fetchone()
    match_id = match_row[0]

    # Dimension scores
    for (dimension, weight, raw_score, weighted_score, rationale, null_applied) in dimension_scores:
        conn.execute(
            """
            INSERT INTO public.match_dimension_scores
                (match_id, dimension, weight, raw_score, weighted_score,
                 rationale, null_handling_applied)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, dimension) DO UPDATE SET
                raw_score      = EXCLUDED.raw_score,
                weighted_score = EXCLUDED.weighted_score
            """,
            (match_id, dimension, weight, raw_score, weighted_score, rationale, null_applied),
        )


def main() -> None:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2-binary is required. Run: pip install psycopg2-binary")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase is required. Run: pip install supabase")
        sys.exit(1)

    if not SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not set. Check apps/api/.env")
        sys.exit(1)

    print(f"Connecting to Supabase at {SUPABASE_URL}")
    print(f"Connecting to DB at {DB_URL}")

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

    raw_conn = psycopg2.connect(DB_URL)
    raw_conn.autocommit = False
    conn = raw_conn.cursor()

    try:
        seed(conn, client)
        raw_conn.commit()
        print("\n✅ Done. Test credentials:\n")
        print(f"  {'Role':<12} {'Email':<28} {'Password'}")
        print(f"  {'────':<12} {'─────':<28} {'────────'}")
        for u in USERS:
            print(f"  {u['role']:<12} {u['email']:<28} {PASSWORD}")
        print(f"\n  Login at: http://localhost:3000/login\n")
    except Exception as exc:
        raw_conn.rollback()
        print(f"\n✗ Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
        raw_conn.close()


if __name__ == "__main__":
    main()
