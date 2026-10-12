# The LLM gateway (validation wrapper)

> **Nothing calls a model provider directly.** Every call goes through
> `src/adintel/llm/gateway.py`, the highest-leverage shared code in the system.

## Call path

```mermaid
sequenceDiagram
    participant A as Agent
    participant G as LLMGateway
    participant M as UsageMeter (budget)
    participant P as Provider (mlx-lm / Bedrock / mock)
    participant DB as llm_calls + prompt_archive
    A->>G: structured(agent, prompt_id, schema, context, untrusted)
    G->>G: system prompt (static) + schema + /no_think  ← stable, cacheable prefix
    G->>G: PII-redact context; fence + redact untrusted; truncate with disclosure
    loop tier in [tier, fallback...]
        loop attempt ≤ 1 + 2 repairs
            G->>M: precheck(estimated tokens + max output)
            G->>P: complete() with retry+jitter on timeout/5xx (max 2)
            P-->>G: text + usage
            G->>M: charge(every attempt, failures included)
            G->>DB: record call (hashes, model, adapter, seed, tokens, cost, status)
            G->>G: strip <think>, extract JSON, Pydantic validate
            alt valid
                G-->>A: StructuredResult(value, tier, fallback_used, call_ids)
            else invalid
                G->>G: repair turn: bad output + exact error + "valid JSON only"
            end
        end
    end
    G-->>A: LLMValidationError / LLMUnavailable → agent's degradation policy
```

## The layers and the failure each prevents

| Layer | Failure it prevents | Code |
|-------|---------------------|------|
| Schema-constrained (Pydantic) output | Code parsing free text with regex | `schema.model_validate_json` |
| Repair loop, **max 2** | One bad field failing a whole run. Capped at 2 because in testing a model once failed the same enum constraint 11 times in a row. | `MAX_REPAIRS` |
| Retry with jitter (timeouts/5xx/429 only) | Throttling cascading into failed runs | `core/resilience.retry_call` |
| Timeouts (tier timeout; HTTP read = tier − 5 s; connect 5 s) | A hung connection holding a worker | `providers/openai_compat.py` |
| Circuit breaker per tier (5 failures / 60 s → open; half-open after 30 s) | Hammering a dead model server | `core/resilience.CircuitBreaker` |
| Bulkhead (max 8 connections per tier) | One slow tier starving the others | `httpx.Limits` |
| Charge budget on every attempt, failures included | Repair loops silently doubling spend | `UsageMeter.charge` |
| Model fallback chain (`frontier → small`, `report → frontier`, `safety → none`) | A model outage taking the product down | `ModelRegistry.chain` |
| Untrusted-content fencing | Prompt injection via ad-platform fields | `security/fencing.py` |
| PII redaction | End-customer data reaching a model | `security/pii.py` |
| Prompt and response hashing + archive (13 months) | Being unable to reproduce a disputed report | `prompt_archive` |
| Qwen `<think>` stripping and `/no_think` | Reasoning text breaking JSON parsing | `strip_thinking` |

## Governance hooks

- **Model registry** (`config/models.yaml`): pinned IDs, adapter SHA-256, owner, production
  equivalent, notional price. Floating references (`latest`, `:latest`, `main`) are refused.
- **Prompt registry** (`prompts/registry.yaml`): each prompt file has a version and a pinned SHA-256.
  Editing a prompt without bumping the version and re-pinning (`python scripts/pin_prompts.py`) is
  refused at startup. System prompts cannot contain template placeholders, which keeps the cacheable
  prefix stable.

## Testing it without a model

`MockProvider` (`llm/providers/mock.py`) is deterministic. Tests script exact responses
(`mock.script("Decision", ["bad", "bad", '{"…": …}'])`), inject `LLMTimeout`, or take a whole tier
down (`mock.take_down("frontier")`). See `tests/unit/test_llm_gateway.py`.
