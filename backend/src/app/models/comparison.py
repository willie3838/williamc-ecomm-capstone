"""Structured Pydantic models for Stage 4 LLM comparison synthesis and per-specification winner evaluation."""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ComparisonSynthesis(BaseModel):
    """Structured response schema for LLM comparison narrative synthesis, persona recommendations, and per-spec winners."""

    summary: str = Field(
        ...,
        description="Comprehensive grounded narrative comparing the products across key features, strictly citing [SKU: <sku>].",
    )
    recommendations: str | None = Field(
        default=None,
        description="Optional tailored buying guidance explaining which product to choose based on user persona or priority use cases, strictly citing [SKU: <sku>].",
    )
    spec_winners: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of specification key (e.g., 'bluetooth_version', 'weight_oz', 'battery_life_hours') "
            "to the winning SKU string (or 'product_a'/'product_b', 'tie', or 'none' if subjective/incomparable)."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalized = dict(data)
            if "summary" not in normalized and "recommendation" in normalized:
                normalized["summary"] = normalized.pop("recommendation")
            for legacy_key in (
                "recommendation",
                "key_differences",
                "tradeoffs",
                "winner_sku",
                "confidence_score",
            ):
                normalized.pop(legacy_key, None)
            return normalized
        return data

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_summary_to_str(cls, v: object) -> str:
        if isinstance(v, list):
            return " ".join(str(item) for item in v if item is not None)
        return str(v) if v is not None else ""

    @field_validator("recommendations", mode="before")
    @classmethod
    def coerce_recommendations_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, list):
            return "\n".join(str(item) for item in v if item is not None)
        if isinstance(v, dict):
            return "\n".join(f"{k}: {val}" for k, val in v.items())
        return str(v)

    @field_validator("spec_winners", mode="before")
    @classmethod
    def coerce_spec_winners(cls, v: object) -> dict[str, str]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return {
                str(k).strip(): str(val).strip()
                for k, val in v.items()
                if k is not None and val is not None
            }
        return {}


__all__ = ["ComparisonSynthesis"]
