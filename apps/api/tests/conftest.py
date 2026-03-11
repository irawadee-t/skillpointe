"""
Shared pytest fixtures for SkillPointe Match API tests.
"""
import os
import time
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Point to test env before importing app modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "super-secret-jwt-token-with-at-least-32-characters-long")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")


TEST_JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"


def make_jwt(
    user_id: str,
    email: str,
    app_role: str,
    expired: bool = False,
    bad_audience: bool = False,
) -> str:
    """Create a test JWT signed with the local Supabase secret."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "wrong-audience" if bad_audience else "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": app_role},
        "exp": now - 60 if expired else now + 3600,
        "iat": now,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def admin_token() -> str:
    return make_jwt("admin-user-uuid", "admin@example.com", "admin")


@pytest.fixture
def applicant_token() -> str:
    return make_jwt("applicant-user-uuid", "applicant@example.com", "applicant")


@pytest.fixture
def employer_token() -> str:
    return make_jwt("employer-user-uuid", "employer@example.com", "employer")


@pytest.fixture
def expired_token() -> str:
    return make_jwt("any-uuid", "x@example.com", "applicant", expired=True)


@pytest.fixture
def bad_audience_token() -> str:
    return make_jwt("any-uuid", "x@example.com", "applicant", bad_audience=True)


@pytest.fixture
def mock_supabase_client() -> Generator[MagicMock, None, None]:
    """
    Mock the Supabase admin client used in auth dependencies and routers.

    We must patch both locations because auth.py imports _get_admin_client
    directly (`from app.auth.dependencies import _get_admin_client`), which
    creates a local reference that patching the source module alone won't
    affect.
    """
    client = MagicMock()
    with (
        patch("app.auth.dependencies._get_admin_client", return_value=client),
        patch("app.routers.auth._get_admin_client", return_value=client),
    ):
        yield client


@pytest.fixture
def client(mock_supabase_client: MagicMock) -> TestClient:
    """FastAPI test client with mocked Supabase."""
    from app.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    return TestClient(app, raise_server_exceptions=False)
