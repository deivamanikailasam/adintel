"""Optimization agent: proposes what to do — it has **no execution tool**.

Every proposal must cite retrieved evidence, passes pure-code brand constraints, gets its exposure and
risk computed in code, is pinned to a snapshot hash of the live entities, and is saved as
*pending approval* with an expiry. Execution is a separate service with no model access.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field

from adintel.agents.base import AgentContext
from adintel.approvals import constraints
from adintel.config import get_settings
from adintel.connectors import get_connector
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, LLMUnavailable, LLMValidationError
from adintel.domain.enums import ActionType, AgentName, DegradationCode, DQVerdict, Platform
from adintel.domain.models import BrandRules, Citation, Recommendation
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.observability.alerts import Severity, raise_alert
from adintel.observability.metrics import INJECTION_FLAGS
from adintel.rag.retriever import RetrievalUnavailable
from adintel.security.secrets import SecretStore

log = logging.getLogger(__name__)
MIN_ROOT_CAUSE_CONFIDENCE = 0.6


class ProposalDraft(BaseModel):
    action_type: ActionType
    platform: Platform
    source_entity_id: str | None = None
    target_entity_id: str
    amount_usd_per_day: float
    expected_impact: str
    expected_cpa_change_pct_low: float | None = None
    expected_cpa_change_pct_high: float | None = None
    rationale: str
    citation_chunk_ids: list[str] = Field(default_factory=list)


class OptimizerOutput(BaseModel):
    proposals: list[ProposalDraft] = Field(default_factory=list, max_length=2)
    injection_suspected: bool = False
    injection_detail: str = ""


def _live_entities(ctx: AgentContext, platform: Platform, entity_ids: list[str]) -> dict[str, dict[str, Any]]:
    cred = SecretStore().get(ctx.tenant_id, str(platform), "read")
    conn = get_connector(platform)
    out = {}
    for eid in entity_ids:
        try:
            out[eid] = conn.get_entity(cred, ctx.brand_id, eid)
        except AdIntelError as exc:
            log.warning("live_entity_unavailable", extra={"entity_id": eid, "reason": str(exc)[:120]})
    return out


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    update: dict[str, Any] = {"optimizer_done": True}
    if state.dq and state.dq.verdict != DQVerdict.TRUSTWORTHY:
        update["degradations"] = [degrade(DegradationCode.OPTIMIZER_BLOCKED_DQ, AgentName.OPTIMIZER)]
        return update
    rcs = [rc for rc in state.root_causes if rc.confidence >= MIN_ROOT_CAUSE_CONFIDENCE and not rc.injection_suspected]
    if not rcs:
        return update
    rc = rcs[0]
    anomaly = next(a for a in state.anomalies if a.anomaly_id == rc.anomaly_id)
    facts = state.metrics_summary.get("analyst_facts", {})
    entity_ids = sorted(set(facts.get("entities_before", {})) | set(facts.get("entities_after", {})))
    live = _live_entities(ctx, anomaly.platform, entity_ids)
    rules_doc = ctx.repo("brand_rules").find_one({"brand_id": ctx.brand_id})
    rules = BrandRules.from_doc(rules_doc) if rules_doc else BrandRules(tenant_id=ctx.tenant_id, brand_id=ctx.brand_id)
    brand = ctx.repo("brands").find_one({"brand_id": ctx.brand_id}) or {}
    try:
        res = ctx.retriever().search(
            f"{rc.summary} remediation playbook {anomaly.metric} {anomaly.platform}",
            brand_id=ctx.brand_id,
            vertical=(brand.get("profile") or {}).get("vertical"),
            doc_types=["playbook", "incident"],
            k=6,
        )
    except RetrievalUnavailable:
        update["degradations"] = [degrade(DegradationCode.VECTOR_SEARCH_UNAVAILABLE, AgentName.OPTIMIZER)]
        return update
    if not res.chunks:
        update["degradations"] = [degrade(DegradationCode.NO_CITATIONS, AgentName.OPTIMIZER, "no evidence")]
        return update
    context = {
        "anomaly": anomaly.model_dump(mode="json"),
        "root_cause": rc.model_dump(mode="json"),
        "facts": facts,
        "live_entities": live,
        "retrieved_chunk_ids": res.ids,
        "constraints": {
            "allowed_actions": [str(a) for a in rules.allowed_actions],
            "max_single_change_pct": rules.max_single_change_pct,
            "min_daily_budget_usd": rules.min_daily_budget_usd,
            "protected_entity_ids": rules.protected_entity_ids,
        },
    }
    try:
        r = ctx.llm.structured(
            agent="optimizer",
            prompt_id="optimizer",
            schema=OptimizerOutput,
            context=context,
            untrusted={"retrieved_evidence": [c.as_evidence() for c in res.chunks]},
            retrieved_doc_ids=res.ids,
            allow_fallback=False,
        )
    except LLMUnavailable:
        update["frontier_available"] = False
        update["degradations"] = [
            degrade(DegradationCode.FRONTIER_UNAVAILABLE, AgentName.OPTIMIZER),
            degrade(DegradationCode.OPTIMIZER_SKIPPED, AgentName.OPTIMIZER, "frontier down"),
        ]
        return update
    except LLMValidationError as exc:
        update["degradations"] = [degrade(DegradationCode.OPTIMIZER_SKIPPED, AgentName.OPTIMIZER, str(exc)[:120])]
        return update
    out = r.value
    if out.injection_suspected:
        INJECTION_FLAGS.labels(agent="optimizer").inc()
        raise_alert(
            Severity.P1,
            "Prompt injection suspected in retrieved evidence",
            tenant_id=ctx.tenant_id,
            brand_id=ctx.brand_id,
            details={"run_id": ctx.run_id, "detail": out.injection_detail[:300]},
            audience="security",
        )
        update["degradations"] = [
            degrade(DegradationCode.INJECTION_SUSPECTED, AgentName.OPTIMIZER, out.injection_detail[:200])
        ]
        return update
    now = utcnow()
    by_id = {c.chunk_id: c for c in res.chunks}
    recs: list[Recommendation] = []
    rejected: list[Any] = []
    for p in out.proposals:
        violations = constraints.check(
            action=p.action_type,
            source=p.source_entity_id,
            target=p.target_entity_id,
            amount=p.amount_usd_per_day,
            rules=rules,
            entities=live,
            citations=p.citation_chunk_ids,
            retrieved_ids=res.ids,
            now=now,
        )
        if p.platform != anomaly.platform:
            violations.append("proposal platform differs from the anomaly's platform")
        if violations:
            log.info("proposal_rejected_by_constraints", extra={"violations": violations})
            rejected.append(degrade(DegradationCode.CONSTRAINT_REJECTED, AgentName.OPTIMIZER, "; ".join(violations)))
            continue
        exposure = constraints.exposure_usd(p.action_type, p.amount_usd_per_day, live, p.target_entity_id)
        risk, irreversible = constraints.risk_for(p.action_type, exposure)
        ids = [i for i in (p.source_entity_id, p.target_entity_id) if i]
        recs.append(
            Recommendation(
                tenant_id=ctx.tenant_id,
                brand_id=ctx.brand_id,
                run_id=ctx.run_id,
                anomaly_id=anomaly.anomaly_id,
                action_type=p.action_type,
                platform=p.platform,
                source_entity_id=p.source_entity_id,
                target_entity_id=p.target_entity_id,
                amount_usd_per_day=round(p.amount_usd_per_day, 2),
                daily_exposure_usd=exposure,
                expected_impact=p.expected_impact,
                expected_cpa_change_pct_low=p.expected_cpa_change_pct_low,
                expected_cpa_change_pct_high=p.expected_cpa_change_pct_high,
                rationale=p.rationale,
                citations=[
                    Citation(chunk_id=c, doc_title=by_id[c].doc_title, snippet=by_id[c].text[:280])
                    for c in p.citation_chunk_ids
                ],
                risk=risk,
                irreversible=irreversible,
                entity_snapshot_hash=constraints.snapshot_hash(live, ids),
                expires_at=now + timedelta(hours=get_settings().recommendation_ttl_hours),
                constraint_checks=[
                    "allowed_action",
                    "entities_active",
                    "max_single_change_pct",
                    "min_daily_budget",
                    "citations_in_evidence",
                    "no_blackout",
                ],
            )
        )
    update["recommendations"] = recs
    if rejected:
        update["degradations"] = rejected
    return update
