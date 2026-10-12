"""Outcome tracking, feature flags and the weekly triage report."""

from datetime import date, timedelta

import pytest

from adintel.approvals.service import ApprovalService, load_user
from adintel.connectors.synthetic import reset_world
from adintel.core.clock import utcnow
from adintel.domain.enums import DegradationCode
from adintel.executor.service import Executor
from adintel.feedback.outcomes import grade, outcomes_job, track_outcomes
from adintel.feedback.triage import render_markdown, triage_job, weekly_triage
from adintel.graph.engine import RunEngine
from adintel.harness.flags import FeatureFlags
from adintel.queueing import EXECUTIONS, get_queue
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START

T = "brightwave"


@pytest.fixture
def seeded(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    return db


def _run(db):
    return RunEngine(db).run(tenant_id=T, brand_id="urban-roast", period_start=PERIOD_START, period_end=PERIOD_END)


def _execute(db):
    rec_id = _run(db).recommendations[0].recommendation_id
    ApprovalService(db, T).approve(rec_id, load_user(db, T, "u_jordan"), typed_exposure_usd=200.0)
    msg = get_queue(EXECUTIONS).receive(wait_seconds=0.1)
    assert Executor(db, T).execute(msg.body["recommendation_id"], msg.body["approval_id"])["status"] == "succeeded"
    return rec_id


def _metrics(db, executed: date, cpa_before: float, cpa_after: float):
    coll = db.collection("metrics_daily")
    coll.delete_many({"tenant_id": T, "brand_id": "urban-roast", "entity_id": {"$in": ["as_ur_a", "as_ur_b"]}})
    for offset in range(-14, 15):
        d = executed + timedelta(days=offset)
        cpa = cpa_before if offset < 0 else cpa_after
        for e in ("as_ur_a", "as_ur_b"):
            coll.insert_one(
                {
                    "tenant_id": T,
                    "brand_id": "urban-roast",
                    "platform": "meta",
                    "date": d.isoformat(),
                    "entity_id": e,
                    "spend": cpa * 10,
                    "conversions": 10,
                }
            )


def _age_execution(db, rec_id, days=20) -> date:
    when = utcnow() - timedelta(days=days)
    db.collection("executions").update_one({"recommendation_id": rec_id}, {"$set": {"executed_at": when.isoformat()}})
    return when.date()


@pytest.mark.parametrize(
    ("actual", "verdict"),
    [(-30, "within_range"), (-50, "better_than_expected"), (-5, "improved_less_than_expected"), (12, "worsened")],
)
def test_grading(actual, verdict):
    assert grade(actual, -34.0, -22.0) == verdict


def test_outcome_is_measured_once_after_14_days(seeded):
    rec_id = _execute(seeded)
    assert track_outcomes(seeded, T) == []  # executed today: too early to judge
    executed = _age_execution(seeded, rec_id)
    _metrics(seeded, executed, cpa_before=40.0, cpa_after=28.0)  # -30%: inside -34%..-22%
    [o] = track_outcomes(seeded, T)
    assert o["verdict"] == "within_range" and o["actual_pct"] == -30.0 and o["days_before"] == 14
    assert track_outcomes(seeded, T) == []  # never measured twice
    rec = seeded.collection("recommendations").find_one({"recommendation_id": rec_id})
    assert rec["outcome"]["verdict"] == "within_range"
    assert seeded.collection("feedback").find_one({"kind": "outcome_measured"})["actual_pct"] == -30.0
    assert seeded.collection("audit_log").find_one({"action": "outcome.measured", "subject_id": rec_id})


def test_worsened_outcome_notifies_account_manager(seeded):
    rec_id = _execute(seeded)
    _metrics(seeded, _age_execution(seeded, rec_id), cpa_before=40.0, cpa_after=48.0)
    assert outcomes_job(seeded) == {"worsened": 1}
    note = seeded.collection("notifications").find_one({"kind": "outcome_worsened"})
    assert note and "+20.0%" in note["detail"]


def test_insufficient_data_claims_nothing(seeded):
    rec_id = _execute(seeded)
    executed = _age_execution(seeded, rec_id)
    _metrics(seeded, executed, 40.0, 30.0)
    seeded.collection("metrics_daily").delete_many({"date": {"$gt": (executed + timedelta(days=3)).isoformat()}})
    [o] = track_outcomes(seeded, T)
    assert o["verdict"] == "insufficient_data" and o["actual_pct"] is None


def test_flag_resolution_brand_over_tenant_over_default(seeded):
    ff = FeatureFlags(seeded, T)
    assert ff.enabled("agent.optimizer", brand_id="urban-roast")
    ff.set("agent.optimizer", False, actor_id="u_admin", reason="pilot")
    ff.set("agent.optimizer", True, actor_id="u_admin", reason="pilot brand", brand_id="urban-roast")
    assert ff.enabled("agent.optimizer", brand_id="urban-roast")
    assert not ff.enabled("agent.optimizer", brand_id="fitely")
    assert FeatureFlags(seeded, "acme").enabled("agent.optimizer")  # one tenant's flags never leak
    assert seeded.collection("audit_log").count({"action": "feature_flag.changed"}) == 2
    with pytest.raises(KeyError):
        ff.enabled("agent.nonexistent")


def test_disabled_optimizer_skips_visibly_and_proposes_nothing(seeded):
    FeatureFlags(seeded, T).set("agent.optimizer", False, actor_id="u_admin", reason="rollout")
    s = _run(seeded)
    assert s.recommendations == []
    assert DegradationCode.FEATURE_DISABLED in {d.code for d in s.degradations}
    assert str(s.status) == "completed"  # a planned rollout is not a degraded run


def test_triage_summarises_signals_and_suggests_actions(seeded):
    rec_id = _execute(seeded)
    _metrics(seeded, _age_execution(seeded, rec_id), 40.0, 48.0)
    track_outcomes(seeded, T)
    r = weekly_triage(seeded, T)
    assert r["runs"]["total"] == 1 and r["decisions"]["approved"] == 1
    assert r["outcomes"] == {"worsened": 1}
    assert any("optimizer flag" in a for a in r["actions"])
    md = render_markdown(r)
    assert md.startswith("# AdIntel weekly triage") and "Suggested actions" in md
    assert weekly_triage(seeded, "acme")["runs"]["total"] == 0  # tenant-scoped
    assert triage_job(seeded) >= 2
