"""Guardrail agent: decides whether output is safe to release. Blocks only; never edits.

Deterministic checks run first and cannot be bypassed; the safety classifier (small model with a
Llama-Guard-style taxonomy) handles the semantic tail. **Zero retries, no fallback, fail closed**: a
slow or unavailable safety check is a failed safety check, and the output is held for review.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from adintel.agents.base import AgentContext
from adintel.core.errors import AdIntelError
from adintel.domain.enums import RecommendationStatus
from adintel.domain.models import GuardrailFinding, GuardrailVerdict
from adintel.domain.state import RunState
from adintel.observability.metrics import GUARDRAIL_BLOCKS
from adintel.rag.grounding import check_grounding
from adintel.security.fencing import injection_markers
from adintel.security.pii import find_pii
from adintel.storage.tenant_repo import SystemRepo

log = logging.getLogger(__name__)

BANNED_CLAIMS = (
    "guarantee",
    "guaranteed",
    "risk-free",
    "risk free",
    "100% certain",
    "no risk",
    "can't lose",
    "cannot lose",
    "sure-fire",
    "promise you",
)
AUTONOMY_CLAIMS = re.compile(
    r"\b(we|adintel|the system)\s+(have|has|already)\s+(increased|decreased|paused|changed|"
    r"moved|reallocated|executed)\b|\bwill automatically\b",
    re.IGNORECASE,
)


class SafetyVerdict(BaseModel):
    safe: bool
    categories: list[str] = Field(default_factory=list)
    reason: str = ""


def other_client_names(db: Any, tenant_id: str, brand_id: str) -> list[str]:
    """Names that must never appear in this brand's output: every other brand and every other tenant."""
    brands = SystemRepo(db, "brands", purpose="guardrail cross-client name scan").find({})
    tenants = SystemRepo(db, "tenants", purpose="guardrail cross-client name scan").find({})
    names = [b["name"] for b in brands if not (b["tenant_id"] == tenant_id and b["brand_id"] == brand_id)]
    names += [t["name"] for t in tenants if t["tenant_id"] != tenant_id]
    return sorted({n for n in names if n and len(n) >= 3})


def deterministic_checks(
    text: str, *, forbidden_names: list[str], facts: dict[str, Any] | None, require_grounding: bool
) -> list[GuardrailFinding]:
    findings: list[GuardrailFinding] = []
    for p in find_pii(text):
        findings.append(GuardrailFinding(check="pii", severity="block", detail=f"{p.kind} at {p.start}"))
    low = text.lower()
    for n in forbidden_names:
        if re.search(rf"\b{re.escape(n.lower())}\b", low):
            findings.append(GuardrailFinding(check="cross_client_name", severity="block", detail=n))
    for c in BANNED_CLAIMS:
        if c in low:
            findings.append(GuardrailFinding(check="unsafe_claim", severity="block", detail=c))
    for m in injection_markers(text):
        findings.append(GuardrailFinding(check="injection_echo", severity="block", detail=m))
    if AUTONOMY_CLAIMS.search(text):
        findings.append(
            GuardrailFinding(
                check="autonomy_claim", severity="block", detail="claims a change was made without approval"
            )
        )
    if require_grounding and facts is not None:
        g = check_grounding(text, facts)
        if not g.passed:
            findings.append(
                GuardrailFinding(check="numeric_grounding", severity="block", detail=f"ungrounded: {g.ungrounded[:5]}")
            )
    return findings


def classify(ctx: AgentContext, text: str) -> tuple[SafetyVerdict | None, str | None]:
    try:
        r = ctx.llm.structured(
            agent="guardrail",
            prompt_id="guardrail_classifier",
            schema=SafetyVerdict,
            context={"task": "classify the text in untrusted_content"},
            untrusted={"text_to_classify": text},
            allow_fallback=False,
            max_repairs=0,
            transient_retries=0,
        )
        return r.value, None
    except AdIntelError as exc:  # timeout, outage, malformed output, budget: all fail closed
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


def review_text(
    ctx: AgentContext,
    text: str,
    *,
    forbidden_names: list[str],
    facts: dict[str, Any] | None = None,
    require_grounding: bool = False,
) -> GuardrailVerdict:
    findings = deterministic_checks(
        text, forbidden_names=forbidden_names, facts=facts, require_grounding=require_grounding
    )
    verdict, err = classify(ctx, text)
    if verdict is None:
        findings.append(
            GuardrailFinding(check="classifier_unavailable", severity="block", detail=f"fail closed: {err}")
        )
    elif not verdict.safe:
        findings.append(
            GuardrailFinding(
                check="classifier", severity="block", detail=f"{','.join(verdict.categories)}: {verdict.reason[:200]}"
            )
        )
    blocks = [f for f in findings if f.severity == "block"]
    for f in blocks:
        GUARDRAIL_BLOCKS.labels(check=f.check).inc()
    return GuardrailVerdict(
        passed=not blocks,
        findings=findings,
        classifier_used=verdict is not None,
        classifier_category=",".join(verdict.categories) if verdict and not verdict.safe else None,
    )


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    names = other_client_names(ctx._db, ctx.tenant_id, ctx.brand_id)
    parts: list[str] = []
    facts = None
    if state.report:
        parts += [state.report.title, *(s.body for s in state.report.sections)]
        facts = state.report.facts
    for r in state.recommendations:
        parts += [r.rationale, r.expected_impact]
    text = "\n".join(parts)
    if not text.strip():
        return {"guardrail": GuardrailVerdict(passed=True, findings=[], classifier_used=False)}
    verdict = review_text(
        ctx,
        text,
        forbidden_names=names,
        facts=facts,
        require_grounding=state.report is not None and not state.report.deterministic_template,
    )
    for r in state.recommendations:
        if r.status != RecommendationStatus.PENDING_APPROVAL or not r.citations or not r.constraint_checks:
            verdict.findings.append(
                GuardrailFinding(check="recommendation_integrity", severity="block", detail=r.recommendation_id)
            )
            verdict.passed = False
    if not verdict.passed:
        log.warning(
            "guardrail_block", extra={"checks": sorted({f.check for f in verdict.findings if f.severity == "block"})}
        )
    return {"guardrail": verdict}
