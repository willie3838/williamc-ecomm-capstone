"""Data access layer for Firestore user actions, feedback, session metrics, and BigQuery query telemetry."""

import logging
from datetime import UTC, datetime

from google.cloud import bigquery, firestore

from app.config import settings
from app.models.analytics import FeedbackRequest, UserActionRequest

logger = logging.getLogger("app.analytics")


class AnalyticsService:
    """Service handling Firestore user events and BigQuery query telemetry streaming."""

    def __init__(
        self,
        firestore_client: firestore.Client | None = None,
        bq_client: bigquery.Client | None = None,
        disable_cloud_clients: bool = False,
    ) -> None:
        self._firestore_client = firestore_client
        self._bq_client = bq_client
        self._disable_cloud_clients = disable_cloud_clients
        self._local_session_counts: dict[str, int] = {}

    def get_firestore_client(self) -> firestore.Client | None:
        """Lazily initialize Firestore client with graceful fallback if unavailable."""
        if self._disable_cloud_clients:
            return None
        if self._firestore_client is not None:
            return self._firestore_client

        try:
            self._firestore_client = firestore.Client(project=settings.gcp_project)
            return self._firestore_client
        except Exception as e:
            logger.warning(
                "Firestore client initialization failed (analytics will be mocked/skipped): %s", e
            )
            return None

    def get_bq_client(self) -> bigquery.Client | None:
        """Lazily initialize BigQuery client."""
        if self._disable_cloud_clients:
            return None
        if self._bq_client is not None:
            return self._bq_client

        try:
            self._bq_client = bigquery.Client(project=settings.gcp_project)
            return self._bq_client
        except Exception as e:
            logger.warning("BigQuery client initialization failed for telemetry: %s", e)
            return None

    def record_user_action(self, action: UserActionRequest) -> str | None:
        """Log user action to Firestore collection 'user_actions'."""
        client = self.get_firestore_client()
        doc_data = {
            "action_type": action.action_type,
            "session_id": action.session_id,
            "query": action.query,
            "category": action.category,
            "target_skus": action.target_skus,
            "metadata": action.metadata,
            "timestamp": action.timestamp.isoformat(),
        }

        if client is not None:
            try:
                _, doc_ref = client.collection("user_actions").add(doc_data)
                logger.info(
                    "Recorded user action '%s' in Firestore (doc: %s)",
                    action.action_type,
                    doc_ref.id,
                )
                return doc_ref.id
            except Exception as e:
                logger.warning("Failed to persist user action to Firestore: %s", e)
        else:
            logger.info("Mocked user action recording: %s", doc_data)

        return None

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        """Log thumbs-up/thumbs-down evaluation feedback to Firestore collection 'feedback'."""
        client = self.get_firestore_client()
        doc_data = {
            "rating": feedback.rating,
            "session_id": feedback.session_id,
            "query": feedback.query,
            "target_skus": feedback.target_skus,
            "trace_id": feedback.trace_id,
            "comment": feedback.comment,
            "timestamp": feedback.timestamp.isoformat(),
        }

        if client is not None:
            try:
                _, doc_ref = client.collection("feedback").add(doc_data)
                logger.info(
                    "Recorded %s feedback in Firestore (doc: %s)", feedback.rating, doc_ref.id
                )
                return doc_ref.id
            except Exception as e:
                logger.warning("Failed to persist feedback to Firestore: %s", e)
        else:
            logger.info("Mocked feedback recording: %s", doc_data)

        return None

    def increment_session_comparisons(self, session_id: str) -> int:
        """Increment and return comparison count for session in Firestore collection 'sessions'."""
        client = self.get_firestore_client()
        now_iso = datetime.now(UTC).isoformat()

        if client is not None:
            try:
                doc_ref = client.collection("sessions").document(session_id)
                doc = doc_ref.get(timeout=2.0)
                if doc.exists:
                    doc_ref.update(
                        {
                            "comparison_count": firestore.Increment(1),
                            "last_seen": now_iso,
                        },
                        timeout=2.0,
                    )
                    updated = doc_ref.get(timeout=2.0)
                    count = int(updated.get("comparison_count") or 1)
                    self._local_session_counts[session_id] = count
                    return count
                else:
                    doc_ref.set(
                        {
                            "session_id": session_id,
                            "comparison_count": 1,
                            "first_seen": now_iso,
                            "last_seen": now_iso,
                        },
                        timeout=2.0,
                    )
                    self._local_session_counts[session_id] = 1
                    return 1
            except Exception as e:
                logger.warning("Failed to update session counter in Firestore: %s", e)

        # In-memory fallback when Firestore is offline, mocked, or credentials expired
        current = self._local_session_counts.get(session_id, 0) + 1
        self._local_session_counts[session_id] = current
        return current

    def record_query_telemetry(
        self,
        query_id: str,
        session_id: str | None,
        query_text: str,
        category: str | None,
        latency_ms: float,
        input_tokens: int | None,
        output_tokens: int | None,
        bq_bytes_billed: int | None,
        retrieved_skus: list[str] | None,
        status: str = "SUCCESS",
        error_message: str | None = None,
    ) -> bool:
        """Stream query operational and cost telemetry to BigQuery table."""
        client = self.get_bq_client()
        table_ref = (
            f"{settings.gcp_project}.{settings.telemetry_dataset}.{settings.telemetry_table}"
        )

        row = {
            "query_id": query_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": session_id,
            "query_text": query_text,
            "category": category,
            "latency_ms": float(latency_ms),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "bq_bytes_billed": bq_bytes_billed,
            "retrieved_skus": str(retrieved_skus or []),
            "status": status,
            "error_message": error_message,
        }

        # Estimate and log query cost in structured logs
        est_bq_cost = ((bq_bytes_billed or 0) / (1024**4)) * 6.25
        est_model_cost = ((input_tokens or 0) / 1e6 * 0.075) + ((output_tokens or 0) / 1e6 * 0.30)
        total_est_cost = round(est_bq_cost + est_model_cost, 6)

        logger.info(
            "Query telemetry: query_id=%s latency=%.2fms bq_bytes=%s tokens=(in:%s, out:%s) est_cost=$%.6f",
            query_id,
            latency_ms,
            bq_bytes_billed,
            input_tokens,
            output_tokens,
            total_est_cost,
            extra={
                "telemetry_query_id": query_id,
                "session_id": session_id,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "bq_bytes_billed": bq_bytes_billed,
                "estimated_cost_usd": total_est_cost,
            },
        )

        if client is not None:
            try:
                errors = client.insert_rows_json(table_ref, [row])
                if errors:
                    logger.warning("BigQuery telemetry insert had errors: %s", errors)
                    return False
                return True
            except Exception as e:
                logger.warning("Failed to stream telemetry to BigQuery: %s", e)

        return False


analytics_service = AnalyticsService()
