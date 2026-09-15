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
        populate_by_name=True,
    )

    project_id: str = Field(
        default="fde-bestbuy-sandbox-dev-508321",
        alias="GCP_PROJECT",
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
    bq_dataset: str = Field(
        default="catalog",
        alias="BQ_DATASET",
        description="BigQuery dataset name",
    )
    bq_table: str = Field(
        default="products",
        alias="BQ_TABLE",
        description="BigQuery catalog products table name",
    )
    gemini_model: str = Field(
        default="gemini-2.5-pro",
        alias="GEMINI_MODEL",
        description="Gemini LLM model name for agent synthesis",
    )
    temperature: float = Field(
        default=0.1,
        alias="AGENT_TEMPERATURE",
        description="Sampling temperature for deterministic grounding",
    )
    max_output_tokens: int = Field(
        default=2048,
        alias="AGENT_MAX_TOKENS",
        description="Max token limit for comparative synthesis",
    )
    enable_tracing: bool = Field(
        default=True,
        alias="ENABLE_TRACING",
        description="Enable OpenTelemetry distributed tracing",
    )
    export_traces_to_cloud: bool = Field(
        default=False,
        alias="EXPORT_TRACES_TO_CLOUD",
        description="Export distributed traces to Google Cloud Trace",
    )
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Application logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    bq_timeout_seconds: float = Field(
        default=2.5,
        alias="BQ_TIMEOUT_SECONDS",
        description="Timeout in seconds for BigQuery query operations",
    )
    bq_max_retries: int = Field(
        default=2,
        alias="BQ_MAX_RETRIES",
        description="Maximum retry attempts for BigQuery catalog queries",
    )

    @property
    def gcp_project(self) -> str:
        """Alias for project_id."""
        return self.project_id

    @property
    def catalog_table_id(self) -> str:
        """Full BigQuery table identifier."""
        return f"{self.project_id}.{self.bq_dataset}.{self.bq_table}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
