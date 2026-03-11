#!/usr/bin/env python3
"""
Connection test utility for SkillPointe Match local dev environment.

Tests:
  - Redis connectivity
  - Supabase REST API connectivity
  - Supabase Auth endpoint availability

Usage:
  python scripts/check_connections.py

Requires: pip install redis httpx python-dotenv
"""
import asyncio
import os
import sys

# Load .env from apps/api if present
from pathlib import Path

env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file)
    print(f"Loaded env from {env_file}")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://localhost:54321")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


async def check_redis() -> bool:
    print("\n[Redis]")
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=3)
        pong = await r.ping()
        await r.aclose()
        if pong:
            print(f"  OK   — connected to {REDIS_URL}")
            return True
        else:
            print(f"  FAIL — unexpected ping response from {REDIS_URL}")
            return False
    except Exception as e:
        print(f"  FAIL — {e}")
        print(f"  Hint: run `docker compose -f infra/docker-compose.local.yml up -d`")
        return False


async def check_supabase() -> bool:
    print("\n[Supabase]")
    try:
        import httpx

        headers = {}
        if SUPABASE_ANON_KEY:
            headers["apikey"] = SUPABASE_ANON_KEY

        async with httpx.AsyncClient(timeout=5.0) as client:
            # REST API
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/",
                headers=headers,
            )
            if resp.status_code in (200, 404):
                print(f"  OK   — REST API reachable at {SUPABASE_URL} (HTTP {resp.status_code})")
            else:
                print(f"  WARN — REST API returned HTTP {resp.status_code}")

            # Auth endpoint
            auth_resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/health",
                headers=headers,
            )
            if auth_resp.status_code == 200:
                print(f"  OK   — Auth endpoint healthy")
            else:
                print(f"  WARN — Auth endpoint returned HTTP {auth_resp.status_code}")

        return True
    except Exception as e:
        print(f"  FAIL — {e}")
        print(
            f"  Hint: run `supabase start` in the repo root to start local Supabase"
        )
        return False


async def main() -> None:
    print("=" * 50)
    print("SkillPointe Match — Connection Check")
    print("=" * 50)

    redis_ok = await check_redis()
    supabase_ok = await check_supabase()

    print()
    if redis_ok and supabase_ok:
        print("All connections OK. Local dev environment is ready.")
        sys.exit(0)
    else:
        print("One or more connections failed. See hints above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
