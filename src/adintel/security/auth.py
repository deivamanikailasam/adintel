"""Authentication and role-based access control.

Two token sources:

* **dev** — a local HS256 issuer behind ``/auth/dev-login`` (disabled outside local/test).
* **oidc** — RS256 tokens from an OpenID Connect provider (Keycloak locally via ``make up``, Cognito,
  Entra ID or Okta in production), verified against the provider's JWKS: signature, issuer, audience,
  expiry. The tenant and roles come from configurable claims.

Either way the tenant comes from the verified token, never from a request parameter. For OIDC the person
must also be **provisioned** in ``users`` (matched by email within the token's tenant): that record holds
their brand scope and personal approval limit, so an identity provider alone can never grant spending
authority (no just-in-time provisioning).
"""

from __future__ import annotations

import threading
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


def _decode_dev(token: str) -> Principal:
    s = get_settings()
    c = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], audience=s.jwt_audience, issuer=s.jwt_issuer)
    return Principal(
        user_id=c["sub"],
        tenant_id=c["tenant_id"],
        email=c.get("email", ""),
        roles=frozenset(Role(r) for r in c.get("roles", [])),
        brand_ids=tuple(c.get("brand_ids", [])),
    )


_jwks: jwt.PyJWKClient | None = None
_jwks_lock = threading.Lock()


def jwks_client() -> jwt.PyJWKClient:
    global _jwks
    with _jwks_lock:
        if _jwks is None:
            s = get_settings()
            url = s.oidc_jwks_url or f"{s.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"
            _jwks = jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)
        return _jwks


def set_jwks_client(client: Any) -> None:
    global _jwks
    with _jwks_lock:
        _jwks = client


def _claim(claims: dict[str, Any], path: str) -> Any:
    cur: Any = claims
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _decode_oidc(token: str) -> Principal:
    from adintel.storage import get_database
    from adintel.storage.tenant_repo import TenantScopedRepo

    s = get_settings()
    key = jwks_client().get_signing_key_from_jwt(token).key
    c = jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        audience=s.oidc_audience,
        issuer=s.oidc_issuer,
        options={"require": ["exp", "iat", "iss", "sub"]},
    )
    tenant = _claim(c, s.oidc_tenant_claim)
    if not tenant or not isinstance(tenant, str):
        raise AuthError(f"token has no {s.oidc_tenant_claim} claim")
    email = str(c.get("email") or "")
    doc = TenantScopedRepo(get_database(), "users", tenant).find_one({"email": email}) if email else None
    if doc is None:
        raise AuthError("user is not provisioned in AdIntel for this tenant")
    user = User.from_doc(doc)
    token_roles = _claim(c, s.oidc_roles_claim) or []
    idp_roles = {Role(r) for r in token_roles if r in {x.value for x in Role}}
    # least privilege: a role must be granted by BOTH the identity provider and the AdIntel user record
    roles = frozenset(idp_roles & set(user.roles)) if idp_roles else frozenset()
    return Principal(user_id=user.user_id, tenant_id=tenant, email=email, roles=roles, brand_ids=tuple(user.brand_ids))


def decode_token(token: str) -> Principal:
    mode = get_settings().auth_mode
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    try:
        if header.get("alg") == "HS256":
            if mode == "oidc":
                raise AuthError("dev tokens are not accepted in oidc mode")
            return _decode_dev(token)
        if mode == "dev":
            raise AuthError("OIDC tokens are not accepted in dev mode")
        return _decode_oidc(token)
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthError(f"invalid token: {exc}") from exc
