"""
Application configuration — loaded from environment variables.
Uses pydantic-settings; will raise a clear error if required fields are missing.
"""
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    app_env: Literal["local", "test", "staging", "production"] = "local"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Database (direct Postgres — used by applicant/employer API routes)
    database_url: str = "postgresql://postgres:postgres@localhost:54322/postgres"

    # Connection pool sizing (per process — see app/db.py). With N replicas the
    # DB sees up to N × db_pool_max_size connections, so in production point
    # database_url at Supabase's pooler and set db_use_pgbouncer=true.
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_command_timeout: float = 30.0
    db_use_pgbouncer: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_extraction_model: str = "gpt-4o-mini"
    # Resilience & latency budget. A user should never wait through a long
    # retry storm — that reads as "broken" long before it succeeds. So:
    #   * ONE retry (not many): a single transient blip (429/5xx/network) is
    #     retried once with the SDK's short backoff; a second retry almost never
    #     converts a failure to a success and just doubles the tail latency.
    #   * A short CONNECT timeout so a dead/unreachable host fails fast (~5s)
    #     instead of making the user wait the full read budget just to connect.
    #   * A generous READ timeout because real LLM generation legitimately takes
    #     10-30s; that's answer latency, not a fault, so we don't cut it short.
    # Worst-case user wait on a hard outage ≈ (connect+read) × (1 retry) ≈ ~50s
    # then a clean graceful fallback — versus ~60s+ before, and it usually
    # resolves on the first attempt in well under the read budget.
    openai_timeout_seconds: float = 30.0
    openai_connect_timeout_seconds: float = 5.0
    openai_max_retries: int = 1

    # Headless (Playwright Chromium) LISTING-ONLY fallback for JS-walled
    # careers sites (see app/skilled_pro/headless.py). Scheduler/background
    # only — never on the request path. Default ON for local/dev; set
    # HEADLESS_SCRAPE_ENABLED=false where Chromium isn't provisioned.
    headless_scrape_enabled: bool = True

    # Sentry
    sentry_dsn: str = ""

    # Storage buckets
    storage_bucket_resumes: str = "resumes"
    storage_bucket_documents: str = "documents"

    # SKILLED Pro — credential signing (Ed25519 PEM) + SKILLED ID API key pepper.
    # In production these come from a KMS/secret store. If unset locally, an
    # ephemeral keypair is generated at startup (records won't verify across
    # restarts — fine for dev, never for prod).
    skilled_signing_private_key: str = ""
    skilled_signing_public_key: str = ""
    skilled_signing_key_id: str = "dev-ephemeral"
    skilled_api_key_pepper: str = ""

    # Drive-time provider — Google Maps Distance Matrix (preferred) or Mapbox.
    # If neither key is set, the drive-time helper falls back to a haversine estimate
    # with a fudge factor (rural roads add ~40% over great-circle).
    google_maps_api_key: str = ""
    mapbox_access_token: str = ""

    # Calendar OAuth sync — the READ (free/busy overlay) tier is BUILT
    # (app/routers/calendar_sync.py + app/skilled_pro/calendar_sync.py).
    # When a pair is set, the UI shows the corresponding "Connect …" button via
    # GET /me/calendar/providers and the button leads to the working
    # auth-code + PKCE flow; leaving them unset (the local default) hides the
    # buttons entirely. Scopes actually requested (minimal, free/busy only):
    #   Google:  https://www.googleapis.com/auth/calendar.freebusy  (+ openid email)
    #   Microsoft Graph:  Calendars.Read (delegated)  (+ openid email offline_access)
    # Redirect URIs to register on the OAuth apps:
    #   {API_PUBLIC_URL}/calendar/callback/google
    #   {API_PUBLIC_URL}/calendar/callback/microsoft
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    ms_graph_client_id: str = ""
    ms_graph_client_secret: str = ""

    # Public origin of THIS API (used to build the OAuth redirect_uri that must
    # exactly match the provider app registration) and of the web app (where
    # the callback sends the browser afterwards; defaults to the first CORS
    # origin when unset).
    api_public_url: str = "http://localhost:8000"
    web_public_url: str = ""

    # Local-only demo calendar: a "Connect demo calendar" button whose
    # connection produces deterministic busy blocks through the SAME
    # storage/fetch/overlay pipeline as real providers — so the whole UX is
    # verifiable without OAuth keys. Refused in production (see
    # enforce_production_safety AND the endpoint's own guard).
    calendar_fake_provider: bool = False

    # SMS / email delivery.
    # Email picks the first configured path: Resend (production) → SMTP
    # (smtp_host/smtp_port; locally this is Supabase's Inbucket/Mailpit at
    # localhost:54325, so every email is really sent and inspectable at
    # http://localhost:54324) → skipped with an honest SendResult.
    # In APP_ENV=local the SMTP fallback defaults to Inbucket automatically.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 0

    @property
    def web_origin(self) -> str:
        """Absolute origin of the web app — for links inside emails (team
        invites, scheduling deep links). Uses web_public_url when set, else
        the first CORS origin (which is the web app in every environment)."""
        if self.web_public_url:
            return self.web_public_url.rstrip("/")
        origins = self.cors_origins_list
        return (origins[0] if origins else "http://localhost:3000").rstrip("/")

    # Credential-verification partners. All optional — adapters return well-formed
    # stubbed results when a key is missing so the flow keeps working end-to-end.
    nccer_api_key: str = ""       # Contact partners@nccer.org for a Registry key
    nsc_api_key: str = ""         # NSC DegreeVerify service account key

    # Checkr — background checks, MVR/CDLIS, professional license verification.
    # Employer-initiated + employer-paid so Checkr owns the FCRA flow. Unset =
    # the hosted invitation is simulated in local and unavailable in production.
    checkr_api_key: str = ""
    checkr_webhook_secret: str = ""   # verifies inbound webhook signatures
    checkr_default_package: str = "driver_pro"  # Checkr package slug to invite into

    # Pluggable OCR + SIS providers. These were previously read via getattr() but
    # never declared, so `extra="ignore"` silently dropped them and the app was
    # locked to the heuristic OCR + mock SIS feed. Declaring them makes the env
    # vars actually take effect. Empty string = "use the environment default"
    # (heuristic/mock in local, safe null provider everywhere else — see
    # get_ocr_provider / get_sis_provider).
    ocr_provider: str = ""        # "" | "heuristic" | "textract" | "null"
    sis_provider: str = ""        # "" | "mock" | "ethos" | "null"

    # App-layer encryption for sensitive at-rest fields (screening answers).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # In production this MUST be set — the config self-check below refuses to
    # boot without it. Dev falls back to a JWT-secret-derived key.
    screening_encryption_key: str = ""

    # CORS
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Production safety checks — invoked from FastAPI startup.
# ---------------------------------------------------------------------------

class ProductionConfigError(RuntimeError):
    """Raised when the app is misconfigured to run in production."""


def _project_host_label(settings: Settings) -> str:
    """First hostname label of the site we already trust, e.g. 'skilled-nation'
    from https://skilled-nation.vercel.app.

    Used to scope the CORS preview-origin regex to this project without naming
    it in code, so a rebrand doesn't turn into a boot failure.
    """
    candidates = [settings.web_public_url, *settings.cors_origins_list]
    for raw in candidates:
        host = urlparse(raw.strip()).hostname if raw and "//" in raw else None
        if not host or host in ("localhost", "127.0.0.1"):
            continue
        label = host.split(".")[0].lower()
        # "www" and bare platform hosts carry no project identity.
        if label and label not in ("www", "vercel", "api"):
            return label
    return ""


def enforce_production_safety(settings: Settings, logger) -> None:
    """
    Validate config once at startup. In production, fail hard on missing
    launch-critical secrets. Log warnings for optional degradations.

    Called from app.main.lifespan.
    """
    is_prod = settings.app_env == "production"

    # --- Warnings (any environment) ---------------------------------------
    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY unset — LLM features (chat, extraction, AI priority, i18n) will degrade."
        )
    if not settings.google_maps_api_key and not settings.mapbox_access_token:
        logger.warning(
            "No drive-time provider key set (google_maps_api_key / mapbox_access_token). "
            "Falling back to haversine estimates (~40%% inaccurate on rural routes)."
        )

    if not is_prod:
        return

    # --- Hard failures in production --------------------------------------
    errors: list[str] = []

    # Signing key (SKILLED Pro) — ephemeral key is a footgun in prod because
    # signed credentials stop verifying on every restart.
    if not settings.skilled_signing_private_key or settings.skilled_signing_key_id == "dev-ephemeral":
        errors.append(
            "SKILLED_SIGNING_PRIVATE_KEY must be set to a stable Ed25519 PEM "
            "(and SKILLED_SIGNING_KEY_ID must not be 'dev-ephemeral') in production."
        )

    # Screening answer encryption
    if not settings.screening_encryption_key:
        errors.append(
            "SCREENING_ENCRYPTION_KEY must be set in production. Generate with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        )

    # The demo calendar provider is a dev fixture; it must not exist in prod.
    if settings.calendar_fake_provider:
        errors.append(
            "CALENDAR_FAKE_PROVIDER must be false in production — the demo "
            "calendar is a local development fixture only."
        )

    # No localhost URLs in prod
    for name, val in (
        ("supabase_url", settings.supabase_url),
        ("database_url", settings.database_url),
        ("redis_url", settings.redis_url),
    ):
        if val and ("localhost" in val or "127.0.0.1" in val):
            errors.append(f"{name} points at localhost in production ({val!r}).")

    # CORS: with allow_credentials=True, an over-broad origin regex trusts any
    # matching site. Judge the pattern's SHAPE, not its brand text — an earlier
    # version required the literal project name, so renaming the project made
    # even a correctly scoped regex unbootable.
    regex_raw = (settings.cors_origin_regex or "").strip()
    if regex_raw:
        faults: list[str] = []
        if not (regex_raw.startswith("^") and regex_raw.endswith("$")):
            faults.append(
                "it is not anchored with ^ and $, so it matches any origin that "
                "merely contains the pattern"
            )
        if ".*" in regex_raw or ".+" in regex_raw:
            faults.append(
                "it contains an unbounded wildcard (.* or .+), which matches "
                "arbitrary hosts"
            )
        # Scope it to this deployment's own project, derived from the hosts we
        # already trust, so the check follows the project instead of a constant.
        label = _project_host_label(settings)
        if label and label not in regex_raw.lower():
            faults.append(
                f"it does not mention this project's host label ({label!r}), so it "
                "can match another tenant's deploys on the same platform"
            )
        if faults:
            joined_faults = "; ".join(faults)
            example = f"^https://{label or 'your-project'}-[a-z0-9-]+\\.vercel\\.app$"
            errors.append(
                "CORS_ORIGIN_REGEX is unsafe for a credentialed API "
                f"({settings.cors_origin_regex!r}): {joined_faults}. "
                f"Use a pattern like {example}"
            )

    if errors:
        joined = "\n  - ".join(errors)
        raise ProductionConfigError(
            f"Refusing to boot with production-unsafe config:\n  - {joined}"
        )
