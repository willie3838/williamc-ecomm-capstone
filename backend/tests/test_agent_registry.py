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


def test_all_five_stage_prompts_and_version_pinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify all 5 pipeline stage prompts resolve independently and support per-stage version pinning + TTL cache."""
    from app.agent.prompts import PROMPT_CATALOG
    from app.agent.prompts_service import clear_prompt_cache, get_stage_prompt

    clear_prompt_cache()
    assert len(PROMPT_CATALOG) == 5
    for stage_key in ("system", "stage1", "stage3", "stage4", "chat"):
        text, ver = get_stage_prompt(stage_key)
        assert len(text) > 50
        assert ver == settings.prompt_version

    # Verify per-stage version override (e.g. STAGE4_PROMPT_VERSION="1")
    monkeypatch.setattr(settings, "stage4_prompt_version", "1")
    _, stage4_ver = get_stage_prompt("stage4")
    assert stage4_ver == "1"

    # Verify 60s TTL refresh for 'latest' vs permanent cache for pinned version
    monkeypatch.setattr(settings, "enable_vertex_prompt_registry", True)
    monkeypatch.setattr(settings, "prompt_cache_ttl_seconds", 60)
    clear_prompt_cache()

    mock_obj = MagicMock()
    mock_obj.prompt_data = "Pinned Stage 4 Template v1"
    mock_obj.version_id = "1"
    with (
        patch("vertexai.init"),
        patch("vertexai.preview.prompts.get", return_value=mock_obj) as mock_get,
    ):
        t1, v1 = get_stage_prompt("stage4")
        t2, v2 = get_stage_prompt("stage4")
        assert t1 == "Pinned Stage 4 Template v1"
        assert v1 == "1"
        assert (t1, v1) == (t2, v2)
        # Pinned version '1' is cached permanently on second call
        assert mock_get.call_count == 1
    clear_prompt_cache()


def test_build_a2a_agent_card_default() -> None:
    """Verify stateless A2A Agent Card generation for Google Cloud Agent Registry."""
    card = build_a2a_agent_card(base_url="https://catalog-comparison-service.a.run.app")
    assert card["name"] == "techbuy-catalog-comparison-agent"
    assert card["version"] == "1.2.0-tiered"
    assert card["supportedInterfaces"][0]["protocolBinding"] == "HTTP+JSON"
    assert (
        card["supportedInterfaces"][0]["url"]
        == "https://catalog-comparison-service.a.run.app/api/compare"
    )
    assert len(card["skills"]) >= 2
    assert card["metadata"]["model_version"] == "tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001"
    assert card["metadata"]["gcp_agent_registry"] == "agentregistry.googleapis.com"


def test_build_a2a_agent_card_baseline_pro() -> None:
    """Verify stateless A2A Agent Card generation for baseline pro variant."""
    card = build_a2a_agent_card(
        base_url="https://catalog-comparison-service.a.run.app",
        version="1.0.0",
    )
    assert card["version"] == "1.0.0"
    assert card["metadata"]["model_version"] == "gemini-2.5-pro@001"


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
    assert data["active_default"] == "1.2.0-tiered"
    version_ids = [v["version"] for v in data["versions"]]
    assert "1.0.0" in version_ids
    assert "1.1.0-flash" in version_ids
    assert "1.2.0-tiered" in version_ids


def test_compare_with_default_agent_version(client: TestClient) -> None:
    """Verify POST /api/compare defaults to active agent version 1.2.0-tiered."""
    resp = client.post(
        "/api/compare",
        json={"query": "Apple MacBook Air M3 vs Dell XPS 13"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_version"] == "1.2.0-tiered"
    assert "tiered-hybrid" in data["model_version"]
    assert data["prompt_version"] == "2026.03-v2"


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


def test_prompts_service_no_test_detection_branches() -> None:
    """Verify prompts_service.py contains zero PYTEST_CURRENT_TEST or assert_called branches."""
    from pathlib import Path

    import app.agent.prompts_service as ps_mod

    src = Path(ps_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("PYTEST_CURRENT_TEST", "assert_called", "pytest", '"Mock"'):
        assert forbidden not in src, f"Forbidden token {forbidden!r} found in prompts_service.py"
