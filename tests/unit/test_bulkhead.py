"""Bulkheads per model tier: saturation fails fast and falls back instead of piling up on the server."""

import threading
import time
from dataclasses import replace

import pytest

from adintel.llm import bulkhead
from adintel.llm.bulkhead import TierSaturated, slot
from adintel.llm.registry import get_registry


@pytest.fixture(autouse=True)
def _reset():
    bulkhead.reset()
    yield
    bulkhead.reset()


def test_slot_limits_concurrency_and_times_out_fast():
    tier = replace(get_registry().tiers["frontier"], max_concurrency=1, queue_timeout_seconds=0.05)
    held = threading.Event()
    release = threading.Event()

    def hold():
        with slot(tier):
            held.set()
            release.wait(2)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(1)
    t0 = time.perf_counter()
    with pytest.raises(TierSaturated), slot(tier):
        pass
    assert time.perf_counter() - t0 < 0.5
    release.set()
    t.join()
    with slot(tier):  # freed again
        pass


def test_saturated_frontier_falls_back_to_small(db, mock_llm, monkeypatch):
    from adintel.agents.orchestrator import OrchestratorOutput
    from adintel.llm.gateway import CallContext, LLMGateway

    reg = get_registry()
    monkeypatch.setitem(
        reg.tiers, "frontier", replace(reg.tiers["frontier"], max_concurrency=1, queue_timeout_seconds=0.01)
    )
    sem = bulkhead._semaphore(reg.tiers["frontier"])
    sem.acquire()  # someone else holds the only frontier slot
    try:
        gw = LLMGateway(db, CallContext(tenant_id="brightwave", brand_id="urban-roast", run_id="r1"))
        r = gw.structured(
            agent="orchestrator", prompt_id="orchestrator", schema=OrchestratorOutput, context={"anomalies": []}
        )
        assert r.tier == "small" and r.fallback_used
    finally:
        sem.release()


def test_oversized_request_body_is_refused(db, mock_llm):
    from fastapi.testclient import TestClient

    from adintel.api.app import create_app

    c = TestClient(create_app(start_inline_worker=False))
    r = c.post("/auth/dev-login", content=b"x" * 2_000_001, headers={"content-type": "application/json"})
    assert r.status_code == 413
