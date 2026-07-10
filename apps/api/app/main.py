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

from app.config import enforce_production_safety, get_settings
from app.routers import admin, applicants, auth, employers, health, jobs
from app.routers import chat, messaging
from app.routers import credentials, consent, skilled_id, ingest, verified_workers
from app.routers import skilled_id_admin, resume, sync, foundation, institution
from app.routers import job_imports as job_imports_router
from app.routers import resume_intake, notif_prefs, i18n_router, training
from app.routers import commute as commute_router
from app.routers import credential_verify
from app.routers import applications as applications_router
from app.routers import interviews as interviews_router
from app.routers import notifications_api, account, sla
from app.routers import employer_public, analytics_chat
from app.worker.scheduler import create_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start / stop the APScheduler on application lifecycle events."""
    # Fail fast on production misconfiguration before we start accepting traffic.
    enforce_production_safety(get_settings(), logger)

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

    # SKILLED Pro
    app.include_router(credentials.router)  # /applicant/me/credentials
    app.include_router(consent.router)      # /applicant/me/consent
    app.include_router(skilled_id.router)   # /skilled-id/v1/verify (B2B API)
    app.include_router(ingest.router)       # /admin/credentials/ingest (bulk)
    app.include_router(verified_workers.router)  # /employer/me/verified-workers (+ verify)
    app.include_router(skilled_id_admin.router)  # /admin/skilled-id (partner console)
    app.include_router(resume.router)            # /applicant/me/summary + resume.pdf
    app.include_router(sync.router)              # /admin/sync (SKILLED Nation <-> Pro)
    app.include_router(foundation.router)        # /admin/foundation (impact analytics)
    app.include_router(institution.router)        # /institution/me (partner portal)
    app.include_router(job_imports_router.emp_router)        # /employer/jobs/imports
    app.include_router(job_imports_router.adm_router)        # /admin/job-imports
    app.include_router(job_imports_router.emp_notif_router)  # /employer/notifications

    # Robustness pack
    app.include_router(resume_intake.router)   # /applicant/me/resume/*
    app.include_router(notif_prefs.router)     # /me/preferences
    app.include_router(i18n_router.router)     # /i18n/translate, /i18n/job/{id}
    app.include_router(training.pub_router)    # /training/programs
    app.include_router(training.app_router)    # /applicant/me/matches/{id}/training
    app.include_router(commute_router.router)  # /applicant/me/matches/{id}/commute
    app.include_router(credential_verify.router)  # /applicant/me/credentials/{id}/verify

    # Transaction stack
    app.include_router(applications_router.applicant_router)   # /applicant/me/{jobs/{id}/screening, jobs/{id}/apply, applications*}
    app.include_router(applications_router.employer_router)    # /employer/me/{jobs/{id}/screening, applications*}
    app.include_router(interviews_router.emp_router)           # /employer/me/{availability, applications/{id}/propose}
    app.include_router(interviews_router.app_router)           # /applicant/me/interviews*
    app.include_router(notifications_api.router)               # /me/notifications*
    app.include_router(account.user_router)                    # /me/account/{email,phone,skilled-id}
    app.include_router(account.admin_router)                   # /admin/account-recovery
    app.include_router(sla.router)                             # /admin/analytics/sla
    app.include_router(employer_public.router)                 # /employers/{id}/public
    app.include_router(analytics_chat.router)                  # /employer/me/analytics/chat

    return app


app = create_app()
