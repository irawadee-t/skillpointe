"""
Health check endpoint.
Returns the status of the API and its upstream dependencies (Supabase, Redis).
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    status: str
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    env: str
    dependencies: dict[str, DependencyStatus]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    dependencies: dict[str, DependencyStatus] = {}

    # --- Supabase ping ---
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            # Send the anon key — a keyless request to /rest/v1/ returns 401 on
            # Supabase Cloud, which would otherwise show a false "degraded".
            headers = (
                {"apikey": settings.supabase_anon_key}
                if settings.supabase_anon_key
                else {}
            )
            resp = await client.get(f"{settings.supabase_url}/rest/v1/", headers=headers)
            if resp.status_code in (200, 404):
                dependencies["supabase"] = DependencyStatus(status="ok")
            else:
                dependencies["supabase"] = DependencyStatus(
                    status="degraded", detail=f"HTTP {resp.status_code}"
                )
    except Exception as exc:
        dependencies["supabase"] = DependencyStatus(status="error", detail=str(exc))

    # --- Postgres ping (the actual data path — asyncpg, not the REST gateway) ---
    try:
        from app.db import get_db

        async with get_db() as conn:
            await conn.fetchval("SELECT 1")
        dependencies["postgres"] = DependencyStatus(status="ok")
    except Exception as exc:
        dependencies["postgres"] = DependencyStatus(status="error", detail=str(exc)[:200])

    # --- Redis ping ---
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        dependencies["redis"] = DependencyStatus(status="ok")
    except Exception as exc:
        dependencies["redis"] = DependencyStatus(status="error", detail=str(exc))

    overall = (
        "ok"
        if all(d.status == "ok" for d in dependencies.values())
        else "degraded"
    )

    return HealthResponse(
        status=overall,
        env=settings.app_env,
        dependencies=dependencies,
    )


@router.get("/live", tags=["health"])
async def liveness() -> dict[str, str]:
    """Liveness probe: is the process up? Cheap, no dependency checks — a failing
    dependency should not cause the orchestrator to kill and restart the pod."""
    return {"status": "alive"}


@router.get("/ready", tags=["health"])
async def readiness() -> JSONResponse:
    """Readiness probe: can this instance serve traffic right now? Checks the
    data path (Postgres). Returns 503 when not ready so a load balancer can
    route around it without tearing the instance down."""
    try:
        from app.db import get_db

        async with get_db() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "ready"})
    except Exception as exc:
        return JSONResponse({"status": "not_ready", "detail": str(exc)[:200]}, status_code=503)
