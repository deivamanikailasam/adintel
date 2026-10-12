"""Deterministic mock provider for tests, CI evals and the offline demo.

Routing: a request's ``metadata["schema"]`` (structured calls) or ``metadata["prompt_id"]`` (text
calls) selects a handler. Handlers receive the parsed ``<context>`` JSON and return the model's text.

* ``script(key, [...])`` queues exact responses (strings or exceptions) — used to test repair loops,
  fallbacks, timeouts and injection handling.
* Default handlers (``adintel.llm.mock_handlers``) implement simple, deterministic stand-ins for each
  agent so end-to-end golden runs work without any model. They are **not** the agents' logic: they
  only fill the schema plausibly from the context, exactly like a well-behaved model would.
"""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from typing import Any

from adintel.llm.types import CompletionRequest, CompletionResult, Message, TierConfig, estimate_tokens

Handler = Callable[[dict[str, Any], list[Message], TierConfig], str]
_HANDLERS: dict[str, Handler] = {}
_CTX_RE = re.compile(r"<context>\n(.*?)\n</context>", re.DOTALL)


def register(key: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[key] = fn
        return fn

    return deco


def parse_context(messages: list[Message]) -> dict[str, Any]:
    for m in reversed(messages):
        if m.role == "user":
            match = _CTX_RE.search(m.content)
            if match:
                try:
                    data = json.loads(match.group(1))
                    return data if isinstance(data, dict) else {"value": data}
                except json.JSONDecodeError:
                    return {"text": match.group(1)}
    return {}


class MockProvider:
    _shared: MockProvider | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._scripts: dict[str, deque[Any]] = defaultdict(deque)
        self._tier_down: set[str] = set()
        self.requests: list[tuple[str, CompletionRequest]] = []
        self._mu = threading.Lock()

    @classmethod
    def shared(cls) -> MockProvider:
        with cls._lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        with cls._lock:
            cls._shared = None

    def script(self, key: str, responses: list[Any]) -> None:
        with self._mu:
            self._scripts[key].extend(responses)

    def take_down(self, tier: str) -> None:
        self._tier_down.add(tier)

    def restore(self, tier: str) -> None:
        self._tier_down.discard(tier)

    def _respond(self, req: CompletionRequest, tier: TierConfig) -> str:
        from adintel.core.errors import LLMUnavailable

        if tier.name in self._tier_down:
            raise LLMUnavailable(f"mock: tier {tier.name} is down")
        keys = [k for k in (f"{tier.name}:{req.metadata.get('schema')}", req.metadata.get("schema"),
                            req.metadata.get("prompt_id")) if k]
        with self._mu:
            self.requests.append((tier.name, req))
            for k in keys:
                if self._scripts.get(k):
                    item = self._scripts[k].popleft()
                    if isinstance(item, BaseException):
                        raise item
                    return item if isinstance(item, str) else json.dumps(item)
        import adintel.llm.mock_handlers  # noqa: F401 - registers default handlers

        for k in keys:
            if k in _HANDLERS:
                return _HANDLERS[k](parse_context(req.messages), req.messages, tier)
        return json.dumps({"note": "mock: no handler", "keys": keys})

    def complete(self, req: CompletionRequest, tier: TierConfig) -> CompletionResult:
        text = self._respond(req, tier)
        return CompletionResult(text=text, tokens_in=estimate_tokens("".join(m.content for m in req.messages)),
                                tokens_out=estimate_tokens(text), latency_ms=1.0, model_id=tier.model_id)

    def stream(self, req: CompletionRequest, tier: TierConfig) -> Iterator[str | CompletionResult]:
        result = self.complete(req, tier)
        for word in re.findall(r"\S+\s*", result.text):
            yield word
        yield result
