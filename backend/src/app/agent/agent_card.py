"""Stateless A2A Agent Card generator for Google Cloud Agent Registry discovery."""

from __future__ import annotations

from typing import Any

from app.config import settings


def build_a2a_agent_card(
    base_url: str,
    version: str | None = None,
) -> dict[str, Any]:
    """Return the standard A2A Agent Card (`/.well-known/agent-card.json`).

    Conforms to the Google Cloud Agent Registry (`gcloud agent-registry`) and
    Agent-to-Agent (A2A) protocol discovery schema so Google Cloud Console and
    Gemini Enterprise can inspect the Cloud Run service's endpoints and skills.
    """
    clean_url = base_url.rstrip("/")
    resolved_version = version or settings.agent_version
    is_flash = "flash" in resolved_version.lower()
    model_name = "gemini-2.5-flash" if is_flash else settings.gemini_model
    model_version = "gemini-2.5-flash@001" if is_flash else settings.model_version
    prompt_version = "2026.03-v2" if is_flash else settings.prompt_version

    return {
        "name": "techbuy-catalog-comparison-agent",
        "description": (
            "TechBuy Retailers Catalog Comparison Agent powered by Google ADK, Gemini 2.5, "
            "Vertex AI Prompt Management, and BigQuery grounding."
        ),
        "version": resolved_version,
        "provider": {
            "organization": "TechBuy Retailers FDE Capstone",
            "url": clean_url,
        },
        "supportedInterfaces": [
            {
                "url": f"{clean_url}/api/compare",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            }
        ],
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "spec-comparison",
                "name": "Product Specification Comparison",
                "description": "Side-by-side feature matrix comparison strictly grounded in BigQuery SKUs.",
                "tags": ["ecommerce", "comparison", "bigquery", "citations"],
            },
            {
                "id": "intent-classification",
                "name": "Semantic Query Intent Classification",
                "description": "Classifies shopper queries and suppresses non-comparative rants.",
                "tags": ["intent", "guardrails"],
            },
            {
                "id": "catalog-retrieval",
                "name": "Parameterized BigQuery Catalog Search",
                "description": "Retrieves deduplicated, brand-balanced product SKUs.",
                "tags": ["bigquery", "retrieval"],
            },
        ],
        "metadata": {
            "gcp_project": settings.project_id,
            "gcp_agent_registry": "agentregistry.googleapis.com",
            "region": getattr(settings, "region", "us-central1"),
            "model": model_name,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "vertex_prompt_id": getattr(settings, "vertex_prompt_id", ""),
        },
    }
