"""Unit tests for configuration management and settings."""

import pytest

from app.config import Settings, get_settings


def test_default_settings() -> None:
    """Verify default configuration settings align with GCP environment requirements."""
    settings = Settings()
    assert settings.project_id == "fde-bestbuy-sandbox-dev-508321"
    assert settings.service_name == "catalog-backend"
    assert settings.environment == "development"
    assert settings.port == 8080
    assert settings.cors_origins == ["*"]
    assert settings.api_version == "0.1.0"


def test_custom_settings_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings parse environment variables with APP_ prefix."""
    monkeypatch.setenv("APP_PROJECT_ID", "custom-gcp-project")
    monkeypatch.setenv("APP_SERVICE_NAME", "custom-service")
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_PORT", "9090")
    monkeypatch.setenv("APP_CORS_ORIGINS", '["https://example.com", "https://bestbuy.com"]')
    monkeypatch.setenv("APP_API_VERSION", "1.0.0")

    settings = Settings()
    assert settings.project_id == "custom-gcp-project"
    assert settings.service_name == "custom-service"
    assert settings.environment == "production"
    assert settings.port == 9090
    assert settings.cors_origins == ["https://example.com", "https://bestbuy.com"]
    assert settings.api_version == "1.0.0"


def test_get_settings_cached() -> None:
    """Verify get_settings returns a cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
