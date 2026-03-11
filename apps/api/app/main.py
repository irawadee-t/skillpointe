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

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, health

logger = logging.getLogger(__name__)


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
    )

    # CORS — restrict to known origins in non-local envs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)       # /auth/me, /auth/complete-signup, /auth/invite-employer

    # Placeholder routers — added in Phase 3+
    # app.include_router(applicants.router, prefix="/applicants")
    # app.include_router(employers.router, prefix="/employers")
    # app.include_router(jobs.router, prefix="/jobs")
    # app.include_router(matches.router, prefix="/matches")
    # app.include_router(admin.router, prefix="/admin")

    return app


app = create_app()
