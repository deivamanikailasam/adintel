from __future__ import annotations

import json
from typing import Any


def sse(data: dict[str, Any], *, event: str | None = None, id: str | int | None = None) -> str:
    lines = []
    if id is not None:
        lines.append(f"id: {id}")
    if event:
        lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, default=str))
    return "\n".join(lines) + "\n\n"
