"""
Health check endpoint.
Returns the status of the API and its upstream dependencies (Supabase, Redis).
"""
from fastapi import APIRouter
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
            resp = await client.get(f"{settings.supabase_url}/rest/v1/")
            if resp.status_code in (200, 404):
                dependencies["supabase"] = DependencyStatus(status="ok")
            else:
                dependencies["supabase"] = DependencyStatus(
                    status="degraded", detail=f"HTTP {resp.status_code}"
                )
    except Exception as exc:
        dependencies["supabase"] = DependencyStatus(status="error", detail=str(exc))

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
