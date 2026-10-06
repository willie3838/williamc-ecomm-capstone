"""Unit tests asserting forensic audit integrity fixes for all 5 landmines.

Ensures:
1. evals/benchmark_models.py contains NO artificial min(p50, ...) or min(p95, ...) latency clamping
   and hoists ComparisonOrchestrator instantiation outside per-case loops.
2. orchestrator.py and hermetic_adapter.py do NOT spoof models or drop schemas in live vs test modes,
   and configure ThinkingConfig(thinking_budget=0) on low-latency Flash stages.
3. MultiAgentCoordinator executes self.adk_sequential_agent sub-agents through genuine ADK
   InMemorySessionService session.state handoffs, and execute_with_adk_runner() honors _final_text.
4. backend/src/app/tools/catalog.py removes 'not os.environ.get(PYTEST_CURRENT_TEST)' special-case
   snapshot bypass branching, maintaining consistent direct parameterized BigQuery SQL across test and live.
5. hermetic_adapter.py removes post-LLM string concatenation of missing [SKU: ...] and price bullets,
   passing precomputed price deltas into the prompt and validating via verify_and_scrub_synthesis_claims.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"


def test_eval_benchmark_no_latency_clamping_and_hoisted_orchestrator():
    """Verify evals/benchmark_models.py has zero artificial latency clamping and hoists orchestrator."""
    benchmark_file = REPO_ROOT / "evals" / "benchmark_models.py"
    assert benchmark_file.exists(), f"{benchmark_file} not found"
    content = benchmark_file.read_text(encoding="utf-8")

    # 1. No artificial clamping patterns
    assert "min(p50," not in content, (
        "Found artificial min(p50, ...) clamping in benchmark_models.py!"
    )
    assert "min(p95," not in content, (
        "Found artificial min(p95, ...) clamping in benchmark_models.py!"
    )
    assert "min(measured_p50_ms," not in content, (
        "Found artificial min(measured_p50_ms, ...) clamping in benchmark_models.py!"
    )
    assert "min(measured_p95_ms," not in content, (
        "Found artificial min(measured_p95_ms, ...) clamping in benchmark_models.py!"
    )

    # 2. Hoisting check: ComparisonOrchestrator should not be inside 'for c in cases:' loop in run_per_stage_benchmarks
    # We inspect the AST of run_per_stage_benchmarks
    tree = ast.parse(content)
    run_per_stage_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_per_stage_benchmarks":
            run_per_stage_fn = node
            break
    assert run_per_stage_fn is not None, "run_per_stage_benchmarks not found in AST"

    # In each stage loop (for model in STAGE_MODELS:), ComparisonOrchestrator should be instantiated
    # BEFORE the inner 'for c in cases:' loop
    stage_for_loops = [
        n
        for n in ast.walk(run_per_stage_fn)
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "model"
    ]
    assert len(stage_for_loops) >= 3, "Expected at least 3 stage loops (Stage 1, 2, 3)"
    for loop in stage_for_loops:
        inner_cases_loop = next(
            (
                n
                for n in ast.walk(loop)
                if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "c"
            ),
            None,
        )
        assert inner_cases_loop is not None, "Expected inner 'for c in cases:' loop"
        # Check that ComparisonOrchestrator is NOT called inside inner_cases_loop
        orch_calls_inside_cases = [
            n
            for n in ast.walk(inner_cases_loop)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "ComparisonOrchestrator"
        ]
        assert len(orch_calls_inside_cases) == 0, (
            "ComparisonOrchestrator instantiation must be hoisted outside 'for c in cases:' loop!"
        )


def test_no_model_or_schema_spoofing_in_orchestrator():
    """Verify orchestrator.py does not switch models or drop response_schema between test and live."""
    orch_file = BACKEND_DIR / "src" / "app" / "agent" / "orchestrator.py"
    content = orch_file.read_text(encoding="utf-8")

    # Neither classify_intent_with_llm nor _rerank_with_llm nor synthesize_comparison_with_llm should have:
    # call_model = "gemini-2.5-flash-lite" if not is_mock_env else ...
    assert 'call_model = "gemini-2.5-flash-lite" if not is_mock_env else' not in content, (
        "orchestrator.py contains test-vs-live model spoofing!"
    )
    # response_schema should not be conditionally None based on is_mock_env
    assert "response_schema=QueryIntentAnalysis if is_mock_env else None" not in content, (
        "orchestrator.py drops QueryIntentAnalysis schema in live mode!"
    )
    assert "response_schema=CandidateRankingResponse if is_mock_env else None" not in content, (
        "orchestrator.py drops CandidateRankingResponse schema in live mode!"
    )
    assert "response_schema=ComparisonSynthesis if is_mock_env else None" not in content, (
        "orchestrator.py drops ComparisonSynthesis schema in live mode!"
    )


def test_no_model_or_schema_spoofing_in_adk_llm_and_hermetic_adapter_deleted():
    """Verify hermetic_adapter.py is deleted and adk_llm.py _call_real_vertex_gemini honors requested model and schema."""
    old_adapter = BACKEND_DIR / "src" / "app" / "agent" / "hermetic_adapter.py"
    assert not old_adapter.exists(), "hermetic_adapter.py must be deleted!"

    adapter_file = BACKEND_DIR / "src" / "app" / "agent" / "adk_llm.py"
    content = adapter_file.read_text(encoding="utf-8")

    # _call_real_vertex_gemini should not force target_model to flash-lite when pro or tiered-hybrid is requested
    assert (
        'target_model = (\n        "gemini-2.5-flash-lite"\n        if model in ("gemini-1.5-flash", "gemini-2.5-pro", "tiered-hybrid", "")'
        not in content
    ), "adk_llm.py silently overrides model to gemini-2.5-flash-lite in live mode!"
    # response_schema should not be conditional on assert_called or PYTEST_CURRENT_TEST
    assert (
        'if hasattr(genai.Client, "assert_called") or os.environ.get("PYTEST_CURRENT_TEST"):\n            cfg_kwargs["response_schema"] = schema_cls'
        not in content
    ), "adk_llm.py drops response_schema in live mode!"


def test_thinking_config_zero_budget_on_flash_stages():
    """Verify ThinkingConfig(thinking_budget=0) is configured on low-latency Flash stages."""
    from app.agent.orchestrator import ComparisonOrchestrator

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "intent_type": "COMPARISON",
            "is_comparison_eligible": True,
            "detected_category": "Laptops",
            "target_keywords": ["MacBook", "Dell XPS"],
            "reasoning": "Comparison request.",
        }
    )
    mock_response.usage_metadata.prompt_token_count = 150
    mock_response.usage_metadata.candidates_token_count = 50
    mock_client.models.generate_content.return_value = mock_response

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-2.5-flash")
    orch.classify_intent_with_llm("MacBook vs Dell XPS", model="gemini-2.5-flash")

    # Verify generate_content call config
    assert mock_client.models.generate_content.called
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    config = call_kwargs.get("config")
    assert config is not None, "GenerateContentConfig was not passed"
    assert hasattr(config, "thinking_config"), "thinking_config missing from config"
    assert config.thinking_config is not None, "thinking_config is None"
    assert config.thinking_config.thinking_budget == 0, (
        f"Expected thinking_budget=0 on Flash stage, got {config.thinking_config.thinking_budget}"
    )


def test_multi_agent_coordinator_uses_adk_sequential_agent_and_session_state():
    """Verify MultiAgentCoordinator.execute() runs through self.adk_sequential_agent with session.state handoffs."""
    from app.agent.multi_agent import MultiAgentCoordinator

    mock_bq = MagicMock()
    # Return mock catalog rows
    mock_bq.query_and_wait.return_value = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 13-inch M3",
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 120,
            "specifications": {"ram_gb": 16, "storage_gb": 512, "battery_life_hours": 18},
            "url": "https://www.techbuy.com/site/sku/6534606.p",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": "Dell XPS 13 Intel Core Ultra 7",
            "brand": "Dell",
            "category": "Laptops",
            "price": 1299.0,
            "rating": 4.6,
            "review_count": 85,
            "specifications": {"ram_gb": 16, "storage_gb": 512, "battery_life_hours": 14},
            "url": "https://www.techbuy.com/site/sku/6575132.p",
            "in_stock": True,
        },
    ]

    from google.adk.workflow import FunctionNode, Workflow

    coordinator = MultiAgentCoordinator(bq_client=mock_bq, model="gemini-2.5-flash")
    assert not hasattr(coordinator, "adk_sequential_agent")
    assert hasattr(coordinator, "adk_workflow"), "adk_workflow missing"
    assert isinstance(coordinator.adk_workflow, Workflow)
    assert coordinator.adk_workflow.graph is not None
    function_nodes = [
        n for n in coordinator.adk_workflow.graph.nodes if isinstance(n, FunctionNode)
    ]
    assert len(function_nodes) == 4, (
        "Expected 4 FunctionNode stages in adk_workflow (QueryIntent, CatalogRetrieval, RelevanceDetector, SpecComparison)"
    )

    # Execute pipeline
    resp = coordinator.execute("MacBook Air vs Dell XPS 13", category="Laptops")
    assert resp is not None
    assert len(resp.products) >= 2

    # Check that session_state was tracked during execution
    assert hasattr(coordinator, "last_session_state"), (
        "coordinator.last_session_state must be recorded"
    )
    session_state = coordinator.last_session_state
    assert isinstance(session_state, dict), "last_session_state must be a dict"
    assert "stage_1_intent" in session_state, "stage_1_intent missing from session.state"
    assert "stage_2_retrieval" in session_state, "stage_2_retrieval missing from session.state"
    assert "stage_3_relevance" in session_state, "stage_3_relevance missing from session.state"
    assert "stage_4_synthesis" in session_state, "stage_4_synthesis missing from session.state"


def test_execute_with_adk_runner_honors_final_text():
    """Verify execute_with_adk_runner() consumes and parses _final_text from ADK runner."""
    from app.agent.orchestrator import ComparisonOrchestrator

    mock_synth_json = json.dumps(
        {
            "summary": "Apple MacBook Air [SKU: 6534606] lasts up to 18 hours. Dell XPS 13 [SKU: 6575132] provides 14 hours.",
            "recommendations": "Best for battery: Apple MacBook Air [SKU: 6534606]. Best for Windows: Dell XPS 13 [SKU: 6575132].",
        }
    )

    with patch("app.agent.runner.run_adk_agent_sync") as mock_run_sync:
        mock_run_sync.return_value = (mock_synth_json, [])
        orch = ComparisonOrchestrator(model="gemini-2.5-flash")

        # Mock query_catalog
        with patch("app.tools.catalog.query_catalog") as mock_qc:
            mock_qc.return_value = [
                {
                    "sku": "6534606",
                    "name": "Apple MacBook Air 13-inch M3",
                    "brand": "Apple",
                    "category": "Laptops",
                    "price": 1099.0,
                    "rating": 4.8,
                    "review_count": 120,
                    "specifications": {"battery_life_hours": 18},
                    "url": "https://www.techbuy.com/site/sku/6534606.p",
                    "in_stock": True,
                },
                {
                    "sku": "6575132",
                    "name": "Dell XPS 13 Intel Core Ultra 7",
                    "brand": "Dell",
                    "category": "Laptops",
                    "price": 1299.0,
                    "rating": 4.6,
                    "review_count": 85,
                    "specifications": {"battery_life_hours": 14},
                    "url": "https://www.techbuy.com/site/sku/6575132.p",
                    "in_stock": True,
                },
            ]
            resp = orch.execute_with_adk_runner("MacBook Air vs Dell XPS 13", category="Laptops")
            assert resp is not None
            assert "[SKU: 6534606]" in resp.summary
            assert "[SKU: 6575132]" in resp.summary
            # Assert that the summary came from _final_text
            assert "lasts up to 18 hours" in resp.summary


def test_query_catalog_no_test_environment_branching_for_cache():
    """Verify backend/src/app/tools/catalog.py removes 'not os.environ.get(PYTEST_CURRENT_TEST)' snapshot bypass."""
    catalog_tool_file = BACKEND_DIR / "src" / "app" / "tools" / "catalog.py"
    content = catalog_tool_file.read_text(encoding="utf-8")

    qc_start = content.find("def query_catalog(")
    qc_end = content.find("query_params: list[bigquery")
    qc_section = content[qc_start:qc_end]
    # In query_catalog, should not have the snapshot branch bypassing BigQuery when not PYTEST_CURRENT_TEST
    assert 'not os.environ.get("PYTEST_CURRENT_TEST")' not in qc_section, (
        "Found test-vs-live snapshot bypass branch in query_catalog()!"
    )
    assert "snapshot = warm_full_catalog_cache()" not in qc_section, (
        "Found snapshot bypass in query_catalog()!"
    )


def test_verify_and_scrub_synthesis_claims_no_artificial_concatenation():
    """Verify verify_and_scrub_synthesis_claims scrubs invalid SKUs without artificially concatenating strings."""
    from app.agent.adk_llm import verify_and_scrub_synthesis_claims
    from app.models.responses import ProductSpec

    products = [
        ProductSpec(
            sku="6534606",
            name="Apple MacBook Air 13-inch M3",
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"battery_life_hours": 18},
        ),
        ProductSpec(
            sku="6575132",
            name="Dell XPS 13 Intel Core Ultra 7",
            brand="Dell",
            category="Laptops",
            price=1299.0,
            specifications={"battery_life_hours": 14},
        ),
    ]

    # Case 1: Valid citations remain intact
    valid_summary = "MacBook Air [SKU: 6534606] vs Dell XPS 13 [SKU: 6575132]."
    valid_recs = "Choose Apple [SKU: 6534606] or Dell [SKU: 6575132]."
    scrubbed_s, scrubbed_r = verify_and_scrub_synthesis_claims(valid_summary, valid_recs, products)
    assert "[SKU: 6534606]" in scrubbed_s
    assert "[SKU: 6575132]" in scrubbed_s

    # Case 2: Hallucinated SKU is scrubbed
    hallucinated_summary = "MacBook Air [SKU: 6534606] vs Fake Laptop [SKU: 9999999]."
    scrubbed_s, _ = verify_and_scrub_synthesis_claims(hallucinated_summary, None, products)
    assert "[SKU: 6534606]" in scrubbed_s
    assert "[SKU: 9999999]" not in scrubbed_s

    # Case 3: Does NOT artificially append missing SKUs if LLM omitted them
    partial_summary = "Only MacBook Air [SKU: 6534606] was discussed."
    scrubbed_s, _ = verify_and_scrub_synthesis_claims(partial_summary, None, products)
    assert "[SKU: 6575132]" not in scrubbed_s, (
        "Must not artificially inject missing SKU into summary!"
    )


def test_no_cross_request_llm_future_caching() -> None:
    """orchestrator.py must pop intra-request speculative futures and never cache LLM responses across requests."""
    source = (BACKEND_DIR / "src" / "app" / "agent" / "orchestrator.py").read_text(encoding="utf-8")
    assert "_SPECULATIVE_INTENT_FUTURES" not in source, (
        "Cross-request intent future cache is forbidden!"
    )
    assert "_SPECULATIVE_CHAT_FUTURES" not in source, (
        "Cross-request chat future cache is forbidden!"
    )
    assert "def _get_speculative_future(" not in source, (
        "Non-destructive _get_speculative_future cross-request cache lookup is forbidden!"
    )
    assert "def _get_or_create_speculative_future(" not in source, (
        "Cross-request _get_or_create_speculative_future is forbidden!"
    )


def test_chat_with_products_uses_active_model_not_flash_lite() -> None:
    """chat_with_products must use active_model rather than hardcoding gemini-2.5-flash-lite."""
    source = (BACKEND_DIR / "src" / "app" / "agent" / "orchestrator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "chat_with_products":
            fn_src = ast.get_source_segment(source, node) or ""
            assert 'call_model = "gemini-2.5-flash-lite"' not in fn_src, (
                "chat_with_products must not downgrade active_model to gemini-2.5-flash-lite!"
            )
            assert "call_model = active_model" in fn_src
            return
    raise AssertionError("Could not find chat_with_products in orchestrator.py")


def test_analytics_service_no_fake_uuid_shortcut() -> None:
    """analytics.py must not use _is_client_mocked or return synthetic act-/fb- UUIDs before Firestore write."""
    source = (BACKEND_DIR / "src" / "app" / "data" / "analytics.py").read_text(encoding="utf-8")
    assert "_is_client_mocked" not in source, "analytics.py must not branch on _is_client_mocked!"
    assert 'f"act-{uuid' not in source, "analytics.py must not fabricate act-<uuid> document IDs!"
    assert 'f"fb-{uuid' not in source, "analytics.py must not fabricate fb-<uuid> document IDs!"


def test_multi_agent_coordinator_propagates_synthesis_model_to_all_specialists() -> None:
    """MultiAgentCoordinator must propagate synthesis_model to QueryIntentAgent and RelevanceDetectorAgent."""
    from app.agent.multi_agent import MultiAgentCoordinator

    mock_bq = MagicMock()
    coordinator = MultiAgentCoordinator(
        bq_client=mock_bq,
        model="gemini-2.5-flash",
        synthesis_model="gemini-2.5-pro",
    )
    assert coordinator.intent_agent.synthesis_model == "gemini-2.5-pro"
    assert coordinator.relevance_agent.synthesis_model == "gemini-2.5-pro"
    assert coordinator.comparison_agent.synthesis_model == "gemini-2.5-pro"


def test_no_model_armor_global_rewrite_or_lite_bypass() -> None:
    """adk_llm.py and orchestrator.py must never disable Model Armor globally or skip 'lite' models."""
    ha_src = (BACKEND_DIR / "src" / "app" / "agent" / "adk_llm.py").read_text(encoding="utf-8")
    orch_src = (BACKEND_DIR / "src" / "app" / "agent" / "orchestrator.py").read_text(
        encoding="utf-8"
    )

    assert "modelarmor.googleapis.com/v1/" not in ha_src, (
        "Global modelarmor.googleapis.com endpoint is forbidden; use modelarmor.{loc}.rep.googleapis.com!"
    )
    assert "_MODEL_ARMOR_AVAILABLE = False" not in ha_src, (
        "Permanently disabling _MODEL_ARMOR_AVAILABLE in adk_llm.py is forbidden!"
    )
    assert "_MODEL_ARMOR_AVAILABLE = False" not in orch_src, (
        "Permanently disabling _MODEL_ARMOR_AVAILABLE in orchestrator.py is forbidden!"
    )
    assert '"lite" not in' not in ha_src, "Skipping Model Armor on 'lite' models is forbidden!"
    assert '"lite" not in' not in orch_src, "Skipping Model Armor on 'lite' models is forbidden!"


def test_zero_pytest_or_mock_branches_in_production_code() -> None:
    """Ensure production code under backend/src/app contains zero test-environment detection branches."""
    app_root = Path(__file__).resolve().parents[1] / "src" / "app"
    forbidden_patterns = (
        "PYTEST_CURRENT_TEST",
        "assert_called",
        '"pytest" in sys.modules',
        "'pytest' in sys.modules",
        '"Mock" in type(',
        "'Mock' in type(",
    )
    violations: list[str] = []
    for py_file in sorted(app_root.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden_patterns:
                if pat in line:
                    rel_path = py_file.relative_to(app_root.parents[2])
                    violations.append(f"{rel_path}:{line_no}: found {pat!r} -> {stripped}")
    assert not violations, (
        "Production code in backend/src/app/ must NEVER branch on pytest or mock attributes:\n"
        + "\n".join(violations)
    )
