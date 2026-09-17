"""Unit tests for Analytics, Insights & Feedback services and API endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.data.analytics import AnalyticsService
from app.main import create_app
from app.models.analytics import FeedbackRequest, UserActionRequest


def test_analytics_models():
    action = UserActionRequest(
        action_type="copy_markdown",
        session_id="sess-123",
        query="Compare MacBook and Dell",
        target_skus=["6534606", "6543210"],
    )
    assert action.action_type == "copy_markdown"
    assert action.session_id == "sess-123"
    assert len(action.target_skus) == 2

    feedback = FeedbackRequest(
        rating="thumbs_up",
        session_id="sess-123",
        query="Compare MacBook and Dell",
        target_skus=["6534606", "6543210"],
        trace_id="0123456789abcdef0123456789abcdef",
    )
    assert feedback.rating == "thumbs_up"
    assert feedback.trace_id == "0123456789abcdef0123456789abcdef"


def test_analytics_service_mocked_clients():
    mock_firestore = MagicMock()
    mock_collection = MagicMock()
    mock_doc = MagicMock()
    mock_doc.id = "doc-test-123"
    mock_collection.add.return_value = (None, mock_doc)
    mock_firestore.collection.return_value = mock_collection

    mock_bq = MagicMock()
    mock_bq.insert_rows_json.return_value = []

    service = AnalyticsService(firestore_client=mock_firestore, bq_client=mock_bq)

    # Test record_user_action
    action = UserActionRequest(
        action_type="copy_markdown",
        session_id="sess-test-1",
        query="MacBook vs Dell",
    )
    doc_id = service.record_user_action(action)
    assert doc_id == "doc-test-123"
    mock_firestore.collection.assert_called_with("user_actions")

    # Test record_feedback
    feedback = FeedbackRequest(
        rating="thumbs_up",
        session_id="sess-test-1",
        query="MacBook vs Dell",
    )
    fb_id = service.record_feedback(feedback)
    assert fb_id == "doc-test-123"
    mock_firestore.collection.assert_called_with("feedback")

    # Test record_query_telemetry
    success = service.record_query_telemetry(
        query_id="trace-123",
        session_id="sess-test-1",
        query_text="MacBook vs Dell",
        category="Laptops",
        latency_ms=1250.0,
        input_tokens=150,
        output_tokens=300,
        bq_bytes_billed=1048576,
        retrieved_skus=["6534606", "6543210"],
    )
    assert success is True
    assert mock_bq.insert_rows_json.called


def test_analytics_api_endpoints():
    app = create_app()
    client = TestClient(app)

    # Test POST /api/actions
    resp_action = client.post(
        "/api/actions",
        json={
            "action_type": "copy_markdown",
            "session_id": "sess-unit-1",
            "query": "MacBook vs Dell",
            "target_skus": ["111", "222"],
        },
    )
    assert resp_action.status_code == 200
    assert resp_action.json()["status"] == "recorded"

    # Test POST /api/feedback
    resp_fb = client.post(
        "/api/feedback",
        json={
            "rating": "thumbs_up",
            "session_id": "sess-unit-1",
            "query": "MacBook vs Dell",
            "target_skus": ["111", "222"],
        },
    )
    assert resp_fb.status_code == 200
    assert resp_fb.json()["status"] == "recorded"
