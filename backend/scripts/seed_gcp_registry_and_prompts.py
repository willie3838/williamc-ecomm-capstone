"""Seed Vertex AI Prompt Management and Google Cloud Agent Registry in GCP."""

from __future__ import annotations

import json
import logging
import subprocess

import vertexai
from vertexai.preview import prompts

from app.agent.agent_card import build_a2a_agent_card
from app.agent.prompts import SYSTEM_INSTRUCTION
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_prompts() -> str:
    """Create versioned system instructions in Vertex AI Prompt Management."""
    logger.info("Initializing Vertex AI in %s (%s)...", settings.project_id, settings.region)
    vertexai.init(project=settings.project_id, location=settings.region)

    # Version 1 (Baseline Pro)
    p1 = prompts.Prompt(
        prompt_data="Compare products side-by-side using strictly grounded BigQuery catalog specifications.",
        prompt_name="catalog-comparison-system-prompt",
        system_instruction=SYSTEM_INSTRUCTION,
        model_name="gemini-2.5-pro",
    )
    v1 = prompts.create_version(p1)
    prompt_resource_id = getattr(v1, "prompt_id", None) or getattr(v1, "id", None)
    logger.info(
        "Created Vertex AI Prompt Version 1 (ID: %s, Version: %s)",
        prompt_resource_id,
        getattr(v1, "version_id", "v1"),
    )

    # Version 2 (Canary Flash)
    p2 = prompts.Prompt(
        prompt_data="Compare products side-by-side using high-throughput Gemini 2.5 Flash and strict BigQuery grounding.",
        prompt_name="catalog-comparison-system-prompt",
        system_instruction=SYSTEM_INSTRUCTION + "\nRespond with ultra-concise synthesis.",
        model_name="gemini-2.5-flash",
    )
    v2 = prompts.create_version(p2, prompt_id=prompt_resource_id)
    logger.info(
        "Created Vertex AI Prompt Version 2 (ID: %s, Version: %s)",
        prompt_resource_id,
        getattr(v2, "version_id", "v2"),
    )

    return str(prompt_resource_id)


def sync_agent_registry() -> None:
    """Register or update the Cloud Run service in Google Cloud Agent Registry."""
    cloud_run_url = "https://catalog-comparison-service-499572810092.us-central1.run.app"
    card = build_a2a_agent_card(cloud_run_url, include_metadata=False)
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
        # If update fails (e.g. doesn't exist), try create
        cmd[3] = "create"
        res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode == 0:
        logger.info("Agent Registry registration succeeded:\n%s", res.stdout)
    else:
        logger.warning("Agent Registry registration returned:\n%s\n%s", res.stdout, res.stderr)


if __name__ == "__main__":
    seed_prompts()
    sync_agent_registry()
