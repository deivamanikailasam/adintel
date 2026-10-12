"""LLM providers behind one interface (ADR L-01)."""

from adintel.llm.providers.base import LLMProvider, get_provider, set_provider_override

__all__ = ["LLMProvider", "get_provider", "set_provider_override"]
