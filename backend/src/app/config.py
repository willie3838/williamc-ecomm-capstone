"""Environment settings and configuration for the Best Buy Catalog Agent service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable override support."""

    gcp_project: str = Field(default="fde-bestbuy-sandbox-dev-508321", alias="GCP_PROJECT")
    bq_dataset: str = Field(default="catalog", alias="BQ_DATASET")
    bq_table: str = Field(default="products", alias="BQ_TABLE")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")
    temperature: float = Field(default=0.1, alias="AGENT_TEMPERATURE")
    max_output_tokens: int = Field(default=2048, alias="AGENT_MAX_TOKENS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def catalog_table_id(self) -> str:
        """Full BigQuery table identifier."""
        return f"{self.gcp_project}.{self.bq_dataset}.{self.bq_table}"


settings = Settings()
