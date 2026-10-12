from datetime import date

import pytest

from adintel.core.errors import BudgetExceeded, CheckpointCorrupted, KillSwitchEngaged, RateLimited
from adintel.domain.enums import AgentName, DegradationCode
from adintel.domain.state import BudgetLimits, BudgetUsage, RunState
from adintel.harness import admission
from adintel.harness.admission import RateLimiter, admit
from adintel.harness.budget import UsageMeter
from adintel.harness.checkpoint import CheckpointStore
from adintel.harness.degradation import MATRIX, degrade
from adintel.harness.idempotency import run_idempotency_key
from adintel.harness.killswitch import KillSwitches
from adintel.harness.timeouts import AGENT_SECONDS, AGENT_TIERS, RUN_SECONDS, STEP_DISPATCH_SECONDS, TCP_CONNECT_SECONDS
from adintel.llm.registry import get_registry


def _state():
    return RunState(run_id="run1", tenant_id="t1", brand_id="b1", period_start=date(2026, 10, 5),
                    period_end=date(2026, 10, 11))


def test_timeouts_strictly_nest():
    reg = get_registry()
    assert RUN_SECONDS > STEP_DISPATCH_SECONDS
    for agent, secs in AGENT_SECONDS.items():
        assert STEP_DISPATCH_SECONDS > secs, agent
        tiers = AGENT_TIERS.get(agent, ())
        assert secs > sum(reg.tiers[t].timeout_seconds for t in tiers), agent
    for t in reg.tiers.values():
        http_read = t.timeout_seconds - 5
        assert t.timeout_seconds > http_read > t.connect_timeout_seconds >= TCP_CONNECT_SECONDS - 0.001


def test_budget_meter_limits_each_dimension():
    m = UsageMeter(BudgetLimits(max_steps=2, max_tokens=100, max_cost_usd=1.0), BudgetUsage())
    m.charge(50, 40, 0.5)
    m.precheck(tokens=10)
    with pytest.raises(BudgetExceeded, match="tokens"):
        m.precheck(tokens=11)
    with pytest.raises(BudgetExceeded, match="cost"):
        m.precheck(cost=0.6)
    m.step(); m.step()
    assert m.exhausted_reason(extra_steps=1) == "steps"


def test_idempotency_key_is_stable_and_sensitive():
    k = dict(tenant_id="t", brand_id="b", period_start=date(2026, 10, 5), period_end=date(2026, 10, 11),
             goal="weekly_report", schedule_date="2026-10-12")
    assert run_idempotency_key(**k) == run_idempotency_key(**k)
    assert run_idempotency_key(**k) != run_idempotency_key(**{**k, "brand_id": "c"})


def test_checkpoint_round_trip_and_corruption(db):
    store = CheckpointStore(db, "t1")
    s = _state()
    store.save(s, version=0)
    s.visits["anomaly"] = 1
    store.save(s, version=1)
    v, restored = store.latest("run1")
    assert v == 1 and restored.visits == {"anomaly": 1}
    db.collection("run_checkpoints").update_one({"run_id": "run1", "step": 1},
                                                {"$set": {"state": '{"run_id": "tampered"}'}})
    with pytest.raises(CheckpointCorrupted):
        store.latest("run1")


def test_kill_switches_all_scopes(db):
    ks = KillSwitches(db)
    assert ks.engaged(tenant_id="t1", brand_id="b1", agent="analyst") is None
    ks.set("agent", "analyst", True, actor_id="admin1", reason="bad prompt")
    assert ks.engaged(tenant_id="t1", brand_id="b1", agent="analyst") == "agent:analyst"
    assert ks.engaged(tenant_id="t1", brand_id="b1", agent="report") is None
    ks.set("brand", "t1/b1", True, actor_id="admin1", reason="client request", tenant_id_for_audit="t1")
    assert ks.engaged(tenant_id="t1", brand_id="b1") == "brand:t1/b1"
    ks.set("global", "*", True, actor_id="admin1", reason="incident")
    assert ks.engaged(tenant_id="t2") == "global:*"
    with pytest.raises(ValueError):
        ks.set("planet", "x", True, actor_id="a", reason="r")


def test_admission_checks(db, monkeypatch):
    db.collection("tenants").insert_one({"tenant_id": "t1", "name": "T", "active": True})
    admit(db, tenant_id="t1", brand_id="b1")
    with pytest.raises(KillSwitchEngaged):
        admit(db, tenant_id="nope", brand_id="b1")
    db.collection("cost_events").insert_one({"tenant_id": "t1", "day": __import__("adintel.core.clock",
                                             fromlist=["utcnow"]).utcnow().date().isoformat(), "cost_usd": 999})
    with pytest.raises(RateLimited):
        admit(db, tenant_id="t1", brand_id="b1")


def test_rate_limiter():
    rl = RateLimiter(2, 60)
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a") and rl.allow("b")


def test_every_degradation_code_is_in_the_matrix_with_a_caveat_policy():
    assert set(MATRIX) == set(DegradationCode)
    d = degrade(DegradationCode.PLATFORM_UNAVAILABLE, AgentName.INGESTION, "TikTok")
    assert "TikTok" in d.client_caveat
