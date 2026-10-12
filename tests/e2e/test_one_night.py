"""One night in production: three brands, three different paths (the story in docs/00-overview)."""

import pytest

from adintel.connectors.synthetic import reset_world
from adintel.domain.enums import RecommendationStatus, RunStatus
from adintel.graph.engine import RunEngine
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START


@pytest.fixture
def engine(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    return RunEngine(db)


def run(engine, brand):
    return engine.run(tenant_id="brightwave", brand_id=brand, period_start=PERIOD_START, period_end=PERIOD_END,
                      trigger="schedule", schedule_date=PERIOD_END)


def test_urban_roast_full_investigation(engine, db):
    s = run(engine, "urban-roast")
    assert s.status == RunStatus.AWAITING_APPROVAL, (s.degradations, s.abort_reason)
    agents = [str(t.agent) for t in s.traces]
    assert agents[:3] == ["ingestion", "data_quality", "orchestrator"]
    for a in ("anomaly", "analyst", "optimizer", "report", "guardrail"):
        assert a in agents
    assert any(d.decided_by == "model" for d in s.decisions)
    rule_hops = sum(d.decided_by.startswith("rule:") for d in s.decisions)
    assert rule_hops >= 0.6 * len(s.decisions)  # most hops make no model call
    rec = db.collection("recommendations").find_one({"run_id": s.run_id})
    assert rec["status"] == RecommendationStatus.PENDING_APPROVAL and rec["amount_usd_per_day"] == 200.0
    assert db.collection("reports").find_one({"run_id": s.run_id})["status"] == "released"
    assert db.collection("notifications").count({"kind": "approval_needed"}) == 1
    assert s.usage.steps <= 13 and s.usage.cost_usd < 2.0


def test_fitely_clean_path_skips_analyst_and_optimizer(engine):
    s = run(engine, "fitely")
    agents = {str(t.agent) for t in s.traces}
    assert s.status == RunStatus.COMPLETED and "analyst" not in agents and "optimizer" not in agents
    assert all(d.decided_by.startswith("rule:") for d in s.decisions)  # zero model calls for routing


def test_northpeak_abort_path_never_reaches_the_orchestrator(engine, db):
    s = run(engine, "northpeak")
    assert s.status == RunStatus.ABORTED_DATA_QUALITY
    assert "orchestrator" not in {str(t.agent) for t in s.traces} and s.report is None
    assert db.collection("notifications").find_one({"kind": "reporting_paused"})


def test_clean_path_costs_a_fraction_of_the_full_path(engine):
    full = run(engine, "urban-roast").usage.cost_usd
    clean = run(engine, "fitely").usage.cost_usd
    assert clean * 3 < full


def test_duplicate_trigger_maps_to_the_existing_run(engine, db):
    a, created_a = engine.start(tenant_id="brightwave", brand_id="fitely", period_start=PERIOD_START,
                                period_end=PERIOD_END, schedule_date=PERIOD_END)
    b, created_b = engine.start(tenant_id="brightwave", brand_id="fitely", period_start=PERIOD_START,
                                period_end=PERIOD_END, schedule_date=PERIOD_END)
    assert created_a and not created_b and a["run_id"] == b["run_id"]


def test_every_run_leaves_a_verifiable_audit_chain(engine, db):
    from adintel.audit import verify_all_tenants

    run(engine, "urban-roast")
    assert all(v.ok for v in verify_all_tenants(db))
