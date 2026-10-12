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
