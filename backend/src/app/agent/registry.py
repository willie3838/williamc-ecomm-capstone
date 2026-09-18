"""Google Cloud Agent Registry & Agent-to-Agent (A2A) Domain Engine.

Manages registered AI agent versions, pairing immutable snapshots of code logic,
prompt templates, foundation model checkpoints, and declared capabilities.
Provides discovery endpoints conforming to Google Cloud Agent Registry & A2A specifications.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.prompts import SYSTEM_INSTRUCTION
from app.config import settings

logger = logging.getLogger(__name__)


class AgentSkill(BaseModel):
    """An autonomous capability or tool offered by the agent under A2A specification."""

    id: str = Field(..., description="Unique machine-readable skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    description: str = Field(..., description="Functional description of the skill")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class AgentVersionSpec(BaseModel):
    """An immutable release snapshot of an AI Agent version."""

    version: str = Field(..., description="Semantic version string (e.g., 1.0.0)")
    display_name: str = Field(..., description="Display title for Agent Registry catalog")
    description: str = Field(..., description="High-level description of this agent version")
    model: str = Field(..., description="Foundation model family (e.g. gemini-2.5-pro)")
    model_version: str = Field(
        ..., description="Pinned Vertex AI model version (e.g. gemini-2.5-pro@001)"
    )
    prompt_version: str = Field(..., description="System prompt template version identifier")
    system_instruction: str = Field(
        ..., description="Complete system prompt instruction for this release"
    )
    skills: list[AgentSkill] = Field(default_factory=list, description="Declared capabilities")
    is_default: bool = Field(
        default=False, description="Whether this version is the production default"
    )
    changelog: str = Field(default="", description="Summary of changes in this release")
    created_at: str = Field(
        default="2026-03-01T00:00:00Z", description="ISO 8601 release timestamp"
    )


class A2ASupportedInterface(BaseModel):
    """Network interface and protocol binding for agent invocation."""

    url: str
    protocol_binding: str = Field(default="HTTP+JSON", alias="protocolBinding")
    protocol_version: str = Field(default="1.0.0", alias="protocolVersion")

    model_config = {"populate_by_name": True}


class A2ACapabilities(BaseModel):
    """Declared capabilities under Agent2Agent (A2A) specification."""

    streaming: bool = False
    push_notifications: bool = Field(default=False, alias="pushNotifications")

    model_config = {"populate_by_name": True}


class AgentCard(BaseModel):
    """Standard Agent-to-Agent (A2A) Agent Card metadata object."""

    name: str
    description: str
    version: str
    capabilities: A2ACapabilities = Field(default_factory=A2ACapabilities)
    default_input_modes: list[str] = Field(
        default_factory=lambda: ["text/plain", "application/json"], alias="defaultInputModes"
    )
    default_output_modes: list[str] = Field(
        default_factory=lambda: ["application/json"], alias="defaultOutputModes"
    )
    supported_interfaces: list[A2ASupportedInterface] = Field(
        default_factory=list, alias="supportedInterfaces"
    )
    skills: list[AgentSkill] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class AgentRegistry:
    """Central registry and fleet catalog for AI Agent versions and A2A Agent Cards."""

    def __init__(self) -> None:
        self._versions: dict[str, AgentVersionSpec] = {}
        self._default_version: str = getattr(settings, "agent_version", "1.0.0")
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register the built-in production baseline and candidate versions."""
        # Core shared skills
        skill_compare = AgentSkill(
            id="spec-comparison",
            name="SpecComparison",
            description="Performs grounded side-by-side feature comparison with verifiable Best Buy SKU citations",
            tags=["comparison", "electronics", "grounding", "bigquery"],
        )
        skill_intent = AgentSkill(
            id="intent-classification",
            name="IntentClassification",
            description="Analyzes customer query intent (comparison, product search, or conversational chatter)",
            tags=["intent", "classification", "safety"],
        )
        skill_retrieval = AgentSkill(
            id="catalog-retrieval",
            name="CatalogRetrieval",
            description="Queries live BigQuery catalog with keyword extraction and schema validation",
            tags=["tools", "bigquery", "catalog"],
        )

        # 1. Version 1.0.0: Production Baseline (Gemini 2.5 Pro)
        v1_spec = AgentVersionSpec(
            version="1.0.0",
            display_name="Best Buy Catalog Comparison Agent (Stable Baseline)",
            description="Production comparison assistant grounded strictly in Google Cloud BigQuery catalog",
            model=getattr(settings, "gemini_model", "gemini-2.5-pro"),
            model_version=getattr(settings, "model_version", "gemini-2.5-pro@001"),
            prompt_version=getattr(settings, "prompt_version", "2026.03-v1"),
            system_instruction=SYSTEM_INSTRUCTION,
            skills=[skill_compare, skill_intent, skill_retrieval],
            is_default=True,
            changelog="Initial production release with zero-hallucination spec grounding and SKU citations.",
            created_at="2026-03-01T00:00:00Z",
        )
        self.register(v1_spec)

        # 2. Version 1.1.0-flash: High-Throughput Canary Candidate (Gemini 2.5 Flash)
        flash_instruction = (
            SYSTEM_INSTRUCTION + "\n\n6. HIGH-THROUGHPUT CONCISE SYNTHESIS:\n"
            "   - Prioritize concise, high-signal comparisons to optimize customer decision speed.\n"
            "   - Lead with decisive trade-off bullets before the side-by-side matrix."
        )
        skill_fast_synthesis = AgentSkill(
            id="fast-tradeoff-synthesis",
            name="FastTradeoffSynthesis",
            description="Generates concise decision summaries in <1.5s using Gemini 2.5 Flash",
            tags=["latency", "synthesis", "gemini-flash"],
        )
        v1_1_flash = AgentVersionSpec(
            version="1.1.0-flash",
            display_name="Best Buy Catalog Comparison Agent (Flash Canary)",
            description="High-throughput canary variant powered by Gemini 2.5 Flash for sub-second comparison synthesis",
            model="gemini-2.5-flash",
            model_version="gemini-2.5-flash@001",
            prompt_version="2026.03-v2",
            system_instruction=flash_instruction,
            skills=[skill_compare, skill_intent, skill_retrieval, skill_fast_synthesis],
            is_default=False,
            changelog="Switched foundational model to Gemini 2.5 Flash with concise trade-off prompt guidelines.",
            created_at="2026-03-15T00:00:00Z",
        )
        self.register(v1_1_flash)

    def register(self, spec: AgentVersionSpec) -> None:
        """Register a new immutable agent version specification."""
        self._versions[spec.version] = spec
        if spec.is_default:
            self._default_version = spec.version
        logger.info(
            "Registered Agent Version '%s' (model=%s, prompt=%s, default=%s)",
            spec.version,
            spec.model_version,
            spec.prompt_version,
            spec.is_default,
        )

    def get_version(self, version_id: str | None = None) -> AgentVersionSpec:
        """Resolve an agent version by ID, falling back to active production default."""
        if version_id and version_id in self._versions:
            return self._versions[version_id]

        if version_id and version_id not in self._versions:
            logger.warning(
                "Requested Agent Version '%s' not found in Agent Registry. Falling back to default '%s'.",
                version_id,
                self._default_version,
            )

        return self._versions.get(self._default_version) or next(iter(self._versions.values()))

    def list_versions(self) -> list[dict[str, Any]]:
        """List summaries of all registered agent versions."""
        results = []
        for v in self._versions.values():
            results.append(
                {
                    "version": v.version,
                    "display_name": v.display_name,
                    "description": v.description,
                    "model": v.model,
                    "model_version": v.model_version,
                    "prompt_version": v.prompt_version,
                    "is_default": v.version == self._default_version,
                    "skills_count": len(v.skills),
                    "created_at": v.created_at,
                    "changelog": v.changelog,
                }
            )
        return results

    def generate_agent_card(
        self,
        base_url: str = "",
        version_id: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Generate a Google Cloud & A2A standard Agent Card for the resolved version."""
        target_version = version or version_id
        spec = self.get_version(target_version)
        effective_base = (
            base_url.rstrip("/")
            if base_url
            else "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app"
        )
        compare_url = f"{effective_base}/api/compare"

        card = AgentCard(
            name="bestbuy-catalog-comparison-agent",
            description=spec.description,
            version=spec.version,
            capabilities=A2ACapabilities(streaming=False, push_notifications=False),
            default_input_modes=["text/plain", "application/json"],
            default_output_modes=["application/json"],
            supported_interfaces=[
                A2ASupportedInterface(
                    url=compare_url,
                    protocol_binding="HTTP+JSON",
                    protocol_version="1.0.0",
                )
            ],
            skills=spec.skills,
            metadata={
                "model": spec.model,
                "model_version": spec.model_version,
                "prompt_version": spec.prompt_version,
                "framework": "google-adk",
                "managed_by": "terraform",
                "is_default": spec.version == self._default_version,
                "cloud_run_service": "catalog-comparison-service",
            },
        )
        return card.model_dump(by_alias=True)


# Singleton instance
_registry_instance: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Provide singleton AgentRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = AgentRegistry()
    return _registry_instance
