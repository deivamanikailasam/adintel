"""Host resource monitoring and the user-facing status banner."""

from collections import namedtuple

import pytest
from fastapi.testclient import TestClient

from adintel.api.app import create_app
from adintel.api.routers import status as status_router
from adintel.connectors.synthetic import reset_world
from adintel.observability import host
from adintel.seed.catalog import seed

Usage = namedtuple("Usage", "total used free")


def test_sample_reports_real_numbers(tmp_path):
    s = host.sample([tmp_path])
    assert 0 <= s["disk_free_ratio"][str(tmp_path)] <= 1


@pytest.mark.parametrize(
    ("free", "mem", "load", "expected"),
    [(0.5, 0.5, 0.5, []), (0.10, 0.5, 0.5, ["P2"]), (0.03, 0.04, 3.0, ["P1", "P1", "P2"])],
)
def test_thresholds(free, mem, load, expected):
    s = {"disk_free_ratio": {"/data": free}, "memory_available_ratio": mem, "load_per_cpu": load}
    assert [sev for sev, _ in host.problems(s)] == expected


def test_host_job_pages_on_a_full_disk(db, monkeypatch):
    monkeypatch.setattr(host.shutil, "disk_usage", lambda p: Usage(100, 98, 2))
    assert host.host_job()[0][0] == "P1"
    assert db.collection("notifications").find_one({"severity": "P1"})["title"].startswith("Host resources: disk")


@pytest.fixture
def client(db, mock_llm, monkeypatch):
    reset_world()
    seed(db, with_kb=False)
    status_router._cache.update(at=0.0, models=None)
    c = TestClient(create_app(start_inline_worker=False))
    token = c.post("/auth/dev-login", json={"email": "viewer@brightwave.example"}).json()["access_token"]
    return c, {"Authorization": f"Bearer {token}"}


def test_status_ok_then_degraded(client, monkeypatch):
    c, h = client
    monkeypatch.setattr(
        host,
        "sample",
        lambda paths=None: {"disk_free_ratio": {"/d": 0.5}, "memory_available_ratio": 0.5, "load_per_cpu": 0.1},
    )
    monkeypatch.setattr(
        status_router, "_models", lambda: {"frontier": True, "small": True, "report": True, "safety": True}
    )
    assert c.get("/status", headers=h).json()["status"] == "ok"
    monkeypatch.setattr(
        status_router, "_models", lambda: {"frontier": False, "small": True, "report": True, "safety": True}
    )
    r = c.get("/status", headers=h).json()
    assert r["status"] == "degraded" and "backup model" in r["messages"][0]["text"]
    monkeypatch.setattr(
        status_router, "_models", lambda: {"frontier": True, "small": True, "report": True, "safety": False}
    )
    assert c.get("/status", headers=h).json()["status"] == "down"
    assert c.get("/status").status_code == 401
