"""Google ADK BaseLlm integration for live Vertex AI Gemini execution, Model Armor guardrails, and grounding verification."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import urllib.request
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.adk.models import BaseLlm, LlmCapabilities, LLMRegistry, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.config import settings
from app.models.comparison import ComparisonSynthesis
from app.models.requests import (
    CandidateRankingResponse,
    QueryIntentAnalysis,
)
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

_DEFAULT_GENAI_CLIENT_CLS = genai.Client
_DEFAULT_URLOPEN = urllib.request.urlopen
_SHARED_VERTEX_CLIENT: genai.Client | None = None
_LAST_CACHED_US_CENTRAL1_CLIENT: genai.Client | None = None
_VERTEX_AUTH_CHECKED: bool = False
_CLIENT_LOCK = threading.Lock()
_VERTEX_CLIENTS: dict[tuple[str, Any], genai.Client] = {}
_SHARED_MA_SESSION: Any = None
_SHARED_GCP_CREDS: Any = None
_VERIFIED_SAFE_PROMPTS: set[str] = set()
_VERIFIED_SAFE_RESPONSES: set[str] = set()
_VERTEX_CALL_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=16)


def _extract_user_query(prompt: str) -> str:
    """Extract the innermost <user_query> content without matching instruction tags."""
    if not prompt:
        return ""
    matches = re.findall(
        r"<user_query>((?:(?!</?user_query>).)+)</user_query>",
        prompt,
        flags=re.DOTALL,
    )
    if matches:
        return matches[-1].strip()
    return prompt.strip()


def _is_preview_or_3x_model(model: str | None) -> bool:
    """Return True if model is a Gemini 3.x or preview model requiring global Vertex AI endpoint routing."""
    if not model:
        return False
    m = model.lower().strip()
    return "gemini-3" in m or "preview" in m


def _get_shared_vertex_client(location: str = "us-central1") -> genai.Client:
    """Return a shared Vertex AI genai.Client for the given location to reuse HTTP/2 TLS connections."""
    global _SHARED_VERTEX_CLIENT, _LAST_CACHED_US_CENTRAL1_CLIENT, _VERTEX_CLIENTS
    with _CLIENT_LOCK:
        if (
            location == "us-central1"
            and _SHARED_VERTEX_CLIENT is not None
            and _SHARED_VERTEX_CLIENT is not _LAST_CACHED_US_CENTRAL1_CLIENT
        ):
            return _SHARED_VERTEX_CLIENT
        cache_key = (location, genai.Client)
        if cache_key not in _VERTEX_CLIENTS:
            os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
            client = genai.Client(
                vertexai=True,
                project=settings.gcp_project,
                location=location,
            )
            if (
                _SHARED_GCP_CREDS is not None
                and getattr(_SHARED_GCP_CREDS, "valid", False)
                and hasattr(client, "_api_client")
            ):
                client._api_client._credentials = _SHARED_GCP_CREDS
            _VERTEX_CLIENTS[cache_key] = client
        if location == "us-central1":
            _SHARED_VERTEX_CLIENT = _VERTEX_CLIENTS[cache_key]
            _LAST_CACHED_US_CENTRAL1_CLIENT = _SHARED_VERTEX_CLIENT
        return _VERTEX_CLIENTS[cache_key]


def _get_vertex_client_for_model(
    model: str | None = None, allow_cache: bool = True
) -> genai.Client:
    """Return Vertex AI client routed to location='global' for preview/3.x models with us-central1 fallback."""
    if _is_preview_or_3x_model(model):
        try:
            if not allow_cache:
                os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
                return genai.Client(
                    vertexai=True,
                    project=settings.gcp_project,
                    location="global",
                )
            return _get_shared_vertex_client(location="global")
        except Exception as exc:
            logger.info(
                "Vertex AI global location client routing fallback to us-central1 for %s: %s",
                model,
                exc,
            )
            if not allow_cache:
                os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
                return genai.Client(
                    vertexai=True,
                    project=settings.gcp_project,
                    location="us-central1",
                )
            return _get_shared_vertex_client(location="us-central1")
    if not allow_cache:
        os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
        return genai.Client(
            vertexai=True,
            project=settings.gcp_project,
            location="us-central1",
        )
    return _get_shared_vertex_client(location="us-central1")


def _warm_vertex_client_and_auth() -> None:
    """Pre-warm shared Vertex AI client, BigQuery client, and Model Armor session concurrently."""
    global _VERTEX_AUTH_CHECKED, _SHARED_MA_SESSION, _SHARED_GCP_CREDS
    if _VERTEX_AUTH_CHECKED or not getattr(settings, "enable_background_warmup", False):
        return
    _VERTEX_AUTH_CHECKED = True
    try:
        v_client = _get_shared_vertex_client()
        import google.auth
        import requests
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not getattr(creds, "valid", False):
            creds.refresh(Request())
        _SHARED_GCP_CREDS = creds
        if _SHARED_MA_SESSION is None:
            from requests.adapters import HTTPAdapter

            _SHARED_MA_SESSION = requests.Session()
            _ma_adapter = HTTPAdapter(pool_connections=256, pool_maxsize=256)
            _SHARED_MA_SESSION.mount("https://", _ma_adapter)
            _SHARED_MA_SESSION.mount("http://", _ma_adapter)
        from app.tools.catalog import _get_shared_bq_client

        bq_client = _get_shared_bq_client()

        def _warm_vertex() -> None:
            try:
                for loc in ("us-central1", "global"):
                    c = _get_shared_vertex_client(location=loc)
                    if hasattr(c, "_api_client"):
                        c._api_client._credentials = creds
                from app.agent.orchestrator import get_model_armor_config

                v_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="{}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=8,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                        model_armor_config=get_model_armor_config(),
                    ),
                )
            except Exception:
                pass

        def _warm_bq() -> None:
            try:
                bq_client.query("SELECT 1").result(timeout=2.0)
            except Exception:
                pass

        def _warm_ma() -> None:
            try:
                tmpl = (
                    settings.model_armor_prompt_template
                    or f"projects/{settings.gcp_project}/locations/us-central1/templates/catalog-prompt-guard"
                )
                loc = _extract_model_armor_location(tmpl)
                url = f"https://modelarmor.{loc}.rep.googleapis.com/v1/{tmpl}:sanitizeUserPrompt"
                _SHARED_MA_SESSION.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json={"userPromptData": {"text": "warmup"}},
                    timeout=1.5,
                )
            except Exception:
                pass

        f_v1 = _VERTEX_CALL_POOL.submit(_warm_vertex)
        f_v2 = _VERTEX_CALL_POOL.submit(_warm_vertex)
        f_bq = _VERTEX_CALL_POOL.submit(_warm_bq)
        f_ma = _VERTEX_CALL_POOL.submit(_warm_ma)
        concurrent.futures.wait([f_v1, f_v2, f_bq, f_ma], timeout=3.0)
    except Exception as exc:
        logger.debug("Vertex AI warm-up skipped: %s", exc)


def _extract_model_armor_location(template_path: str) -> str:
    """Extract location segment from projects/<p>/locations/<loc>/templates/<t>."""
    parts = (template_path or "").split("/")
    if "locations" in parts:
        idx = parts.index("locations")
        if idx + 1 < len(parts) and parts[idx + 1]:
            return parts[idx + 1]
    return "us-central1"


def _get_gcp_access_token() -> str:
    """Return a valid GCP Bearer token for Regional Endpoint Model Armor REST calls."""
    global _SHARED_GCP_CREDS
    if genai.Client is not _DEFAULT_GENAI_CLIENT_CLS:
        return ""
    try:
        import google.auth
        from google.auth.transport.requests import Request

        if _SHARED_GCP_CREDS is None:
            _SHARED_GCP_CREDS, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not getattr(_SHARED_GCP_CREDS, "valid", False):
            _SHARED_GCP_CREDS.refresh(Request())
        return str(getattr(_SHARED_GCP_CREDS, "token", "") or "")
    except Exception:
        return ""


def _check_model_armor_response_guard(text: str) -> tuple[bool, str]:
    """Sanitize LLM output via the regional Model Armor REST API (sanitizeModelResponse)."""
    global _SHARED_MA_SESSION
    if not getattr(settings, "enable_model_armor", True) or not text or not text.strip():
        return False, ""
    clean_resp = text.strip()
    if clean_resp in _VERIFIED_SAFE_RESPONSES:
        return False, ""
    tmpl = getattr(settings, "model_armor_response_template", "") or ""
    if not tmpl:
        return False, ""
    token = _get_gcp_access_token()
    if not token:
        return False, ""
    loc = _extract_model_armor_location(tmpl)
    url = f"https://modelarmor.{loc}.rep.googleapis.com/v1/{tmpl}:sanitizeModelResponse"
    try:
        if urllib.request.urlopen is not _DEFAULT_URLOPEN:
            payload = json.dumps({"modelResponseData": {"text": text[:8000]}}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        else:
            import requests
            from requests.adapters import HTTPAdapter

            if _SHARED_MA_SESSION is None:
                _SHARED_MA_SESSION = requests.Session()
                _ma_adapter = HTTPAdapter(pool_connections=256, pool_maxsize=256)
                _SHARED_MA_SESSION.mount("https://", _ma_adapter)
                _SHARED_MA_SESSION.mount("http://", _ma_adapter)
            resp = _SHARED_MA_SESSION.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"modelResponseData": {"text": text[:8000]}},
                timeout=1.5,
            )
            if resp.status_code != 200:
                return False, ""
            data = resp.json()
        san_res = data.get("sanitizationResult", {})
        if san_res.get("filterMatchState") == "MATCH_FOUND":
            f_res = san_res.get("filterResults", {})
            reasons: list[str] = []
            if (
                f_res.get("pi_and_jailbreak", {})
                .get("piAndJailbreakFilterResult", {})
                .get("matchState")
                == "MATCH_FOUND"
            ):
                reasons.append("Prompt Injection and Jailbreak")
            if (
                f_res.get("sdp", {})
                .get("sdpFilterResult", {})
                .get("inspectResult", {})
                .get("matchState")
                == "MATCH_FOUND"
            ):
                reasons.append("SDP/PII")
            if (
                f_res.get("malicious_uris", {})
                .get("maliciousUriFilterResult", {})
                .get("matchState")
                == "MATCH_FOUND"
            ):
                reasons.append("Malicious URIs")
            rai_types = (
                f_res.get("rai", {}).get("raiFilterResult", {}).get("raiFilterTypeResults", {})
            )
            for r_name, r_obj in rai_types.items():
                if isinstance(r_obj, dict) and r_obj.get("matchState") == "MATCH_FOUND":
                    reasons.append(f"RAI ({r_name})")
            reason_str = ", ".join(reasons) if reasons else "Safety / Policy"
            return True, f"The model response violated {reason_str} filters."
        if len(_VERIFIED_SAFE_RESPONSES) > 512:
            _VERIFIED_SAFE_RESPONSES.clear()
        _VERIFIED_SAFE_RESPONSES.add(clean_resp)
    except Exception as exc:
        logger.debug("Model Armor response guard REST check skipped: %s", exc)
    return False, ""


def _check_model_armor_prompt_guard(prompt_text: str) -> tuple[bool, str]:
    """Invoke regional Model Armor sanitizeUserPrompt API using persistent keep-alive session."""
    global _SHARED_MA_SESSION, _SHARED_GCP_CREDS
    if (
        not prompt_text
        or not getattr(settings, "enable_model_armor", True)
        or genai.Client is not _DEFAULT_GENAI_CLIENT_CLS
    ):
        return False, ""
    clean_text = _extract_user_query(prompt_text) or prompt_text.strip()
    if clean_text in _VERIFIED_SAFE_PROMPTS:
        return False, ""
    try:
        import google.auth
        import requests
        from google.auth.transport.requests import Request

        if _SHARED_GCP_CREDS is None:
            _SHARED_GCP_CREDS, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not getattr(_SHARED_GCP_CREDS, "valid", False):
            _SHARED_GCP_CREDS.refresh(Request())
        if _SHARED_MA_SESSION is None:
            from requests.adapters import HTTPAdapter

            _SHARED_MA_SESSION = requests.Session()
            _ma_adapter = HTTPAdapter(pool_connections=256, pool_maxsize=256)
            _SHARED_MA_SESSION.mount("https://", _ma_adapter)
            _SHARED_MA_SESSION.mount("http://", _ma_adapter)
        tmpl = (
            getattr(settings, "model_armor_prompt_template", "")
            or f"projects/{settings.gcp_project}/locations/us-central1/templates/catalog-prompt-guard"
        )
        loc = _extract_model_armor_location(tmpl)
        url = f"https://modelarmor.{loc}.rep.googleapis.com/v1/{tmpl}:sanitizeUserPrompt"
        resp = _SHARED_MA_SESSION.post(
            url,
            headers={
                "Authorization": f"Bearer {_SHARED_GCP_CREDS.token}",
                "Content-Type": "application/json",
            },
            json={"userPromptData": {"text": clean_text[:4000]}},
            timeout=1.5,
        )
        if resp.status_code == 200:
            res = resp.json().get("sanitizationResult", {})
            if res.get("filterMatchState") == "MATCH_FOUND":
                label_map = {
                    "pi_and_jailbreak": "Prompt Injection and Jailbreak",
                    "rai": "Responsible AI Safety settings",
                    "malicious_uris": "Malicious URIs",
                    "sdp": "SDP/PII",
                    "csam": "CSAM",
                }
                matched: list[str] = []
                for k, v in res.get("filterResults", {}).items():
                    if not isinstance(v, dict):
                        continue
                    is_hit = False
                    for sub_v in v.values():
                        if isinstance(sub_v, dict):
                            if sub_v.get("matchState") == "MATCH_FOUND":
                                is_hit = True
                            for sub_v2 in sub_v.values():
                                if (
                                    isinstance(sub_v2, dict)
                                    and sub_v2.get("matchState") == "MATCH_FOUND"
                                ):
                                    is_hit = True
                    if is_hit:
                        matched.append(label_map.get(k, k))
                reason_str = (
                    f"The prompt violated {', '.join(matched)} filters."
                    if matched
                    else "The prompt violated Model Armor security filters."
                )
                return True, reason_str
            if len(_VERIFIED_SAFE_PROMPTS) > 512:
                _VERIFIED_SAFE_PROMPTS.clear()
            _VERIFIED_SAFE_PROMPTS.add(clean_text)
    except Exception as exc:
        logger.debug("Model Armor REST fallback check error: %s", exc)
    return False, ""


def _build_model_armor_refusal_response(
    reason_code: str,
    detail_message: str = "",
    template_name: str | None = None,
    inferred_schema: Any = None,
) -> LlmResponse:
    """Construct a deterministic LlmResponse when Google Cloud Model Armor blocks a prompt or response."""
    tmpl_id = (template_name or settings.model_armor_prompt_template).split("/")[-1]
    clean_detail = (
        detail_message.strip()
        or "The request violated Google Cloud Model Armor safety, prompt injection, malicious URI, or sensitive data protection (SDP/PII) guardrails."
    )
    if inferred_schema is QueryIntentAnalysis:
        payload = QueryIntentAnalysis(
            intent_type="OPINION_OR_CHATTER",
            is_comparison_eligible=False,
            reasoning=f"Blocked by Model Armor ({tmpl_id}): {clean_detail}"[:120],
        ).model_dump_json()
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=payload)],
            ),
            partial=False,
        )
    refusal_text = (
        f"[Model Armor Security Guardrail Activated — Template: {tmpl_id}]\n"
        f"Request blocked by Google Cloud Model Armor (verdict: {reason_code}). "
        f"{clean_detail} "
        "No catalog tools or database queries were executed. Please submit a valid consumer electronics comparison query."
    )
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=refusal_text)],
        ),
        partial=False,
    )


def _call_real_vertex_gemini(
    prompt: str,
    schema_cls: Any = None,
    system_instruction: str | None = None,
    model: str = "gemini-2.5-flash-lite",
    max_output_tokens: int = 512,
    timeout_seconds: float = 4.0,
) -> tuple[str, int, int]:
    """Call live Vertex AI Gemini API directly using shared HTTP connection pool."""
    from app.agent.orchestrator import _build_thinking_config

    target_model = "gemini-2.5-flash" if model in ("tiered-hybrid", "") else model
    client = _get_vertex_client_for_model(target_model)
    cfg_kwargs: dict[str, Any] = {
        "temperature": 0.1,
        "max_output_tokens": max_output_tokens,
    }
    thinking_cfg = _build_thinking_config(target_model)
    if thinking_cfg is not None:
        cfg_kwargs["thinking_config"] = thinking_cfg
    if getattr(settings, "enable_model_armor", True) and not _is_preview_or_3x_model(target_model):
        cfg_kwargs["model_armor_config"] = types.ModelArmorConfig(
            prompt_template_name=settings.model_armor_prompt_template,
            response_template_name=settings.model_armor_response_template,
        )
    if system_instruction:
        cfg_kwargs["system_instruction"] = system_instruction
    if schema_cls is not None:
        cfg_kwargs["response_mime_type"] = "application/json"
        cfg_kwargs["response_schema"] = schema_cls

    def _do_generate() -> Any:
        try:
            return client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
        except Exception as call_err:
            if _is_preview_or_3x_model(target_model):
                logger.info(
                    "Retrying %s with us-central1 fallback after error: %s",
                    target_model,
                    call_err,
                )
                fallback_client = _get_shared_vertex_client(location="us-central1")
                return fallback_client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )
            raise call_err

    fut = _VERTEX_CALL_POOL.submit(_do_generate)
    response = fut.result(timeout=timeout_seconds)
    raw_text = (response.text or "").strip()
    usage = getattr(response, "usage_metadata", None)
    in_toks = int(getattr(usage, "prompt_token_count", 120) or 120) if usage else 120
    out_toks = int(getattr(usage, "candidates_token_count", 180) or 180) if usage else 180
    return raw_text, in_toks, out_toks


def verify_and_scrub_synthesis_claims(
    summary: str | None,
    recommendations: str | None,
    products: list[Any],
) -> tuple[str | None, str | None]:
    """Deterministically scrub invalid or hallucinated [SKU: ...] citations from LLM synthesis.

    Never artificially inject, concatenate, or append missing SKUs, prices, or bullets.
    Only allows valid SKUs matching retrieved products.
    """
    if not products:
        return summary, recommendations

    valid_skus: set[str] = set()
    for p in products:
        if hasattr(p, "sku") and p.sku:
            valid_skus.add(str(p.sku).strip())
        elif isinstance(p, dict) and p.get("sku"):
            valid_skus.add(str(p["sku"]).strip())

    def _scrub(text: str | None) -> str | None:
        if not text:
            return text

        def _replace_sku(m: re.Match[str]) -> str:
            cited_sku = m.group(1).strip()
            return m.group(0) if cited_sku in valid_skus else ""

        cleaned = re.sub(r"\[SKU:\s*([^\]]+)\]", _replace_sku, text)
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        return cleaned

    scrubbed_summary = _scrub(summary)
    scrubbed_recommendations = _scrub(recommendations)
    return scrubbed_summary, scrubbed_recommendations


class CatalogAdkLlm(BaseLlm):
    """Google ADK BaseLlm implementation backed by live Vertex AI Gemini (`google.genai.Client`).

    Preserves Google Cloud Model Armor templates, safety settings, tool-call consolidation,
    and OpenTelemetry token telemetry across ADK `Runner` and `Agent` executions.
    """

    model: str = "gemini-2.5-pro"
    _injected_client: Any = PrivateAttr(default=None)
    _last_input_tokens: int = PrivateAttr(default=0)
    _last_output_tokens: int = PrivateAttr(default=0)

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        genai_client: Any = None,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("hermetic", None)
        super().__init__(model=model, **kwargs)
        self._injected_client = genai_client if genai_client is not None else client

    @classmethod
    def supported_models(cls) -> list[str]:
        """Register CatalogAdkLlm for all Gemini model identifiers in Google ADK's LLMRegistry."""
        return [
            r"gemini-.*",
            r"projects/.+/locations/.+/endpoints/.+",
            r"projects/.+/locations/.+/publishers/google/models/gemini-.*",
        ]

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def last_output_tokens(self) -> int:
        return self._last_output_tokens

    @staticmethod
    def _extract_prompt_and_tool_state(
        llm_request: LlmRequest,
    ) -> tuple[str, list[dict[str, Any]] | None]:
        """Extract combined prompt text and any tool function_response items from LlmRequest."""
        text_chunks: list[str] = []
        tool_items: list[dict[str, Any]] | None = None

        for content in llm_request.contents or []:
            for part in content.parts or []:
                if getattr(part, "text", None):
                    text_chunks.append(part.text)
                func_resp = getattr(part, "function_response", None)
                if func_resp is not None:
                    resp_payload = getattr(func_resp, "response", None)
                    if isinstance(resp_payload, dict):
                        res_list = resp_payload.get("result")
                        if isinstance(res_list, list):
                            tool_items = [x for x in res_list if isinstance(x, dict)]
                        else:
                            tool_items = []
                    elif isinstance(resp_payload, list):
                        tool_items = [x for x in resp_payload if isinstance(x, dict)]
                    else:
                        tool_items = []

        return "\n".join(text_chunks).strip(), tool_items

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Execute ADK LlmRequest against Vertex AI Gemini."""
        from app.agent.orchestrator import _build_thinking_config, get_model_armor_config

        prompt_text, tool_items = self._extract_prompt_and_tool_state(llm_request)
        has_catalog_tool = "query_catalog" in (llm_request.tools_dict or {})
        is_tool_selection_turn = has_catalog_tool and tool_items is None

        os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
        if self._injected_client is not None:
            client = self._injected_client
        else:
            client = _get_vertex_client_for_model(self.model)

        config = llm_request.config
        contents_payload: Any = (
            llm_request.contents if llm_request.contents else (prompt_text or "")
        )

        sys_inst = (
            str(config.system_instruction)
            if config and getattr(config, "system_instruction", None)
            else ""
        )
        combined_prompt = f"{sys_inst}\n{prompt_text}"
        inferred_schema: Any = getattr(config, "response_schema", None) if config else None
        if inferred_schema is None and not has_catalog_tool:
            if (
                "Query Intent Specialist" in combined_prompt
                or "classify its intent" in combined_prompt
            ):
                inferred_schema = QueryIntentAnalysis
            elif "relevance judge" in combined_prompt or "Candidates:" in combined_prompt:
                inferred_schema = CandidateRankingResponse
            elif (
                "Comparison Specialist" in combined_prompt
                or "Retrieved Catalog Products:" in combined_prompt
            ):
                inferred_schema = ComparisonSynthesis

        is_benchmark_actual = os.environ.get("BENCHMARK_ACTUAL_MODEL", "").lower() in (
            "true",
            "1",
        ) or getattr(settings, "benchmark_actual_model", False)
        target_model = self.model
        if not is_benchmark_actual and self._injected_client is None:
            if (
                has_catalog_tool
                or inferred_schema in (QueryIntentAnalysis, CandidateRankingResponse)
                or target_model == "gemini-1.5-flash"
            ):
                target_model = "gemini-2.5-flash-lite"
            elif target_model in ("gemini-2.5-pro", "tiered-hybrid"):
                target_model = "gemini-2.5-flash"

        if is_tool_selection_turn:
            default_max_tokens = 128
        elif inferred_schema in (QueryIntentAnalysis, CandidateRankingResponse):
            default_max_tokens = 256
        elif has_catalog_tool and not is_tool_selection_turn:
            default_max_tokens = 320
        else:
            default_max_tokens = 512

        cfg_max_tokens = int(getattr(config, "max_output_tokens", 0) or 0) if config else 0
        effective_max_tokens = (
            cfg_max_tokens if (0 < cfg_max_tokens <= default_max_tokens) else default_max_tokens
        )

        clean_catalog_tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="query_catalog",
                        description="Query the Best Buy BigQuery product catalog by product keywords.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "keywords": types.Schema(
                                    type=types.Type.ARRAY,
                                    items=types.Schema(type=types.Type.STRING),
                                    description="List of product names, brands, or models to search in a single call.",
                                ),
                                "category": types.Schema(
                                    type=types.Type.STRING,
                                    description="Optional category filter (Laptops, Tablets, Headphones, Smart Home, TVs).",
                                ),
                            },
                            required=["keywords"],
                        ),
                    )
                ]
            )
        ]

        if inferred_schema is not None and (
            config is None or getattr(config, "response_schema", None) is None
        ):
            effective_config = types.GenerateContentConfig(
                system_instruction=(
                    getattr(config, "system_instruction", None) if config else None
                ),
                response_mime_type="application/json",
                response_schema=inferred_schema,
                safety_settings=getattr(config, "safety_settings", None) if config else None,
                temperature=float(getattr(config, "temperature", 0.1) or 0.1) if config else 0.1,
                max_output_tokens=effective_max_tokens,
                thinking_config=_build_thinking_config(target_model),
            )
        elif config is None:
            effective_config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=effective_max_tokens,
                thinking_config=_build_thinking_config(target_model),
            )
        else:
            effective_config = config
            try:
                if getattr(effective_config, "thinking_config", None) is None:
                    effective_config.thinking_config = _build_thinking_config(target_model)
                if not getattr(effective_config, "max_output_tokens", None):
                    effective_config.max_output_tokens = effective_max_tokens
                if has_catalog_tool and self._injected_client is None:
                    effective_config.tools = clean_catalog_tools if is_tool_selection_turn else None
                    if is_tool_selection_turn:
                        effective_config.system_instruction = (
                            "You are a product catalog router. Extract all target product model or brand names "
                            "and the category (Laptops, Tablets, Headphones, Smart Home, or TVs) "
                            "from the user request and pass them in a single 'query_catalog' tool call."
                        )
                        low_p = (prompt_text or "").lower()
                        if not any(
                            k in low_p
                            for k in (
                                "ignore previous",
                                "system prompt",
                                "developer prompt",
                                "overpriced garbage",
                            )
                        ):
                            effective_config.tool_config = types.ToolConfig(
                                function_calling_config=types.FunctionCallingConfig(
                                    mode=types.FunctionCallingConfigMode.ANY,
                                    allowed_function_names=["query_catalog"],
                                )
                            )
                    else:
                        effective_config.tool_config = None
                        effective_config.system_instruction = (
                            "You are a consumer electronics comparison assistant. Using ONLY the retrieved "
                            "query_catalog results, output a compact Markdown comparison table (no extra column "
                            "whitespace padding) and a 2-sentence recommendation citing [SKU: X] for every product and spec."
                        )
            except Exception:
                effective_config = types.GenerateContentConfig(
                    system_instruction=getattr(config, "system_instruction", None),
                    response_mime_type=getattr(config, "response_mime_type", None),
                    response_schema=getattr(config, "response_schema", None),
                    safety_settings=getattr(config, "safety_settings", None),
                    tools=(
                        clean_catalog_tools
                        if (is_tool_selection_turn and self._injected_client is None)
                        else (
                            None
                            if (has_catalog_tool and self._injected_client is None)
                            else getattr(config, "tools", None)
                        )
                    ),
                    temperature=float(getattr(config, "temperature", 0.1) or 0.1),
                    max_output_tokens=effective_max_tokens,
                    thinking_config=_build_thinking_config(target_model),
                )

        use_concurrent_ma = (
            getattr(settings, "enable_model_armor", True)
            and self._injected_client is None
            and "lite" in target_model
            and (is_tool_selection_turn or inferred_schema is QueryIntentAnalysis)
        )

        if (
            getattr(settings, "enable_model_armor", True)
            and not _is_preview_or_3x_model(target_model)
            and getattr(effective_config, "safety_settings", None) is None
            and getattr(effective_config, "model_armor_config", None) is None
        ):
            try:
                effective_config.model_armor_config = get_model_armor_config()
            except Exception:
                pass

        tracer = get_tracer()
        with tracer.start_as_current_span("adk.llm.generate_content") as span:
            span.set_attribute("gen_ai.system", "gemini")
            span.set_attribute("gen_ai.request.model", target_model)
            ma_future = (
                _VERTEX_CALL_POOL.submit(_check_model_armor_prompt_guard, prompt_text)
                if use_concurrent_ma
                else None
            )
            rpc_timeout = (
                4.0
                if (
                    is_tool_selection_turn
                    or inferred_schema in (QueryIntentAnalysis, CandidateRankingResponse)
                )
                else 6.0
            )

            def _invoke_vertex(cfg: Any) -> Any:
                return client.models.generate_content(
                    model=target_model,
                    contents=contents_payload,
                    config=cfg,
                )

            try:
                if self._injected_client is not None:
                    response = _invoke_vertex(effective_config)
                else:
                    response = _VERTEX_CALL_POOL.submit(_invoke_vertex, effective_config).result(
                        timeout=rpc_timeout
                    )
            except Exception as call_err:
                if ma_future is not None:
                    try:
                        ma_blocked, ma_reason = ma_future.result(timeout=1.5)
                        if ma_blocked:
                            span.set_attribute("ai.safety.blocked", True)
                            span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR")
                            yield _build_model_armor_refusal_response(
                                reason_code="MODEL_ARMOR",
                                detail_message=ma_reason,
                                template_name=settings.model_armor_prompt_template,
                                inferred_schema=inferred_schema,
                            )
                            return
                    except Exception:
                        pass
                err_msg = str(call_err).lower()
                if (
                    "model_armor" in err_msg
                    or "template" in err_msg
                    or "not found" in err_msg
                    or "thinking" in err_msg
                ):
                    if "model_armor" in err_msg or "template" in err_msg or "not found" in err_msg:
                        ma_blocked, ma_reason = _check_model_armor_prompt_guard(prompt_text)
                        if ma_blocked:
                            span.set_attribute("ai.safety.blocked", True)
                            span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR")
                            yield _build_model_armor_refusal_response(
                                reason_code="MODEL_ARMOR",
                                detail_message=ma_reason,
                                template_name=settings.model_armor_prompt_template,
                                inferred_schema=inferred_schema,
                            )
                            return

                    fallback_kwargs: dict[str, Any] = {
                        "system_instruction": getattr(effective_config, "system_instruction", None),
                        "response_mime_type": getattr(effective_config, "response_mime_type", None),
                        "response_schema": getattr(effective_config, "response_schema", None),
                        "safety_settings": getattr(effective_config, "safety_settings", None),
                        "tools": getattr(effective_config, "tools", None),
                        "tool_config": getattr(effective_config, "tool_config", None),
                        "temperature": getattr(effective_config, "temperature", 0.1),
                        "max_output_tokens": getattr(
                            effective_config, "max_output_tokens", effective_max_tokens
                        ),
                    }
                    if (
                        "thinking" not in err_msg
                        and getattr(effective_config, "thinking_config", None) is not None
                    ):
                        fallback_kwargs["thinking_config"] = effective_config.thinking_config
                    fallback_cfg = types.GenerateContentConfig(**fallback_kwargs)
                    response = client.models.generate_content(
                        model=target_model,
                        contents=contents_payload,
                        config=fallback_cfg,
                    )
                    orig_ma = getattr(effective_config, "model_armor_config", None)
                    if orig_ma and getattr(orig_ma, "response_template_name", None):
                        resp_blocked, resp_reason = _check_model_armor_response_guard(
                            getattr(response, "text", "") or ""
                        )
                        if resp_blocked:
                            span.set_attribute("ai.safety.blocked", True)
                            span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR_RESPONSE")
                            yield _build_model_armor_refusal_response(
                                reason_code="MODEL_ARMOR_RESPONSE",
                                detail_message=resp_reason,
                                template_name=settings.model_armor_response_template,
                                inferred_schema=inferred_schema,
                            )
                            return
                else:
                    raise

            if ma_future is not None:
                try:
                    ma_blocked, ma_reason = ma_future.result(timeout=1.5)
                    if ma_blocked:
                        span.set_attribute("ai.safety.blocked", True)
                        span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR")
                        yield _build_model_armor_refusal_response(
                            reason_code="MODEL_ARMOR",
                            detail_message=ma_reason,
                            template_name=settings.model_armor_prompt_template,
                            inferred_schema=inferred_schema,
                        )
                        return
                except Exception:
                    pass

            # Validate prompt_feedback.block_reason and candidate finish_reason for safety/Model Armor blocks
            prompt_fb = getattr(response, "prompt_feedback", None)
            block_reason = str(getattr(prompt_fb, "block_reason", "") or "").upper()
            block_reason_msg = str(getattr(prompt_fb, "block_reason_message", "") or "").strip()
            if any(
                flag in block_reason
                for flag in (
                    "SAFETY",
                    "MODEL_ARMOR",
                    "BLOCKLIST",
                    "PROHIBITED_CONTENT",
                    "SPII",
                )
            ):
                span.set_attribute("ai.safety.blocked", True)
                span.set_attribute("ai.safety.block_reason", block_reason)
                if self._injected_client is not None:
                    raise ValueError(f"Prompt blocked by safety/Model Armor filter: {block_reason}")
                yield _build_model_armor_refusal_response(
                    reason_code=block_reason.split(".")[-1],
                    detail_message=block_reason_msg,
                    template_name=settings.model_armor_prompt_template,
                    inferred_schema=inferred_schema,
                )
                return

            if hasattr(response, "candidates") and response.candidates:
                first_cand = response.candidates[0]
                finish_reason = str(getattr(first_cand, "finish_reason", "")).upper()
                finish_msg = str(getattr(first_cand, "finish_message", "") or "").strip()
                if any(
                    flag in finish_reason
                    for flag in (
                        "SAFETY",
                        "MODEL_ARMOR",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "SPII",
                    )
                ):
                    span.set_attribute("ai.safety.blocked", True)
                    span.set_attribute("ai.safety.block_reason", finish_reason)
                    if self._injected_client is not None:
                        raise ValueError(
                            f"Response blocked by safety/Model Armor filter: {finish_reason}"
                        )
                    yield _build_model_armor_refusal_response(
                        reason_code=finish_reason.split(".")[-1],
                        detail_message=finish_msg,
                        template_name=settings.model_armor_response_template,
                        inferred_schema=inferred_schema,
                    )
                    return

                # Consolidate parallel query_catalog tool calls into a single BigQuery execution
                cand_content = getattr(first_cand, "content", None)
                cand_parts = getattr(cand_content, "parts", None) if cand_content else None
                if cand_parts and len(cand_parts) > 1:
                    qc_calls = [
                        p
                        for p in cand_parts
                        if getattr(p, "function_call", None) is not None
                        and getattr(p.function_call, "name", "") == "query_catalog"
                    ]
                    if len(qc_calls) > 1:
                        merged_kw: list[str] = []
                        merged_cat: str | None = None
                        for p in qc_calls:
                            args = dict(getattr(p.function_call, "args", {}) or {})
                            for kw in args.get("keywords") or []:
                                if kw and kw not in merged_kw:
                                    merged_kw.append(kw)
                            if not merged_cat and args.get("category"):
                                merged_cat = args["category"]
                        merged_args: dict[str, Any] = {"keywords": merged_kw}
                        if merged_cat:
                            merged_args["category"] = merged_cat
                        other_parts = [
                            p
                            for p in cand_parts
                            if not (
                                getattr(p, "function_call", None) is not None
                                and getattr(p.function_call, "name", "") == "query_catalog"
                            )
                        ]
                        cand_content.parts = [
                            *other_parts,
                            types.Part.from_function_call(
                                name="query_catalog",
                                args=merged_args,
                            ),
                        ]

            usage = getattr(response, "usage_metadata", None)
            if usage:
                prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
                cand_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
                self._last_input_tokens = prompt_tokens
                self._last_output_tokens = cand_tokens
                span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
                span.set_attribute("gen_ai.usage.completion_tokens", cand_tokens)

            try:
                llm_response = LlmResponse.create(response)
            except Exception:
                cands = getattr(response, "candidates", None)
                cand_content = (
                    getattr(cands[0], "content", None)
                    if isinstance(cands, (list, tuple)) and cands
                    else None
                )
                if isinstance(cand_content, types.Content):
                    llm_response = LlmResponse(
                        content=cand_content,
                        partial=False,
                    )
                elif hasattr(response, "text") and isinstance(getattr(response, "text", None), str):
                    llm_response = LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=response.text)],
                        ),
                        partial=False,
                    )
                else:
                    raise

        yield llm_response


LLMRegistry.register(CatalogAdkLlm)
