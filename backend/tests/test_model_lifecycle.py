"""Unit tests for AI Lifecycle Management, Model Experimentation & Automated Rollback Router."""

from app.agent.lifecycle import ModelLifecycleRouter, ModelVariant, RoutingDecision


def test_model_router_manual_override():
    """Verify manual override via header/parameter directly selects requested variant."""
    router = ModelLifecycleRouter(
        champion_model="gemini-2.5-flash",
        challenger_model="gemini-2.5-pro",
    )

    decision_challenger = router.route(override_variant="challenger")
    assert decision_challenger.variant == ModelVariant.CHALLENGER
    assert decision_challenger.model_name == "gemini-2.5-pro"
    assert decision_challenger.reason == "manual_header_override"

    decision_champion = router.route(override_variant="champion")
    assert decision_champion.variant == ModelVariant.CHAMPION
    assert decision_champion.model_name == "gemini-2.5-flash"
    assert decision_champion.reason == "manual_header_override"


def test_model_router_disabled_routes_to_champion():
    """Verify when experiments are disabled, 100% of traffic routes to champion."""
    router = ModelLifecycleRouter(
        champion_model="gemini-2.5-flash",
        challenger_model="gemini-2.5-pro",
        enabled=False,
    )

    for i in range(20):
        decision = router.route(session_id=f"session_{i}")
        assert decision.variant == ModelVariant.CHAMPION
        assert decision.model_name == "gemini-2.5-flash"
        assert decision.reason == "experiment_disabled"


def test_model_router_deterministic_sticky_session():
    """Verify sticky sessions consistently hash to the exact same model variant."""
    router = ModelLifecycleRouter(
        champion_model="gemini-2.5-flash",
        challenger_model="gemini-2.5-pro",
        challenger_percentage=50,
    )

    session_a = "user_session_alpha_123"
    session_b = "user_session_beta_456"

    first_decision_a = router.route(session_id=session_a)
    first_decision_b = router.route(session_id=session_b)

    # Subsequent requests with identical session IDs must return identical routing decisions
    for _ in range(10):
        assert router.route(session_id=session_a).variant == first_decision_a.variant
        assert router.route(session_id=session_b).variant == first_decision_b.variant


def test_model_router_percentage_bounds():
    """Verify 0% and 100% boundary conditions for traffic splitting."""
    router_0 = ModelLifecycleRouter(challenger_percentage=0)
    for i in range(10):
        assert router_0.route(session_id=f"sess_{i}").variant == ModelVariant.CHAMPION

    router_100 = ModelLifecycleRouter(challenger_percentage=100)
    for i in range(10):
        assert router_100.route(session_id=f"sess_{i}").variant == ModelVariant.CHALLENGER


def test_execute_with_resilient_fallback_on_challenger_failure():
    """Verify automated circuit-breaker rollback to Champion when Challenger model fails."""
    router = ModelLifecycleRouter(
        champion_model="gemini-2.5-flash",
        challenger_model="gemini-2.5-pro",
    )

    decision = RoutingDecision(
        model_name="gemini-2.5-pro",
        variant=ModelVariant.CHALLENGER,
        experiment_id="exp-1",
        reason="traffic_split",
    )

    def flaky_model_invoker(model: str):
        if model == "gemini-2.5-pro":
            raise RuntimeError("Challenger 503 Quota Spike")
        return f"Success with {model}"

    result, final_decision = router.execute_with_resilient_fallback(decision, flaky_model_invoker)

    assert result == "Success with gemini-2.5-flash"
    assert final_decision.variant == ModelVariant.CHAMPION
    assert final_decision.model_name == "gemini-2.5-flash"
    assert "automated_rollback_after_challenger_failure" in final_decision.reason


def test_execute_with_resilient_fallback_on_challenger_success():
    """Verify normal execution when Challenger succeeds without error."""
    router = ModelLifecycleRouter()
    decision = RoutingDecision(
        model_name="gemini-2.5-pro",
        variant=ModelVariant.CHALLENGER,
        experiment_id="exp-1",
        reason="traffic_split",
    )

    def healthy_invoker(model: str):
        return f"Result from {model}"

    result, final_decision = router.execute_with_resilient_fallback(decision, healthy_invoker)
    assert result == "Result from gemini-2.5-pro"
    assert final_decision.variant == ModelVariant.CHALLENGER
