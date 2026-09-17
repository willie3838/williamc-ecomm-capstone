"""AI Lifecycle Management & Model Experimentation Router.

Enforces production model lifecycle practices:
1. Versioned Model Routing (Champion vs Challenger).
2. Deterministic, sticky traffic splitting across user sessions.
3. OpenTelemetry experiment telemetry tracking and latency comparison.
4. Automated circuit breaker rollback to Champion on Challenger anomalies.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.config import settings
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class ModelVariant(StrEnum):
    """Experiment model variant classification."""

    CHAMPION = "champion"
    CHALLENGER = "challenger"


@dataclass
class RoutingDecision:
    """Outcome of model routing decision."""

    model_name: str
    variant: ModelVariant
    experiment_id: str
    reason: str


class ModelLifecycleRouter:
    """Manages AI model lifecycle, traffic splitting, and automated rollback."""

    def __init__(
        self,
        champion_model: str | None = None,
        challenger_model: str | None = None,
        challenger_percentage: int | None = None,
        experiment_id: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.champion_model = champion_model or getattr(
            settings, "champion_model", "gemini-2.5-flash"
        )
        self.challenger_model = challenger_model or getattr(
            settings, "challenger_model", "gemini-2.5-pro"
        )
        self.challenger_percentage = (
            challenger_percentage
            if challenger_percentage is not None
            else getattr(settings, "challenger_traffic_percentage", 10)
        )
        self.experiment_id = experiment_id or getattr(
            settings, "active_experiment_id", "exp-2026-flash-vs-pro-v1"
        )
        self.enabled = (
            enabled if enabled is not None else getattr(settings, "enable_model_experiment", True)
        )

    def route(
        self,
        session_id: str | None = None,
        override_variant: str | None = None,
        context_key: str = "",
    ) -> RoutingDecision:
        """Determine target model for request based on override, sticky hash, or fallback."""
        with tracer.start_as_current_span("lifecycle.model_routing") as span:
            span.set_attribute("experiment.id", self.experiment_id)

            # 1. Manual Header / Parameter Override
            if override_variant:
                norm = override_variant.strip().lower()
                if norm in {ModelVariant.CHALLENGER.value, "challenger"}:
                    decision = RoutingDecision(
                        model_name=self.challenger_model,
                        variant=ModelVariant.CHALLENGER,
                        experiment_id=self.experiment_id,
                        reason="manual_header_override",
                    )
                    self._record_telemetry(span, decision)
                    return decision
                elif norm in {ModelVariant.CHAMPION.value, "champion"}:
                    decision = RoutingDecision(
                        model_name=self.champion_model,
                        variant=ModelVariant.CHAMPION,
                        experiment_id=self.experiment_id,
                        reason="manual_header_override",
                    )
                    self._record_telemetry(span, decision)
                    return decision

            # 2. If experiments disabled, route 100% to Champion
            if not self.enabled or self.challenger_percentage <= 0:
                decision = RoutingDecision(
                    model_name=self.champion_model,
                    variant=ModelVariant.CHAMPION,
                    experiment_id=self.experiment_id,
                    reason="experiment_disabled",
                )
                self._record_telemetry(span, decision)
                return decision

            # 3. Deterministic Sticky Hashing
            seed = session_id or context_key or "default_bucket"
            bucket = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % 100

            if bucket < self.challenger_percentage:
                decision = RoutingDecision(
                    model_name=self.challenger_model,
                    variant=ModelVariant.CHALLENGER,
                    experiment_id=self.experiment_id,
                    reason=f"traffic_split_bucket_{bucket}_lt_{self.challenger_percentage}",
                )
            else:
                decision = RoutingDecision(
                    model_name=self.champion_model,
                    variant=ModelVariant.CHAMPION,
                    experiment_id=self.experiment_id,
                    reason=f"traffic_split_bucket_{bucket}_gte_{self.challenger_percentage}",
                )

            self._record_telemetry(span, decision)
            return decision

    def execute_with_resilient_fallback(
        self,
        decision: RoutingDecision,
        invoker_fn: Callable[[str], Any],
        fallback_invoker_fn: Callable[[str], Any] | None = None,
    ) -> tuple[Any, RoutingDecision]:
        """Execute model invocation with automatic rollback to Champion if Challenger encounters an anomaly."""
        try:
            result = invoker_fn(decision.model_name)
            return result, decision
        except Exception as err:
            if decision.variant == ModelVariant.CHALLENGER:
                logger.warning(
                    "Challenger model %s failed with error: %s. Initiating automated circuit-breaker rollback to Champion.",
                    decision.model_name,
                    err,
                )
                fallback_decision = RoutingDecision(
                    model_name=self.champion_model,
                    variant=ModelVariant.CHAMPION,
                    experiment_id=self.experiment_id,
                    reason=f"automated_rollback_after_challenger_failure: {err}",
                )
                fb_fn = fallback_invoker_fn or invoker_fn
                result = fb_fn(self.champion_model)
                return result, fallback_decision
            raise

    def _record_telemetry(self, span: Any, decision: RoutingDecision) -> None:
        """Annotate span with structured experiment dimensions."""
        span.set_attribute("experiment.id", decision.experiment_id)
        span.set_attribute("experiment.variant", decision.variant.value)
        span.set_attribute("experiment.model_name", decision.model_name)
        span.set_attribute("experiment.routing_reason", decision.reason)
        logger.info(
            "Model routing decision: variant=%s model=%s reason=%s exp=%s",
            decision.variant.value,
            decision.model_name,
            decision.reason,
            decision.experiment_id,
        )
