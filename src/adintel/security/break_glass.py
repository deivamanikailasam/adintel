"""Break-glass: time-boxed, audited, two-person emergency access.

Support engineers and on-call staff sometimes need more access than their day-to-day role — to look at
every brand during an incident, or to engage a kill switch at 3 a.m. Standing admin rights for everyone are
the usual (bad) answer. Instead:

* A person **requests** elevation (``admin`` and/or ``all brands`` visibility) with a reason and a ticket, for
  at most 4 hours.
* A **different** admin approves it; only then does it become active, until it expires.
* **Emergency** path when nobody can approve: active immediately for at most 60 minutes, a **P1 page to
  security**, and a mandatory post-incident review flag on the grant.
* Elevation never grants money authority: approvals read the approver's *stored* roles and limit, which a
  grant does not change; destructive admin actions (user erasure, feature flags, SCIM tokens) are refused
  while elevated (``Principal.elevated``).
* Requested, approved, used-from, revoked and expired are all in the audit log; grants end by themselves.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError
from adintel.core.ids import new_id
from adintel.domain.enums import AuditAction, Role
from adintel.observability.alerts import Severity, raise_alert
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

MAX_MINUTES = 240
MAX_EMERGENCY_MINUTES = 60
GRANTABLE = {"admin", "all_brands"}


class BreakGlassError(AdIntelError):
    pass


def _repo(db: Database, tenant_id: str) -> TenantScopedRepo:
    return TenantScopedRepo(db, "access_grants", tenant_id)


def _audit(db: Database, p: Principal, action: AuditAction, grant: dict[str, Any], **details: Any) -> None:
    AuditLog(db, p.tenant_id).append(
        action,
        actor_type="human",
        actor_id=p.user_id,
        subject_type="access_grant",
        subject_id=grant["grant_id"],
        details={"user_id": grant["user_id"], "scopes": grant["scopes"], **details},
    )


def request(
    db: Database, p: Principal, *, scopes: list[str], reason: str, ticket: str, minutes: int, emergency: bool = False
) -> dict[str, Any]:
    bad = set(scopes) - GRANTABLE
    if not scopes or bad:
        raise BreakGlassError(f"scopes must be a subset of {sorted(GRANTABLE)}")
    if len(reason.strip()) < 10 or not ticket.strip():
        raise BreakGlassError("a reason (≥ 10 characters) and a ticket reference are required")
    limit = MAX_EMERGENCY_MINUTES if emergency else MAX_MINUTES
    minutes = max(5, min(minutes, limit))
    now = utcnow()
    grant = {
        "grant_id": new_id("bg"),
        "user_id": p.user_id,
        "scopes": sorted(set(scopes)),
        "reason": reason.strip()[:500],
        "ticket": ticket.strip()[:100],
        "minutes": minutes,
        "emergency": emergency,
        "status": "active" if emergency else "requested",
        "requested_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=minutes)).isoformat() if emergency else None,
        "review_required": emergency,
    }
    _repo(db, p.tenant_id).insert(grant)
    _audit(db, p, AuditAction.BREAK_GLASS_REQUESTED, grant, emergency=emergency, minutes=minutes)
    if emergency:
        raise_alert(
            Severity.P1,
            "Emergency break-glass access activated",
            tenant_id=p.tenant_id,
            details={"user_id": p.user_id, "scopes": grant["scopes"], "ticket": grant["ticket"]},
            audience="security",
        )
    return grant


def approve(db: Database, approver: Principal, grant_id: str) -> dict[str, Any]:
    repo = _repo(db, approver.tenant_id)
    g = repo.find_one({"grant_id": grant_id})
    if g is None or g["status"] != "requested":
        raise BreakGlassError("no pending request with that id")
    if g["user_id"] == approver.user_id:
        raise BreakGlassError("a different admin must approve your own elevation")
    if approver.elevated or Role.ADMIN not in approver.roles:
        raise BreakGlassError("only a non-elevated admin can approve elevation")
    now = utcnow()
    expires = (now + timedelta(minutes=int(g["minutes"]))).isoformat()
    repo.update_one(
        {"grant_id": grant_id},
        {
            "$set": {
                "status": "active",
                "approved_by": approver.user_id,
                "approved_at": now.isoformat(),
                "expires_at": expires,
            }
        },
    )
    g.update(status="active", expires_at=expires)
    _audit(db, approver, AuditAction.BREAK_GLASS_APPROVED, g, expires_at=expires)
    raise_alert(
        Severity.P3,
        "Break-glass access approved",
        tenant_id=approver.tenant_id,
        details={"user_id": g["user_id"], "scopes": g["scopes"], "approved_by": approver.user_id},
        audience="security",
    )
    return g


def revoke(db: Database, actor: Principal, grant_id: str) -> None:
    repo = _repo(db, actor.tenant_id)
    g = repo.find_one({"grant_id": grant_id})
    if g is None or g["status"] not in ("requested", "active"):
        raise BreakGlassError("nothing to revoke")
    if actor.user_id != g["user_id"] and Role.ADMIN not in actor.roles:
        raise BreakGlassError("only the holder or an admin can revoke")
    repo.update_one(
        {"grant_id": grant_id},
        {"$set": {"status": "revoked", "revoked_by": actor.user_id, "revoked_at": utcnow().isoformat()}},
    )
    _audit(db, actor, AuditAction.BREAK_GLASS_REVOKED, g)


def active_grants(db: Database, tenant_id: str, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
    now_s = (now or utcnow()).isoformat()
    return [
        g
        for g in _repo(db, tenant_id).find({"user_id": user_id, "status": "active"})
        if (g.get("expires_at") or "") > now_s
    ]


def elevate(db: Database, p: Principal) -> Principal:
    """Apply any active grant to a signed-in principal (called once per request)."""
    grants = active_grants(db, p.tenant_id, p.user_id)
    if not grants:
        return p
    scopes = {s for g in grants for s in g["scopes"]}
    roles = set(p.roles) | ({Role.ADMIN} if "admin" in scopes else set())
    brand_ids = () if "all_brands" in scopes or "admin" in scopes else p.brand_ids
    return replace(p, roles=frozenset(roles), brand_ids=brand_ids, elevated=True, grant_id=grants[0]["grant_id"])


def refuse_if_elevated(p: Principal, what: str) -> None:
    if p.elevated:
        raise BreakGlassError(f"{what} is not allowed under break-glass access")


def expire_job(db: Database) -> int:
    """Mark ended grants as expired (and audit it) so the record is accurate; access already stopped."""
    from adintel.storage.tenant_repo import SystemRepo

    now = utcnow().isoformat()
    n = 0
    sys_repo = SystemRepo(db, "access_grants", purpose="break-glass expiry")
    for g in sys_repo.find({"status": "active"}):
        if (g.get("expires_at") or "") <= now:
            sys_repo.update_one(
                {"tenant_id": g["tenant_id"], "grant_id": g["grant_id"]}, {"$set": {"status": "expired"}}
            )
            AuditLog(db, g["tenant_id"]).append(
                AuditAction.BREAK_GLASS_EXPIRED,
                actor_type="system",
                actor_id="system:break-glass",
                subject_type="access_grant",
                subject_id=g["grant_id"],
                details={"user_id": g["user_id"]},
            )
            n += 1
    return n
