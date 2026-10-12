"""Conversational memory: the last 20 turns verbatim plus a running summary of older turns (90 days)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from adintel.core.clock import utcnow
from adintel.llm.types import Message
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

KEEP_TURNS = 20
RETENTION = timedelta(days=90)


class ConversationStore:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self._repo = TenantScopedRepo(db, "chat_sessions", tenant_id)

    def load(self, session_id: str) -> dict[str, Any] | None:
        return self._repo.find_one({"session_id": session_id})

    def ensure(self, session_id: str, *, brand_id: str, user_id: str) -> dict[str, Any]:
        doc = self.load(session_id)
        if doc is None:
            doc = {"session_id": session_id, "brand_id": brand_id, "user_id": user_id, "turns": [], "summary": "",
                   "created_at": utcnow().isoformat(), "expire_at": utcnow() + RETENTION}
            self._repo.insert(doc)
        return doc

    def history(self, doc: dict[str, Any]) -> list[Message]:
        msgs = []
        if doc.get("summary"):
            msgs.append(Message("user", f"(Summary of earlier conversation: {doc['summary']})"))
            msgs.append(Message("assistant", "Understood."))
        msgs += [Message(t["role"], t["content"]) for t in doc.get("turns", [])[-KEEP_TURNS:]]
        return msgs

    def append(self, session_id: str, question: str, answer: str) -> None:
        doc = self.load(session_id) or {}
        turns = [*doc.get("turns", []), {"role": "user", "content": question, "at": utcnow().isoformat()},
                 {"role": "assistant", "content": answer, "at": utcnow().isoformat()}]
        summary = doc.get("summary", "")
        if len(turns) > KEEP_TURNS:
            old, turns = turns[:-KEEP_TURNS], turns[-KEEP_TURNS:]
            gist = "; ".join(t["content"][:120] for t in old if t["role"] == "user")
            summary = (summary + " | " if summary else "") + f"Earlier questions: {gist}"
            summary = summary[-2000:]
        self._repo.update_one({"session_id": session_id}, {"$set": {
            "turns": turns, "summary": summary, "updated_at": utcnow().isoformat(),
            "expire_at": utcnow() + RETENTION}})
