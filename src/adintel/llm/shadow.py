"""Shadow mode (champion / challenger): try a new model on real traffic without letting it decide anything.

The promotion gate (``evals/gate.py``) proves a candidate model on golden datasets; it cannot prove it on
*this week's* data. Shadow mode closes that gap. For a configured champion tier, a sample of successful
structured calls is replayed — same redacted messages — against the challenger tier **after** the
champion's answer has already been returned. The challenger's output is validated against the same schema,
compared field by field with the champion's, and stored in ``shadow_results``. It is never used, never
charged to the run's budget, and a challenger failure is just a data point.

Configure in ``config/models.yaml``::

    tiers:
      frontier_next: { ...a normal tier definition... }
    shadow:
      frontier: { challenger: frontier_next, sample_rate: 0.2 }

then read the verdict with ``adintel shadow-report`` (or ``GET /admin/shadow``). A challenger is
"ready" after ≥ 50 samples with ≥ 98 % schema validity and ≥ 85 % field agreement — the evidence the
"3-day shadow on 20 % of traffic" step of the promotion gate asks for.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from statistics import median
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from adintel.core.clock import utcnow
from adintel.llm import bulkhead
from adintel.llm.providers import get_provider
from adintel.llm.types import CompletionRequest, Message, TierConfig
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

if TYPE_CHECKING:
    from adintel.llm.gateway import LLMGateway

log = logging.getLogger(__name__)
NEVER_SHADOWED = frozenset({"guardrail"})  # the safety path stays single-model and fail-closed
READY = {"min_samples": 50, "min_valid_rate": 0.98, "min_field_agreement": 0.85}

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow")
_sync = threading.local()


def sampled(key: str, rate: float) -> bool:
    """Deterministic sampling: the same call is always in or out of the sample."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < rate


def agreement(champion: dict[str, Any], challenger: dict[str, Any]) -> float:
    keys = set(champion) | set(challenger)
    return round(sum(champion.get(k) == challenger.get(k) for k in keys) / len(keys), 4) if keys else 1.0


def maybe_shadow(
    gw: LLMGateway,
    *,
    agent: str,
    champion: TierConfig,
    messages: list[Message],
    request: CompletionRequest,
    schema: type[BaseModel],
    value: BaseModel,
    call_id: str,
    latency_ms: float,
) -> None:
    plan = gw.registry.shadow.get(champion.name)
    if not plan or agent in NEVER_SHADOWED or not sampled(call_id, plan["sample_rate"]):
        return
    challenger = gw.registry.tiers[plan["challenger"]]
    job = (gw._db, gw.ctx.tenant_id, gw.ctx.run_id, agent, champion, challenger, messages, request, schema, value)
    if getattr(_sync, "on", False):
        _run(*job, call_id, latency_ms)
    else:
        _pool.submit(_run, *job, call_id, latency_ms)


def _run(
    db: Database,
    tenant_id: str,
    run_id: str | None,
    agent: str,
    champion: TierConfig,
    challenger: TierConfig,
    messages: list[Message],
    request: CompletionRequest,
    schema: type[BaseModel],
    value: BaseModel,
    call_id: str,
    champion_latency_ms: float,
) -> None:
    doc: dict[str, Any] = {
        "agent": agent,
        "run_id": run_id,
        "champion_call_id": call_id,
        "champion_tier": champion.name,
        "champion_model": champion.model_id,
        "challenger_tier": challenger.name,
        "challenger_model": challenger.model_id,
        "champion_latency_ms": champion_latency_ms,
        "created_at": utcnow().isoformat(),
    }
    t0 = time.perf_counter()
    try:
        req = CompletionRequest(
            messages=messages,
            temperature=request.temperature,
            max_tokens=min(request.max_tokens, challenger.max_output_tokens),
            seed=request.seed,
            metadata={**request.metadata, "shadow": True},
        )
        with bulkhead.slot(challenger):
            result = get_provider(challenger.provider).complete(req, challenger)
        doc["challenger_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        doc["tokens"] = {"in": result.tokens_in, "out": result.tokens_out}
        try:
            from adintel.llm.gateway import extract_json  # late: gateway imports this module

            other = schema.model_validate_json(extract_json(result.text))
            a, b = value.model_dump(mode="json"), other.model_dump(mode="json")
            doc.update(valid=True, exact=a == b, field_agreement=agreement(a, b))
        except ValidationError as exc:
            doc.update(valid=False, exact=False, field_agreement=0.0, error=str(exc.errors()[:3])[:500])
    except Exception as exc:  # a challenger failure is a data point, never a problem for the run
        doc.update(valid=False, exact=False, field_agreement=0.0, error=f"{type(exc).__name__}: {exc}"[:500])
        doc["challenger_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    try:
        TenantScopedRepo(db, "shadow_results", tenant_id).insert(doc)
    except Exception:
        log.exception("shadow_record_failed")


def report(db: Database, tenant_id: str, *, days: int = 3) -> list[dict[str, Any]]:
    since = (utcnow() - timedelta(days=days)).isoformat()
    rows = TenantScopedRepo(db, "shadow_results", tenant_id).find({"created_at": {"$gte": since}})
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["challenger_model"], r["agent"]), []).append(r)
    out = []
    for (model, agent), rs in sorted(groups.items()):
        n = len(rs)
        valid = sum(r["valid"] for r in rs) / n
        agree = sum(r["field_agreement"] for r in rs) / n
        lat_c = [r["champion_latency_ms"] for r in rs if r.get("champion_latency_ms")]
        lat_x = [r["challenger_latency_ms"] for r in rs if r.get("challenger_latency_ms")]
        ready = n >= READY["min_samples"] and valid >= READY["min_valid_rate"] and agree >= READY["min_field_agreement"]
        out.append(
            {
                "challenger_model": model,
                "agent": agent,
                "samples": n,
                "valid_rate": round(valid, 3),
                "exact_rate": round(sum(r["exact"] for r in rs) / n, 3),
                "field_agreement": round(agree, 3),
                "p50_latency_ms": {
                    "champion": median(lat_c) if lat_c else None,
                    "challenger": median(lat_x) if lat_x else None,
                },
                "verdict": "ready" if ready else ("collecting" if n < READY["min_samples"] else "not_ready"),
            }
        )
    return out
