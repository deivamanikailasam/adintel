"""Monthly chaos tests, run on every commit: kill a worker mid-run (it must resume), return 503 from a
platform (it must degrade), hang the guardrail (it must fail closed), corrupt a checkpoint (it must fail
cleanly), exhaust the budget (it must finalize best-effort), flip a kill switch mid-run."""

import threading

import pytest

from adintel.connectors.synthetic import inject_failure, reset_world
from adintel.domain.enums import DegradationCode, Platform, RecommendationStatus, RunStatus
from adintel.graph.engine import RunEngine
from adintel.harness.killswitch import KillSwitches
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START

pytestmark = pytest.mark.chaos


@pytest.fixture
def engine(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    return RunEngine(db)


def start(engine, brand="urban-roast"):
    doc, _ = engine.start(tenant_id="brightwave", brand_id=brand, period_start=PERIOD_START, period_end=PERIOD_END)
    return doc["run_id"]


def test_worker_killed_mid_run_resumes_from_checkpoint(engine, db, monkeypatch):
    run_id = start(engine)
    stop = threading.Event()
    from adintel.harness import checkpoint as cp

    orig = cp.CheckpointStore.save

    def save(self, state, *, version):
        if version == 5:
            stop.set()  # SIGTERM arrives after the 5th step
        return orig(self, state, version=version)

    monkeypatch.setattr(cp.CheckpointStore, "save", save)
    assert engine.execute("brightwave", run_id, stop=stop) is None
    first = db.collection("run_checkpoints").count({"run_id": run_id})
    final = engine.execute("brightwave", run_id)  # another worker picks the message up
    assert final.status == RunStatus.AWAITING_APPROVAL
    agents = [str(t.agent) for t in final.traces]
    assert agents.count("ingestion") == 1 and agents.count("anomaly") == 1  # nothing re-ran
    assert db.collection("run_checkpoints").count({"run_id": run_id}) > first


def test_platform_503_degrades_not_fails(engine, monkeypatch):
    monkeypatch.setattr("adintel.core.resilience.time.sleep", lambda s: None)
    inject_failure("fitely", Platform.TIKTOK, "outage")
    s = engine.execute("brightwave", start(engine, "fitely"))
    assert s.status == RunStatus.DEGRADED and s.has_degradation(DegradationCode.PLATFORM_UNAVAILABLE)
    caveats = next(x for x in s.report.sections if x.key == "caveats").body
    assert "tiktok" in caveats


def test_guardrail_hang_fails_closed_and_quarantines(engine, db, monkeypatch):
    from adintel.domain.enums import AgentName
    from adintel.harness import timeouts

    monkeypatch.setitem(timeouts.AGENT_SECONDS, AgentName.GUARDRAIL, 0.2)
    import time

    from adintel.agents import guardrail

    monkeypatch.setattr(guardrail, "classify", lambda ctx, text: (time.sleep(2), (None, "hung"))[1])
    s = engine.execute("brightwave", start(engine))
    assert s.status == RunStatus.HELD
    rec = db.collection("recommendations").find_one({"run_id": s.run_id})
    assert rec["status"] == RecommendationStatus.QUARANTINED
    assert db.collection("reports").find_one({"run_id": s.run_id})["status"] == "held"


def test_corrupt_checkpoint_fails_cleanly(engine, db):
    run_id = start(engine)
    engine.execute("brightwave", run_id, stop=_stop_after_first())
    db.collection("run_checkpoints").update_many({"run_id": run_id}, {"$set": {"state": "{garbage"}})
    assert engine.execute("brightwave", run_id) is None
    assert db.collection("runs").find_one({"run_id": run_id})["status"] == RunStatus.FAILED


def _stop_after_first():
    e = threading.Event()
    e.set()
    return e


def test_budget_exhaustion_finalizes_best_effort(engine, monkeypatch):
    monkeypatch.setenv("ADINTEL_RUN_MAX_COST_USD", "0.003")
    from adintel.config import reset_settings_cache

    reset_settings_cache()
    s = engine.execute("brightwave", start(engine))
    assert s.budget_exhausted and s.report is not None and s.report.deterministic_template
    assert s.has_degradation(DegradationCode.BUDGET_EXHAUSTED) and s.guardrail.passed
    assert s.status in (RunStatus.DEGRADED, RunStatus.AWAITING_APPROVAL)


def test_kill_switch_stops_the_next_dispatch(engine, db, monkeypatch):
    run_id = start(engine)
    from adintel.agents import anomaly

    orig = anomaly.run

    def flip(state, ctx):
        KillSwitches(db).set("brand", "brightwave/urban-roast", True, actor_id="u_admin", reason="client call",
                             tenant_id_for_audit="brightwave")
        return orig(state, ctx)

    monkeypatch.setitem(__import__("adintel.graph.nodes", fromlist=["AGENTS"]).AGENTS,
                        __import__("adintel.domain.enums", fromlist=["AgentName"]).AgentName.ANOMALY, flip)
    s = engine.execute("brightwave", run_id)
    assert s.status == RunStatus.KILLED and "analyst" not in {str(t.agent) for t in s.traces}


def test_agent_crash_degrades_instead_of_failing(engine, monkeypatch):
    from adintel.domain.enums import AgentName
    from adintel.graph import nodes

    def boom(state, ctx):
        raise RuntimeError("bug")

    monkeypatch.setitem(nodes.AGENTS, AgentName.ANALYST, boom)
    s = engine.execute("brightwave", start(engine))
    assert s.has_degradation(DegradationCode.ANALYST_SKIPPED) and s.report is not None
    assert not s.recommendations
