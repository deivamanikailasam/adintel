"""The mlx-lm / OpenAI-compatible provider against a fake HTTP server (httpx.MockTransport)."""

import json
from dataclasses import replace

import httpx
import pytest

from adintel.core.errors import LLMTimeout, LLMUnavailable
from adintel.llm.providers.openai_compat import OpenAICompatProvider
from adintel.llm.registry import get_registry
from adintel.llm.types import CompletionRequest, CompletionResult, Message


def provider_with(handler, tier):
    p = OpenAICompatProvider()
    p._clients[tier.name] = httpx.Client(base_url=tier.base_url, transport=httpx.MockTransport(handler))
    return p


def req():
    return CompletionRequest(
        messages=[Message("system", "s"), Message("user", "u")], temperature=0.0, max_tokens=50, seed=7
    )


@pytest.fixture
def tier():
    return get_registry().tiers["small"]


def test_completion_is_parsed_with_usage(tier):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": tier.model_id,
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 8}},
            },
        )

    r = provider_with(handler, tier).complete(req(), tier)
    assert r.text == '{"ok": true}' and r.tokens_in == 12 and r.tokens_out == 3 and r.cached_tokens == 8
    assert seen["model"] == tier.model_id and seen["max_tokens"] == 50 and "seed" not in seen  # mlx: no seed


def test_seed_and_extra_body_are_sent_when_configured(tier):
    seen = {}
    t = replace(tier, supports_seed=True, extra_body={"chat_template_kwargs": {"enable_thinking": False}})

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    r = provider_with(handler, t).complete(req(), t)
    assert seen["seed"] == 7 and seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert r.tokens_in > 0  # estimated when the server omits usage


@pytest.mark.parametrize("status", [500, 503, 429, 400])
def test_http_errors_map_to_unavailable(tier, status):
    p = provider_with(lambda r: httpx.Response(status, text="boom"), tier)
    with pytest.raises(LLMUnavailable):
        p.complete(req(), tier)


def test_timeouts_and_connection_errors(tier):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeout):
        provider_with(timeout, tier).complete(req(), tier)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailable):
        provider_with(refused, tier).complete(req(), tier)


def test_circuit_opens_after_repeated_failures(tier):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    p = provider_with(handler, tier)
    for _ in range(5):
        with pytest.raises(LLMUnavailable):
            p.complete(req(), tier)
    with pytest.raises(LLMUnavailable, match="circuit open"):
        p.complete(req(), tier)
    assert len(calls) == 5  # the sixth call never reached the server


def test_streaming_yields_deltas_then_usage(tier):
    body = (
        "".join(
            f"data: {json.dumps(c)}\n\n"
            for c in [
                {"choices": [{"delta": {"content": "Hello "}}]},
                {"choices": [{"delta": {"content": "world"}}]},
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 2}},
            ]
        )
        + "data: [DONE]\n\n"
    )
    p = provider_with(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}), tier)
    items = list(p.stream(req(), tier))
    assert items[:2] == ["Hello ", "world"]
    final = items[-1]
    assert isinstance(final, CompletionResult) and final.text == "Hello world" and final.tokens_in == 9


def test_health_lists_served_models(tier):
    p = provider_with(lambda r: httpx.Response(200, json={"data": [{"id": tier.model_id}]}), tier)
    assert p.health(tier) == {"ok": True, "status": 200, "models": [tier.model_id]}
