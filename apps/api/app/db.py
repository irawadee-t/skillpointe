"""
db.py — asyncpg connection POOL for FastAPI route handlers.

A single shared pool is created lazily on first use (and pre-warmed at app
startup) and reused for the whole process. Every request borrows a connection
from the pool with `pool.acquire()` and returns it — no per-request TCP/TLS/auth
handshake, and a hard cap on concurrent Postgres connections so the database
can't be overwhelmed under load.

Usage is unchanged for callers:
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT ...", ...)

Scaling notes:
- `max_size` is PER PROCESS. With N horizontally-scaled replicas the database
  sees up to N × max_size connections, so keep max_size modest and, in
  production, point DATABASE_URL at Supabase's connection pooler (Supavisor,
  transaction mode, port 6543) which multiplexes many client connections onto
  far fewer real Postgres connections. Set DB_USE_PGBOUNCER=true in that case —
  transaction-mode poolers don't support server-side prepared statements, so we
  disable asyncpg's statement cache.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import asyncpg

from app.config import get_settings

_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Runs once per pooled connection — register the JSONB codec so JSONB
    columns decode to Python dicts/lists."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool() -> asyncpg.Pool:
    """Return the shared pool, creating it on first use (double-checked lock so
    concurrent first requests don't each build a pool)."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                settings = get_settings()
                _pool = await asyncpg.create_pool(
                    settings.database_url,
                    min_size=settings.db_pool_min_size,
                    max_size=settings.db_pool_max_size,
                    max_inactive_connection_lifetime=300.0,
                    command_timeout=settings.db_command_timeout,
                    init=_init_connection,
                    # pgBouncer/Supavisor transaction mode can't hold prepared
                    # statements across pooled connections — disable the cache.
                    statement_cache_size=0 if settings.db_use_pgbouncer else 256,
                )
    return _pool


@asynccontextmanager
async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Borrow a connection from the shared pool for the duration of the block."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_db_pool() -> None:
    """Close the pool on shutdown so connections are released cleanly."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
