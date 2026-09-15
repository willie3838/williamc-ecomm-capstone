"""Configuration management for Best Buy Catalog Comparison Agent."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables with fallback defaults."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str = Field(
        default="fde-bestbuy-sandbox-dev-508321",
        description="Target Google Cloud project ID",
    )
    service_name: str = Field(
        default="catalog-backend",
        description="Logical service identifier for tracing and logging",
    )
    environment: str = Field(
        default="development",
        description="Deployment environment (development, staging, production)",
    )
    port: int = Field(
        default=8080,
        description="Listening port for the application server",
    )
    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed CORS origin patterns",
    )
    api_version: str = Field(
        default="0.1.0",
        description="Semantic version of the application API",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
