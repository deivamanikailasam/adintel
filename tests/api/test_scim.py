"""SCIM 2.0 provisioning: joiners, movers, leavers — and money authority never comes from the IdP."""

import pytest
from fastapi.testclient import TestClient

from adintel.api.app import create_app
from adintel.api.routers.scim import issue_token
from adintel.connectors.synthetic import reset_world
from adintel.seed.catalog import seed


@pytest.fixture
def scim(db, mock_llm):
    reset_world()
    seed(db, with_kb=False)
    client = TestClient(create_app(start_inline_worker=False))
    return client, {"Authorization": f"Bearer {issue_token(db, 'brightwave', actor_id='test')}"}, db


NEW = {
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
    "userName": "Nia@BrightWave.example",
    "name": {"formatted": "Nia Okafor"},
    "externalId": "okta-123",
    "active": True,
    "roles": [{"value": "account_manager"}],
}


def test_auth_is_required_and_tenant_scoped(scim):
    client, h, db = scim
    assert client.get("/scim/v2/Users").status_code == 401
    assert client.get("/scim/v2/Users", headers={"Authorization": "Bearer nope"}).status_code == 401
    users = client.get("/scim/v2/Users", headers=h).json()
    assert users["totalResults"] > 0 and all(u["userName"].endswith("@brightwave.example") for u in users["Resources"])
    acme = {"Authorization": f"Bearer {issue_token(db, 'acme', actor_id='test')}"}
    assert client.get("/scim/v2/Users/u_jordan", headers=acme).status_code == 404  # another tenant's user


def test_joiner_mover_leaver(scim):
    client, h, db = scim
    r = client.post("/scim/v2/Users", json=NEW, headers=h)
    assert r.status_code == 201
    uid = r.json()["id"]
    doc = db.collection("users").find_one({"user_id": uid})
    assert doc["email"] == "nia@brightwave.example" and doc["approval_limit_usd"] == 0.0  # no money authority
    assert client.post("/scim/v2/Users", json=NEW, headers=h).status_code == 409
    found = client.get('/scim/v2/Users?filter=userName eq "nia@brightwave.example"', headers=h).json()
    assert found["totalResults"] == 1
    # mover: role change
    patch = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "roles", "value": [{"value": "senior_account_manager"}]}],
    }
    assert client.patch(f"/scim/v2/Users/{uid}", json=patch, headers=h).json()["roles"] == [
        {"value": "senior_account_manager"}
    ]
    # the IdP cannot raise an approval limit
    bad = {"Operations": [{"op": "replace", "path": "approval_limit_usd", "value": 1e9}]}
    assert client.patch(f"/scim/v2/Users/{uid}", json=bad, headers=h).status_code == 400
    # leaver: deactivation removes access on the next request
    login = client.post("/auth/dev-login", json={"email": "nia@brightwave.example"}).json()["access_token"]
    assert client.get("/brands", headers={"Authorization": f"Bearer {login}"}).status_code == 200
    assert client.delete(f"/scim/v2/Users/{uid}", headers=h).status_code == 204
    assert client.get("/brands", headers={"Authorization": f"Bearer {login}"}).status_code == 401
    assert db.collection("users").find_one({"user_id": uid})["roles"] == []
    actions = [a["action"] for a in db.collection("audit_log").find({"subject_id": uid})]
    assert actions == ["user.provisioned", "user.updated", "user.deprovisioned"]


def test_unknown_roles_and_filters_are_rejected(scim):
    client, h, _ = scim
    assert (
        client.post(
            "/scim/v2/Users", json={**NEW, "userName": "x@b.example", "roles": [{"value": "god"}]}, headers=h
        ).status_code
        == 400
    )
    assert client.get('/scim/v2/Users?filter=name co "a"', headers=h).status_code == 400
    assert client.get("/scim/v2/ServiceProviderConfig").json()["patch"]["supported"] is True
