"""Amazon Bedrock provider (production). Uses the Converse API; requires the ``aws`` extra.

Model IDs must be exact, versioned Bedrock IDs (never an alias). Prompt caching and guardrail IDs are
configured in ``extra_body`` of the tier (``{"guardrailConfig": {...}}``).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from adintel.core.errors import LLMTimeout, LLMUnavailable
from adintel.core.resilience import CircuitOpen, breaker
from adintel.llm.types import CompletionRequest, CompletionResult, TierConfig


class BedrockProvider:
    _shared: BedrockProvider | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self._client: Any = boto3.client(
            "bedrock-runtime", config=Config(read_timeout=85, connect_timeout=5, retries={"max_attempts": 0})
        )

    @classmethod
    def shared(cls) -> BedrockProvider:
        with cls._lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def complete(self, req: CompletionRequest, tier: TierConfig) -> CompletionResult:
        from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

        cb = breaker(f"llm:{tier.name}")
        try:
            cb.before_call()
        except CircuitOpen as exc:
            raise LLMUnavailable(tier.name) from exc
        system = [{"text": m.content} for m in req.messages if m.role == "system"]
        messages = [{"role": m.role, "content": [{"text": m.content}]} for m in req.messages if m.role != "system"]
        t0 = time.perf_counter()
        try:
            out = self._client.converse(
                modelId=tier.model_id, system=system, messages=messages,
                inferenceConfig={"temperature": req.temperature, "maxTokens": req.max_tokens},
                **tier.extra_body,
            )
        except ReadTimeoutError as exc:
            cb.record_failure()
            raise LLMTimeout(tier.name) from exc
        except (ClientError, BotoCoreError) as exc:
            cb.record_failure()
            raise LLMUnavailable(f"{tier.name}: {exc}") from exc
        cb.record_success()
        text = "".join(c.get("text", "") for c in out["output"]["message"]["content"])
        usage = out.get("usage", {})
        return CompletionResult(text=text, tokens_in=usage.get("inputTokens", 0),
                                tokens_out=usage.get("outputTokens", 0),
                                cached_tokens=usage.get("cacheReadInputTokens", 0),
                                latency_ms=(time.perf_counter() - t0) * 1000, model_id=tier.model_id,
                                finish_reason=out.get("stopReason", "stop"))
