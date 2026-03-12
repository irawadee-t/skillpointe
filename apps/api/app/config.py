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

    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
