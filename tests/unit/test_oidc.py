import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from adintel.config import reset_settings_cache
from adintel.core.errors import AuthError
from adintel.domain.enums import Role
from adintel.security import auth
from adintel.seed.catalog import seed

ISS = "http://localhost:8180/realms/adintel"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


@pytest.fixture
def oidc(db, monkeypatch):
    seed(db, with_kb=False)
    monkeypatch.setenv("ADINTEL_AUTH_MODE", "oidc")
    reset_settings_cache()
    auth.set_jwks_client(FakeJWKS())
    yield
    auth.set_jwks_client(None)


def token(key=KEY, **over):
    now = int(time.time())
    claims = {
        "iss": ISS,
        "aud": "adintel-api",
        "sub": "kc-123",
        "iat": now,
        "exp": now + 300,
        "email": "jordan@brightwave.example",
        "tenant_id": "brightwave",
        "realm_access": {"roles": ["account_manager"]},
    }
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def test_valid_oidc_token_maps_to_the_provisioned_user(oidc):
    p = auth.decode_token(token())
    assert p.user_id == "u_jordan" and p.tenant_id == "brightwave" and p.roles == {Role.ACCOUNT_MANAGER}
    assert p.brand_ids == ("urban-roast", "fitely")


@pytest.mark.parametrize(
    "bad",
    [
        {"iss": "https://evil.example"},
        {"aud": "someone-else"},
        {"exp": int(time.time()) - 10},
        {"tenant_id": None},
        {"email": "stranger@brightwave.example"},
    ],
)
def test_rejected_tokens(oidc, bad):
    with pytest.raises(AuthError):
        auth.decode_token(token(**bad))


def test_wrong_signature_is_rejected(oidc):
    with pytest.raises(AuthError):
        auth.decode_token(token(key=OTHER))


def test_idp_cannot_escalate_beyond_the_adintel_record(oidc):
    p = auth.decode_token(token(realm_access={"roles": ["account_manager", "admin", "head_of_performance"]}))
    assert p.roles == {Role.ACCOUNT_MANAGER}  # intersection with the user record


def test_tenant_claim_cannot_reach_another_tenants_user(oidc):
    with pytest.raises(AuthError, match="not provisioned"):
        auth.decode_token(token(tenant_id="acme"))  # jordan is not an acme user


def test_dev_tokens_refused_in_oidc_mode(oidc, db):
    from adintel.approvals.service import load_user

    dev = auth.issue_token(load_user(db, "brightwave", "u_jordan"))
    with pytest.raises(AuthError, match="not accepted"):
        auth.decode_token(dev)


def test_production_requires_oidc():
    from adintel.config import Settings
    from adintel.core.errors import ConfigError

    with pytest.raises(ConfigError, match="AUTH_MODE"):
        Settings(
            env="production",
            jwt_secret="x" * 40,
            approval_signing_key="y" * 40,
            dev_login_enabled=False,
            storage="mongo",
            queue="sqs",
            llm_provider="bedrock",
        ).validate_for_environment()
