"""Pytest configuration and global fixtures for backend tests."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_bq_client():
    """Fixture providing a mocked BigQuery client with standard test data."""
    with patch("google.cloud.bigquery.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance
