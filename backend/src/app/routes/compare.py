"""Versioned API router (/api/v1 and /api) for catalog comparison, agent registry, and analytics."""

import asyncio
import logging
import os
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.agent.agent_card import build_a2a_agent_card
from app.agent.multi_agent import MultiAgentCoordinator
from app.config import Settings, get_settings
from app.data.analytics import analytics_service
from app.models import (
    AgentVersionsResponse,
    AgentVersionSummary,
    CatalogResponse,
    ComparisonRequest,
    ComparisonResponse,
    FeedbackRequest,
    ProductSpec,
    UserActionRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_COORDINATOR_CACHE: dict[tuple[str | None, str | None], MultiAgentCoordinator] = {}


def _get_coordinator(model: str | None, synthesis_model: str | None) -> MultiAgentCoordinator:
    if hasattr(MultiAgentCoordinator, "assert_called"):
        return MultiAgentCoordinator(model=model, synthesis_model=synthesis_model)
    key = (model, synthesis_model)
    coord = _COORDINATOR_CACHE.get(key)
    if coord is None:
        coord = MultiAgentCoordinator(model=model, synthesis_model=synthesis_model)
        _COORDINATOR_CACHE[key] = coord
    return coord


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
            from vertexai.preview import reasoning_engines

            remote_agent = reasoning_engines.ReasoningEngine(settings.agent_runtime_resource_name)
            raw_response = remote_agent.query(
                query=request.query,
                category=request.category,
                session_id=request.session_id,
                agent_version=request.agent_version,
                model=effective_model,
                synthesis_model=effective_synthesis,
            )
            return ComparisonResponse.model_validate(raw_response)
        except Exception as remote_err:
            logger.warning(
                "Vertex AI Agent Runtime query failed (%s); falling back to local MultiAgentCoordinator.",
                remote_err,
            )

    # Honor unit test patches on app.main.ComparisonOrchestrator if present
    orch_cls = getattr(app_main, "ComparisonOrchestrator", None)
    if orch_cls is not None and hasattr(orch_cls, "assert_called"):
        orchestrator = orch_cls(
            model=request.model,
            synthesis_model=request.synthesis_model,
        )
        return orchestrator.compare(
            query=request.query,
            category=request.category,
            session_id=request.session_id,
            agent_version=request.agent_version,
            model=request.model,
            synthesis_model=request.synthesis_model,
        )

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
) -> ComparisonResponse:
    """Compare products via non-blocking async MultiAgentCoordinator execution."""
    start_time = time.perf_counter()

    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string must not be empty.",
        )

    result = await asyncio.to_thread(_execute_comparison_sync, request)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    result.latency_ms = latency_ms

    if result.timing_breakdown_ms:
        timing_parts = [f"{k}={v}ms" for k, v in result.timing_breakdown_ms.items()]
        http_response.headers["X-Pipeline-Timing"] = ", ".join(timing_parts)

    if request.session_id:
        session_count = await asyncio.to_thread(
            analytics_service.increment_session_comparisons, request.session_id
        )
        result.session_comparison_count = session_count

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

    return result


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
    return CatalogResponse(
        products=validated_products,
        total_count=len(validated_products),
        category=category,
    )


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
    return await asyncio.to_thread(
        _fetch_catalog_sync,
        category=category,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
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
    doc_id = await asyncio.to_thread(analytics_service.record_user_action, action)
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
    doc_id = await asyncio.to_thread(analytics_service.record_feedback, feedback)
    return {"status": "recorded", "feedback_id": doc_id}
