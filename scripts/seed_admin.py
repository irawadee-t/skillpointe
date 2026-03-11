#!/usr/bin/env python3
"""
Seed the first admin user.

Creates a Supabase Auth user with the given email/password,
creates a user_profiles row with role='admin',
and sets app_metadata.role='admin' so the JWT includes the role.

Usage:
    cd apps/api && source .venv/bin/activate
    python ../../scripts/seed_admin.py --email admin@example.com --password <secret>

Requirements:
    pip install supabase python-dotenv

Must be run with apps/api/.env loaded (or env vars set in shell).
"""
import argparse
import os
import sys
from pathlib import Path

# Load apps/api/.env
env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"Loaded env from {env_file}")


def seed_admin(email: str, password: str) -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    from supabase import create_client

    client = create_client(supabase_url, service_role_key)

    print(f"\nCreating admin auth user: {email}")

    # Create Supabase Auth user
    try:
        resp = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,  # skip email confirmation
                "app_metadata": {"role": "admin"},
            }
        )
        user_id = resp.user.id
        print(f"  Auth user created: {user_id}")
    except Exception as exc:
        print(f"  ERROR creating auth user: {exc}")
        sys.exit(1)

    # Create user_profiles row
    try:
        client.table("user_profiles").insert(
            {"user_id": user_id, "role": "admin", "onboarding_complete": True}
        ).execute()
        print(f"  user_profiles row created with role=admin")
    except Exception as exc:
        print(f"  ERROR creating user_profiles: {exc}")
        print(f"  Auth user was created (id={user_id}) but profile insert failed.")
        print(f"  Run manually: INSERT INTO user_profiles (user_id, role) VALUES ('{user_id}', 'admin');")
        sys.exit(1)

    print(f"\nAdmin user ready.")
    print(f"  Email:   {email}")
    print(f"  User ID: {user_id}")
    print(f"  Role:    admin")
    print(f"\nSign in at http://localhost:3000/login")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed first admin user")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    seed_admin(args.email, args.password)
