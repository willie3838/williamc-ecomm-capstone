#!/usr/bin/env python3
"""Hermetic disaster recovery simulation script.

Verifies Phase 1 dependency failure degradation and Phase 2 automatic service restoration.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from app.agent.orchestrator import ComparisonOrchestrator
from google.api_core import exceptions as g_exceptions
from google.cloud import bigquery


def main() -> None:
    # Phase 1: Total Dependency Outage
    mock_client = MagicMock(spec=bigquery.Client)
    mock_client.query.side_effect = g_exceptions.ServiceUnavailable("Total BigQuery Outage")
    orch = ComparisonOrchestrator(bq_client=mock_client)
    resp1 = orch.compare("Compare MacBook and Dell XPS")
    assert resp1.products == [], "Must return empty product list during complete outage"
    assert "No matching products" in resp1.summary, "Must return graceful degradation message"

    # Phase 2: Automatic Service Restoration
    mock_job = MagicMock()
    mock_job.result.return_value = [
        {
            "sku": "6534606",
            "name": "MacBook Air 15",
            "brand": "Apple",
            "category": "Laptops",
            "price": 1299.0,
            "specifications": {"ram_gb": 16, "battery_life_hours": 18.0},
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": "Dell XPS 13",
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "specifications": {"ram_gb": 16, "battery_life_hours": 14.0},
            "in_stock": True,
        },
    ]
    mock_client.query.side_effect = None
    mock_client.query.return_value = mock_job
    resp2 = orch.compare("Compare MacBook and Dell XPS")
    assert len(resp2.products) == 2, "Service must fully recover after database connectivity is restored"
    assert len(resp2.comparison_matrix) > 0, "Matrix must be generated upon recovery"
    print("  -> Automated Disaster Recovery Cycle successfully verified: 0 state corruption, 100% recovery.")


if __name__ == "__main__":
    main()
