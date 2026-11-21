"""Stage 2 API tests use LiteLLM's mock_response support, never live APIs."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from litellm import Router


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@pytest.fixture
def mock_litellm_router(monkeypatch):
    from app import llm_gateway

    def make_router(simulated_failures=None):
        failures = simulated_failures or {}
        deployments = llm_gateway._deployments(failures)
        for deployment in deployments:
            key_id = deployment["model_info"]["id"]
            if key_id not in failures:
                deployment["litellm_params"]["mock_response"] = "mocked Lyftr response"
        return Router(
            model_list=deployments,
            num_retries=0,
            max_fallbacks=max(0, len(deployments) - 1),
            disable_cooldowns=True,
            cache_responses=True,
        )

    monkeypatch.setattr(llm_gateway, "_make_router", make_router)
    monkeypatch.setattr(llm_gateway, "router", None)
    return llm_gateway


def test_chat_success_has_exact_metadata(client: TestClient, mock_litellm_router):
    session_id = _unique("chat-success")
    response = client.post(
        "/chat",
        json={"session_id": session_id, "message": _unique("hello"), "system_prompt": "Be concise."},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"session_id", "reply", "metadata"}
    assert body["session_id"] == session_id
    assert body["reply"] == "mocked Lyftr response"
    assert set(body["metadata"]) == {
        "resolution_source",
        "model",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "key_id",
        "fallback_attempts",
    }
    assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert body["metadata"]["key_id"] == "key_1"
    assert body["metadata"]["fallback_attempts"] == 0
    assert isinstance(body["metadata"]["input_tokens"], int)
    assert isinstance(body["metadata"]["output_tokens"], int)
    assert body["metadata"]["latency_ms"] >= 0


def test_chat_sends_complete_multiturn_context(client, mock_litellm_router, monkeypatch):
    from app import routes
    from app.llm_gateway import GatewayResult

    session_id = _unique("multi-turn")
    seen_messages = []

    async def capture(messages, simulated_failures=None):
        seen_messages.append(messages)
        return GatewayResult(
            reply=f"reply-{len(seen_messages)}",
            model="test-model",
            input_tokens=5,
            output_tokens=2,
            key_id="key_1",
            fallback_attempts=0,
            cache_hit=False,
        )

    monkeypatch.setattr(routes, "complete", capture)
    assert client.post(
        "/chat",
        json={"session_id": session_id, "message": "first", "system_prompt": "Initial prompt"},
    ).status_code == 200
    assert client.post("/chat", json={"session_id": session_id, "message": "second"}).status_code == 200
    assert client.post(
        "/chat",
        json={"session_id": session_id, "message": "third", "system_prompt": "Replacement prompt"},
    ).status_code == 200

    assert seen_messages[1] == [
        {"role": "system", "content": "Initial prompt"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply-1"},
        {"role": "user", "content": "second"},
    ]
    assert seen_messages[2] == [
        {"role": "system", "content": "Replacement prompt"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply-1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply-2"},
        {"role": "user", "content": "third"},
    ]
    from app.database import get_session_system_prompt
    assert get_session_system_prompt(session_id) == "Replacement prompt"


def test_provider_failure_uses_router_fallback(client, mock_litellm_router, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_failure_simulation", True)
    configured_keys = settings.parse_api_keys().copy()
    response = client.post(
        "/chat",
        headers={"X-Simulate-Failure": "key_1=429"},
        json={"session_id": _unique("fallback"), "message": _unique("fallback prompt")},
    )

    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["key_id"] == "key_2"
    assert metadata["fallback_attempts"] == 1
    assert metadata["resolution_source"] == "LIVE_INFERENCE"
    assert settings.parse_api_keys() == configured_keys


@pytest.mark.parametrize("header", ["*=429", "key_1=429,key_2=500"])
def test_all_simulated_providers_fail_without_history(
    client, mock_litellm_router, monkeypatch, header
):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_failure_simulation", True)
    session_id = _unique("failed-simulation")
    response = client.post(
        "/chat",
        headers={"X-Simulate-Failure": header},
        json={"session_id": session_id, "message": _unique("unavailable")},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "all providers unavailable"}
    assert client.get(f"/sessions/{session_id}/messages").status_code == 404


def test_failure_simulation_is_ignored_when_disabled(
    client, mock_litellm_router, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_failure_simulation", False)
    response = client.post(
        "/chat",
        headers={"X-Simulate-Failure": "not-even-valid"},
        json={"session_id": _unique("simulation-disabled"), "message": _unique("normal request")},
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert response.json()["metadata"]["key_id"] == "key_1"


def test_native_cache_same_and_cross_session(client, mock_litellm_router):
    prompt = _unique("same-context")
    system_prompt = "Answer briefly."
    first_session = _unique("cache-session-a")

    first = client.post(
        "/chat",
        json={"session_id": first_session, "message": prompt, "system_prompt": system_prompt},
    ).json()
    same_session = client.post(
        "/chat",
        json={"session_id": first_session, "message": prompt},
    ).json()
    other_session = client.post(
        "/chat",
        json={"session_id": _unique("cache-session-b"), "message": prompt, "system_prompt": system_prompt},
    ).json()

    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert first["metadata"]["input_tokens"] > 0
    assert first["metadata"]["output_tokens"] > 0
    assert "metadata" in other_session, other_session
    assert same_session["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert same_session["metadata"]["key_id"] == "key_1"
    assert other_session["metadata"]["resolution_source"] == "LLM_CACHE"
    assert other_session["reply"] == first["reply"]
    assert other_session["metadata"]["key_id"] is None
    assert other_session["metadata"]["fallback_attempts"] == 0
    assert other_session["metadata"]["input_tokens"] == first["metadata"]["input_tokens"]
    assert other_session["metadata"]["output_tokens"] == first["metadata"]["output_tokens"]

    history = client.get(f"/sessions/{first_session}/messages").json()["messages"]
    assert [(item["role"], item["content"]) for item in history] == [
        ("user", prompt),
        ("assistant", first["reply"]),
        ("user", prompt),
        ("assistant", same_session["reply"]),
    ]


def test_native_cache_misses_for_message_and_system_prompt(
    client, mock_litellm_router
):
    session_id = _unique("cache-miss-session")
    message = _unique("cache-message")
    first = client.post(
        "/chat",
        json={"session_id": session_id, "message": message, "system_prompt": "Prompt A"},
    ).json()
    different_message = client.post(
        "/chat",
        json={"session_id": session_id, "message": _unique("different-message")},
    ).json()
    different_system_prompt = client.post(
        "/chat",
        json={"session_id": session_id, "message": message, "system_prompt": "Prompt B"},
    ).json()

    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert different_message["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert different_system_prompt["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_provider_failure_is_not_persisted(client, mock_litellm_router, monkeypatch):
    from app.config import settings

    configured_keys = settings.parse_api_keys().copy()
    monkeypatch.setattr(settings, "enable_failure_simulation", True)
    session_id = _unique("no-failed-history")
    response = client.post(
        "/chat",
        headers={"X-Simulate-Failure": "*=429"},
        json={"session_id": session_id, "message": _unique("fail")},
    )
    assert response.status_code == 503
    assert settings.parse_api_keys() == configured_keys
    assert client.get(f"/sessions/{session_id}/messages").status_code == 404
