"""Run engine: admission → state init (checkpoint v0) → graph loop (checkpoint every step, progress
events) → finalize. Idempotent start, resumable execution, graceful stop."""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any

from adintel.agents.base import AgentContext
from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, CheckpointCorrupted
from adintel.core.ids import new_id
from adintel.domain.enums import AuditAction, RunStatus
from adintel.domain.state import BudgetLimits, BudgetUsage, RunState
from adintel.graph import events
from adintel.graph.build import build_graph
from adintel.harness.admission import admit
from adintel.harness.budget import UsageMeter
from adintel.harness.checkpoint import CheckpointStore
from adintel.harness.idempotency import run_idempotency_key
from adintel.llm.gateway import CallContext, LLMGateway
from adintel.observability import context
from adintel.observability.langfuse import get_langfuse
from adintel.observability.tracing import span
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)


class RunEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------------------------------------
    def start(self, *, tenant_id: str, brand_id: str, period_start: date, period_end: date,
              goal: str = "weekly_report", trigger: str = "api", requested_by: str | None = None,
              schedule_date: date | None = None) -> tuple[dict[str, Any], bool]:
        """Admission + idempotent run record. Returns (run_doc, created)."""
        admit(self.db, tenant_id=tenant_id, brand_id=brand_id)
        brand = TenantScopedRepo(self.db, "brands", tenant_id).find_one({"brand_id": brand_id})
        if brand is None or not brand.get("active", True):
            raise AdIntelError(f"unknown or inactive brand {brand_id}")
        key = run_idempotency_key(tenant_id=tenant_id, brand_id=brand_id, period_start=period_start,
                                  period_end=period_end, goal=goal,
                                  schedule_date=schedule_date or utcnow().date())
        runs = TenantScopedRepo(self.db, "runs", tenant_id)
        doc = {"run_id": new_id("run"), "brand_id": brand_id, "brand_name": brand["name"],
               "idempotency_key": key, "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
               "goal": goal, "trigger": trigger, "requested_by": requested_by, "status": str(RunStatus.PENDING),
               "platforms": brand["platforms"], "created_at": utcnow().isoformat()}
        audit = AuditLog(self.db, tenant_id, system_version=get_settings().system_version)
        try:
            runs.insert(doc)
        except DuplicateKey:
            existing = runs.find_one({"idempotency_key": key})
            assert existing is not None
            audit.append(AuditAction.RUN_DUPLICATE, actor_type="system", actor_id=f"trigger:{trigger}",
                         subject_type="run", subject_id=existing["run_id"], run_id=existing["run_id"])
            return existing, False
        audit.append(AuditAction.RUN_STARTED, actor_type="human" if requested_by else "system",
                     actor_id=requested_by or f"trigger:{trigger}", subject_type="run", subject_id=doc["run_id"],
                     run_id=doc["run_id"], details={"brand_id": brand_id, "period_end": doc["period_end"]})
        return doc, True

    # ------------------------------------------------------------------------------------------------
    def _initial_state(self, run: dict[str, Any]) -> RunState:
        s = get_settings()
        return RunState(run_id=run["run_id"], tenant_id=run["tenant_id"], brand_id=run["brand_id"],
                        brand_name=run.get("brand_name", ""), period_start=date.fromisoformat(run["period_start"]),
                        period_end=date.fromisoformat(run["period_end"]), goal=run.get("goal", "weekly_report"),
                        trigger=run.get("trigger", "api"), requested_by=run.get("requested_by"),
                        platforms=list(run.get("platforms", [])),
                        limits=BudgetLimits(max_steps=s.run_max_steps, max_tokens=s.run_max_tokens,
                                            max_cost_usd=s.run_max_cost_usd, max_wall_seconds=s.run_max_wall_seconds),
                        usage=BudgetUsage())

    def execute(self, tenant_id: str, run_id: str, *, stop: threading.Event | None = None) -> RunState | None:
        """Run (or resume) a run to completion. Returns None if stopped gracefully mid-run."""
        runs = TenantScopedRepo(self.db, "runs", tenant_id)
        run = runs.find_one({"run_id": run_id})
        if run is None:
            raise AdIntelError(f"unknown run {run_id}")
        if RunStatus(run["status"]).terminal:
            log.info("run_already_finished", extra={"run_id": run_id})
            return None
        store = CheckpointStore(self.db, tenant_id)
        try:
            restored = store.latest(run_id)
        except CheckpointCorrupted as exc:
            log.error("checkpoint_corrupted", extra={"run_id": run_id})
            runs.update_one({"run_id": run_id}, {"$set": {"status": str(RunStatus.FAILED), "abort_reason": str(exc),
                                                          "finished_at": utcnow().isoformat()}})
            return None
        if restored:
            version, state = restored
            log.info("run_resumed", extra={"run_id": run_id, "from_checkpoint": version})
        else:
            version, state = 0, self._initial_state(run)
            store.save(state, version=0)
        runs.update_one({"run_id": run_id}, {"$set": {"status": str(RunStatus.RUNNING),
                                                      "started_at": utcnow().isoformat()}})
        meter = UsageMeter(state.limits, state.usage)

        def ctx_factory() -> AgentContext:
            gw = LLMGateway(self.db, CallContext(tenant_id=tenant_id, run_id=run_id, brand_id=state.brand_id,
                                                 step=meter.usage.steps), meter=meter)
            return AgentContext(self.db, tenant_id, state.brand_id, run_id, gw, meter)

        graph = build_graph(self.db, ctx_factory)
        lf = get_langfuse()
        if lf:
            lf.trace(run_id, f"run:{state.brand_id}", tenant_id=tenant_id,
                     metadata={"brand_id": state.brand_id, "period_end": str(state.period_end)})
        final: RunState = state
        with context.bind(run_id=run_id, tenant_id=tenant_id, brand_id=state.brand_id), \
                span("run", run_id=run_id, brand_id=state.brand_id):
            events.publish(self.db, tenant_id, run_id, "run_started", {"resumed_from": version if restored else None})
            first = True
            for value in graph.stream(state, stream_mode="values",
                                      config={"recursion_limit": state.limits.max_steps * 2 + 10}):
                if first:  # "values" mode echoes the input state first
                    first = False
                    continue
                cur = value if isinstance(value, RunState) else RunState.model_validate(value)
                version += 1
                store.save(cur, version=version)
                last = cur.traces[-1] if cur.traces else None
                events.publish(self.db, tenant_id, run_id, "step", {
                    "version": version, "agent": str(last.agent) if last else None,
                    "summary": last.summary if last else None, "status": str(cur.status),
                    "steps": cur.usage.steps, "cost_usd": cur.usage.cost_usd})
                final = cur
                if stop is not None and stop.is_set() and not cur.finalized:
                    log.warning("run_interrupted_gracefully", extra={"checkpoint": version})
                    events.publish(self.db, tenant_id, run_id, "interrupted", {"checkpoint": version})
                    return None
        events.publish(self.db, tenant_id, run_id, "run_finished", {"status": str(final.status)})
        return final

    def run(self, **kwargs: Any) -> RunState | None:
        doc, _ = self.start(**kwargs)
        return self.execute(kwargs["tenant_id"], doc["run_id"])
