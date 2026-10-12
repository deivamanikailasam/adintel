# L-01: One OpenAI-compatible provider for local models

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

mlx_lm.server exposes an OpenAI-compatible /v1/chat/completions endpoint. vLLM, SGLang, LM Studio, Ollama and SageMaker LMI containers expose the same API.

## Decision

A single OpenAICompatProvider talks to any of them; a BedrockProvider (Converse API) implements the same interface for production. Agents never see the difference.

## Consequences

Provider-specific features (Bedrock prompt caching headers, guardrail IDs) are configured per provider, not per agent.

## Alternatives rejected

Calling mlx in-process via the Python API (ties the worker to Apple Silicon, no process isolation); a framework abstraction such as LiteLLM (extra dependency on the hot path).

## Revisit when

A provider needs features the OpenAI-compatible shape can't express.
