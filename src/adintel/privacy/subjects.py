"""Data-subject rights for the people who use AdIntel (agency staff): access and erasure.

AdIntel holds very little personal data by design — client ad metrics are about campaigns, not people,
and PII is redacted before any model call. What it does hold about a user: their profile (name, email,
roles, limits), their decisions (approvals, rejections with free-text notes, ratings), their chat sessions,
and audit entries naming their user id.

* **Access** (``export_user``): everything above, as one JSON document.
* **Erasure** (``erase_user``): the profile is pseudonymised (email and name replaced, roles removed so the
  account can never act again), chat sessions are deleted, free-text notes are blanked. Approvals,
  executions and audit entries keep the opaque ``user_id``: who approved a spend of client money is a
  record the agency must keep (legal obligation / legitimate interest), and removing it would break the
  hash chain. The pseudonymised profile no longer links that id to a person.
* Both actions are themselves audited, with counts only.
"""

from __future__ import annotations

import hashlib
from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

ERASED_NOTE = "[erased at the user's request]"


def _user(db: Database, tenant_id: str, user_id: str) -> dict[str, Any]:
    u = TenantScopedRepo(db, "users", tenant_id).find_one({"user_id": user_id})
    if u is None:
        raise LookupError(f"user {user_id} not found in tenant {tenant_id}")
    return u


def export_user(db: Database, tenant_id: str, user_id: str, *, actor_id: str) -> dict[str, Any]:
    profile = _user(db, tenant_id, user_id)

    def repo(c: str) -> TenantScopedRepo:
        return TenantScopedRepo(db, c, tenant_id)

    out = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "exported_at": utcnow().isoformat(),
        "profile": {k: v for k, v in profile.items() if k != "_id"},
        "approvals": repo("approvals").find({"$or": [{"approver_id": user_id}, {"second_approver_id": user_id}]}),
        "rejections": repo("recommendations").find({"rejection.by": user_id}),
        "feedback": repo("feedback").find({"user_id": user_id}),
        "chat_sessions": repo("chat_sessions").find({"user_id": user_id}),
        "audit_entries": repo("audit_log").find({"actor_id": user_id}, sort=[("seq", 1)]),
    }
    for v in out.values():
        if isinstance(v, list):
            for d in v:
                d.pop("_id", None)
    AuditLog(db, tenant_id).append(
        AuditAction.PRIVACY_EXPORT,
        actor_type="human",
        actor_id=actor_id,
        subject_type="user",
        subject_id=user_id,
        details={k: len(v) for k, v in out.items() if isinstance(v, list)},
    )
    return out


def erase_user(db: Database, tenant_id: str, user_id: str, *, actor_id: str, reason: str) -> dict[str, int]:
    profile = _user(db, tenant_id, user_id)
    if profile.get("erased_at"):
        return {"already_erased": 1}
    token = hashlib.sha256(f"{tenant_id}/{user_id}/{profile.get('email')}".encode()).hexdigest()[:12]
    now = utcnow().isoformat()
    TenantScopedRepo(db, "users", tenant_id).update_one(
        {"user_id": user_id},
        {
            "$set": {
                "email": f"erased-{token}@invalid.example",
                "name": "Erased user",
                "roles": [],
                "brand_ids": [],
                "approval_limit_usd": 0.0,
                "erased_at": now,
            }
        },
    )
    chats = SystemRepo(db, "chat_sessions", purpose="privacy erasure").delete_many(
        {"tenant_id": tenant_id, "user_id": user_id}
    )
    notes = TenantScopedRepo(db, "feedback", tenant_id).update_many(
        {"user_id": user_id, "note": {"$exists": True}}, {"$set": {"note": ERASED_NOTE}}
    )
    rejections = TenantScopedRepo(db, "recommendations", tenant_id).update_many(
        {"rejection.by": user_id}, {"$set": {"rejection.note": ERASED_NOTE}}
    )
    counts = {"profile": 1, "chat_sessions_deleted": chats, "notes_blanked": notes + rejections}
    AuditLog(db, tenant_id).append(
        AuditAction.PRIVACY_ERASURE,
        actor_type="human",
        actor_id=actor_id,
        subject_type="user",
        subject_id=user_id,
        details={**counts, "reason": reason[:200]},
    )
    return counts
