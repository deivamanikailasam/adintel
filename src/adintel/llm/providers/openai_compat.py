"""OpenAI-compatible chat-completions provider: mlx_lm.server, vLLM, SGLang, LM Studio, SageMaker LMI.

Local default: two ``mlx_lm.server`` processes (small tier on :8080, frontier tier on :8081).
Timeouts are layered: TCP connect (5 s) < HTTP read (tier timeout − 5 s) < LLM call budget.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx

from adintel.core.errors import LLMTimeout, LLMUnavailable
from adintel.core.resilience import CircuitOpen, breaker
from adintel.llm.providers.base import LLMProvider
from adintel.llm.types import CompletionRequest, CompletionResult, TierConfig, estimate_tokens


class OpenAICompatProvider(LLMProvider):
    _shared: OpenAICompatProvider | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._clients: dict[str, httpx.Client] = {}
        self._clients_lock = threading.Lock()

    @classmethod
    def shared(cls) -> OpenAICompatProvider:
        with cls._lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def _client(self, tier: TierConfig) -> httpx.Client:
        with self._clients_lock:
            if tier.name not in self._clients:
                read = max(1.0, tier.timeout_seconds - 5)
                self._clients[tier.name] = httpx.Client(
                    base_url=tier.base_url.rstrip("/"),
                    timeout=httpx.Timeout(read, connect=tier.connect_timeout_seconds),
                    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),  # bulkhead per tier
                )
            return self._clients[tier.name]

    @staticmethod
    def _body(req: CompletionRequest, tier: TierConfig, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": tier.model_id,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": stream,
        }
        if req.stop:
            body["stop"] = req.stop
        if req.seed is not None and tier.supports_seed:
            body["seed"] = req.seed
        if stream:
            body["stream_options"] = {"include_usage": True}
        body.update(tier.extra_body)
        return body

    def complete(self, req: CompletionRequest, tier: TierConfig) -> CompletionResult:
        cb = breaker(f"llm:{tier.name}")
        try:
            cb.before_call()
        except CircuitOpen as exc:
            raise LLMUnavailable(f"circuit open for tier {tier.name}") from exc
        t0 = time.perf_counter()
        try:
            resp = self._client(tier).post("/chat/completions", json=self._body(req, tier, stream=False))
        except httpx.TimeoutException as exc:
            cb.record_failure()
            raise LLMTimeout(f"{tier.name}: {exc.__class__.__name__}") from exc
        except httpx.TransportError as exc:
            cb.record_failure()
            raise LLMUnavailable(f"{tier.name}: {exc.__class__.__name__}: {exc}") from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            cb.record_failure()
            raise LLMUnavailable(f"{tier.name}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            cb.record_failure()
            raise LLMUnavailable(f"{tier.name}: HTTP {resp.status_code}: {resp.text[:200]}")
        cb.record_success()
        data = resp.json()
        choice = data["choices"][0]
        text = choice.get("message", {}).get("content") or ""
        usage = data.get("usage") or {}
        prompt_text = "".join(m.content for m in req.messages)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or estimate_tokens(prompt_text)),
            tokens_out=int(usage.get("completion_tokens") or estimate_tokens(text)),
            cached_tokens=int(cached),
            latency_ms=(time.perf_counter() - t0) * 1000,
            model_id=str(data.get("model") or tier.model_id),
            finish_reason=str(choice.get("finish_reason") or "stop"),
        )

    def stream(self, req: CompletionRequest, tier: TierConfig) -> Iterator[str | CompletionResult]:
        cb = breaker(f"llm:{tier.name}")
        try:
            cb.before_call()
        except CircuitOpen as exc:
            raise LLMUnavailable(f"circuit open for tier {tier.name}") from exc
        t0 = time.perf_counter()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        try:
            with self._client(tier).stream(
                "POST", "/chat/completions", json=self._body(req, tier, stream=True)
            ) as resp:
                if resp.status_code >= 400:
                    cb.record_failure()
                    raise LLMUnavailable(f"{tier.name}: HTTP {resp.status_code}")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for ch in chunk.get("choices", []):
                        delta = (ch.get("delta") or {}).get("content")
                        if delta:
                            parts.append(delta)
                            yield delta
        except httpx.TimeoutException as exc:
            cb.record_failure()
            raise LLMTimeout(f"{tier.name}: stream timeout") from exc
        except httpx.TransportError as exc:
            cb.record_failure()
            raise LLMUnavailable(f"{tier.name}: {exc}") from exc
        cb.record_success()
        text = "".join(parts)
        prompt_text = "".join(m.content for m in req.messages)
        yield CompletionResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or estimate_tokens(prompt_text)),
            tokens_out=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=(time.perf_counter() - t0) * 1000,
            model_id=tier.model_id,
        )

    def health(self, tier: TierConfig) -> dict[str, Any]:
        try:
            r = self._client(tier).get("/models")
            return {
                "ok": r.status_code == 200,
                "status": r.status_code,
                "models": [m.get("id") for m in r.json().get("data", [])] if r.status_code == 200 else [],
            }
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc)}
