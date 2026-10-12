from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from adintel.core.errors import AuthError
from adintel.domain.enums import Role
from adintel.harness.admission import RateLimiter
from adintel.security.auth import Principal, decode_token
from adintel.storage import get_database
from adintel.storage.base import Database

_api_limiter = RateLimiter(600, 60.0)


def db() -> Database:
    return get_database()


def principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("access_token", "")
    if not token:
        raise HTTPException(401, "missing bearer token")
    try:
        p = decode_token(token)
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    if not _api_limiter.allow(p.tenant_id):
        raise HTTPException(429, "tenant rate limit exceeded")
    return p


def require(*roles: Role) -> Callable[[Principal], Principal]:
    def dep(p: Principal = Depends(principal)) -> Principal:
        if not (p.roles & set(roles)) and Role.ADMIN not in p.roles:
            raise HTTPException(403, f"requires one of {[str(r) for r in roles]}")
        return p

    return dep


def check_brand(p: Principal, brand_id: str) -> None:
    if not p.can_see_brand(brand_id):
        raise HTTPException(403, "brand not in your scope")


ANY_STAFF = (Role.VIEWER, Role.ACCOUNT_MANAGER, Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE)
APPROVERS = (Role.ACCOUNT_MANAGER, Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE)
SENIORS = (Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE)
