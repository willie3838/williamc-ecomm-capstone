"""Seed and synchronize all 5 stage prompts in Vertex AI Prompt Management and Google Cloud Agent Registry.

Idempotent & Diff-Aware Governance:
- Manages all 5 pipeline prompts defined in `app.agent.prompts.PROMPT_CATALOG`:
  1. `catalog-comparison-system-prompt`
  2. `stage1-query-intent-prompt`
  3. `stage3-relevance-rerank-prompt`
  4. `stage4-spec-synthesis-prompt`
  5. `multi-turn-followup-chat-prompt`
- Looks up existing prompt resources by `prompt_name` (never creates duplicate Prompt resources).
- Compares local prompt text against the latest version stored in GCP and ONLY creates a new
  version (`v2`, `v3`, ...) when the prompt text has actually changed.
- Decouples Prompt Management from model selection (runtime models are controlled via env vars).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from typing import Any

import vertexai
from vertexai.preview import prompts

from app.agent.agent_card import build_a2a_agent_card
from app.agent.prompts import PROMPT_CATALOG, SYSTEM_INSTRUCTION
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _extract_prompt_text(prompt_obj: Any) -> str:
    """Extract normalized prompt text from a Vertex AI Prompt object."""
    raw_data = getattr(prompt_obj, "prompt_data", None) or getattr(
        prompt_obj, "system_instruction", None
    )
    if isinstance(raw_data, str):
        return raw_data.strip()
    if raw_data is not None and hasattr(raw_data, "system_instruction"):
        return str(raw_data.system_instruction).strip()
    return ""


def _get_latest_version_id(prompt_id: str) -> str:
    """Return the latest version_id string for a given prompt_id in GCP."""
    try:
        versions = list(prompts.list_versions(prompt_id=prompt_id))
        if versions:
            return str(getattr(versions[-1], "version_id", "1"))
    except Exception:
        pass
    return "1"


def seed_prompts(reset_existing: bool = False) -> dict[str, str]:
    """Synchronize all 5 pipeline prompts in Vertex AI Prompt Management idempotently.

    Args:
        reset_existing: If True, deletes existing prompts with matching names first
            to perform a clean Version 1 baseline across all 5 prompts.

    Returns:
        dict[str, str]: Mapping of prompt_name -> GCP prompt_id.
    """
    os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
    os.environ.pop("CLOUDSDK_CONTEXT_AWARE_CERTIFICATE_CONFIG_FILE_PATH", None)
    os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

    logger.info("Initializing Vertex AI in %s (%s)...", settings.project_id, settings.region)
    vertexai.init(project=settings.project_id, location=settings.region)

    existing_list = list(prompts.list())
    by_name: dict[str, list[str]] = {}
    for item in existing_list:
        p_id = str(getattr(item, "prompt_id", "") or "")
        p_name = str(getattr(item, "prompt_name", None) or getattr(item, "display_name", "") or "")
        if p_id and p_name:
            by_name.setdefault(p_name, []).append(p_id)

    # Prune duplicate prompt resources or reset if requested
    canonical_ids: dict[str, str] = {}
    for p_name, id_list in by_name.items():
        if p_name not in PROMPT_CATALOG:
            continue
        if reset_existing:
            for dup_id in id_list:
                logger.info("Deleting legacy prompt resource %s (%s)...", dup_id, p_name)
                prompts.delete(prompt_id=dup_id)
        else:
            # Keep the first (canonical) prompt resource and delete any accidental duplicates
            canonical_ids[p_name] = id_list[0]
            for dup_id in id_list[1:]:
                logger.info("Pruning duplicate prompt resource %s for '%s'...", dup_id, p_name)
                prompts.delete(prompt_id=dup_id)

    resolved_prompt_ids: dict[str, str] = {}
    # Note: Vertex AI's Prompt protobuf requires a nominal model_name field at storage time;
    # runtime model execution is 100% decoupled and controlled via STAGE*_MODEL env vars.
    nominal_schema_model = settings.gemini_model

    for prompt_name, prompt_text in PROMPT_CATALOG.items():
        desired_text = prompt_text.strip()
        existing_id = canonical_ids.get(prompt_name)

        if existing_id:
            try:
                latest_obj = prompts.get(prompt_id=existing_id)
                current_gcp_text = _extract_prompt_text(latest_obj)
                latest_ver = _get_latest_version_id(existing_id)
                if current_gcp_text == desired_text:
                    logger.info(
                        "Prompt '%s' (ID: %s) is up to date at version %s — skipping version creation.",
                        prompt_name,
                        existing_id,
                        latest_ver,
                    )
                    resolved_prompt_ids[prompt_name] = existing_id
                    continue
                logger.info(
                    "Prompt '%s' (ID: %s) text changed vs version %s — creating new version...",
                    prompt_name,
                    existing_id,
                    latest_ver,
                )
                updated_prompt = prompts.Prompt(
                    prompt_name=prompt_name,
                    prompt_data=desired_text,
                    system_instruction=SYSTEM_INSTRUCTION,
                    model_name=nominal_schema_model,
                )
                new_ver_obj = prompts.create_version(updated_prompt, prompt_id=existing_id)
                new_ver_id = getattr(new_ver_obj, "version_id", None) or _get_latest_version_id(
                    existing_id
                )
                logger.info(
                    "Created new version %s for prompt '%s' (ID: %s)",
                    new_ver_id,
                    prompt_name,
                    existing_id,
                )
                resolved_prompt_ids[prompt_name] = existing_id
                continue
            except Exception as exc:
                logger.warning(
                    "Could not inspect existing prompt %s (%s); creating fresh resource...",
                    existing_id,
                    exc,
                )

        # Create initial Version 1 for this prompt
        new_prompt = prompts.Prompt(
            prompt_name=prompt_name,
            prompt_data=desired_text,
            system_instruction=SYSTEM_INSTRUCTION,
            model_name=nominal_schema_model,
        )
        v1_obj = prompts.create_version(new_prompt)
        created_id = str(getattr(v1_obj, "prompt_id", None) or getattr(v1_obj, "id", ""))
        created_ver = str(getattr(v1_obj, "version_id", None) or "1")
        logger.info(
            "Created prompt '%s' (ID: %s, Initial Version: %s)",
            prompt_name,
            created_id,
            created_ver,
        )
        resolved_prompt_ids[prompt_name] = created_id

    return resolved_prompt_ids


def sync_agent_registry() -> None:
    """Register or update the Cloud Run service in Google Cloud Agent Registry."""
    cloud_run_url = "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app"
    card = build_a2a_agent_card(cloud_run_url)
    temp_card_path = "/tmp/agent-card.json"
    with open(temp_card_path, "w") as f:
        json.dump(card, f)

    service_id = "bestbuy-catalog-comparison-agent"
    logger.info("Registering/Updating service %s in Agent Registry...", service_id)

    cmd = [
        "gcloud",
        "agent-registry",
        "services",
        "update",
        service_id,
        f"--project={settings.project_id}",
        f"--location={settings.region}",
        "--display-name=Best Buy Catalog Comparison Agent",
        "--description=Grounded product comparison agent using Google ADK, Gemini 2.5, Vertex AI Prompt Management, and BigQuery",
        "--agent-spec-type=a2a-agent-card",
        f"--agent-spec-content={temp_card_path}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        cmd[3] = "create"
        res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode == 0:
        logger.info("Agent Registry registration succeeded:\n%s", res.stdout)
    else:
        logger.warning("Agent Registry registration returned:\n%s\n%s", res.stdout, res.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synchronize Vertex AI Prompt Management and Agent Registry."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing duplicate/legacy prompts first and seed clean Version 1 prompts.",
    )
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Only synchronize Vertex AI Prompt Management (skip Agent Registry CLI call).",
    )
    args = parser.parse_args()
    ids = seed_prompts(reset_existing=args.reset)
    logger.info("Synchronized Prompt Resource IDs: %s", json.dumps(ids, indent=2))
    if not args.skip_registry:
        sync_agent_registry()
