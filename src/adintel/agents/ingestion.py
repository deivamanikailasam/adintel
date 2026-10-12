"""Ingestion agent: correct, normalised data from 5 ad platforms. Deterministic code; the small model
only *proposes* mappings for unknown fields (never applied automatically)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from adintel.agents.base import AgentContext
from adintel.analytics.frames import load_frame, period_summary
from adintel.connectors import get_connector
from adintel.connectors.normalize import normalise
from adintel.core.errors import AdIntelError, PlatformUnavailable
from adintel.core.resilience import CircuitOpen, breaker, retry_call
from adintel.domain.enums import AgentName, DegradationCode, Platform, RunStatus
from adintel.domain.models import PlatformFetch
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.harness.timeouts import PLATFORM_FETCH_SECONDS
from adintel.security.secrets import SecretStore

log = logging.getLogger(__name__)
HISTORY_DAYS = 180


class FieldMapping(BaseModel):
    field: str
    maps_to: str
    confidence: float = Field(ge=0, le=1)


class MappingProposal(BaseModel):
    mappings: list[FieldMapping]
    injection_suspected: bool = False
    injection_detail: str = ""


def _fetch_one(ctx: AgentContext, platform: Platform, start: date, end: date) -> tuple[PlatformFetch, list[Any]]:
    t0 = time.perf_counter()
    cb = breaker(f"platform:{platform}")
    try:
        cb.before_call()
    except CircuitOpen:
        return PlatformFetch(platform=platform, ok=False, error="circuit open"), []
    try:
        cred = SecretStore().get(ctx.tenant_id, str(platform), "read")
        raw = retry_call(lambda: get_connector(platform).fetch(cred, ctx.brand_id, start, end), retries=1,
                         transient=(PlatformUnavailable,), base_delay=0.5)
        rows, unmapped = normalise(raw, tenant_id=ctx.tenant_id, brand_id=ctx.brand_id)
        cb.record_success()
    except AdIntelError as exc:
        cb.record_failure()
        return PlatformFetch(platform=platform, ok=False, error=str(exc)[:300],
                             latency_ms=(time.perf_counter() - t0) * 1000), []
    keys = [(r.platform, r.entity_id, r.date) for r in rows]
    raw_total = round(sum(r.spend for r in rows), 2)
    return PlatformFetch(platform=platform, ok=True, rows=len(rows), latency_ms=(time.perf_counter() - t0) * 1000,
                         unmapped_fields=unmapped, raw_spend_total_usd=raw_total,
                         duplicates=len(keys) - len(set(keys)),
                         currencies=sorted({r.currency_original for r in rows})), rows


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    platforms = [Platform(p) for p in state.platforms]
    start = state.period_end - timedelta(days=HISTORY_DAYS - 1)
    fetches: list[PlatformFetch] = []
    all_rows: list[Any] = []
    degradations = []
    pool = ThreadPoolExecutor(max_workers=max(1, len(platforms)), thread_name_prefix="ingest")
    futures = {p: pool.submit(_fetch_one, ctx, p, start, state.period_end) for p in platforms}
    for p, fut in futures.items():
        try:
            f, rows = fut.result(timeout=PLATFORM_FETCH_SECONDS)
        except FutureTimeout:
            f, rows = PlatformFetch(platform=p, ok=False, error=f"timeout after {PLATFORM_FETCH_SECONDS:.0f}s"), []
        fetches.append(f)
        all_rows.extend(rows)
        if not f.ok:
            degradations.append(degrade(DegradationCode.PLATFORM_UNAVAILABLE, AgentName.INGESTION, str(p)))
    pool.shutdown(wait=False, cancel_futures=True)

    repo = ctx.repo("metrics_daily")
    for r in all_rows:
        doc = r.model_dump(mode="json")
        repo.update_one({"brand_id": r.brand_id, "platform": doc["platform"], "entity_id": r.entity_id,
                         "date": doc["date"]}, {"$set": doc}, upsert=True)

    drift = {str(f.platform): f.unmapped_fields for f in fetches if f.unmapped_fields}
    for platform, fields in drift.items():
        degradations.append(degrade(DegradationCode.SCHEMA_DRIFT, AgentName.INGESTION, platform))
        _propose_mapping(ctx, platform, fields)

    ok = [str(f.platform) for f in fetches if f.ok]
    update: dict[str, Any] = {"fetches": fetches, "degradations": degradations}
    if not ok:
        update["degradations"] = [*degradations, degrade(DegradationCode.ALL_PLATFORMS_UNAVAILABLE,
                                                         AgentName.INGESTION, "all")]
        update["status"] = RunStatus.FAILED
        update["abort_reason"] = "all platforms unavailable; retry scheduled for 06:00"
        return update
    df = load_frame(repo, ctx.brand_id, start, state.period_end, ok)
    update["metrics_ref"] = {"collection": "metrics_daily", "brand_id": ctx.brand_id, "start": start.isoformat(),
                             "end": state.period_end.isoformat(), "platforms": ok}
    update["metrics_summary"] = period_summary(df, state.period_start, state.period_end)
    return update


def _propose_mapping(ctx: AgentContext, platform: str, fields: list[str]) -> None:
    """Best effort: a proposal for engineering review. Never applied, never blocks the run."""
    try:
        res = ctx.llm.structured(agent="ingestion", prompt_id="ingestion_mapping", schema=MappingProposal,
                                 context={"platform": platform,
                                          "canonical_fields": ["impressions", "clicks", "spend", "conversions",
                                                               "revenue", "daily_budget", "ignore"]},
                                 untrusted={f"{platform}_unknown_fields": fields})
        ctx.repo("notifications").insert({"kind": "schema_mapping_proposal", "platform": platform,
                                          "brand_id": ctx.brand_id, "run_id": ctx.run_id,
                                          "proposal": res.value.model_dump(), "audience": "engineering",
                                          "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    except Exception as exc:  # noqa: BLE001 - a proposal must never fail ingestion
        log.warning("mapping_proposal_failed", extra={"platform": platform, "reason": str(exc)[:200]})
