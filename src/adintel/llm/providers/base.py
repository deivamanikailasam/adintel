from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from adintel.llm.types import CompletionRequest, CompletionResult, TierConfig


class LLMProvider(ABC):
    """Raises ``LLMTimeout`` / ``LLMUnavailable``; never returns partial garbage silently."""

    @abstractmethod
    def complete(self, req: CompletionRequest, tier: TierConfig) -> CompletionResult: ...

    def stream(self, req: CompletionRequest, tier: TierConfig) -> Iterator[str | CompletionResult]:
        """Yield text deltas, then a final ``CompletionResult`` with usage. Default: no streaming."""
        result = self.complete(req, tier)
        yield result.text
        yield result


_override: LLMProvider | None = None


def set_provider_override(provider: LLMProvider | None) -> None:
    """Tests and evals inject a provider (e.g. a scripted mock) here."""
    global _override
    _override = provider


def get_provider(kind: str) -> LLMProvider:
    if _override is not None:
        return _override
    if kind == "openai_compat":
        from adintel.llm.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider.shared()
    if kind == "bedrock":
        from adintel.llm.providers.bedrock import BedrockProvider

        return BedrockProvider.shared()
    if kind == "mock":
        from adintel.llm.providers.mock import MockProvider

        return MockProvider.shared()
    raise ValueError(f"unknown provider {kind!r}")
