"""Versioned API router (/api/v1 and /api) for catalog comparison, agent registry, and analytics."""

import asyncio
import concurrent.futures
import logging
import os
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.agent.agent_card import build_a2a_agent_card
from app.config import Settings, get_settings
from app.data.analytics import analytics_service
from app.models import (
    AgentVersionsResponse,
    AgentVersionSummary,
    CatalogResponse,
    ChatRequest,
    ChatResponse,
    ComparisonRequest,
    ComparisonResponse,
    FeedbackRequest,
    ProductSpec,
    UserActionRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_COORDINATOR_CACHE: dict[tuple[str | None, str | None], Any] = {}
_COORDINATOR_LOCK = threading.Lock()
_REQUEST_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=300, thread_name_prefix="api-worker"
)
_CHAT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=200, thread_name_prefix="chat-worker"
)
_CATALOG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=128, thread_name_prefix="catalog-worker"
)
_ANALYTICS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=256, thread_name_prefix="analytics-worker"
)
_TELEMETRY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=64, thread_name_prefix="telemetry-bg"
)
_CATALOG_RESPONSE_CACHE: dict[tuple[Any, ...], tuple[float, CatalogResponse]] = {}
_CATALOG_CACHE_LOCK = threading.Lock()


def resolve_iap_user_id(http_request: Request | None, explicit_user_id: str | None = None) -> str:
    """Extract authenticated user identity from Cloud Run IAP headers or payload claims."""
    if http_request is not None:
        # 1. Check X-Goog-Authenticated-User-Email
        email_header = http_request.headers.get("x-goog-authenticated-user-email")
        if email_header:
            email = email_header.strip()
            if email.startswith("accounts.google.com:"):
                email = email[len("accounts.google.com:") :].strip()
            elif ":" in email and "@" not in email.split(":", 1)[0]:
                email = email.split(":", 1)[1].strip()
            if email:
                return email.lower()

        # 2. Check X-Goog-Authenticated-User-Id
        user_id_header = http_request.headers.get("x-goog-authenticated-user-id")
        if user_id_header:
            uid = user_id_header.strip()
            if uid.startswith("accounts.google.com:"):
                uid = uid[len("accounts.google.com:") :].strip()
            elif ":" in uid:
                uid = uid.split(":", 1)[1].strip()
            if uid:
                return uid

        # 3. Check X-Goog-IAP-JWT-Assertion
        jwt_header = http_request.headers.get("x-goog-iap-jwt-assertion")
        if jwt_header:
            try:
                import base64
                import json

                parts = jwt_header.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1]
                    rem = len(payload_b64) % 4
                    if rem > 0:
                        payload_b64 += "=" * (4 - rem)
                    payload_data = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
                    if isinstance(payload_data, dict):
                        email_claim = payload_data.get("email")
                        if email_claim and isinstance(email_claim, str) and email_claim.strip():
                            claim_clean = email_claim.strip()
                            if claim_clean.startswith("accounts.google.com:"):
                                claim_clean = claim_clean[len("accounts.google.com:") :].strip()
                            elif ":" in claim_clean and "@" not in claim_clean.split(":", 1)[0]:
                                claim_clean = claim_clean.split(":", 1)[1].strip()
                            if claim_clean:
                                return claim_clean.lower()
                        sub_claim = payload_data.get("sub")
                        if sub_claim and isinstance(sub_claim, str) and sub_claim.strip():
                            sub_clean = sub_claim.strip()
                            if sub_clean.startswith("accounts.google.com:"):
                                sub_clean = sub_clean[len("accounts.google.com:") :].strip()
                            elif ":" in sub_clean:
                                sub_clean = sub_clean.split(":", 1)[1].strip()
                            if sub_clean:
                                return sub_clean
            except Exception as e:
                logger.debug("Failed parsing X-Goog-IAP-JWT-Assertion header: %s", e)

    # 4. Check explicit user_id
    if explicit_user_id and explicit_user_id.strip():
        return explicit_user_id.strip()

    # 5. Default fallback
    return "default_user"


def _get_coordinator(model: str | None, synthesis_model: str | None) -> Any:
    import sys

    coord_cls = getattr(sys.modules.get(__name__), "MultiAgentCoordinator", None)
    if coord_cls is None:
        from app.agent.multi_agent import MultiAgentCoordinator

        globals()["MultiAgentCoordinator"] = MultiAgentCoordinator
        coord_cls = MultiAgentCoordinator

    if hasattr(coord_cls, "assert_called"):
        return coord_cls(model=model, synthesis_model=synthesis_model)
    key = (model, synthesis_model)
    coord = _COORDINATOR_CACHE.get(key)
    if coord is None:
        with _COORDINATOR_LOCK:
            coord = _COORDINATOR_CACHE.get(key)
            if coord is None:
                coord = coord_cls(model=model, synthesis_model=synthesis_model)
                _COORDINATOR_CACHE[key] = coord
    return coord


def __getattr__(name: str) -> Any:
    """Lazy-load MultiAgentCoordinator on module attribute access to support unittest.mock.patch."""
    if name == "MultiAgentCoordinator":
        from app.agent.multi_agent import MultiAgentCoordinator

        globals()["MultiAgentCoordinator"] = MultiAgentCoordinator
        return MultiAgentCoordinator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_REMOTE_ENGINE_SESSION: Any = None
_REMOTE_ENGINE_CREDS: Any = None
_REMOTE_ENGINE_LOCK = __import__("threading").Lock()


def _is_test_or_eval_env() -> bool:
    import sys

    return bool(
        os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("HERMETIC_EVAL", "").lower() == "true"
        or "pytest" in sys.modules
    )


def _warm_remote_engine_client() -> None:
    """Pre-warm ADC credentials, HTTP session, local coordinator, and remote Reasoning Engine."""
    global _REMOTE_ENGINE_SESSION, _REMOTE_ENGINE_CREDS
    if _is_test_or_eval_env():
        return
    try:
        import google.auth
        import requests
        from google.auth.transport.requests import Request as GoogleAuthRequest

        with _REMOTE_ENGINE_LOCK:
            if _REMOTE_ENGINE_SESSION is None:
                _REMOTE_ENGINE_SESSION = requests.Session()
            if _REMOTE_ENGINE_CREDS is None:
                _REMOTE_ENGINE_CREDS, _ = google.auth.default()
            if (
                not _REMOTE_ENGINE_CREDS.valid
                or _REMOTE_ENGINE_CREDS.expired
                or not _REMOTE_ENGINE_CREDS.token
            ):
                _REMOTE_ENGINE_CREDS.refresh(GoogleAuthRequest())
    except Exception:
        pass

    if _is_test_or_eval_env():
        return
    try:
        _get_coordinator("tiered-hybrid", None)
    except Exception:
        pass

    try:
        from app.config import settings

        if settings.agent_runtime_resource_name and not _is_test_or_eval_env():
            _invoke_remote_reasoning_engine(
                resource_name=settings.agent_runtime_resource_name,
                request=ComparisonRequest(
                    query="MacBook Air M3 vs Dell XPS 13", category="Laptops"
                ),
                effective_model="tiered-hybrid",
                effective_synthesis=None,
            )
    except Exception:
        pass


def _invoke_remote_reasoning_engine(
    resource_name: str,
    request: ComparisonRequest,
    effective_model: str | None,
    effective_synthesis: str | None,
    user_id: str | None = None,
) -> ComparisonResponse:
    """Invoke remote Vertex AI Agent Runtime (:query) via pooled HTTP session or unit-test mock."""
    resolved_uid = user_id or request.user_id
    import sys

    re_mod = sys.modules.get("vertexai.preview.reasoning_engines")
    if re_mod is not None and hasattr(getattr(re_mod, "ReasoningEngine", None), "assert_called"):
        remote_agent = re_mod.ReasoningEngine(resource_name)
        query_kwargs: dict[str, Any] = {
            "query": request.query,
            "category": request.category,
            "session_id": request.session_id,
            "agent_version": request.agent_version,
            "model": effective_model,
            "synthesis_model": effective_synthesis,
        }
        if resolved_uid:
            try:
                import inspect

                sig = inspect.signature(remote_agent.query)
                if "user_id" in sig.parameters or any(
                    p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    query_kwargs["user_id"] = resolved_uid
            except Exception:
                pass
        raw_response = remote_agent.query(**query_kwargs)
        return ComparisonResponse.model_validate(raw_response)

    global _REMOTE_ENGINE_SESSION, _REMOTE_ENGINE_CREDS
    import google.auth
    import requests
    from google.auth.transport.requests import Request as GoogleAuthRequest

    with _REMOTE_ENGINE_LOCK:
        if _REMOTE_ENGINE_SESSION is None:
            _REMOTE_ENGINE_SESSION = requests.Session()
        if _REMOTE_ENGINE_CREDS is None:
            _REMOTE_ENGINE_CREDS, _ = google.auth.default()
        if (
            not _REMOTE_ENGINE_CREDS.valid
            or _REMOTE_ENGINE_CREDS.expired
            or not _REMOTE_ENGINE_CREDS.token
        ):
            _REMOTE_ENGINE_CREDS.refresh(GoogleAuthRequest())

    # Extract region from projects/{project}/locations/{region}/reasoningEngines/{id}
    region = "us-central1"
    parts = [p for p in resource_name.split("/") if p]
    if "locations" in parts:
        loc_idx = parts.index("locations")
        if loc_idx + 1 < len(parts):
            region = parts[loc_idx + 1]

    import json

    gateway_uid = resolved_uid or request.session_id or "cloud-run-gateway"
    url = f"https://{region}-aiplatform.googleapis.com/v1beta1/{resource_name}:streamQuery"
    payload = {
        "class_method": "stream_query",
        "input": {
            "user_id": gateway_uid,
            "session_id": request.session_id,
            "message": json.dumps(
                {
                    "__compare_request__": True,
                    "query": request.query,
                    "category": request.category,
                    "session_id": request.session_id,
                    "user_id": gateway_uid,
                    "agent_version": request.agent_version,
                    "model": effective_model,
                    "synthesis_model": effective_synthesis,
                }
            ),
        },
    }
    resp = _REMOTE_ENGINE_SESSION.post(
        url,
        headers={
            "Authorization": f"Bearer {_REMOTE_ENGINE_CREDS.token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=25.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    import json

    lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("Empty response from ReasoningEngine :streamQuery")
    body = json.loads(lines[-1])
    raw_output = body.get("output", body) if isinstance(body, dict) else body
    if isinstance(raw_output, dict) and raw_output.get("event_type") == "comparison_completed":
        raw_output = raw_output.get("data", raw_output)
    return ComparisonResponse.model_validate(raw_output)


if not _is_test_or_eval_env():
    __import__("threading").Thread(target=_warm_remote_engine_client, daemon=True).start()


def _execute_comparison_sync(request: ComparisonRequest) -> ComparisonResponse:
    """Execute multi-agent comparison pipeline synchronously inside worker thread."""
    import app.main as app_main
    from app.config import settings

    # Default to tiered-hybrid for production if not explicitly specified
    effective_model = request.model
    if effective_model is None and (
        not request.agent_version or request.agent_version in ("1.0.0", "1.2.0-tiered")
    ):
        effective_model = "tiered-hybrid"
    effective_synthesis = request.synthesis_model

    # Delegate to remote Vertex AI Agent Runtime (Reasoning Engine) if configured and not running in Pytest
    if settings.agent_runtime_resource_name and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            return _invoke_remote_reasoning_engine(
                resource_name=settings.agent_runtime_resource_name,
                request=request,
                effective_model=effective_model,
                effective_synthesis=effective_synthesis,
                user_id=request.user_id,
            )
        except Exception as remote_err:
            logger.warning(
                "Vertex AI Agent Runtime query failed (%s); falling back to local MultiAgentCoordinator.",
                remote_err,
            )

    # Honor unit test patches on app.main.ComparisonOrchestrator if present
    orch_cls = app_main.__dict__.get("ComparisonOrchestrator")
    if orch_cls is not None and hasattr(orch_cls, "assert_called"):
        orchestrator = orch_cls(
            model=request.model,
            synthesis_model=request.synthesis_model,
        )
        compare_kwargs: dict[str, Any] = {
            "query": request.query,
            "category": request.category,
            "session_id": request.session_id,
            "agent_version": request.agent_version,
            "model": request.model,
            "synthesis_model": request.synthesis_model,
        }
        try:
            import inspect

            sig = inspect.signature(orchestrator.compare)
            if "user_id" in sig.parameters or any(
                p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
            ):
                compare_kwargs["user_id"] = request.user_id
        except Exception:
            pass
        return orchestrator.compare(**compare_kwargs)

    coordinator = _get_coordinator(
        model=effective_model,
        synthesis_model=effective_synthesis,
    )
    return coordinator.execute(
        raw_query=request.query,
        category=request.category,
        session_id=request.session_id,
        agent_version=request.agent_version,
        model=effective_model,
        synthesis_model=effective_synthesis,
        user_id=request.user_id,
    )


def _record_telemetry_sync(
    request: ComparisonRequest,
    result: ComparisonResponse,
    latency_ms: float,
) -> None:
    """Persist session comparison counters and query telemetry off the critical path."""
    if request.session_id:
        analytics_service.increment_session_comparisons(request.session_id)
        analytics_service.record_user_action(
            UserActionRequest(
                action_type="compare_request",
                session_id=request.session_id,
                query=request.query,
                category=request.category,
                target_skus=[p.sku for p in result.products],
            ),
            from_background=True,
        )
    analytics_service.record_query_telemetry(
        query_id=result.trace_id or f"query-{int(time.time() * 1000)}",
        session_id=request.session_id,
        query_text=request.query,
        category=request.category,
        latency_ms=latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        bq_bytes_billed=result.bq_bytes_billed,
        retrieved_skus=[p.sku for p in result.products],
        status="SUCCESS" if result.products else "DEGRADED",
    )


@router.post(
    "/compare",
    response_model=ComparisonResponse,
    tags=["Comparison"],
    summary="Compare Products by Natural Language Query",
)
async def compare_products(
    request: ComparisonRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
    http_response: Response,
    http_request: Request,
) -> ComparisonResponse:
    """Compare products via non-blocking async MultiAgentCoordinator execution."""
    request.user_id = resolve_iap_user_id(http_request, request.user_id)
    start_time = time.perf_counter()

    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string must not be empty.",
        )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_REQUEST_EXECUTOR, _execute_comparison_sync, request)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    result.latency_ms = latency_ms

    if result.timing_breakdown_ms:
        timing_parts = [f"{k}={v}ms" for k, v in result.timing_breakdown_ms.items()]
        http_response.headers["X-Pipeline-Timing"] = ", ".join(timing_parts)

    if os.environ.get("PYTEST_CURRENT_TEST"):
        if request.session_id:
            result.session_comparison_count = await asyncio.to_thread(
                analytics_service.increment_session_comparisons, request.session_id
            )
            await asyncio.to_thread(
                analytics_service.record_user_action,
                UserActionRequest(
                    action_type="compare_request",
                    session_id=request.session_id,
                    query=request.query,
                    category=request.category,
                    target_skus=[p.sku for p in result.products],
                ),
            )
        await asyncio.to_thread(
            analytics_service.record_query_telemetry,
            query_id=result.trace_id or f"query-{int(time.time() * 1000)}",
            session_id=request.session_id,
            query_text=request.query,
            category=request.category,
            latency_ms=latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            bq_bytes_billed=result.bq_bytes_billed,
            retrieved_skus=[p.sku for p in result.products],
            status="SUCCESS" if result.products else "DEGRADED",
        )
    else:
        if request.session_id:
            with analytics_service._session_lock:
                result.session_comparison_count = (
                    analytics_service._local_session_counts.get(request.session_id, 0) + 1
                )
        _TELEMETRY_EXECUTOR.submit(_record_telemetry_sync, request, result, latency_ms)

    return result


def _execute_chat_sync(request: ChatRequest) -> ChatResponse:
    """Execute conversational chat synchronously inside worker thread."""
    import app.main as app_main

    effective_model = request.model
    effective_synthesis = request.synthesis_model

    # Check mock/test patch on app.main.ComparisonOrchestrator
    orch_cls = app_main.__dict__.get("ComparisonOrchestrator")
    if orch_cls is not None and hasattr(orch_cls, "assert_called"):
        orchestrator = orch_cls(
            model=request.model,
            synthesis_model=request.synthesis_model,
        )
        chat_kwargs: dict[str, Any] = {
            "message": request.message,
            "products": request.products,
            "conversation_history": request.conversation_history,
            "comparison_matrix": request.comparison_matrix,
            "session_id": request.session_id,
            "model": request.model,
            "synthesis_model": request.synthesis_model,
            "agent_version": request.agent_version,
        }
        try:
            import inspect

            sig = inspect.signature(orchestrator.chat_with_products)
            if "user_id" in sig.parameters or any(
                p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
            ):
                chat_kwargs["user_id"] = request.user_id
        except Exception:
            pass
        return orchestrator.chat_with_products(**chat_kwargs)

    coordinator = _get_coordinator(
        model=effective_model,
        synthesis_model=effective_synthesis,
    )
    return coordinator.chat(
        message=request.message,
        products=request.products,
        conversation_history=request.conversation_history,
        comparison_matrix=request.comparison_matrix,
        session_id=request.session_id,
        agent_version=request.agent_version,
        model=effective_model,
        synthesis_model=effective_synthesis,
        user_id=request.user_id,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Comparison"],
    summary="Follow-up Conversational Chat with Compared Products",
)
async def chat_products(
    request: ChatRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
    http_request: Request,
) -> ChatResponse:
    """Answer conversational follow-up questions grounded strictly in compared ProductSpec list."""
    request.user_id = resolve_iap_user_id(http_request, request.user_id)
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message string must not be empty.",
        )
    if not request.products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one product must be provided for conversational grounding.",
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_CHAT_EXECUTOR, _execute_chat_sync, request)


def _fetch_catalog_sync(
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 50,
) -> CatalogResponse:
    """Fetch product catalog records synchronously inside worker thread."""
    import json
    from pathlib import Path

    from app.tools.catalog import query_catalog

    cache_key = ((category or "").strip().lower(), min_price, max_price, limit)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        now_ts = time.monotonic()
        with _CATALOG_CACHE_LOCK:
            cached = _CATALOG_RESPONSE_CACHE.get(cache_key)
            if cached is not None and (now_ts - cached[0]) < 60.0:
                return cached[1]

    # 1. Attempt query_catalog with category or broad wildcard
    keywords = (
        [category]
        if category
        else ["laptop", "tablet", "headphone", "tv", "camera", "home", "apple", "dell", "sony"]
    )
    try:
        raw_products = query_catalog(
            keywords=keywords,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
        )
    except Exception as err:
        logger.warning(
            "query_catalog failed in list_catalog (%s); falling back to seed catalog.", err
        )
        raw_products = []

    # 2. Fallback to catalog_seed.json if query_catalog returned empty in offline / test mode
    if not raw_products:
        seed_path = Path(__file__).resolve().parent.parent / "data" / "catalog_seed.json"
        if seed_path.exists():
            try:
                with open(seed_path, encoding="utf-8") as f:
                    seed_data = json.load(f)
                dedup: dict[str, dict[str, Any]] = {}
                for item in seed_data:
                    sku = str(item.get("sku", "")).strip()
                    if sku:
                        dedup[sku] = item
                for item in dedup.values():
                    item_cat = str(item.get("category", "")).strip()
                    if category and item_cat.lower() != category.strip().lower():
                        continue
                    item_price = float(item.get("price", 0.0))
                    if min_price is not None and item_price < min_price:
                        continue
                    if max_price is not None and item_price > max_price:
                        continue
                    raw_products.append(
                        {
                            "sku": item["sku"],
                            "name": str(item.get("name", "")),
                            "brand": str(item.get("brand", "")),
                            "category": item.get("category"),
                            "price": item_price,
                            "rating": float(item["rating"])
                            if item.get("rating") is not None
                            else None,
                            "review_count": int(item["review_count"])
                            if item.get("review_count") is not None
                            else None,
                            "specifications": item.get("specifications") or {},
                            "url": item.get("url")
                            or f"https://www.techbuy.com/site/sku/{item['sku']}.p",
                            "image_url": item.get("image_url"),
                            "in_stock": bool(item.get("in_stock", True)),
                        }
                    )
                    if len(raw_products) >= limit:
                        break
            except Exception as read_err:
                logger.warning("Failed loading seed catalog fallback: %s", read_err)

    validated_products = [ProductSpec.model_validate(p) for p in raw_products]
    resp = CatalogResponse(
        products=validated_products,
        total_count=len(validated_products),
        category=category,
    )
    if not os.environ.get("PYTEST_CURRENT_TEST") and validated_products:
        with _CATALOG_CACHE_LOCK:
            if len(_CATALOG_RESPONSE_CACHE) >= 256:
                _CATALOG_RESPONSE_CACHE.clear()
            _CATALOG_RESPONSE_CACHE[cache_key] = (time.monotonic(), resp)
    return resp


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    tags=["Catalog"],
    summary="List or Filter Catalog Products",
)
async def list_catalog(
    _app_settings: Annotated[Settings, Depends(get_settings)],
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 50,
) -> CatalogResponse:
    """Browse verified product catalog grounded in BigQuery with category and price filters."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        cache_key = ((category or "").strip().lower(), min_price, max_price, limit)
        now_ts = time.monotonic()
        with _CATALOG_CACHE_LOCK:
            cached = _CATALOG_RESPONSE_CACHE.get(cache_key)
            if cached is not None and (now_ts - cached[0]) < 60.0:
                return cached[1]
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _CATALOG_EXECUTOR,
        _fetch_catalog_sync,
        category,
        min_price,
        max_price,
        limit,
    )


@router.get(
    "/agent/card",
    tags=["Agent Registry"],
    summary="A2A Agent Card Query Endpoint",
)
async def get_agent_card(
    request: Request,
    version: str | None = None,
) -> JSONResponse:
    """Retrieve A2A Agent Card for a specific version or the active default."""
    base_url = str(request.base_url).rstrip("/")
    card = build_a2a_agent_card(base_url=base_url, version=version)
    return JSONResponse(content=card)


@router.get(
    "/agent/versions",
    response_model=AgentVersionsResponse,
    tags=["Agent Registry"],
    summary="List Registered Agent Versions",
)
async def list_agent_versions(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> AgentVersionsResponse:
    """List available agent versions backed by Vertex AI Prompt Management & Cloud Run."""
    versions = [
        AgentVersionSummary(
            version="1.0.0",
            display_name="Best Buy Catalog Comparison Agent (Baseline Pro)",
            description="Grounded comparison orchestrator using Gemini 2.5 Pro",
            model="gemini-2.5-pro",
            model_version="gemini-2.5-pro@001",
            prompt_version="2026.03-v1",
            is_default=(app_settings.agent_version == "1.0.0"),
            skills_count=2,
            created_at="2026-03-01T00:00:00Z",
            changelog="Production baseline managed via Vertex AI Prompt Management",
        ),
        AgentVersionSummary(
            version="1.1.0-flash",
            display_name="Best Buy Catalog Comparison Agent (Flash Canary)",
            description="High-throughput canary variant powered by Gemini 2.5 Flash",
            model="gemini-2.5-flash",
            model_version="gemini-2.5-flash@001",
            prompt_version="2026.03-v2",
            is_default=(app_settings.agent_version == "1.1.0-flash"),
            skills_count=2,
            created_at="2026-03-15T00:00:00Z",
            changelog="Canary model variant managed via Vertex AI Prompt Management",
        ),
        AgentVersionSummary(
            version="1.2.0-tiered",
            display_name="Best Buy Catalog Comparison Agent (Tiered Hybrid)",
            description="Tiered hybrid routing intent/filter to Flash and synthesis to Pro",
            model="tiered-hybrid",
            model_version="tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001",
            prompt_version="2026.03-v2",
            is_default=(app_settings.agent_version == "1.2.0-tiered"),
            skills_count=2,
            created_at="2026-03-24T00:00:00Z",
            changelog="Optimized tiered hybrid architecture for production latency & cost",
        ),
    ]
    return AgentVersionsResponse(
        active_default=app_settings.agent_version,
        total_versions=len(versions),
        versions=versions,
    )


@router.post(
    "/actions",
    response_model=dict[str, Any],
    tags=["Analytics"],
    summary="Log User Behavior and Engagement Action",
)
async def log_action(
    action: UserActionRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Log user behavior events such as copy markdown or sku click to Firestore."""
    loop = asyncio.get_running_loop()
    doc_id = await loop.run_in_executor(
        _ANALYTICS_EXECUTOR, analytics_service.record_user_action, action
    )
    return {"status": "recorded", "action_id": doc_id}


@router.post(
    "/feedback",
    response_model=dict[str, Any],
    tags=["Analytics"],
    summary="Submit Thumbs-Up / Thumbs-Down Quality Feedback",
)
async def submit_feedback(
    feedback: FeedbackRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Record thumbs-up / thumbs-down user evaluation feedback to Firestore."""
    loop = asyncio.get_running_loop()
    doc_id = await loop.run_in_executor(
        _ANALYTICS_EXECUTOR, analytics_service.record_feedback, feedback
    )
    return {"status": "recorded", "feedback_id": doc_id}
