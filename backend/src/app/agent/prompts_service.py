"""Native Google Cloud Vertex AI Prompt Management Integration.

Manages versioned prompt templates across all 5 pipeline stages in Google Cloud
Vertex AI Prompt Management. Strictly decoupled from model selection (which is
governed by environment variables and runtime failover).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.prompts import PROMPT_CATALOG, SYSTEM_INSTRUCTION
from app.config import settings

logger = logging.getLogger(__name__)

# Cache mapping (prompt_id, version_id) -> (resolved_prompt_text, resolved_version_id)
_PROMPT_CACHE: dict[tuple[str, str], tuple[str, str]] = {}
_PROMPT_CACHE_TIMESTAMPS: dict[tuple[str, str], float] = {}
_NAME_TO_PROMPT_ID_CACHE: dict[str, str] = {}

_STAGE_CONFIG_MAP: dict[str, tuple[str, str, str]] = {
    "system": (
        "catalog-comparison-system-prompt",
        "vertex_prompt_id",
        "system_prompt_version",
    ),
    "catalog-comparison-system-prompt": (
        "catalog-comparison-system-prompt",
        "vertex_prompt_id",
        "system_prompt_version",
    ),
    "stage1": (
        "stage1-query-intent-prompt",
        "stage1_prompt_id",
        "stage1_prompt_version",
    ),
    "stage1-query-intent-prompt": (
        "stage1-query-intent-prompt",
        "stage1_prompt_id",
        "stage1_prompt_version",
    ),
    "stage3": (
        "stage3-relevance-rerank-prompt",
        "stage3_prompt_id",
        "stage3_prompt_version",
    ),
    "stage3-relevance-rerank-prompt": (
        "stage3-relevance-rerank-prompt",
        "stage3_prompt_id",
        "stage3_prompt_version",
    ),
    "stage4": (
        "stage4-spec-synthesis-prompt",
        "stage4_prompt_id",
        "stage4_prompt_version",
    ),
    "stage4-spec-synthesis-prompt": (
        "stage4-spec-synthesis-prompt",
        "stage4_prompt_id",
        "stage4_prompt_version",
    ),
    "chat": (
        "multi-turn-followup-chat-prompt",
        "chat_prompt_id",
        "chat_prompt_version",
    ),
    "multi-turn-followup-chat-prompt": (
        "multi-turn-followup-chat-prompt",
        "chat_prompt_id",
        "chat_prompt_version",
    ),
}


def clear_prompt_cache() -> None:
    """Clear in-memory prompt and ID resolution caches."""
    _PROMPT_CACHE.clear()
    _PROMPT_CACHE_TIMESTAMPS.clear()
    _NAME_TO_PROMPT_ID_CACHE.clear()


def _is_dynamic_latest_version(version_str: str) -> bool:
    """Return True if version_str refers to the mutable 'latest' head rather than a pinned version ID."""
    return version_str.strip().lower() == "latest"


def _default_fallback_for_prompt(prompt_id_or_name: str) -> str:
    """Return the local fallback prompt text for a given prompt identifier or name."""
    if prompt_id_or_name in PROMPT_CATALOG:
        return PROMPT_CATALOG[prompt_id_or_name]
    for canonical_name, id_attr, _ in _STAGE_CONFIG_MAP.values():
        configured_id = getattr(settings, id_attr, "")
        if prompt_id_or_name == configured_id:
            return PROMPT_CATALOG.get(canonical_name, SYSTEM_INSTRUCTION)
    return SYSTEM_INSTRUCTION


def get_stage_prompt(
    stage_or_prompt_name: str,
    version_id: str | None = None,
) -> tuple[str, str]:
    """Fetch versioned prompt template for a specific pipeline stage ('system', 'stage1', 'stage3', 'stage4', 'chat').

    Resolution order for version:
    1. Explicit `version_id` parameter if passed
    2. Stage-specific env var (`SYSTEM_PROMPT_VERSION`, `STAGE1_PROMPT_VERSION`, `STAGE3_PROMPT_VERSION`, `STAGE4_PROMPT_VERSION`, `CHAT_PROMPT_VERSION`)
    3. Global `PROMPT_VERSION` setting (`settings.prompt_version`)
    """
    canonical_name, id_attr, ver_attr = _STAGE_CONFIG_MAP.get(
        stage_or_prompt_name,
        (stage_or_prompt_name, "vertex_prompt_id", "system_prompt_version"),
    )
    target_prompt_id = getattr(settings, id_attr, canonical_name) or canonical_name
    stage_ver_override = getattr(settings, ver_attr, None)
    effective_version = version_id or stage_ver_override or settings.prompt_version
    return get_active_prompt(prompt_id=target_prompt_id, version_id=effective_version)


def get_active_prompt(
    prompt_id: str | None = None,
    version_id: str | None = None,
) -> tuple[str, str]:
    """Fetch versioned prompt from Google Cloud Vertex AI Prompt Management.

    Uses `vertexai.preview.prompts.get(prompt_id=..., version_id=...)` when
    `settings.enable_vertex_prompt_registry` is enabled, allowing instant rollback
    to any historical version (`1`, `2`, ...) stored in GCP or live 60s TTL refresh
    when `version_id="latest"`.
    Falls back gracefully to the local prompt catalog when disabled or offline.

    Returns:
        tuple[str, str]: (prompt_text, resolved_prompt_version)
    """
    target_prompt_id = prompt_id or getattr(
        settings, "vertex_prompt_id", "catalog-comparison-system-prompt"
    )
    stage_override = getattr(settings, "system_prompt_version", None) if prompt_id is None else None
    target_version = version_id or stage_override or settings.prompt_version
    fallback_text = _default_fallback_for_prompt(target_prompt_id)

    if not getattr(settings, "enable_vertex_prompt_registry", False):
        return fallback_text, target_version

    try:
        import vertexai
        from vertexai.preview import prompts

        cache_key = (target_prompt_id, target_version)
        now = time.monotonic()
        ttl_seconds = float(getattr(settings, "prompt_cache_ttl_seconds", 60))

        if cache_key in _PROMPT_CACHE:
            if not _is_dynamic_latest_version(target_version):
                # Pinned immutable version ('1', '2', etc.) never changes; serve from cache permanently
                return _PROMPT_CACHE[cache_key]
            cached_at = _PROMPT_CACHE_TIMESTAMPS.get(cache_key, 0.0)
            if (now - cached_at) < ttl_seconds:
                return _PROMPT_CACHE[cache_key]

        project = getattr(settings, "gcp_project", settings.project_id)
        location = getattr(settings, "region", "us-central1")
        vertexai.init(project=project, location=location)

        resolved_gcp_prompt_id = _NAME_TO_PROMPT_ID_CACHE.get(target_prompt_id, target_prompt_id)
        prompt_obj: Any = prompts.get(
            prompt_id=resolved_gcp_prompt_id,
            version_id=target_version if not _is_dynamic_latest_version(target_version) else None,
        )
        raw_data = getattr(prompt_obj, "prompt_data", None) or getattr(
            prompt_obj, "system_instruction", None
        )
        if isinstance(raw_data, str) and raw_data:
            resolved_instruction = raw_data
        elif raw_data is not None and hasattr(raw_data, "system_instruction"):
            resolved_instruction = str(raw_data.system_instruction)
        else:
            resolved_instruction = fallback_text

        resolved_ver = str(getattr(prompt_obj, "version_id", None) or target_version)
        _PROMPT_CACHE[cache_key] = (resolved_instruction, resolved_ver)
        _PROMPT_CACHE_TIMESTAMPS[cache_key] = now
        return resolved_instruction, resolved_ver
    except Exception as exc:
        logger.warning(
            "Vertex AI Prompt Management lookup failed for prompt_id=%s version=%s (%s); "
            "falling back to local prompt template.",
            target_prompt_id,
            target_version,
            exc,
        )
        _PROMPT_CACHE[(target_prompt_id, target_version)] = (fallback_text, target_version)
        _PROMPT_CACHE_TIMESTAMPS[(target_prompt_id, target_version)] = time.monotonic()
        return fallback_text, target_version
