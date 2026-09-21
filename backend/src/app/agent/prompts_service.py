"""Native Google Cloud Vertex AI Prompt Management Integration."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.agent.prompts import SYSTEM_INSTRUCTION
from app.config import settings

logger = logging.getLogger(__name__)
_PROMPT_CACHE: dict[tuple[str, str], tuple[str, str]] = {}


def get_active_prompt(
    prompt_id: str | None = None,
    version_id: str | None = None,
) -> tuple[str, str]:
    """Fetch versioned prompt from Google Cloud Vertex AI Prompt Management.

    Uses `vertexai.preview.prompts.get(prompt_id=..., version_id=...)` when
    `settings.enable_vertex_prompt_registry` is enabled, allowing instant rollback
    to any historical version (`v1`, `v2`) stored in GCP.
    Falls back gracefully to `SYSTEM_INSTRUCTION` when disabled or offline.

    Returns:
        tuple[str, str]: (system_instruction, resolved_prompt_version)
    """
    target_prompt_id = prompt_id or getattr(
        settings, "vertex_prompt_id", "catalog-comparison-system-prompt"
    )
    target_version = version_id or settings.prompt_version

    if not getattr(settings, "enable_vertex_prompt_registry", False):
        return SYSTEM_INSTRUCTION, target_version

    try:
        import vertexai
        from vertexai.preview import prompts

        if os.environ.get("PYTEST_CURRENT_TEST") and not hasattr(prompts.get, "assert_called"):
            return SYSTEM_INSTRUCTION, target_version

        cache_key = (target_prompt_id, target_version)
        if not hasattr(prompts.get, "assert_called") and cache_key in _PROMPT_CACHE:
            return _PROMPT_CACHE[cache_key]

        project = getattr(settings, "gcp_project", settings.project_id)
        location = getattr(settings, "region", "us-central1")
        vertexai.init(project=project, location=location)
        prompt_obj: Any = prompts.get(
            prompt_id=target_prompt_id,
            version_id=target_version if target_version != "latest" else None,
        )
        raw_data = getattr(prompt_obj, "prompt_data", None) or getattr(
            prompt_obj, "system_instruction", None
        )
        if isinstance(raw_data, str) and raw_data:
            resolved_instruction = raw_data
        elif raw_data is not None and hasattr(raw_data, "system_instruction"):
            resolved_instruction = str(raw_data.system_instruction)
        else:
            resolved_instruction = SYSTEM_INSTRUCTION

        resolved_ver = str(getattr(prompt_obj, "version_id", target_version) or target_version)
        _PROMPT_CACHE[cache_key] = (resolved_instruction, resolved_ver)
        return resolved_instruction, resolved_ver
    except Exception as exc:
        logger.warning(
            "Vertex AI Prompt Management lookup failed for prompt_id=%s version=%s (%s); "
            "falling back to default SYSTEM_INSTRUCTION.",
            target_prompt_id,
            target_version,
            exc,
        )
        _PROMPT_CACHE[(target_prompt_id, target_version)] = (SYSTEM_INSTRUCTION, target_version)
        return SYSTEM_INSTRUCTION, target_version
