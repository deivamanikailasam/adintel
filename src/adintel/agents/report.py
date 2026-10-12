"""Report agent: the client-facing weekly report in brand voice.

Fallback ladder (numeric grounding never degrades):
1. report tier (small model + LoRA adapter for the brand's tone cluster), temperature 0.2;
2. if any number fails grounding → rewrite with the frontier tier (``report_fallback_frontier``);
3. if that fails too, or models/budget are unavailable → a deterministic template whose numbers are
   correct by construction (``report_template``).
Caveats from every degradation are appended by code, verbatim — the model cannot drop them.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator

from adintel.agents.base import AgentContext
from adintel.core.errors import BudgetExceeded, LLMUnavailable, LLMValidationError
from adintel.domain.enums import AgentName, DegradationCode
from adintel.domain.models import Report, ReportSection
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.observability.metrics import GROUNDING_FAILURES
from adintel.rag.grounding import check_grounding

log = logging.getLogger(__name__)
SECTION_KEYS = ["summary", "performance", "anomalies", "recommendations", "caveats", "next_steps"]
TITLES = {
    "summary": "Summary",
    "performance": "Performance",
    "anomalies": "What changed",
    "recommendations": "Proposed actions",
    "caveats": "Caveats",
    "next_steps": "Next steps",
}


class SectionOut(BaseModel):
    key: str
    title: str
    body: str = Field(max_length=3000)


class ReportOutput(BaseModel):
    title: str = Field(max_length=200)
    sections: list[SectionOut]

    @field_validator("sections")
    @classmethod
    def _order(cls, v: list[SectionOut]) -> list[SectionOut]:
        keys = [s.key for s in v]
        if keys != SECTION_KEYS:
            raise ValueError(f"sections must be exactly {SECTION_KEYS} in order, got {keys}")
        return v


def build_facts(state: RunState) -> dict[str, Any]:
    ms = state.metrics_summary
    caveats = list(dict.fromkeys(d.client_caveat for d in state.degradations if d.client_caveat))
    return {
        "brand": state.brand_name or state.brand_id,
        "period": {"start": state.period_start.isoformat(), "end": state.period_end.isoformat()},
        "current": ms.get("current", {}),
        "previous": ms.get("previous", {}),
        "changes": ms.get("changes", {}),
        "by_platform": ms.get("by_platform", {}),
        "anomalies": [
            {
                "metric": str(a.metric),
                "platform": str(a.platform),
                "campaign": a.entity_name,
                "direction": a.direction,
                "observed": round(a.observed, 2),
                "expected": round(a.expected, 2),
                "normal_range_low": round(a.lower, 2),
                "normal_range_high": round(a.upper, 2),
                "deviation_pct": a.deviation_pct,
                "days": a.days,
                "severity": str(a.severity),
                "spend_at_risk_weekly": a.spend_at_risk_weekly,
            }
            for a in state.material_anomalies()
        ],
        "root_causes": [
            {"summary": rc.summary, "confidence": rc.confidence}
            for rc in state.root_causes
            if not rc.injection_suspected
        ],
        "recommendations": [
            {
                "action": str(r.action_type),
                "amount_usd_per_day": r.amount_usd_per_day,
                "daily_exposure_usd": r.daily_exposure_usd,
                "from": r.source_entity_id,
                "to": r.target_entity_id,
                "expected_cpa_change_pct_low": r.expected_cpa_change_pct_low,
                "expected_cpa_change_pct_high": r.expected_cpa_change_pct_high,
                "rationale": r.rationale,
            }
            for r in state.recommendations
        ],
        "caveats": caveats,
    }


def _money(v: Any) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def _pct(v: Any) -> str:
    return "n/a" if v is None else f"{abs(v):.1f}% {'higher' if v > 0 else 'lower'}"


def render_template(facts: dict[str, Any]) -> ReportOutput:
    """Deterministic report: every number is copied from the facts."""
    cur, ch = facts["current"], facts["changes"]
    p = facts["period"]
    perf = [
        f"Spend was {_money(cur.get('spend'))} ({_pct(ch.get('spend_change_pct'))} than the prior period), "
        f"with {cur.get('conversions', 0):,} conversions and {_money(cur.get('revenue'))} in revenue. "
        f"CPA was {_money(cur.get('cpa'))} and ROAS {cur.get('roas') if cur.get('roas') is not None else 'n/a'}."
    ]
    for plat, t in sorted(facts["by_platform"].items()):
        perf.append(f"- {plat}: spend {_money(t.get('spend'))}, CPA {_money(t.get('cpa'))}.")
    anomalies = [
        f"- {a['campaign']} ({a['platform']}): {a['metric'].upper()} {a['observed']} vs an expected "
        f"{a['expected']} (normal range {a['normal_range_low']}–{a['normal_range_high']}) for {a['days']} "
        f"days, {a['severity']} severity."
        for a in facts["anomalies"]
    ] or ["No material changes were detected this period."]
    for rc in facts["root_causes"]:
        anomalies.append(f"Likely cause: {rc['summary']}")
    recs = [
        f"- Proposed: {r['action'].replace('_', ' ')} of {_money(r['amount_usd_per_day'])}/day "
        f"(awaiting approval by the account team)."
        for r in facts["recommendations"]
    ] or ["No changes are proposed this week."]
    return ReportOutput(
        title=f"{facts['brand']} — weekly performance, {p['start']} to {p['end']}",
        sections=[
            SectionOut(
                key="summary",
                title=TITLES["summary"],
                body=f"This report covers {p['start']} to {p['end']}. "
                + (
                    f"{len(facts['anomalies'])} material change(s) were found."
                    if facts["anomalies"]
                    else "Performance was within its normal range."
                ),
            ),
            SectionOut(key="performance", title=TITLES["performance"], body="\n".join(perf)),
            SectionOut(key="anomalies", title=TITLES["anomalies"], body="\n".join(anomalies)),
            SectionOut(key="recommendations", title=TITLES["recommendations"], body="\n".join(recs)),
            SectionOut(
                key="caveats", title=TITLES["caveats"], body="\n".join(f"- {c}" for c in facts["caveats"]) or "None."
            ),
            SectionOut(
                key="next_steps",
                title=TITLES["next_steps"],
                body="Your account manager will review the findings and any proposed changes with you.",
            ),
        ],
    )


def _enforce_caveats(out: ReportOutput, caveats: list[str]) -> ReportOutput:
    sec = next(s for s in out.sections if s.key == "caveats")
    missing = [c for c in caveats if c not in sec.body]
    if missing:
        body = "" if sec.body.strip().lower() in ("", "none.", "none") else sec.body.rstrip() + "\n"
        sec.body = body + "\n".join(f"- {c}" for c in missing)
    return out


def _to_report(out: ReportOutput, facts: dict[str, Any], tier: str, *, template: bool, adapter: str | None) -> Report:
    text = "\n".join(s.body for s in out.sections)
    return Report(
        title=out.title,
        sections=[ReportSection(key=s.key, title=s.title, body=s.body) for s in out.sections],
        facts=facts,
        model_tier=tier,
        adapter_sha256=adapter,
        deterministic_template=template,
        grounding=check_grounding(text + "\n" + out.title, facts),
    )


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    brand = ctx.repo("brands").find_one({"brand_id": ctx.brand_id}) or {}
    return write(
        ctx,
        build_facts(state),
        brand.get("profile") or {},
        budget_exhausted=state.budget_exhausted,
        frontier_available=state.frontier_available,
    )


def write(
    ctx: AgentContext,
    facts: dict[str, Any],
    profile: dict[str, Any],
    *,
    budget_exhausted: bool = False,
    frontier_available: bool = True,
) -> dict[str, Any]:
    """Write a grounded report from facts (also used directly by the report eval suite)."""
    context = {
        "findings": facts,
        "tone_cluster": profile.get("tone_cluster", "neutral"),
        "voice_notes": profile.get("voice_notes", ""),
        "required_sections": SECTION_KEYS,
    }
    degradations = []
    tone_tier = ctx.llm.registry.report_tier(context["tone_cluster"])
    adapter = ctx.llm.registry.tiers[tone_tier].adapter_sha256
    if not budget_exhausted:
        for tier in (tone_tier, "frontier"):
            if tier == "frontier" and not frontier_available:
                break
            try:
                r = ctx.llm.structured(
                    agent="report",
                    prompt_id="report",
                    schema=ReportOutput,
                    context=context,
                    tier_override=tier,
                    allow_fallback=False,
                )
            except (LLMUnavailable, LLMValidationError) as exc:
                log.warning("report_tier_failed", extra={"tier": tier, "reason": str(exc)[:160]})
                if tier != "frontier":
                    degradations.append(
                        degrade(DegradationCode.REPORT_FALLBACK_FRONTIER, AgentName.REPORT, type(exc).__name__)
                    )
                continue
            except BudgetExceeded:
                break
            out = _enforce_caveats(r.value, facts["caveats"])
            report = _to_report(out, facts, tier, template=False, adapter=adapter if tier != "frontier" else None)
            if report.grounding and report.grounding.passed:
                return {"report": report, "degradations": degradations}
            GROUNDING_FAILURES.labels(agent=f"report:{tier}").inc()
            log.warning(
                "report_grounding_failed",
                extra={"tier": tier, "ungrounded": report.grounding.ungrounded if report.grounding else []},
            )
            if tier != "frontier":
                degradations.append(
                    degrade(DegradationCode.REPORT_FALLBACK_FRONTIER, AgentName.REPORT, "number check failed")
                )
    degradations.append(degrade(DegradationCode.REPORT_TEMPLATE, AgentName.REPORT))
    facts["caveats"] = list(
        dict.fromkeys([*facts["caveats"], *(d.client_caveat for d in degradations if d.client_caveat)])
    )
    out = render_template(facts)
    return {"report": _to_report(out, facts, "template", template=True, adapter=None), "degradations": degradations}
