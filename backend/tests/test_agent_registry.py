"""Unit and integration tests for Google Cloud Agent Registry & A2A Versioning."""

import pytest
from fastapi.testclient import TestClient

from app.agent.registry import (
    AgentRegistry,
    AgentSkill,
    AgentVersionSpec,
    get_agent_registry,
)
from app.main import create_app


@pytest.fixture
def registry() -> AgentRegistry:
    """Provide a clean AgentRegistry instance."""
    return get_agent_registry()


@pytest.fixture
def client() -> TestClient:
    """Provide a FastAPI TestClient."""
    app = create_app()
    return TestClient(app)


def test_agent_registry_default_version(registry: AgentRegistry) -> None:
    """Verify registry returns default version 1.0.0 when no version specified."""
    version_spec = registry.get_version()
    assert version_spec.version == "1.0.0"
    assert "gemini-2.5-pro" in version_spec.model
    assert version_spec.prompt_version == "2026.03-v1"
    assert len(version_spec.skills) >= 2
    assert any(s.id == "spec-comparison" for s in version_spec.skills)


def test_agent_registry_get_flash_canary(registry: AgentRegistry) -> None:
    """Verify registry can resolve candidate 1.1.0-flash version."""
    version_spec = registry.get_version("1.1.0-flash")
    assert version_spec.version == "1.1.0-flash"
    assert "gemini-2.5-flash" in version_spec.model
    assert "flash" in version_spec.model_version


def test_agent_registry_unknown_fallback(registry: AgentRegistry) -> None:
    """Verify registry falls back to default version on unknown version identifier."""
    version_spec = registry.get_version("non-existent-version-99")
    assert version_spec.version == "1.0.0"
    assert "gemini-2.5-pro" in version_spec.model


def test_agent_registry_list_versions(registry: AgentRegistry) -> None:
    """Verify listing all registered versions returns summaries."""
    versions = registry.list_versions()
    assert len(versions) >= 2
    version_ids = [v["version"] for v in versions]
    assert "1.0.0" in version_ids
    assert "1.1.0-flash" in version_ids
    default_entry = next(v for v in versions if v["is_default"])
    assert default_entry["version"] == "1.0.0"


def test_agent_registry_generate_a2a_agent_card(registry: AgentRegistry) -> None:
    """Verify A2A compliant Agent Card generation."""
    card = registry.generate_agent_card(base_url="https://catalog-comparison-service.a.run.app")
    assert card["name"] == "bestbuy-catalog-comparison-agent"
    assert card["version"] == "1.0.0"
    assert "supportedInterfaces" in card
    assert len(card["supportedInterfaces"]) == 1
    assert card["supportedInterfaces"][0]["protocolBinding"] == "HTTP+JSON"
    assert (
        card["supportedInterfaces"][0]["url"]
        == "https://catalog-comparison-service.a.run.app/api/compare"
    )
    assert "skills" in card
    assert len(card["skills"]) >= 2
    assert "capabilities" in card
    assert "metadata" in card
    assert card["metadata"]["model_version"] == "gemini-2.5-pro@001"
    assert card["metadata"]["prompt_version"] == "2026.03-v1"


def test_agent_registry_register_custom_version(registry: AgentRegistry) -> None:
    """Verify dynamic registration of an experimental agent version."""
    custom_spec = AgentVersionSpec(
        version="2.0.0-experimental",
        display_name="Experimental Autonomous Agent",
        description="Experimental 2.0 version",
        model="gemini-2.5-pro",
        model_version="gemini-2.5-pro@002",
        prompt_version="2026.04-exp",
        system_instruction="You are an experimental assistant.",
        skills=[AgentSkill(id="exp-skill", name="ExpSkill", description="Exp description")],
        is_default=False,
        changelog="Added experimental planning features",
        created_at="2026-04-01T00:00:00Z",
    )
    registry.register(custom_spec)
    retrieved = registry.get_version("2.0.0-experimental")
    assert retrieved.version == "2.0.0-experimental"
    assert retrieved.prompt_version == "2026.04-exp"


def test_api_well_known_agent_card_endpoint(client: TestClient) -> None:
    """Verify /.well-known/agent-card.json returns valid A2A Agent Card."""
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "bestbuy-catalog-comparison-agent"
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
    """Verify /api/agent/versions returns list of registered versions."""
    resp = client.get("/api/agent/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert "active_default" in data
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
