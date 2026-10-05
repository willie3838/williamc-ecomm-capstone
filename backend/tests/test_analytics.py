from unittest.mock import MagicMock, patch

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


def test_analytics_service_client_initialization_branches(monkeypatch):
    """Verify get_firestore_client and get_bq_client initialization branches."""
    # Branch 1: disable_cloud_clients=True
    service_disabled = AnalyticsService(disable_cloud_clients=True)
    assert service_disabled.get_firestore_client() is None
    assert service_disabled.get_bq_client() is None

    # Branch 2: Cached client returned directly
    mock_fs = MagicMock()
    mock_bq = MagicMock()
    service_cached = AnalyticsService(firestore_client=mock_fs, bq_client=mock_bq)
    assert service_cached.get_firestore_client() is mock_fs
    assert service_cached.get_bq_client() is mock_bq

    # Branch 3: PYTEST_CURRENT_TEST returns None
    service_fresh = AnalyticsService()
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_analytics.py")
    assert service_fresh.get_firestore_client() is None
    assert service_fresh.get_bq_client() is None

    # Branch 4: Unset PYTEST_CURRENT_TEST, client construction raises Exception
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with patch("google.cloud.firestore.Client", side_effect=Exception("Firestore Init Error")):
        assert service_fresh.get_firestore_client() is None

    with patch("google.cloud.bigquery.Client", side_effect=Exception("BigQuery Init Error")):
        assert service_fresh.get_bq_client() is None

    # Branch 5: Client construction succeeds
    mock_created_fs = MagicMock()
    mock_created_bq = MagicMock()
    with patch("google.cloud.firestore.Client", return_value=mock_created_fs):
        service_real_fs = AnalyticsService()
        assert service_real_fs.get_firestore_client() is mock_created_fs
        # Verify cached on second call
        assert service_real_fs.get_firestore_client() is mock_created_fs

    with patch("google.cloud.bigquery.Client", return_value=mock_created_bq):
        service_real_bq = AnalyticsService()
        assert service_real_bq.get_bq_client() is mock_created_bq
        # Verify cached on second call
        assert service_real_bq.get_bq_client() is mock_created_bq


def test_record_user_action_and_feedback_mock_and_error_branches():
    """Verify fallback when client is None or raises an exception during write."""
    # Test with client=None (in-memory mock fallback)
    service_none = AnalyticsService(disable_cloud_clients=True)

    action = UserActionRequest(
        action_type="sku_click",
        session_id="sess-none-1",
        query="MacBook vs iPad",
    )
    assert service_none.record_user_action(action) is None

    feedback = FeedbackRequest(
        rating="thumbs_down",
        session_id="sess-none-1",
        query="MacBook vs iPad",
        comment="Needs more specs",
    )
    assert service_none.record_feedback(feedback) is None

    # Test with client that raises an exception during add
    mock_fs = MagicMock()
    mock_coll = MagicMock()
    mock_coll.add.side_effect = Exception("Firestore write error")
    mock_fs.collection.return_value = mock_coll

    service_error = AnalyticsService(firestore_client=mock_fs)
    assert service_error.record_user_action(action) is None
    assert service_error.record_feedback(feedback) is None


def test_increment_session_comparisons_all_branches():
    """Verify increment_session_comparisons with Firestore existing doc, new doc, error, and in-memory fallback."""
    # Branch 1: In-memory fallback (client is None)
    service_mem = AnalyticsService(disable_cloud_clients=True)
    assert service_mem.increment_session_comparisons("sess-mem") == 1
    assert service_mem.increment_session_comparisons("sess-mem") == 2
    assert service_mem.increment_session_comparisons("sess-other") == 1

    # Branch 2: Firestore client with existing doc
    mock_fs = MagicMock()
    mock_coll = MagicMock()
    mock_doc_ref = MagicMock()
    mock_existing_doc = MagicMock()
    mock_existing_doc.exists = True
    mock_updated_doc = MagicMock()
    mock_updated_doc.get.return_value = 4

    mock_doc_ref.get.side_effect = [mock_existing_doc, mock_updated_doc]
    mock_coll.document.return_value = mock_doc_ref
    mock_fs.collection.return_value = mock_coll

    service_fs = AnalyticsService(firestore_client=mock_fs)
    count = service_fs.increment_session_comparisons("sess-exist")
    assert count == 4
    assert mock_doc_ref.update.called

    # Branch 3: Firestore client with new doc (doc.exists is False)
    mock_new_doc = MagicMock()
    mock_new_doc.exists = False
    mock_doc_ref.get.side_effect = [mock_new_doc]

    count_new = service_fs.increment_session_comparisons("sess-new")
    assert count_new == 1
    assert mock_doc_ref.set.called

    # Branch 4: Firestore raises exception (should fall back to in-memory counter)
    mock_doc_ref.get.side_effect = Exception("Firestore timeout")
    fallback_count = service_fs.increment_session_comparisons("sess-err")
    assert fallback_count == 1
    assert service_fs.increment_session_comparisons("sess-err") == 2


def test_record_query_telemetry_errors_and_none_client():
    """Verify record_query_telemetry when BQ client returns insert errors, raises exception, or is None."""
    # Case 1: client is None
    service_none = AnalyticsService(disable_cloud_clients=True)
    success_none = service_none.record_query_telemetry(
        query_id="q-none",
        session_id="s-none",
        query_text="Surface vs Mac",
        category="Laptops",
        latency_ms=100.0,
        input_tokens=10,
        output_tokens=20,
        bq_bytes_billed=1000,
        retrieved_skus=["111"],
    )
    assert success_none is False

    # Case 2: client returns insert errors
    mock_bq = MagicMock()
    mock_bq.insert_rows_json.return_value = [{"error": "Invalid schema"}]
    service_err = AnalyticsService(bq_client=mock_bq)

    success_err = service_err.record_query_telemetry(
        query_id="q-err",
        session_id="s-err",
        query_text="Surface vs Mac",
        category="Laptops",
        latency_ms=100.0,
        input_tokens=10,
        output_tokens=20,
        bq_bytes_billed=1000,
        retrieved_skus=["111"],
    )
    assert success_err is False

    # Case 3: client raises exception during insert_rows_json
    mock_bq.insert_rows_json.side_effect = Exception("BQ Network Error")
    success_exc = service_err.record_query_telemetry(
        query_id="q-exc",
        session_id="s-exc",
        query_text="Surface vs Mac",
        category="Laptops",
        latency_ms=100.0,
        input_tokens=10,
        output_tokens=20,
        bq_bytes_billed=1000,
        retrieved_skus=["111"],
    )
    assert success_exc is False
