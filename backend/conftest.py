import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure hermetic test execution without attempting remote cloud trace exports
os.environ.setdefault("EXPORT_TRACES_TO_CLOUD", "false")


@pytest.fixture(autouse=True)
def _isolate_task2_singletons(monkeypatch: pytest.MonkeyPatch):
    """Reset module-level caches and default cloud runtime flags before and after each test."""
    from app.agent import prompts_service
    from app.config import settings
    from app.data.analytics import analytics_service
    from app.routes import compare as compare_routes
    from app.tools import catalog

    monkeypatch.setattr(settings, "agent_runtime_resource_name", None, raising=False)
    monkeypatch.setattr(analytics_service, "_disable_cloud_clients", True, raising=False)

    def _clear_caches() -> None:
        catalog._SHARED_BQ_CLIENT = None
        if hasattr(catalog, "_SHARED_BQ_CLIENT_CLS"):
            catalog._SHARED_BQ_CLIENT_CLS = None
        compare_routes._COORDINATOR_CACHE.clear()
        prompts_service.clear_prompt_cache()

    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def mock_bq_client():
    """Fixture providing a mocked BigQuery client with standard test data."""
    with patch("google.cloud.bigquery.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


def pytest_addoption(parser):
    """Add custom CLI options to pytest."""
    parser.addoption(
        "--no-doc",
        action="store_true",
        default=False,
        help="Explicitly bypass documentation synchronization requirement.",
    )
