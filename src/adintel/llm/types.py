"""Provider-neutral request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TierConfig:
    name: str
    provider: str
    base_url: str
    model_id: str
    context_window: int
    timeout_seconds: float
    connect_timeout_seconds: float
    max_output_tokens: int
    fallback: str | None
    price_input: float  # USD per 1M tokens (notional for local models)
    price_output: float
    price_cached_input: float
    adapter_path: str | None = None
    adapter_sha256: str | None = None
    supports_seed: bool = False
    extra_body: dict[str, Any] = field(default_factory=dict)
    owner: str = ""
    production_equivalent: str = ""
    max_concurrency: int = 4  # bulkhead: requests in flight per process to this server+model
    queue_timeout_seconds: float = 30.0  # wait this long for a slot, then fail fast (fallback chain)


@dataclass(frozen=True)
class AgentModelConfig:
    agent: str
    tier: str
    temperature: float
    max_input_tokens: int
    max_output_tokens: int


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass
class CompletionRequest:
    messages: list[Message]
    temperature: float
    max_tokens: int
    seed: int | None = None
    stop: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # e.g. schema name, agent (mock routing)


@dataclass
class CompletionResult:
    text: str
    tokens_in: int
    tokens_out: int
    cached_tokens: int = 0
    latency_ms: float = 0.0
    model_id: str = ""
    finish_reason: str = "stop"


def estimate_tokens(text: str) -> int:
    """Cheap, conservative estimate (≈4 chars/token) used for pre-call budget checks."""
    return max(1, len(text) // 4 + 1)
