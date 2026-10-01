import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure hermetic test execution without attempting remote cloud trace exports
os.environ.setdefault("EXPORT_TRACES_TO_CLOUD", "false")


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
