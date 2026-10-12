"""Break-glass: two-person, time-boxed, audited elevation that never confers money authority."""

import pytest
from fastapi.testclient import TestClient

from adintel.api.app import create_app
from adintel.connectors.synthetic import reset_world
from adintel.security.break_glass import expire_job
from adintel.seed.catalog import seed


@pytest.fixture
def env(db, mock_llm):
    reset_world()
    seed(db, with_kb=False)
    c = TestClient(create_app(start_inline_worker=False))

    def login(email):
        return {"Authorization": f"Bearer {c.post('/auth/dev-login', json={'email': email}).json()['access_token']}"}

    return c, login, db


REQ = {"scopes": ["all_brands"], "reason": "investigating NorthPeak data outage", "ticket": "INC-42", "minutes": 30}


def test_two_person_elevation_and_expiry(env):
    c, login, db = env
    priya, admin = login("priya@brightwave.example"), login("admin@brightwave.example")
    assert c.get("/brands/urban-roast/summary", headers=priya).status_code == 403  # not her brand
    g = c.post("/admin/break-glass/requests", json=REQ, headers=priya).json()
    assert g["status"] == "requested"
    assert c.get("/brands/urban-roast/summary", headers=priya).status_code == 403  # not until approved
    assert c.post(f"/admin/break-glass/{g['grant_id']}/approve", headers=priya).status_code == 403  # not an admin
    assert c.post(f"/admin/break-glass/{g['grant_id']}/approve", headers=admin).json()["status"] == "active"
    assert c.get("/brands/urban-roast/summary", headers=priya).status_code == 200  # elevated
    # time runs out → access ends by itself, and the record is updated
    db.collection("access_grants").update_one(
        {"grant_id": g["grant_id"]}, {"$set": {"expires_at": "2000-01-01T00:00:00"}}
    )
    assert c.get("/brands/urban-roast/summary", headers=priya).status_code == 403
    assert expire_job(db) == 1
    actions = [a["action"] for a in db.collection("audit_log").find({"subject_id": g["grant_id"]})]
    assert actions == ["break_glass.requested", "break_glass.approved", "break_glass.expired"]


def test_emergency_path_pages_security_and_blocks_destructive_actions(env):
    c, login, db = env
    viewer = login("viewer@brightwave.example")
    g = c.post(
        "/admin/break-glass/requests",
        headers=viewer,
        json={
            "scopes": ["admin"],
            "reason": "3am outage, no admin reachable",
            "ticket": "INC-43",
            "minutes": 240,
            "emergency": True,
        },
    ).json()
    assert g["status"] == "active" and g["minutes"] == 60 and g["review_required"]  # capped at 60 minutes
    assert db.collection("notifications").find_one({"title": "Emergency break-glass access activated"})
    sw = {"scope": "brand", "key": "urban-roast", "engaged": True, "reason": "incident"}
    assert c.post("/admin/kill-switches", json=sw, headers=viewer).status_code == 200  # the point of break-glass
    erase = c.post("/admin/privacy/users/u_jordan/erase", json={"reason": "x"}, headers=viewer)
    assert erase.status_code == 403 and "break-glass" in erase.json()["detail"]
    flag = c.post("/admin/flags", json={"flag": "agent.optimizer", "enabled": False, "reason": "x"}, headers=viewer)
    assert flag.status_code == 403
    assert c.post(f"/admin/break-glass/{g['grant_id']}/revoke", headers=viewer).json()["status"] == "revoked"
    assert c.post("/admin/kill-switches", json=sw, headers=viewer).status_code == 403


def test_elevation_never_grants_spending_authority(env):
    c, login, db = env
    viewer, admin = login("viewer@brightwave.example"), login("admin@brightwave.example")
    g = c.post("/admin/break-glass/requests", json={**REQ, "scopes": ["admin"]}, headers=viewer).json()
    c.post(f"/admin/break-glass/{g['grant_id']}/approve", headers=admin)
    from adintel.approvals.service import load_user

    assert load_user(db, "brightwave", "u_viewer").approval_limit_usd == 0.0  # stored authority untouched
    bad = c.post("/admin/break-glass/requests", json={**REQ, "scopes": ["head_of_performance"]}, headers=viewer)
    assert bad.status_code == 422  # money roles are not grantable
    short = c.post("/admin/break-glass/requests", json={**REQ, "reason": "because"}, headers=viewer)
    assert short.status_code == 422
