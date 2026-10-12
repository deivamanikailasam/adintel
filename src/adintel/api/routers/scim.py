"""SCIM 2.0 user provisioning (RFC 7643/7644 subset) — joiners, movers and leavers from the identity provider.

Okta, Microsoft Entra ID and Keycloak (with a SCIM plugin) push user changes here, so AdIntel's user list
follows HR instead of an admin's memory. Each tenant has its own bearer token (``adintel scim token``),
stored only as a SHA-256 hash.

Governance decisions encoded here:

* SCIM manages **identity and roles**; **money authority does not come from the IdP**: a provisioned user
  starts with ``approval_limit_usd = 0`` and brand scope set by an AdIntel admin.
* Deleting a user **deactivates** them (``active: false``, roles removed): they lose access on their next
  request; their approvals stay attributable. Erasure is a separate, audited privacy request.
* Every change is written to the tenant's audit log with the IdP as the actor.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from adintel.api.deps import db
from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.core.ids import new_id
from adintel.domain.enums import AuditAction, Role
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

router = APIRouter(prefix="/scim/v2", tags=["scim"], include_in_schema=False)
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
VALID_ROLES = {r.value for r in Role}


def issue_token(database: Database, tenant_id: str, *, actor_id: str) -> str:
    token = "scim_" + secrets.token_urlsafe(32)
    TenantScopedRepo(database, "scim_tokens", tenant_id).insert(
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "created_at": utcnow().isoformat(),
            "revoked": False,
        }
    )
    AuditLog(database, tenant_id).append(
        AuditAction.SCIM_CREDENTIAL_ISSUED,
        actor_type="human",
        actor_id=actor_id,
        subject_type="scim",
        subject_id=tenant_id,
    )
    return token


def scim_tenant(authorization: str | None = Header(default=None), database: Database = Depends(db)) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    doc = SystemRepo(database, "scim_tokens", purpose="scim auth").find_one({"token_sha256": digest})
    if not token or doc is None or doc.get("revoked") or not hmac.compare_digest(doc["token_sha256"], digest):
        raise HTTPException(401, "invalid SCIM token")
    return str(doc["tenant_id"])


def _error(status: int, detail: str, scim_type: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"schemas": [ERROR_SCHEMA], "status": str(status), "detail": detail}
    if scim_type:
        body["scimType"] = scim_type
    return JSONResponse(body, status_code=status, media_type="application/scim+json")


def _to_scim(u: dict[str, Any], base: str) -> dict[str, Any]:
    return {
        "schemas": [USER_SCHEMA],
        "id": u["user_id"],
        "externalId": u.get("external_id"),
        "userName": u["email"],
        "name": {"formatted": u.get("name", "")},
        "displayName": u.get("name", ""),
        "emails": [{"value": u["email"], "primary": True}],
        "active": u.get("active", True),
        "roles": [{"value": r} for r in u.get("roles", [])],
        "meta": {
            "resourceType": "User",
            "location": f"{base}/scim/v2/Users/{u['user_id']}",
            "lastModified": u.get("updated_at"),
        },
    }


def _roles(body: dict[str, Any]) -> list[str]:
    raw = body.get("roles") or []
    vals = [str(r.get("value") if isinstance(r, dict) else r) for r in raw]
    bad = [v for v in vals if v not in VALID_ROLES]
    if bad:
        raise ValueError(f"unknown role(s) {bad}; valid: {sorted(VALID_ROLES)}")
    return sorted(set(vals)) or ["viewer"]


def _audit(database: Database, tenant: str, action: AuditAction, user_id: str, details: dict[str, Any]) -> None:
    AuditLog(database, tenant).append(
        action, actor_type="system", actor_id="system:scim", subject_type="user", subject_id=user_id, details=details
    )


@router.get("/ServiceProviderConfig")
def service_provider_config() -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "primary": True}],
    }


@router.get("/Users")
def list_users(
    request: Request,
    filter: str | None = None,
    startIndex: int = 1,
    count: int = 100,
    tenant: str = Depends(scim_tenant),
    database: Database = Depends(db),
) -> Any:
    flt: dict[str, Any] = {}
    if filter:
        parts = filter.split(" eq ", 1)
        if len(parts) != 2 or parts[0].strip() not in ("userName", "externalId"):
            return _error(
                400, "only 'userName eq \"…\"' and 'externalId eq \"…\"' filters are supported", "invalidFilter"
            )
        flt = {"email" if parts[0].strip() == "userName" else "external_id": parts[1].strip().strip('"')}
    rows = TenantScopedRepo(database, "users", tenant).find(flt, sort=[("email", 1)])
    page = rows[max(0, startIndex - 1) : max(0, startIndex - 1) + max(0, min(count, 200))]
    base = str(request.base_url).rstrip("/")
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": len(rows),
        "startIndex": startIndex,
        "itemsPerPage": len(page),
        "Resources": [_to_scim(u, base) for u in page],
    }


@router.get("/Users/{user_id}")
def get_user(
    user_id: str, request: Request, tenant: str = Depends(scim_tenant), database: Database = Depends(db)
) -> Any:
    u = TenantScopedRepo(database, "users", tenant).find_one({"user_id": user_id})
    return _to_scim(u, str(request.base_url).rstrip("/")) if u else _error(404, "user not found")


@router.post("/Users", status_code=201)
def create_user(
    body: dict[str, Any], request: Request, tenant: str = Depends(scim_tenant), database: Database = Depends(db)
) -> Any:
    email = str(body.get("userName") or "").strip().lower()
    if "@" not in email:
        return _error(400, "userName must be the user's email address", "invalidValue")
    try:
        roles = _roles(body)
    except ValueError as exc:
        return _error(400, str(exc), "invalidValue")
    if SystemRepo(database, "users", purpose="scim uniqueness").find_one({"email": email}):
        return _error(409, "a user with this userName already exists", "uniqueness")
    name = (body.get("name") or {}).get("formatted") or body.get("displayName") or email
    doc = {
        "user_id": new_id("u"),
        "external_id": body.get("externalId"),
        "email": email,
        "name": name,
        "roles": roles,
        "approval_limit_usd": 0.0,  # money authority is granted in AdIntel, never by the IdP
        "brand_ids": [],
        "active": bool(body.get("active", True)),
        "provisioned_by": "scim",
        "updated_at": utcnow().isoformat(),
    }
    try:
        TenantScopedRepo(database, "users", tenant).insert(doc)
    except DuplicateKey:
        return _error(409, "a user with this userName already exists", "uniqueness")
    _audit(
        database, tenant, AuditAction.USER_PROVISIONED, str(doc["user_id"]), {"roles": roles, "active": doc["active"]}
    )
    return JSONResponse(
        _to_scim(doc, str(request.base_url).rstrip("/")), status_code=201, media_type="application/scim+json"
    )


def _apply(database: Database, tenant: str, user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    repo = TenantScopedRepo(database, "users", tenant)
    if repo.find_one({"user_id": user_id}) is None:
        return None
    if changes.get("active") is False:
        changes["roles"] = []
    repo.update_one({"user_id": user_id}, {"$set": {**changes, "updated_at": utcnow().isoformat()}})
    action = AuditAction.USER_DEPROVISIONED if changes.get("active") is False else AuditAction.USER_UPDATED
    _audit(database, tenant, action, user_id, {k: v for k, v in changes.items() if k != "name"})
    return repo.find_one({"user_id": user_id})


@router.put("/Users/{user_id}")
def replace_user(
    user_id: str,
    body: dict[str, Any],
    request: Request,
    tenant: str = Depends(scim_tenant),
    database: Database = Depends(db),
) -> Any:
    try:
        changes = {
            "roles": _roles(body),
            "active": bool(body.get("active", True)),
            "name": (body.get("name") or {}).get("formatted") or body.get("displayName"),
        }
    except ValueError as exc:
        return _error(400, str(exc), "invalidValue")
    u = _apply(database, tenant, user_id, {k: v for k, v in changes.items() if v is not None})
    return _to_scim(u, str(request.base_url).rstrip("/")) if u else _error(404, "user not found")


@router.patch("/Users/{user_id}")
def patch_user(
    user_id: str,
    body: dict[str, Any],
    request: Request,
    tenant: str = Depends(scim_tenant),
    database: Database = Depends(db),
) -> Any:
    changes: dict[str, Any] = {}
    for op in body.get("Operations", []):
        if str(op.get("op", "")).lower() not in ("replace", "add"):
            return _error(400, "only add/replace operations are supported", "invalidSyntax")
        path, value = op.get("path"), op.get("value")
        items = value.items() if path is None and isinstance(value, dict) else [(path, value)]
        for p, v in items:
            if p == "active":
                changes["active"] = v if isinstance(v, bool) else str(v).lower() == "true"
            elif p == "roles":
                try:
                    changes["roles"] = _roles({"roles": v})
                except ValueError as exc:
                    return _error(400, str(exc), "invalidValue")
            elif p in ("displayName", "name.formatted"):
                changes["name"] = v
            else:
                return _error(400, f"attribute {p!r} cannot be changed through SCIM", "mutability")
    u = _apply(database, tenant, user_id, changes)
    return _to_scim(u, str(request.base_url).rstrip("/")) if u else _error(404, "user not found")


@router.delete("/Users/{user_id}", status_code=204, response_class=Response)
def delete_user(user_id: str, tenant: str = Depends(scim_tenant), database: Database = Depends(db)) -> Response:
    if _apply(database, tenant, user_id, {"active": False}) is None:
        return _error(404, "user not found")
    return Response(status_code=204)
