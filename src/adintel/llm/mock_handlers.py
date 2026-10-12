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
