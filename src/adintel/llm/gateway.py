"""The validation wrapper — the highest-leverage shared code in the system.

Nothing calls a model provider directly. Each layer here exists to stop a specific failure:

| Layer | Failure it prevents |
|-------|---------------------|
| Schema-constrained (Pydantic) output | Code parsing free text with regex |
| Repair loop, max 2 | One bad field failing a whole run |
| Retry with jitter (transient errors only) | Monday 8 AM throttling cascading into failed runs |
| Timeout (per tier, nested inside the agent timeout) | A hung connection holding a worker |
| Charge budget on every attempt, failures included | Repair loops silently doubling spend |
| Model fallback chain | A provider outage taking the product down |
| Untrusted-content fencing | Prompt injection via ad-platform API fields |
| PII redaction | End-customer data reaching a model provider |
| Prompt and response hashing + archive | Being unable to reproduce a disputed report |
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from adintel.core.clock import utcnow
from adintel.core.errors import BudgetExceeded, LLMTimeout, LLMUnavailable, LLMValidationError
from adintel.core.hashing import canonical_json, sha256_obj, sha256_text
from adintel.core.ids import new_id
from adintel.core.resilience import retry_call
from adintel.harness.budget import UnlimitedMeter, UsageMeter
from adintel.llm.prompts import Prompt, get_prompts
from adintel.llm.providers import get_provider
from adintel.llm.registry import ModelRegistry, get_registry
from adintel.llm.types import CompletionRequest, CompletionResult, Message, TierConfig, estimate_tokens
from adintel.observability import metrics
from adintel.observability.langfuse import get_langfuse
from adintel.security.fencing import FENCE_PREAMBLE, fence
from adintel.security.pii import redact
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_REPAIRS = 2
TRANSIENT_RETRIES = 2
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def strip_thinking(text: str) -> str:
    text = _THINK_RE.sub("", text)
    if "</think>" in text:  # an unterminated opening block from some chat templates
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str) -> str:
    text = strip_thinking(text)
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1)
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def cost_of(tier: TierConfig, tokens_in: int, tokens_out: int, cached: int = 0) -> float:
    uncached = max(0, tokens_in - cached)
    return round((uncached * tier.price_input + cached * tier.price_cached_input
                  + tokens_out * tier.price_output) / 1_000_000, 8)


@dataclass
class StructuredResult(Generic[T]):
    value: T
    tier: str
    model_id: str
    fallback_used: bool
    call_ids: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    repairs: int = 0


@dataclass
class TextResult:
    text: str
    tier: str
    model_id: str
    fallback_used: bool
    call_ids: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass
class CallContext:
    tenant_id: str
    run_id: str | None = None
    brand_id: str | None = None
    step: int = 0
    trace_id: str | None = None


class LLMGateway:
    def __init__(self, db: Database, ctx: CallContext, *, meter: UsageMeter | None = None,
                 registry: ModelRegistry | None = None, no_think: bool | None = None) -> None:
        from adintel.config import get_settings

        self._db = db
        self.ctx = ctx
        self.meter = meter or UnlimitedMeter()
        self.registry = registry or get_registry()
        self._calls = TenantScopedRepo(db, "llm_calls", ctx.tenant_id)
        self._archive = TenantScopedRepo(db, "prompt_archive", ctx.tenant_id)
        self._cost = TenantScopedRepo(db, "cost_events", ctx.tenant_id)
        self._no_think = get_settings().qwen_no_think if no_think is None else no_think
        self._lf = get_langfuse()
        self.call_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------------------------------------
    # message assembly: stable prefix first (system prompt + schema), variable content last
    # ------------------------------------------------------------------------------------------------
    def build_messages(self, prompt: Prompt, *, schema: type[BaseModel] | None, context: Any,
                       untrusted: dict[str, Any] | None, task: str | None, max_input_tokens: int,
                       history: list[Message] | None = None) -> tuple[list[Message], list[str]]:
        system = prompt.text
        if untrusted:
            system += "\n\n" + FENCE_PREAMBLE
        if schema is not None:
            system += ("\n\nRespond with ONE JSON object only, no prose, matching this JSON Schema:\n"
                       + json.dumps(schema.model_json_schema(), sort_keys=True))
        if self._no_think:
            system += "\n/no_think"

        redacted_kinds: list[str] = []
        ctx_text = context if isinstance(context, str) else canonical_json(context)
        ctx_text, k1 = redact(ctx_text)
        redacted_kinds += k1
        parts = [f"<context>\n{ctx_text}\n</context>"]
        budget_chars = max_input_tokens * 4 - len(system) - len(ctx_text) - 400
        if untrusted:
            for source, payload in untrusted.items():
                block = fence(source, payload)
                block, k2 = redact(block)
                redacted_kinds += k2
                if len(block) > budget_chars:
                    keep = max(0, budget_chars)
                    block = block[:keep] + ("\n[TRUNCATED: %d characters of %s omitted to fit the context budget]"
                                            % (len(block) - keep, source))
                budget_chars -= len(block)
                parts.append(block)
        if task:
            parts.append(f"<task>\n{task}\n</task>")
        messages = [Message("system", system), *(history or []), Message("user", "\n\n".join(parts))]
        return messages, redacted_kinds

    # ------------------------------------------------------------------------------------------------
    def _seed(self, agent: str) -> int:
        return int(sha256_text(f"{self.ctx.run_id}:{agent}:{self.ctx.step}")[:8], 16)

    def _record(self, *, agent: str, tier: TierConfig, prompt: Prompt, messages: list[Message],
                result: CompletionResult | None, attempt: int, status: str, error: str | None,
                temperature: float, schema_name: str | None, retrieved: list[str], cost: float) -> str:
        call_id = new_id("llm")
        prompt_payload = [{"role": m.role, "content": m.content} for m in messages]
        prompt_hash = sha256_obj(prompt_payload)
        response_text = result.text if result else ""
        response_hash = sha256_text(response_text)
        expire = utcnow() + timedelta(days=395)
        for sha, kind, body in ((prompt_hash, "prompt", prompt_payload), (response_hash, "response", response_text)):
            self._archive.update_one({"sha256": sha}, {"$setOnInsert": {"sha256": sha, "kind": kind, "body": body,
                                                                          "expire_at": expire}}, upsert=True)
        rec = {
            "call_id": call_id, "run_id": self.ctx.run_id, "brand_id": self.ctx.brand_id, "agent": agent,
            "step": self.ctx.step, "tier": tier.name, "model_id": tier.model_id,
            "adapter_sha256": tier.adapter_sha256, "prompt_id": prompt.prompt_id, "prompt_version": prompt.version,
            "prompt_sha256": prompt.sha256, "prompt_hash": prompt_hash, "response_hash": response_hash,
            "schema": schema_name, "temperature": temperature, "seed": self._seed(agent),
            "retrieved_doc_ids": retrieved, "tokens_in": result.tokens_in if result else 0,
            "tokens_out": result.tokens_out if result else 0, "cached_tokens": result.cached_tokens if result else 0,
            "cost_usd": cost, "latency_ms": result.latency_ms if result else None, "attempt": attempt,
            "status": status, "error": error, "created_at": utcnow().isoformat(), "expire_at": expire,
        }
        self._calls.insert(rec)
        self.call_log.append(rec)
        day = utcnow().date().isoformat()
        self._cost.insert({"day": day, "brand_id": self.ctx.brand_id, "run_id": self.ctx.run_id, "agent": agent,
                           "tier": tier.name, "cost_usd": cost, "tokens": rec["tokens_in"] + rec["tokens_out"]})
        labels = {"agent": agent, "model": tier.model_id}
        metrics.LLM_TOKENS.labels(**labels, tenant=self.ctx.tenant_id, direction="in").inc(rec["tokens_in"])
        metrics.LLM_TOKENS.labels(**labels, tenant=self.ctx.tenant_id, direction="out").inc(rec["tokens_out"])
        metrics.LLM_COST.labels(**labels, tenant=self.ctx.tenant_id).inc(cost)
        if result:
            metrics.LLM_LATENCY.labels(**labels).observe(result.latency_ms / 1000)
        if self._lf and self.ctx.run_id:
            now = utcnow()
            self._lf.generation(self.ctx.run_id, name=f"{agent}:{prompt.prompt_id}", model=tier.model_id,
                                input=prompt_payload, output=response_text,
                                usage={"input": rec["tokens_in"], "output": rec["tokens_out"]},
                                metadata={"status": status, "attempt": attempt, "tier": tier.name},
                                start=now - timedelta(milliseconds=rec["latency_ms"] or 0), end=now)
        return call_id

    def _call(self, agent: str, tier: TierConfig, req: CompletionRequest) -> CompletionResult:
        provider = get_provider(tier.provider)

        def on_retry(n: int, exc: BaseException) -> None:
            log.warning("llm_retry", extra={"agent": agent, "tier": tier.name, "attempt": n, "error": str(exc)[:120]})
            # a timed-out attempt was still (partly) billed upstream: charge its input
            est = estimate_tokens("".join(m.content for m in req.messages))
            c = cost_of(tier, est, 0)
            self.meter.charge(est, 0, c)

        return retry_call(lambda: provider.complete(req, tier), retries=TRANSIENT_RETRIES,
                          transient=(LLMTimeout, LLMUnavailable), on_retry=on_retry)

    # ------------------------------------------------------------------------------------------------
    def structured(self, *, agent: str, prompt_id: str, schema: type[T], context: Any,
                   untrusted: dict[str, Any] | None = None, task: str | None = None,
                   retrieved_doc_ids: list[str] | None = None, tier_override: str | None = None,
                   allow_fallback: bool = True) -> StructuredResult[T]:
        cfg = self.registry.agents[agent]
        prompt = get_prompts().get(prompt_id)
        chain = self.registry.chain(tier_override or cfg.tier)
        if not allow_fallback:
            chain = chain[:1]
        messages, redacted = self.build_messages(prompt, schema=schema, context=context, untrusted=untrusted,
                                                 task=task, max_input_tokens=cfg.max_input_tokens)
        if redacted:
            log.info("pii_redacted", extra={"agent": agent, "kinds": sorted(set(redacted))})
        call_ids: list[str] = []
        tin = tout = 0
        spent = 0.0
        last_error: Exception | None = None
        for idx, tier in enumerate(chain):
            if idx > 0:
                metrics.LLM_FALLBACKS.labels(from_tier=chain[idx - 1].name, to_tier=tier.name).inc()
                log.warning("llm_fallback", extra={"agent": agent, "from": chain[idx - 1].name, "to": tier.name})
            convo = list(messages)
            for attempt in range(1, MAX_REPAIRS + 2):
                est = estimate_tokens("".join(m.content for m in convo))
                self.meter.precheck(tokens=est + cfg.max_output_tokens, cost=cost_of(tier, est, cfg.max_output_tokens))
                req = CompletionRequest(messages=convo, temperature=cfg.temperature,
                                        max_tokens=min(cfg.max_output_tokens, tier.max_output_tokens),
                                        seed=self._seed(agent),
                                        metadata={"schema": schema.__name__, "agent": agent, "prompt_id": prompt_id})
                try:
                    result = self._call(agent, tier, req)
                except (LLMTimeout, LLMUnavailable) as exc:
                    metrics.LLM_ERRORS.labels(tier=tier.name, kind=type(exc).__name__).inc()
                    est_cost = cost_of(tier, est, 0)
                    self.meter.charge(est, 0, est_cost)
                    spent += est_cost
                    call_ids.append(self._record(agent=agent, tier=tier, prompt=prompt, messages=convo, result=None,
                                                 attempt=attempt, status=type(exc).__name__, error=str(exc)[:300],
                                                 temperature=cfg.temperature, schema_name=schema.__name__,
                                                 retrieved=retrieved_doc_ids or [], cost=est_cost))
                    last_error = exc
                    break  # next tier in the fallback chain
                cost = cost_of(tier, result.tokens_in, result.tokens_out, result.cached_tokens)
                self.meter.charge(result.tokens_in, result.tokens_out, cost)
                tin += result.tokens_in
                tout += result.tokens_out
                spent += cost
                raw = extract_json(result.text)
                try:
                    value = schema.model_validate_json(raw)
                except ValidationError as exc:
                    metrics.LLM_VALIDATION_FAILURES.labels(schema=schema.__name__).inc()
                    err = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:8])
                    call_ids.append(self._record(agent=agent, tier=tier, prompt=prompt, messages=convo, result=result,
                                                 attempt=attempt, status="validation_failed", error=err[:500],
                                                 temperature=cfg.temperature, schema_name=schema.__name__,
                                                 retrieved=retrieved_doc_ids or [], cost=cost))
                    last_error = LLMValidationError(err)
                    if attempt <= MAX_REPAIRS:
                        metrics.LLM_REPAIRS.labels(schema=schema.__name__, attempt=str(attempt)).inc()
                        convo = [*convo, Message("assistant", result.text[:4000]), Message(
                            "user", "Your previous output failed validation with these errors:\n" + err
                            + "\nReturn ONLY one valid JSON object matching the schema in the system message.")]
                        continue
                    break  # repairs exhausted → next tier
                call_ids.append(self._record(agent=agent, tier=tier, prompt=prompt, messages=convo, result=result,
                                             attempt=attempt, status="ok", error=None, temperature=cfg.temperature,
                                             schema_name=schema.__name__, retrieved=retrieved_doc_ids or [],
                                             cost=cost))
                return StructuredResult(value=value, tier=tier.name, model_id=tier.model_id, fallback_used=idx > 0,
                                        call_ids=call_ids, tokens_in=tin, tokens_out=tout, cost_usd=spent,
                                        repairs=attempt - 1)
        if isinstance(last_error, LLMValidationError):
            raise last_error
        raise LLMUnavailable(f"all tiers failed for {agent}: {last_error}") from last_error

    # ------------------------------------------------------------------------------------------------
    def text(self, *, agent: str, prompt_id: str, context: Any, untrusted: dict[str, Any] | None = None,
             task: str | None = None, history: list[Message] | None = None,
             tier_override: str | None = None) -> TextResult:
        cfg = self.registry.agents[agent]
        prompt = get_prompts().get(prompt_id)
        messages, _ = self.build_messages(prompt, schema=None, context=context, untrusted=untrusted, task=task,
                                          max_input_tokens=cfg.max_input_tokens, history=history)
        last: Exception | None = None
        for idx, tier in enumerate(self.registry.chain(tier_override or cfg.tier)):
            est = estimate_tokens("".join(m.content for m in messages))
            self.meter.precheck(tokens=est + cfg.max_output_tokens)
            req = CompletionRequest(messages=messages, temperature=cfg.temperature,
                                    max_tokens=min(cfg.max_output_tokens, tier.max_output_tokens),
                                    seed=self._seed(agent), metadata={"agent": agent, "prompt_id": prompt_id})
            try:
                result = self._call(agent, tier, req)
            except (LLMTimeout, LLMUnavailable) as exc:
                last = exc
                self.meter.charge(est, 0, cost_of(tier, est, 0))
                continue
            cost = cost_of(tier, result.tokens_in, result.tokens_out, result.cached_tokens)
            self.meter.charge(result.tokens_in, result.tokens_out, cost)
            cid = self._record(agent=agent, tier=tier, prompt=prompt, messages=messages, result=result, attempt=1,
                               status="ok", error=None, temperature=cfg.temperature, schema_name=None,
                               retrieved=[], cost=cost)
            return TextResult(strip_thinking(result.text), tier.name, tier.model_id, idx > 0, [cid],
                              result.tokens_in, result.tokens_out, cost)
        raise LLMUnavailable(f"all tiers failed for {agent}: {last}") from last

    def stream(self, *, agent: str, prompt_id: str, context: Any, untrusted: dict[str, Any] | None = None,
               task: str | None = None, history: list[Message] | None = None,
               tier_override: str | None = None) -> Iterator[str | TextResult]:
        """Yield text deltas (thinking blocks suppressed), then a final TextResult."""
        cfg = self.registry.agents[agent]
        prompt = get_prompts().get(prompt_id)
        messages, _ = self.build_messages(prompt, schema=None, context=context, untrusted=untrusted, task=task,
                                          max_input_tokens=cfg.max_input_tokens, history=history)
        tier = self.registry.tiers[tier_override or cfg.tier]
        req = CompletionRequest(messages=messages, temperature=cfg.temperature,
                                max_tokens=min(cfg.max_output_tokens, tier.max_output_tokens),
                                metadata={"agent": agent, "prompt_id": prompt_id})
        t0 = utcnow()
        first = True
        in_think = False
        for item in get_provider(tier.provider).stream(req, tier):
            if isinstance(item, CompletionResult):
                cost = cost_of(tier, item.tokens_in, item.tokens_out)
                self.meter.charge(item.tokens_in, item.tokens_out, cost)
                cid = self._record(agent=agent, tier=tier, prompt=prompt, messages=messages, result=item, attempt=1,
                                   status="ok", error=None, temperature=cfg.temperature, schema_name=None,
                                   retrieved=[], cost=cost)
                yield TextResult(strip_thinking(item.text), tier.name, tier.model_id, False, [cid], item.tokens_in,
                                 item.tokens_out, cost)
                return
            delta = item
            if "<think>" in delta:
                in_think = True
            if in_think:
                if "</think>" in delta:
                    in_think = False
                    delta = delta.split("</think>", 1)[1]
                else:
                    continue
            if first and delta.strip():
                metrics.LLM_TTFT.labels(model=tier.model_id).observe((utcnow() - t0).total_seconds())
                first = False
            if delta:
                yield delta


__all__ = ["BudgetExceeded", "CallContext", "LLMGateway", "StructuredResult", "TextResult", "extract_json",
           "strip_thinking"]
