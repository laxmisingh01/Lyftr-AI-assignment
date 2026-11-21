"""Stage 2 checks for ordered LiteLLM routing and simulation headers."""

import asyncio
from types import SimpleNamespace

import pytest


def test_router_deployments_preserve_key_priority(monkeypatch):
    from app import llm_gateway

    monkeypatch.setattr(
        llm_gateway.settings,
        "llm_api_keys",
        "key_1=first-secret,key_2=second-secret",
    )
    deployments = llm_gateway._deployments()

    assert [item["model_info"]["id"] for item in deployments] == ["key_1", "key_2"]
    assert [item["litellm_params"]["order"] for item in deployments] == [1, 2]
    assert [item["litellm_params"]["api_key"] for item in deployments] == [
        "first-secret",
        "second-secret",
    ]


def test_simulation_header_parses_specific_and_wildcard(monkeypatch):
    from app import llm_gateway

    monkeypatch.setattr(
        llm_gateway.settings,
        "llm_api_keys",
        "key_1=first-secret,key_2=second-secret",
    )

    assert llm_gateway.parse_simulation_header("key_1=429,key_2=500") == {
        "key_1": 429,
        "key_2": 500,
    }
    assert llm_gateway.parse_simulation_header("*=429") == {
        "key_1": 429,
        "key_2": 429,
    }


@pytest.mark.parametrize("header", ["key_1=200", "key_9=429", "key_1=nope", "*=399"])
def test_simulation_header_rejects_invalid_values(monkeypatch, header):
    from app import llm_gateway

    monkeypatch.setattr(llm_gateway.settings, "llm_api_keys", "key_1=secret")

    with pytest.raises(ValueError):
        llm_gateway.parse_simulation_header(header)


def test_gateway_reports_selected_key_and_usage(monkeypatch):
    from app import llm_gateway

    monkeypatch.setattr(
        llm_gateway.settings,
        "llm_api_keys",
        "key_1=first-secret,key_2=second-secret",
    )
    response = SimpleNamespace(
        _hidden_params={"model_id": "key_2"},
        model="gpt-4o-mini",
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
    )

    class FakeRouter:
        async def acompletion(self, **kwargs):
            assert kwargs["model"] == llm_gateway.MODEL_GROUP
            return response

    monkeypatch.setattr(llm_gateway, "router", FakeRouter())
    result = asyncio.run(
        llm_gateway.complete([{"role": "user", "content": "hi"}])
    )

    assert result.reply == "hello"
    assert result.key_id == "key_2"
    assert result.fallback_attempts == 1
    assert (result.input_tokens, result.output_tokens) == (3, 1)
