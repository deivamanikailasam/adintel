"""LLM-as-judge with a variance band: each judged case runs 3 times and the median is used.
If the target is 0.80 the alarm fires at 0.78, so a single noisy sample can't flip the gate."""

from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, Field

from adintel.core.errors import AdIntelError
from adintel.llm.gateway import LLMGateway

RUNS = 3


class JudgeScore(BaseModel):
    score: float = Field(ge=1, le=5)
    justification: str = ""


def judge(gw: LLMGateway, *, rubric: str, output: str, reference: Any = None) -> float | None:
    scores = []
    for _ in range(RUNS):
        try:
            r = gw.structured(
                agent="judge",
                prompt_id="judge",
                schema=JudgeScore,
                context={"rubric": rubric, "reference": reference},
                untrusted={"output": output},
            )
            scores.append(r.value.score)
        except AdIntelError:
            continue
    return statistics.median(scores) if scores else None
