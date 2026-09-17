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
    agent_version: str = Field(
        default="1.0.0",
        alias="AGENT_VERSION",
        description="Semantic version of the comparison agent orchestration logic",
    )
    prompt_version: str = Field(
        default="2026.03-v1",
        alias="PROMPT_VERSION",
        description="System prompt template version identifier",
    )
    model_version: str = Field(
        default="gemini-2.5-pro@001",
        alias="MODEL_VERSION",
        description="Pinned Vertex AI model version snapshot",
    )
    model_armor_prompt_template: str = Field(
        default="projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-prompt-guard",
        alias="MODEL_ARMOR_PROMPT_TEMPLATE",
        description="Google Cloud Model Armor prompt guardrail template",
    )
    model_armor_response_template: str = Field(
        default="projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-resp-guard",
        alias="MODEL_ARMOR_RESPONSE_TEMPLATE",
        description="Google Cloud Model Armor response guardrail template",
    )
    enable_model_armor: bool = Field(
        default=True,
        alias="ENABLE_MODEL_ARMOR",
        description="Enable Google Cloud Model Armor security guardrails",
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

    telemetry_dataset: str = Field(
        default="catalog_agent_telemetry",
        alias="BIGQUERY_TELEMETRY_DATASET",
        description="BigQuery dataset name for telemetry and analytics",
    )
    telemetry_table: str = Field(
        default="query_telemetry",
        alias="BIGQUERY_TELEMETRY_TABLE",
        description="BigQuery table name for query operational telemetry",
    )

    @property
    def gcp_project(self) -> str:
        """Alias for project_id."""
        return self.project_id

    @property
    def catalog_table_id(self) -> str:
        """Full BigQuery table identifier."""
        return f"{self.project_id}.{self.bq_dataset}.{self.bq_table}"

    @property
    def telemetry_table_id(self) -> str:
        """Full BigQuery telemetry table identifier."""
        return f"{self.project_id}.{self.telemetry_dataset}.{self.telemetry_table}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
