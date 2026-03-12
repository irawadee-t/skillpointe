"""
db.py — asyncpg connection helper for FastAPI route handlers.

Provides a per-request async Postgres connection.
Uses DATABASE_URL from settings (same Postgres instance as the ETL scripts,
port 54322 for local Supabase).

Phase 6+: complex JOIN queries (matches + jobs + employers + dimensions)
need raw SQL; the supabase-py client is used only for Auth/admin operations.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from app.config import get_settings


@asynccontextmanager
async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Async context manager for a single asyncpg connection.

    Usage in route handlers:
        async with get_db() as conn:
            row = await conn.fetchrow("SELECT ...", ...)
    """
    settings = get_settings()
    conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    try:
        # Register JSONB codec so JSONB columns are decoded to Python dicts/lists
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        yield conn
    finally:
        await conn.close()
