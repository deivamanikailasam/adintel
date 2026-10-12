"""JWT authentication and role-based access control.

Locally a dev issuer signs HS256 tokens (``/auth/dev-login``, disabled outside local/test). In production
tokens come from Cognito (RS256, JWKS) — only ``decode_token`` changes. The tenant always comes from the
verified token, never from a request parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import jwt

from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.core.errors import AuthError
from adintel.domain.enums import Role
from adintel.domain.models import User


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    email: str
    roles: frozenset[Role]
    brand_ids: tuple[str, ...]

    @property
    def senior(self) -> bool:
        return bool(self.roles & {Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE, Role.ADMIN})

    def can_see_brand(self, brand_id: str) -> bool:
        return self.senior or not self.brand_ids or brand_id in self.brand_ids


def issue_token(user: User) -> str:
    s = get_settings()
    now = utcnow()
    claims: dict[str, Any] = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "roles": [str(r) for r in user.roles],
        "brand_ids": user.brand_ids,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> Principal:
    s = get_settings()
    try:
        c = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], audience=s.jwt_audience, issuer=s.jwt_issuer)
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    return Principal(
        user_id=c["sub"],
        tenant_id=c["tenant_id"],
        email=c.get("email", ""),
        roles=frozenset(Role(r) for r in c.get("roles", [])),
        brand_ids=tuple(c.get("brand_ids", [])),
    )
