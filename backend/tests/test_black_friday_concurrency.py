"""Unit tests verifying Black Friday high-concurrency thread safety and bounded caches."""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Any
from unittest.mock import MagicMock

from opentelemetry import trace

from app.agent.orchestrator import (
    _MAX_SPECULATIVE_FUTURES,
    _SPECULATIVE_RERANK_FUTURES,
    _SPECULATIVE_SYNTH_FUTURES,
    ComparisonOrchestrator,
    _get_or_create_speculative_future,
    _get_speculative_future,
    _store_speculative_future,
)
from app.data.analytics import _MAX_LOCAL_SESSIONS, AnalyticsService
from app.observability.tracing import _BoundedInMemorySpanExporter, setup_tracing
from app.routes.compare import _COORDINATOR_CACHE, _get_coordinator


def test_orchestrator_thread_local_tokens_and_category_hint() -> None:
    """Concurrent threads sharing one ComparisonOrchestrator must not cross-contaminate tokens or hints."""
    orch = ComparisonOrchestrator(hermetic=True)
    barrier = threading.Barrier(10)
    results: dict[int, tuple[int, int, str | None]] = {}

    def _worker(idx: int) -> None:
        orch.last_input_tokens = idx * 100
        orch.last_output_tokens = idx * 10
        orch._active_category_hint = f"Category-{idx}"
        barrier.wait(timeout=5.0)
        results[idx] = (
            orch.last_input_tokens,
            orch.last_output_tokens,
            orch._active_category_hint,
        )

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(1, 11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(results) == 10
    for idx, (in_tok, out_tok, hint) in results.items():
        assert in_tok == idx * 100
        assert out_tok == idx * 10
        assert hint == f"Category-{idx}"


def test_speculative_futures_bounded_fifo_eviction() -> None:
    """Speculative future caches must evict oldest entries when exceeding _MAX_SPECULATIVE_FUTURES."""
    _SPECULATIVE_SYNTH_FUTURES.clear()
    _SPECULATIVE_RERANK_FUTURES.clear()

    total_to_insert = _MAX_SPECULATIVE_FUTURES + 50
    for i in range(total_to_insert):
        fut: concurrent.futures.Future[str] = concurrent.futures.Future()
        fut.set_result(f"val-{i}")
        _store_speculative_future(_SPECULATIVE_SYNTH_FUTURES, (("SKU1",), f"q-{i}"), fut)

    assert len(_SPECULATIVE_SYNTH_FUTURES) == _MAX_SPECULATIVE_FUTURES
    assert _get_speculative_future(_SPECULATIVE_SYNTH_FUTURES, (("SKU1",), "q-0")) is None
    latest = _get_speculative_future(
        _SPECULATIVE_SYNTH_FUTURES, (("SKU1",), f"q-{total_to_insert - 1}")
    )
    assert latest is not None
    assert latest.result() == f"val-{total_to_insert - 1}"
    _SPECULATIVE_SYNTH_FUTURES.clear()


def test_speculative_future_non_destructive_coalescing() -> None:
    """Multiple concurrent callers asking the same query must share a single in-flight Future."""
    cache: dict[tuple[Any, ...], concurrent.futures.Future[Any]] = {}
    call_count = 0
    call_lock = threading.Lock()

    def _expensive_llm_call() -> str:
        nonlocal call_count
        with call_lock:
            call_count += 1
        return "coalesced-response"

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [
            _get_or_create_speculative_future(cache, ("MacBook vs XPS",), pool, _expensive_llm_call)
            for _ in range(16)
        ]
        outputs = [f.result(timeout=2.0) for f in futures]

    assert all(o == "coalesced-response" for o in outputs)
    assert call_count == 1


def test_analytics_local_sessions_bounded_and_thread_safe() -> None:
    """AnalyticsService._local_session_counts must remain bounded and thread-safe."""
    svc = AnalyticsService(disable_cloud_clients=True)
    for i in range(_MAX_LOCAL_SESSIONS + 25):
        svc.increment_session_comparisons(f"sess-{i}")

    assert len(svc._local_session_counts) == _MAX_LOCAL_SESSIONS
    assert "sess-0" not in svc._local_session_counts
    assert f"sess-{_MAX_LOCAL_SESSIONS + 24}" in svc._local_session_counts


def test_bounded_in_memory_span_exporter_caps_spans() -> None:
    """_BoundedInMemorySpanExporter must cap retained spans at max_spans."""
    _, exporter = setup_tracing(export_to_cloud=False)
    assert isinstance(exporter, _BoundedInMemorySpanExporter)

    small_exporter = _BoundedInMemorySpanExporter(max_spans=15)
    tracer = trace.get_tracer("test.black_friday")
    spans = []
    for i in range(30):
        with tracer.start_as_current_span(f"span-{i}") as sp:
            spans.append(sp)
    small_exporter.export(spans)  # type: ignore[arg-type]
    finished = small_exporter.get_finished_spans()
    assert len(finished) == 15


def test_get_coordinator_double_checked_locking(monkeypatch) -> None:
    """_get_coordinator must instantiate MultiAgentCoordinator only once per key under concurrency."""
    _COORDINATOR_CACHE.clear()
    created_instances: list[MagicMock] = []
    init_lock = threading.Lock()
    barrier = threading.Barrier(8)

    class _FakeCoordinator:
        def __init__(self, model: str | None = None, synthesis_model: str | None = None) -> None:
            with init_lock:
                created_instances.append(MagicMock(model=model, synthesis_model=synthesis_model))

    import app.routes.compare as compare_mod

    monkeypatch.setattr(compare_mod, "MultiAgentCoordinator", _FakeCoordinator)

    def _caller() -> object:
        barrier.wait(timeout=5.0)
        return _get_coordinator("tiered-hybrid", None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        coords = list(pool.map(lambda _: _caller(), range(8)))

    assert len(created_instances) == 1
    assert len({id(c) for c in coords}) == 1
    _COORDINATOR_CACHE.clear()
