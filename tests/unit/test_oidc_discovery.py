"""OIDC discovery: provider endpoints come from the provider, with overrides and a Keycloak fallback."""

import httpx
import pytest

from adintel.config import Settings
from adintel.security import oidc_discovery


@pytest.fixture(autouse=True)
def _reset():
    oidc_discovery.reset()
    yield
    oidc_discovery.reset()


class Resp:
    def __init__(self, doc, status=200):
        self._doc, self.status_code = doc, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)

    def json(self):
        return self._doc


OKTA = "https://acme.okta.com/oauth2/default"
OKTA_DOC = {
    "issuer": OKTA,
    "authorization_endpoint": f"{OKTA}/v1/authorize",
    "token_endpoint": f"{OKTA}/v1/token",
    "jwks_uri": f"{OKTA}/v1/keys",
    "end_session_endpoint": f"{OKTA}/v1/logout",
}


def test_discovered_endpoints_are_used(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "get", lambda url, timeout: calls.append(url) or Resp(OKTA_DOC))
    e = oidc_discovery.endpoints(Settings(oidc_issuer=OKTA))
    assert e["token_endpoint"] == f"{OKTA}/v1/token" and e["jwks_uri"] == f"{OKTA}/v1/keys"
    assert e["source"] == "discovery" and calls == [f"{OKTA}/.well-known/openid-configuration"]
    oidc_discovery.endpoints(Settings(oidc_issuer=OKTA))
    assert len(calls) == 1  # cached


def test_cognito_needs_an_explicit_logout_url(monkeypatch):
    cog = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_abc"
    doc = {k: v.replace(OKTA, cog) for k, v in OKTA_DOC.items() if k != "end_session_endpoint"}
    monkeypatch.setattr(httpx, "get", lambda url, timeout: Resp(doc))
    assert oidc_discovery.endpoints(Settings(oidc_issuer=cog))["end_session_endpoint"] is None
    oidc_discovery.reset()
    e = oidc_discovery.endpoints(
        Settings(oidc_issuer=cog, oidc_end_session_url="https://auth.acme.example/logout", oidc_logout_style="cognito")
    )
    assert e["end_session_endpoint"] == "https://auth.acme.example/logout" and e["logout_style"] == "cognito"


def test_unreachable_or_mismatched_issuer_falls_back_to_keycloak_layout(monkeypatch):
    def boom(url, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    kc = "http://localhost:8180/realms/adintel"
    e = oidc_discovery.endpoints(Settings(oidc_issuer=kc))
    assert e["token_endpoint"] == f"{kc}/protocol/openid-connect/token" and e["source"] == "fallback"
    oidc_discovery.reset()
    monkeypatch.setattr(httpx, "get", lambda url, timeout: Resp({**OKTA_DOC, "issuer": "https://evil.example"}))
    assert oidc_discovery.endpoints(Settings(oidc_issuer=OKTA))["source"] == "fallback"  # never trust a mismatched doc


def test_auth_config_exposes_endpoints(db, mock_llm, monkeypatch):
    from fastapi.testclient import TestClient

    from adintel.api.app import create_app
    from adintel.config import reset_settings_cache

    monkeypatch.setattr(httpx, "get", lambda url, timeout: Resp(OKTA_DOC))
    monkeypatch.setenv("ADINTEL_AUTH_MODE", "both")
    monkeypatch.setenv("ADINTEL_OIDC_ISSUER", OKTA)
    reset_settings_cache()
    cfg = TestClient(create_app(start_inline_worker=False)).get("/auth/config").json()["oidc"]
    assert cfg["authorization_endpoint"].endswith("/v1/authorize") and "jwks_uri" not in cfg
