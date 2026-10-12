"""Chat agent: answers ad-hoc account-manager questions about ONE brand.

Path: semantic cache → route (rules, then small-model router) → facts from the database (+ RAG for
complex questions) → stream the answer (small model for lookups/simple, frontier for complex) through
an incremental output guard → persist the turn → cache it. Tenant and brand come from the session,
never from the question text. Chat cannot change anything.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel

from adintel.agents import guardrail
from adintel.analytics.frames import load_frame, period_summary
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError
from adintel.harness.flags import FeatureFlags
from adintel.llm.gateway import CallContext, LLMGateway, TextResult
from adintel.llm.semantic_cache import get_semantic_cache
from adintel.memory.conversational import ConversationStore
from adintel.rag.retriever import RetrievalUnavailable, Retriever
from adintel.security.fencing import injection_markers
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)
LOOKUP_RE = re.compile(
    r"\b(what|how much|how many|show)\b.*\b(spend|spent|cpa|roas|conversions?|clicks|revenue|ctr)\b", re.IGNORECASE
)
REFUSAL = (
    "I can't share that. I can only discuss this brand's own performance, and I can't change budgets or "
    "approve anything — proposals are reviewed in the Approvals screen."
)


class Route(BaseModel):
    route: Literal["lookup", "simple", "complex"]
    metric: str | None = None
    platform: str | None = None


class ChatService:
    def __init__(self, db: Database, tenant_id: str, brand_id: str, user_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.brand_id = brand_id
        self.user_id = user_id
        self.llm = LLMGateway(db, CallContext(tenant_id=tenant_id, brand_id=brand_id, run_id=None))
        self.memory = ConversationStore(db, tenant_id)

    def route(self, question: str) -> Route:
        if LOOKUP_RE.search(question) and len(question) < 160:
            return Route(route="lookup")
        try:
            return self.llm.structured(
                agent="chat_simple",
                prompt_id="chat_router",
                schema=Route,
                context={"question_length": len(question)},
                untrusted={"question": question},
            ).value
        except AdIntelError:
            return Route(route="complex")

    def facts(self) -> dict[str, Any]:
        end = utcnow().date() - timedelta(days=1)
        latest = TenantScopedRepo(self.db, "metrics_daily", self.tenant_id).find_one(
            {"brand_id": self.brand_id}, sort=[("date", -1)]
        )
        if latest:
            from datetime import date

            end = min(end, date.fromisoformat(latest["date"]))
        start = end - timedelta(days=6)
        df = load_frame(
            TenantScopedRepo(self.db, "metrics_daily", self.tenant_id), self.brand_id, start - timedelta(days=7), end
        )
        open_anoms = TenantScopedRepo(self.db, "anomalies", self.tenant_id).find(
            {"brand_id": self.brand_id, "status": "open"}, limit=5, sort=[("severity", -1)]
        )
        recs = TenantScopedRepo(self.db, "recommendations", self.tenant_id).find(
            {"brand_id": self.brand_id}, sort=[("created_at", -1)], limit=5
        )
        return {
            "last_7_days": period_summary(df, start, end),
            "open_anomalies": [
                {
                    "metric": a["metric"],
                    "campaign": a["entity_name"],
                    "deviation_pct": a["deviation_pct"],
                    "severity": a["severity"],
                }
                for a in open_anoms
            ],
            "recent_recommendations": [
                {"status": r["status"], "action": r["action_type"], "amount_usd_per_day": r["amount_usd_per_day"]}
                for r in recs
            ],
        }

    def ask(self, question: str, session_id: str) -> Iterator[dict[str, Any]]:
        """Yield SSE-ready events: meta, token*, done | blocked."""
        cache = get_semantic_cache()
        cached = cache.get(self.tenant_id, self.brand_id, question)
        if cached:
            yield {"type": "meta", "route": cached.get("route"), "cached": True}
            yield {"type": "token", "text": cached["answer"]}
            yield {"type": "done", **cached}
            return
        session = self.memory.ensure(session_id, brand_id=self.brand_id, user_id=self.user_id)
        if session["brand_id"] != self.brand_id:
            yield {"type": "blocked", "reason": "session belongs to another brand"}
            return
        flagged = injection_markers(question)
        route = self.route(question)
        if route.route == "complex" and not FeatureFlags(self.db, self.tenant_id).enabled(
            "chat.frontier_route", brand_id=self.brand_id
        ):
            route = Route(route="simple")
        facts = self.facts()
        brand = TenantScopedRepo(self.db, "brands", self.tenant_id).find_one({"brand_id": self.brand_id}) or {}
        sources: list[dict[str, str]] = []
        evidence: list[dict[str, Any]] = []
        if route.route == "complex":
            try:
                res = Retriever(self.db, self.tenant_id).search(
                    question, brand_id=self.brand_id, vertical=(brand.get("profile") or {}).get("vertical")
                )
                evidence = [c.as_evidence() for c in res.chunks]
                sources = [{"chunk_id": c.chunk_id, "title": c.doc_title} for c in res.chunks]
            except RetrievalUnavailable:
                log.warning("chat_retrieval_unavailable")
        agent = "chat_complex" if route.route == "complex" else "chat_simple"
        yield {
            "type": "meta",
            "route": route.route,
            "tier": self.llm.registry.agents[agent].tier,
            "cached": False,
            "injection_markers": flagged,
        }
        names = guardrail.other_client_names(self.db, self.tenant_id, self.brand_id)
        # hold back enough characters that a forbidden name can't be half-emitted before it is recognised
        hold = max([len(n) for n in names] + [24]) + 8
        buf = ""
        emitted = 0
        final: TextResult | None = None
        try:
            for item in self.llm.stream(
                agent=agent,
                prompt_id="chat",
                context={"brand": brand.get("name"), "facts": facts},
                untrusted={"retrieved_documents": evidence, "question": question},
                history=self.memory.history(session),
            ):
                if isinstance(item, TextResult):
                    final = item
                    break
                buf += item
                if guardrail.deterministic_checks(buf, forbidden_names=names, facts=None, require_grounding=False):
                    yield {"type": "blocked", "reason": "output guard", "replacement": REFUSAL}
                    self.memory.append(session_id, question, REFUSAL)
                    return
                safe_upto = len(buf) - hold
                if safe_upto > emitted:
                    yield {"type": "token", "text": buf[emitted:safe_upto]}
                    emitted = safe_upto
        except AdIntelError as exc:
            yield {
                "type": "error",
                "message": f"The assistant is unavailable ({type(exc).__name__}). Try again shortly.",
            }
            return
        answer = final.text if final else buf
        if guardrail.deterministic_checks(answer, forbidden_names=names, facts=None, require_grounding=False):
            yield {"type": "blocked", "reason": "output guard", "replacement": REFUSAL}
            self.memory.append(session_id, question, REFUSAL)
            return
        if len(buf) > emitted:
            yield {"type": "token", "text": buf[emitted:]}
        self.memory.append(session_id, question, answer)
        out = {
            "answer": answer,
            "route": route.route,
            "sources": sources,
            "tier": final.tier if final else None,
            "cost_usd": final.cost_usd if final else 0.0,
        }
        if not flagged:
            cache.put(self.tenant_id, self.brand_id, question, out)
        yield {"type": "done", **out, "cached": False}
