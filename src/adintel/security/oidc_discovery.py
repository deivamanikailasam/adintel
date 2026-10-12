"""OIDC discovery: find the identity provider's endpoints instead of assuming Keycloak's URL layout.

Every standard provider publishes ``<issuer>/.well-known/openid-configuration`` with its
``authorization_endpoint``, ``token_endpoint``, ``jwks_uri`` and (most) ``end_session_endpoint``.
Resolution order for each endpoint: explicit setting → discovery document → Keycloak layout (kept so the
Docker Compose stack, where the API container can't reach the browser-facing issuer URL, still works).

Provider notes:

* **Keycloak, Okta, Microsoft Entra ID, Auth0** — discovery includes ``end_session_endpoint``; logout uses
  standard RP-initiated logout (``id_token_hint`` + ``post_logout_redirect_uri``).
* **Amazon Cognito** — discovery has no ``end_session_endpoint``; set ``ADINTEL_OIDC_END_SESSION_URL`` to
  ``https://<your-domain>/logout`` and ``ADINTEL_OIDC_LOGOUT_STYLE=cognito`` (``client_id`` + ``logout_uri``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from adintel.security import egress

log = logging.getLogger(__name__)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()
TTL = 3600.0


def discover(issuer: str) -> dict[str, Any]:
    """The discovery document, cached for an hour; ``{}`` when the issuer is unreachable."""
    with _lock:
        hit = _cache.get(issuer)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    doc: dict[str, Any] = {}
    try:
        egress.check(url, "identity provider discovery")
        r = httpx.get(url, timeout=3.0)
        r.raise_for_status()
        doc = r.json()
        if doc.get("issuer", "").rstrip("/") != issuer.rstrip("/"):
            log.warning("oidc_discovery_issuer_mismatch", extra={"expected": issuer, "got": doc.get("issuer")})
            doc = {}
    except Exception as exc:
        log.info("oidc_discovery_unavailable", extra={"issuer": issuer, "reason": str(exc)[:200]})
    with _lock:
        _cache[issuer] = (time.monotonic(), doc)
    return doc


def endpoints(settings: Any) -> dict[str, Any]:
    issuer = settings.oidc_issuer.rstrip("/")
    doc = discover(issuer)
    kc = f"{issuer}/protocol/openid-connect"
    return {
        "issuer": issuer,
        "authorization_endpoint": settings.oidc_authorization_url or doc.get("authorization_endpoint") or f"{kc}/auth",
        "token_endpoint": settings.oidc_token_url or doc.get("token_endpoint") or f"{kc}/token",
        "jwks_uri": settings.oidc_jwks_url or doc.get("jwks_uri") or f"{kc}/certs",
        "end_session_endpoint": settings.oidc_end_session_url
        or doc.get("end_session_endpoint")
        or (f"{kc}/logout" if not doc else None),
        "logout_style": settings.oidc_logout_style,
        "source": "discovery" if doc else "fallback",
    }


def reset() -> None:
    with _lock:
        _cache.clear()
