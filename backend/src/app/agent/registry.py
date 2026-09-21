"""Agent Registry for versioned prompt, system instruction, and model governance."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.prompts import SYSTEM_INSTRUCTION
from app.agent.prompts_service import get_active_prompt


@dataclass(frozen=True)
class AgentVersionSpec:
    """Specification for a registered agent version."""

    version: str
    display_name: str
    model: str
    model_version: str
    prompt_version: str
    system_instruction: str
    is_default: bool = False


class AgentRegistry:
    """Registry managing versioned agent definitions and Vertex AI Prompt Management bindings."""

    def __init__(self) -> None:
        self._versions: dict[str, AgentVersionSpec] = {
            "1.0.0": AgentVersionSpec(
                version="1.0.0",
                display_name="Best Buy Catalog Comparison Agent (Baseline Pro)",
                model="gemini-2.5-pro",
                model_version="gemini-2.5-pro@001",
                prompt_version="2026.03-v1",
                system_instruction=SYSTEM_INSTRUCTION,
                is_default=True,
            ),
            "1.1.0-flash": AgentVersionSpec(
                version="1.1.0-flash",
                display_name="Best Buy Catalog Comparison Agent (Flash Canary)",
                model="gemini-2.5-flash",
                model_version="gemini-2.5-flash@001",
                prompt_version="2026.03-v2",
                system_instruction=SYSTEM_INSTRUCTION,
                is_default=False,
            ),
            "1.2.0-tiered": AgentVersionSpec(
                version="1.2.0-tiered",
                display_name="Best Buy Catalog Comparison Agent (Tiered Hybrid)",
                model="tiered-hybrid",
                model_version="tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001",
                prompt_version="2026.03-v2",
                system_instruction=SYSTEM_INSTRUCTION,
                is_default=False,
            ),
        }

    def get_version(self, version: str | None = None) -> AgentVersionSpec | None:
        """Look up registered agent version specification and resolve active prompt."""
        target = version or "1.0.0"
        spec = self._versions.get(target)
        if spec is None:
            return None
        prompt_text, resolved_prompt_ver = get_active_prompt(version_id=spec.prompt_version)
        return AgentVersionSpec(
            version=spec.version,
            display_name=spec.display_name,
            model=spec.model,
            model_version=spec.model_version,
            prompt_version=resolved_prompt_ver,
            system_instruction=prompt_text,
            is_default=spec.is_default,
        )

    def list_versions(self) -> list[AgentVersionSpec]:
        """Return all registered agent version specifications."""
        return list(self._versions.values())


default_registry = AgentRegistry()
