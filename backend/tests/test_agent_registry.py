"""Unit and integration tests for Vertex AI Prompt Management & A2A Agent Card Discovery."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.agent_card import build_a2a_agent_card
from app.agent.prompts_service import get_active_prompt
from app.config import settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Provide a FastAPI TestClient."""
    app = create_app()
    return TestClient(app)


def test_get_active_prompt_default_fallback() -> None:
    """Verify get_active_prompt returns local SYSTEM_INSTRUCTION when registry disabled."""
    prompt_text, prompt_ver = get_active_prompt()
    assert "Best Buy Catalog Comparison Agent" in prompt_text or "SKU" in prompt_text
    assert prompt_ver == settings.prompt_version


def test_get_active_prompt_vertex_ai_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_active_prompt fetches prompt template from vertexai.preview.prompts when enabled."""
    monkeypatch.setattr(settings, "enable_vertex_prompt_registry", True)

    mock_prompt_obj = MagicMock()
    mock_prompt_obj.prompt_data = "Vertex AI Managed Grounding Instruction v99"
    mock_prompt_obj.version_id = "2026.04-v99"

    with (
        patch("vertexai.init") as mock_init,
        patch("vertexai.preview.prompts.get", return_value=mock_prompt_obj) as mock_get,
    ):
        prompt_text, prompt_ver = get_active_prompt(
            prompt_id="catalog-comparison-grounding",
            version_id="2026.04-v99",
        )
        mock_init.assert_called_once_with(project=settings.gcp_project, location="us-central1")
        mock_get.assert_called_once_with(
            prompt_id="catalog-comparison-grounding",
            version_id="2026.04-v99",
        )
        assert prompt_text == "Vertex AI Managed Grounding Instruction v99"
        assert prompt_ver == "2026.04-v99"


def test_get_active_prompt_vertex_ai_exception_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify get_active_prompt falls back gracefully if Vertex AI call raises an error."""
    monkeypatch.setattr(settings, "enable_vertex_prompt_registry", True)

    with (
        patch("vertexai.init"),
        patch("vertexai.preview.prompts.get", side_effect=RuntimeError("GCP network error")),
    ):
        prompt_text, prompt_ver = get_active_prompt(version_id="2026.03-v2")
        assert len(prompt_text) > 50
        assert prompt_ver == "2026.03-v2"


def test_build_a2a_agent_card_default() -> None:
    """Verify stateless A2A Agent Card generation for Google Cloud Agent Registry."""
    card = build_a2a_agent_card(base_url="https://catalog-comparison-service.a.run.app")
    assert card["name"] == "techbuy-catalog-comparison-agent"
    assert card["version"] == "1.0.0"
    assert card["supportedInterfaces"][0]["protocolBinding"] == "HTTP+JSON"
    assert (
        card["supportedInterfaces"][0]["url"]
        == "https://catalog-comparison-service.a.run.app/api/compare"
    )
    assert len(card["skills"]) >= 2
    assert card["metadata"]["model_version"] == "gemini-2.5-pro@001"
    assert card["metadata"]["gcp_agent_registry"] == "agentregistry.googleapis.com"


def test_build_a2a_agent_card_flash_variant() -> None:
    """Verify stateless A2A Agent Card generation for flash canary."""
    card = build_a2a_agent_card(
        base_url="https://catalog-comparison-service.a.run.app",
        version="1.1.0-flash",
    )
    assert card["version"] == "1.1.0-flash"
    assert card["metadata"]["model"] == "gemini-2.5-flash"
    assert card["metadata"]["model_version"] == "gemini-2.5-flash@001"
    assert card["metadata"]["prompt_version"] == "2026.03-v2"


def test_api_well_known_agent_card_endpoint(client: TestClient) -> None:
    """Verify /.well-known/agent-card.json returns valid A2A Agent Card."""
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "techbuy-catalog-comparison-agent"
    assert "supportedInterfaces" in data
    assert "skills" in data
    assert "metadata" in data


def test_api_agent_card_version_query(client: TestClient) -> None:
    """Verify /api/agent/card?version=1.1.0-flash returns versioned Agent Card."""
    resp = client.get("/api/agent/card?version=1.1.0-flash")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "1.1.0-flash"
    assert "flash" in data["metadata"]["model_version"]


def test_api_agent_versions_list_endpoint(client: TestClient) -> None:
    """Verify /api/agent/versions returns list of versions."""
    resp = client.get("/api/agent/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_default"] == "1.0.0"
    version_ids = [v["version"] for v in data["versions"]]
    assert "1.0.0" in version_ids
    assert "1.1.0-flash" in version_ids


def test_compare_with_default_agent_version(client: TestClient) -> None:
    """Verify POST /api/compare defaults to agent version 1.0.0."""
    resp = client.post(
        "/api/compare",
        json={"query": "Apple MacBook Air M3 vs Dell XPS 13"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_version"] == "1.0.0"
    assert "gemini-2.5-pro" in data["model_version"]
    assert data["prompt_version"] == "2026.03-v1"


def test_compare_with_canary_agent_version(client: TestClient) -> None:
    """Verify POST /api/compare resolves canary agent version 1.1.0-flash."""
    resp = client.post(
        "/api/compare",
        json={
            "query": "Apple MacBook Air M3 vs Dell XPS 13",
            "agent_version": "1.1.0-flash",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_version"] == "1.1.0-flash"
    assert "gemini-2.5-flash" in data["model_version"]
    assert data["prompt_version"] == "2026.03-v2"
