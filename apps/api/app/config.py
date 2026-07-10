"""
Application configuration — loaded from environment variables.
Uses pydantic-settings; will raise a clear error if required fields are missing.
"""
from functools import lru_cache
from typing import Literal

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

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_extraction_model: str = "gpt-4o-mini"

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

    # SMS / email delivery — stubbed until keys land.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    resend_api_key: str = ""

    # Credential-verification partners. All optional — adapters return well-formed
    # stubbed results when a key is missing so the flow keeps working end-to-end.
    nccer_api_key: str = ""       # Contact partners@nccer.org for a Registry key
    nsc_api_key: str = ""         # NSC DegreeVerify service account key

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

    # No localhost URLs in prod
    for name, val in (
        ("supabase_url", settings.supabase_url),
        ("database_url", settings.database_url),
        ("redis_url", settings.redis_url),
    ):
        if val and ("localhost" in val or "127.0.0.1" in val):
            errors.append(f"{name} points at localhost in production ({val!r}).")

    if errors:
        joined = "\n  - ".join(errors)
        raise ProductionConfigError(
            f"Refusing to boot with production-unsafe config:\n  - {joined}"
        )
