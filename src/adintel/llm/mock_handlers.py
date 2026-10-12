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
