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
from app.routers import (
    account,
    admin,
    admin_jobs,
    admin_ops,
    admin_review,
    analytics_chat,
    applicants,
    auth,
    badges,
    chat,
    consent,
    credential_checkr,
    credential_taxonomy,
    credential_uploads,
    credential_verify,
    credentials,
    employer_public,
    employers,
    foundation,
    health,
    i18n_router,
    ingest,
    institution,
    jobs,
    matching_admin,
    messaging,
    notif_prefs,
    notifications_api,
    resume,
    resume_intake,
    skilled_id,
    skilled_id_admin,
    sla,
    sync,
    training,
    verified_workers,
)
from app.routers import applications as applications_router
from app.routers import calendar_feed as calendar_feed_router
from app.routers import calendar_sync as calendar_sync_router
from app.routers import career_sources as career_sources_router
from app.routers import commute as commute_router
from app.routers import interviews as interviews_router
from app.routers import job_imports as job_imports_router
from app.routers import scheduling as scheduling_router
from app.routers import team as team_router
from app.routers import viz_analytics as viz_analytics_router
from app.util.logging_config import (
    MaxBodySizeMiddleware,
    RequestIdMiddleware,
    setup_logging,
)
from app.worker.scheduler import create_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start / stop the APScheduler on application lifecycle events."""
    # Configure structured logging before anything else emits a line.
    setup_logging(get_settings().app_env)
    # Fail fast on production misconfiguration before we start accepting traffic.
    enforce_production_safety(get_settings(), logger)

    # Pre-warm the shared DB connection pool so the first requests don't pay to
    # build it (and so a bad DATABASE_URL fails fast at boot).
    from app.db import close_db_pool, get_pool
    await get_pool()
    logger.info("Database connection pool ready")

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started — full recompute every 6 hours")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
        await close_db_pool()
        logger.info("Database connection pool closed")


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
        version="0.2.0",
        docs_url="/docs" if settings.is_local else None,
        redoc_url="/redoc" if settings.is_local else None,
        lifespan=lifespan,
    )

    # Consistent RFC 7807 problem+json error envelope across the whole API.
    from app.util.errors import install_error_handlers
    install_error_handlers(app)

    # Reject oversized request bodies before they're read into memory.
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=5 * 1024 * 1024)

    # Request-id correlation (added first = runs innermost, so the id is set for
    # the whole handler; CORS below wraps it as the outermost layer).
    app.add_middleware(RequestIdMiddleware)

    # CORS — restrict to known origins in non-local envs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)         # /auth/me, /auth/complete-signup, /auth/invite-employer
    app.include_router(applicants.router)   # /applicant/me/profile, /applicant/me/matches
    app.include_router(chat.router)         # /applicant/me/chat/sessions
    app.include_router(badges.router)       # /applicant/me/badges

    app.include_router(employers.router)  # /employer/me/company, /employer/me/jobs, ...
    app.include_router(jobs.router)       # /jobs/browse

    app.include_router(messaging.router)  # /conversations

    app.include_router(admin.router)  # /admin/analytics/dashboard, /admin/analytics/job-map

    # SKILLED Pro
    app.include_router(credentials.router)  # /applicant/me/credentials
    app.include_router(consent.router)      # /applicant/me/consent
    app.include_router(skilled_id.router)   # /skilled-id/v1/verify (B2B API)
    app.include_router(ingest.router)       # /admin/credentials/ingest (bulk)
    app.include_router(credential_taxonomy.router)  # /credentials/taxonomy/suggest + /admin/credentials/normalization
    app.include_router(verified_workers.router)  # /employer/me/verified-workers (+ verify)
    app.include_router(skilled_id_admin.router)  # /admin/skilled-id (partner console)
    app.include_router(resume.router)            # /applicant/me/summary + resume.pdf
    app.include_router(sync.router)              # /admin/sync (SKILLED Nation <-> Pro)
    app.include_router(foundation.router)        # /admin/foundation (impact analytics)
    app.include_router(institution.router)        # /institution/me (partner portal)
    app.include_router(job_imports_router.emp_router)        # /employer/jobs/imports
    app.include_router(job_imports_router.adm_router)        # /admin/job-imports
    app.include_router(job_imports_router.emp_notif_router)  # /employer/notifications
    app.include_router(career_sources_router.router)         # /employer/me/career-source
    app.include_router(career_sources_router.adm_router)     # /admin/career-sources

    # Robustness pack
    app.include_router(resume_intake.router)   # /applicant/me/resume/*
    app.include_router(notif_prefs.router)     # /me/preferences
    app.include_router(i18n_router.router)     # /i18n/translate, /i18n/job/{id}
    app.include_router(training.pub_router)    # /training/programs
    app.include_router(training.app_router)    # /applicant/me/matches/{id}/training
    app.include_router(commute_router.router)  # /applicant/me/matches/{id}/commute
    app.include_router(credential_verify.router)  # /applicant/me/credentials/{id}/verify
    app.include_router(credential_uploads.router)         # /applicant/me/credentials/{id}/verify/{upload,phone-link,phone-status}
    app.include_router(credential_uploads.public_router)  # /credential-uploads/{token} (unauthenticated phone upload)
    app.include_router(credential_checkr.router)         # /applicant/me/credentials/{id}/checkr*
    app.include_router(credential_checkr.webhook_router) # /webhooks/checkr

    # Transaction stack
    app.include_router(applications_router.applicant_router)   # /applicant/me/{jobs/{id}/screening, jobs/{id}/apply, applications*}
    app.include_router(applications_router.employer_router)    # /employer/me/{jobs/{id}/screening, applications*}
    app.include_router(interviews_router.emp_router)           # /employer/me/{availability, applications/{id}/propose}
    app.include_router(interviews_router.app_router)           # /applicant/me/interviews*
    app.include_router(team_router.router)                     # /employer/me/team/{overview,invites*}
    app.include_router(team_router.join_router)                # /auth/join/{token}* (public, token-authenticated)
    app.include_router(scheduling_router.router)               # /employer/me/{applications/{id}/scheduling-request, scheduling-requests*}
    app.include_router(calendar_feed_router.user_router)       # /me/calendar/{feed,feed/rotate,providers}
    app.include_router(calendar_feed_router.public_router)     # /calendar/feed.ics (token-authenticated ICS feed)
    app.include_router(calendar_sync_router.user_router)       # /me/calendar/{connect,connections,busy} (OAuth read tier)
    app.include_router(calendar_sync_router.public_router)     # /calendar/callback/{provider} (OAuth redirect)
    app.include_router(notifications_api.router)               # /me/notifications*
    app.include_router(account.user_router)                    # /me/account/{email,phone,skilled-id}
    app.include_router(account.admin_router)                   # /admin/account-recovery
    app.include_router(sla.router)                             # /admin/analytics/sla
    app.include_router(viz_analytics_router.router)            # /viz/matches/{id}/explanation
    app.include_router(employer_public.router)                 # /employers/{id}/public
    app.include_router(analytics_chat.router)                  # /employer/me/analytics/chat
    app.include_router(admin_ops.router)                       # /admin/ops/*
    app.include_router(matching_admin.router)                  # /admin/matching/*
    app.include_router(admin_jobs.router)                      # /admin/jobs (structured jobs console)
    app.include_router(admin_review.router)                    # /admin/review + /admin/audit-logs

    return app


app = create_app()
