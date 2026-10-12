"""Default deterministic handlers for the mock provider, one per schema/prompt.

Each agent module's commit adds its handler here. Handlers read only the ``<context>`` JSON.
"""

from __future__ import annotations

import json
from typing import Any

from adintel.llm.providers.mock import register
from adintel.llm.types import Message, TierConfig


@register("echo")
def _echo(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    return json.dumps(ctx)


@register("dq_summary")
def _dq_summary(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    failed = [c["name"] for c in ctx.get("checks", []) if not c.get("passed")]
    if not failed:
        return "All data-quality checks passed, so tonight's analysis can rely on this data."
    return (f"The data is {ctx.get('verdict')}: the {', '.join(failed)} check(s) failed. "
            "Findings that depend on it are flagged accordingly.")


@register("MappingProposal")
def _mapping(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    import re

    user = messages[-1].content
    fields = re.findall(r'"([a-zA-Z0-9_.]+)"', user.split("<untrusted_content", 1)[-1])
    return json.dumps({"mappings": [{"field": f, "maps_to": "ignore", "confidence": 0.4} for f in fields[:5]]})


@register("AnalystOutput")
def _analyst(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    """Behaves like a careful analyst: first round asks for queries, second round concludes."""
    user = messages[-1].content
    if "ignore prior instructions" in user.lower() or "ignore previous instructions" in user.lower():
        return json.dumps({"hypotheses": [], "queries": [], "root_cause_summary": "", "confidence": 0.0,
                           "injection_suspected": True,
                           "injection_detail": "entity name contains instructions addressed to the model"})
    facts = ctx.get("facts", {})
    dec = facts.get("decomposition", {})
    if ctx.get("round", 1) == 1:
        return json.dumps({"hypotheses": [], "queries": [
            "df.groupby('entity_id')['spend'].sum().round(2)",
            "(df.groupby('entity_id')['spend'].sum() / df.groupby('entity_id')['conversions'].sum()).round(2)",
            "df.groupby('date')['spend'].sum().tail(7).round(2)"], "confidence": 0.0})
    mix_share = dec.get("mix_share_pct") or 0
    before, after = facts.get("entities_before", {}), facts.get("entities_after", {})
    gainer = max(after, key=lambda e: after[e]["spend_share_pct"] - before.get(e, {}).get("spend_share_pct", 0),
                 default=None)
    if mix_share and mix_share >= 50 and gainer:
        name = after[gainer]["entity_name"]
        return json.dumps({
            "hypotheses": [
                {"name": "budget reallocation", "verdict": "confirmed",
                 "evidence": f"{mix_share}% of the CPA change is explained by spend moving to {name}"},
                {"name": "audience fatigue", "verdict": "ruled_out",
                 "evidence": "per-ad-set CTR is within its normal range"},
                {"name": "creative decay", "verdict": "ruled_out",
                 "evidence": "per-ad-set CPA is stable; the blend changed, not the ad sets"}],
            "queries": [], "confidence": 0.81,
            "root_cause_summary": (f"A budget increase made the platform shift spend to {name}, an expensive "
                                   "ad set. The ad sets themselves are fine; the allocation is wrong.")})
    return json.dumps({"hypotheses": [{"name": "auction pressure", "verdict": "inconclusive",
                                       "evidence": "per-ad-set CPA rose without a mix shift"}],
                       "queries": [], "confidence": 0.45,
                       "root_cause_summary": "Per-ad-set efficiency declined; cause not isolated."})


@register("OptimizerOutput")
def _optimizer(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    facts = ctx.get("facts", {})
    before, after = facts.get("entities_before", {}), facts.get("entities_after", {})
    live = ctx.get("live_entities", {})
    cap = ctx.get("constraints", {}).get("max_single_change_pct", 25) / 100
    ids = ctx.get("retrieved_chunk_ids", [])
    if not after or not live or not ids:
        return json.dumps({"proposals": []})
    source = max(after, key=lambda e: after[e]["spend_share_pct"] - before.get(e, {}).get("spend_share_pct", 0))
    target = min((e for e in after if e != source and after[e].get("cpa")), key=lambda e: after[e]["cpa"],
                 default=None)
    if target is None or source not in live:
        return json.dumps({"proposals": []})
    amount = round(float(live[source]["daily_budget"]) * cap, 2)
    return json.dumps({"proposals": [{
        "action_type": "budget_shift", "platform": ctx["anomaly"]["platform"], "source_entity_id": source,
        "target_entity_id": target, "amount_usd_per_day": amount,
        "expected_impact": "CPA expected to fall back towards its normal range within 5-7 days",
        "expected_cpa_change_pct_low": -34.0, "expected_cpa_change_pct_high": -22.0,
        "rationale": (f"Move ${amount:.0f}/day from {after[source]['entity_name']} back to "
                      f"{after[target]['entity_name']}, reversing the platform's reallocation, as in the cited "
                      "incident and playbook."),
        "citation_chunk_ids": ids[:2]}]})


@register("ReportOutput")
def _report(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    f = ctx.get("findings", {})
    cur, ch = f.get("current", {}), f.get("changes", {})

    def money(v: Any) -> str:
        return "n/a" if v is None else f"${v:,.2f}"

    an = f.get("anomalies", [])
    anomaly_text = " ".join(
        f"On {a['platform']}, {a['campaign']} saw {a['metric'].upper()} at {a['observed']} against an expected "
        f"{a['expected']} for {a['days']} days." for a in an) or "Nothing unusual stood out this week."
    rc = " ".join(r["summary"] for r in f.get("root_causes", []))
    recs = " ".join(f"We propose moving {money(r['amount_usd_per_day'])} per day, pending your account team's "
                    "approval." for r in f.get("recommendations", [])) or "No changes are proposed."
    sc = ch.get("spend_change_pct")
    spend_move = f" ({abs(sc):.1f}% {'up' if sc > 0 else 'down'} on the prior period)" if sc is not None else ""
    sections = [
        {"key": "summary", "title": "Summary", "body": f"A steady week for {f.get('brand')}." if not an else
         f"One area needs attention this week for {f.get('brand')}."},
        {"key": "performance", "title": "Performance", "body": (
            f"You invested {money(cur.get('spend'))}{spend_move}, driving {cur.get('conversions')} conversions at a "
            f"CPA of {money(cur.get('cpa'))}.")},
        {"key": "anomalies", "title": "What changed", "body": f"{anomaly_text} {rc}".strip()},
        {"key": "recommendations", "title": "Proposed actions", "body": recs},
        {"key": "caveats", "title": "Caveats", "body": " ".join(f.get("caveats", [])) or "None."},
        {"key": "next_steps", "title": "Next steps", "body": "We'll review progress together next week."},
    ]
    return json.dumps({"title": f"{f.get('brand')} weekly report", "sections": sections})


@register("SafetyVerdict")
def _safety(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    text = messages[-1].content.lower()
    cats = []
    if any(w in text for w in ("kill", "hate", "illegal")):
        cats.append("S5")
    if "without approval" in text or "skip approval" in text:
        cats.append("S6")
    if "competitor's strategy" in text or "other client" in text:
        cats.append("S1")
    return json.dumps({"safe": not cats, "categories": cats, "reason": "mock classifier"})


@register("OrchestratorOutput")
def _orchestrator(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    high = [a for a in ctx.get("anomalies", []) if a.get("severity") in ("high", "critical")]
    if high and not ctx.get("root_cause_exists"):
        return json.dumps({"next_action": "analyst", "reasoning": (
            f"High severity {high[0]['metric']} anomaly with ${high[0]['spend_at_risk_weekly']:,.0f}/week at risk, "
            "trustworthy data and no root cause yet: investigate.")})
    return json.dumps({"next_action": "report", "reasoning": "Remaining anomalies are immaterial."})


@register("Route")
def _route(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    q = messages[-1].content.lower()
    complex_words = ("why", "compare", "strategy", "should we", "explain", "diagnos")
    return json.dumps({"route": "complex" if any(w in q for w in complex_words) else "simple"})


@register("chat")
def _chat(ctx: dict[str, Any], messages: list[Message], tier: TierConfig) -> str:
    facts = ctx.get("facts", {}).get("last_7_days", {}).get("current", {})
    spend = facts.get("spend")
    cpa = facts.get("cpa")
    base = f"Over the last 7 days {ctx.get('brand')} spent ${spend:,.2f}" if spend is not None else "I have no data"
    if cpa is not None:
        base += f" at a CPA of ${cpa:,.2f}"
    return base + ". Proposed changes are reviewed in the Approvals screen."
