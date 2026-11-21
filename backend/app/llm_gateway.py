"""LiteLLM Router setup and deterministic key-priority dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from litellm import Router

from app.config import settings


MODEL_GROUP = "lyftr-chat"
logger = logging.getLogger(__name__)


def _deployment_model(key_id: str, api_key: str) -> str:
    """Choose the provider model for an explicitly named or recognizable key."""
    provider_hint = key_id.lower().replace("-", "_")
    is_gemini = (
        provider_hint in {"gemini", "google", "google_ai", "google_ai_studio"}
        or provider_hint.startswith("gemini_")
        or api_key.startswith("AIza")
    )
    if is_gemini:
        model = settings.gemini_model.strip()
        return model if model.startswith("gemini/") else f"gemini/{model}"

    model = settings.llm_model.strip()
    return model if model.startswith("openai/") else f"openai/{model}"


class AllProvidersUnavailable(Exception):
    """Raised when no configured provider key can complete a request."""


@dataclass(frozen=True)
class GatewayResult:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int
    cache_hit: bool


def _deployments(
    simulated_failures: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    simulated_failures = simulated_failures or {}
    deployments = []
    for order, (key_id, api_key) in enumerate(settings.parse_api_keys().items(), start=1):
        litellm_params: dict[str, Any] = {
            "model": _deployment_model(key_id, api_key),
            "api_key": api_key,
            "order": order,
        }
        if key_id in simulated_failures:
            status_code = simulated_failures[key_id]
            litellm_params["mock_response"] = (
                "litellm.RateLimitError"
                if status_code == 429
                else "litellm.InternalServerError"
            )
        deployment: dict[str, Any] = {
            "model_name": MODEL_GROUP,
            "litellm_params": litellm_params,
            # Stable IDs let the gateway report which configured key won.
            "model_info": {"id": key_id, "cooldown_time": 0},
        }
        deployments.append(deployment)
    return deployments


def _make_router(
    simulated_failures: dict[str, int] | None = None,
) -> Router:
    model_list = _deployments(simulated_failures)
    if not model_list:
        raise AllProvidersUnavailable("all providers unavailable")
    return Router(
        model_list=model_list,
        num_retries=0,
        max_fallbacks=max(0, len(model_list) - 1),
        disable_cooldowns=True,
        cache_responses=settings.cache_enabled and not bool(simulated_failures),
    )


router: Router | None = None


async def complete(
    messages: list[dict[str, str]],
    simulated_failures: dict[str, int] | None = None,
) -> GatewayResult:
    """Complete one request, honoring key order and optional simulated failures.

    Router order fallbacks try lower-priority deployments after a retryable
    provider failure. Simulated provider errors are injected into a
    request-scoped Router deployment config, leaving shared Router state and
    configured API keys unchanged.
    """
    failures = simulated_failures or {}
    configured = settings.parse_api_keys()
    if not settings.enable_failure_simulation:
        failures = {}
    else:
        failures = {key_id: status for key_id, status in failures.items() if key_id in configured}
    if not configured:
        raise AllProvidersUnavailable("all providers unavailable")

    global router
    if failures:
        # LiteLLM's mock_response is configured per deployment and raises a
        # provider-shaped error inside Router, which then runs normal fallback.
        # This request-scoped Router retains the real key values and never
        # forwards those keys for simulated failures.
        active_router = _make_router(failures)
    else:
        if router is None:
            router = _make_router()
        active_router = router
    try:
        response = await active_router.acompletion(
            model=MODEL_GROUP,
            messages=messages,
            max_tokens=settings.llm_max_output_tokens,
        )
    except Exception as exc:
        logger.warning(
            "LLM provider attempts failed (exception_type=%s, deployments=%s)",
            type(exc).__name__,
            [item["litellm_params"]["model"] for item in _deployments()],
        )
        raise AllProvidersUnavailable("all providers unavailable") from exc

    hidden = getattr(response, "_hidden_params", {}) or {}
    key_id = hidden.get("model_id")
    cache_hit = hidden.get("cache_hit") is True
    if cache_hit:
        key_id = None
    elif key_id not in configured:
        # LiteLLM responses expose the selected deployment id in hidden params.
        # Treat missing attribution as a gateway error rather than misreporting.
        raise AllProvidersUnavailable("provider identity unavailable")
    usage = getattr(response, "usage", None)
    return GatewayResult(
        reply=response.choices[0].message.content or "",
        model=getattr(response, "model", settings.llm_model),
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        key_id=key_id,
        fallback_attempts=0 if cache_hit else list(configured).index(key_id),
        cache_hit=cache_hit,
    )


def parse_simulation_header(header: str | None) -> dict[str, int]:
    """Parse `key_1=429,key_2=500` or `*=429` into per-key statuses."""
    if not header:
        return {}
    result: dict[str, int] = {}
    for item in header.split(","):
        key, separator, status = item.strip().partition("=")
        if not separator or not key or not status.isdigit():
            raise ValueError("invalid X-Simulate-Failure header")
        code = int(status)
        if code < 400 or code > 599:
            raise ValueError("simulated status must be between 400 and 599")
        result[key] = code
    if "*" in result:
        return {key: result["*"] for key in settings.parse_api_keys()}
    unknown = set(result) - set(settings.parse_api_keys())
    if unknown:
        raise ValueError(f"unknown simulated key: {sorted(unknown)[0]}")
    return result
