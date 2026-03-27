"""
SkillPointe Match — FastAPI application entry point.

Architecture rules (from CLAUDE.md):
- deterministic scoring is separate from policy reranking and LLM-assisted interpretation
- LLMs are supporting components, never the sole ranking engine
- geography is first-class in all ranking, scoring, and policy layers
- all admin overrides are auditable
- Supabase is the system of record; Redis is for async jobs
"""
import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, applicants, auth, employers, health, jobs
from app.routers import chat, messaging
from app.worker.scheduler import create_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start / stop the APScheduler on application lifecycle events."""
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started — full recompute every 6 hours")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    # Sentry (no-op if DSN is empty)
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.1,
        )

    app = FastAPI(
        title="SkillPointe Match API",
        description=(
            "Bi-directional ranking, explanation, and planning platform. "
            "Roles: admin | applicant | employer."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.is_local else None,
        redoc_url="/redoc" if settings.is_local else None,
        lifespan=lifespan,
    )

    # CORS — restrict to known origins in non-local envs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)         # /auth/me, /auth/complete-signup, /auth/invite-employer
    app.include_router(applicants.router)   # /applicant/me/profile, /applicant/me/matches
    app.include_router(chat.router)         # /applicant/me/chat/sessions

    app.include_router(employers.router)  # /employer/me/company, /employer/me/jobs, ...
    app.include_router(jobs.router)       # /jobs/browse

    app.include_router(messaging.router)  # /conversations

    app.include_router(admin.router)  # /admin/analytics/dashboard, /admin/analytics/job-map

    return app


app = create_app()
