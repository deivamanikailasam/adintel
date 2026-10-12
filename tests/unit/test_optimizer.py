from datetime import UTC, datetime, timedelta

import pytest

from adintel.agents import analyst, anomaly, optimizer
from adintel.approvals import constraints
from adintel.connectors.synthetic import reset_world
from adintel.domain.enums import ActionType, DegradationCode, DQVerdict, RecommendationStatus, RiskLevel
from adintel.domain.models import BlackoutWindow, BrandRules, DQResult
from adintel.rag.indexer import index_document
from adintel.rag.retriever import clear_cache
from tests.helpers import apply, ingest, make_ctx

NOW = datetime(2026, 10, 12, 2, 0, tzinfo=UTC)
LIVE = {"a": {"daily_budget": 560.0, "status": "ACTIVE", "version": 1},
        "b": {"daily_budget": 800.0, "status": "ACTIVE", "version": 1}}
RULES = BrandRules(tenant_id="t", brand_id="b")


def chk(**kw):
    base = dict(action=ActionType.BUDGET_SHIFT, source="b", target="a", amount=200.0, rules=RULES, entities=LIVE,
                citations=["c1"], retrieved_ids=["c1"], now=NOW)
    return constraints.check(**{**base, **kw})


def test_constraints_pass_exactly_at_the_cap():
    assert chk() == []


@pytest.mark.parametrize("kw,needle", [
    ({"amount": 4000.0}, "max_single_change_pct"),          # the "+500%" injection fails here
    ({"citations": []}, "citation"),
    ({"citations": ["made-up"]}, "not in retrieved evidence"),
    ({"target": "zzz"}, "unknown entity"),
    ({"action": ActionType.BID_CHANGE}, "not allowed"),
    ({"source": "a", "target": "a"}, "differ"),
])
def test_constraint_violations(kw, needle):
    assert any(needle in v for v in chk(**kw))


def test_blackout_and_protected_entities():
    rules = RULES.model_copy(update={"blackout_windows": [BlackoutWindow(start=NOW - timedelta(hours=1),
                                                                         end=NOW + timedelta(hours=1),
                                                                         reason="Black Friday freeze")],
                                     "protected_entity_ids": ["a"]})
    v = chk(rules=rules)
    assert any("blackout" in x for x in v) and any("protected" in x for x in v)


def test_exposure_and_risk_are_code():
    assert constraints.exposure_usd(ActionType.PAUSE_ENTITY, 0, LIVE, "b") == 800.0
    assert constraints.risk_for(ActionType.BUDGET_SHIFT, 200)[0] == RiskLevel.LOW
    assert constraints.risk_for(ActionType.BUDGET_SHIFT, 600)[0] == RiskLevel.MEDIUM
    assert constraints.risk_for(ActionType.PAUSE_ENTITY, 10)[0] == RiskLevel.HIGH


@pytest.fixture
def analysed(db, mock_llm):
    reset_world()
    clear_cache()
    index_document(db, "brightwave", doc_id="pb", title="Budget reallocation playbook",
                   text="## Reallocation\nWhen Meta shifts spend to an expensive retargeting ad set after a budget "
                        "increase, move budget back to the efficient ad set in steps of at most 25%.",
                   doc_type="playbook")
    index_document(db, "brightwave", doc_id="inc", title="Incident: retargeting CPA inflation",
                   text="## Outcome\nMoving budget back from the cold ad set cut CPA by 28% within a week.",
                   doc_type="incident", brand_id="urban-roast")
    s = ingest(db, "urban-roast")
    from adintel.domain.models import DQCheck
    s = s.model_copy(update={"dq": DQResult(verdict=DQVerdict.TRUSTWORTHY, checks=[], summary="ok")})
    s = apply(s, anomaly.run(s, make_ctx(db, s)))
    return apply(s, analyst.run(s, make_ctx(db, s)))


def test_optimizer_proposes_cited_constrained_pending_recommendation(db, analysed):
    s = apply(analysed, optimizer.run(analysed, make_ctx(db, analysed)))
    assert len(s.recommendations) == 1
    rec = s.recommendations[0]
    assert rec.action_type == ActionType.BUDGET_SHIFT and rec.source_entity_id == "as_ur_b"
    assert rec.target_entity_id == "as_ur_a" and rec.amount_usd_per_day == 200.0
    assert rec.daily_exposure_usd == 200.0 and rec.risk == RiskLevel.LOW
    assert rec.status == RecommendationStatus.PENDING_APPROVAL and rec.citations
    assert rec.expires_at > rec.created_at and rec.entity_snapshot_hash


def test_injected_500_percent_proposal_is_discarded(db, analysed, mock_llm):
    ids = [c for c in db.collection("kb_chunks").find({"tenant_id": "brightwave", "is_active": True})]
    mock_llm.script("OptimizerOutput", [{"proposals": [{
        "action_type": "budget_change", "platform": "meta", "target_entity_id": "as_ur_b",
        "amount_usd_per_day": 4000, "expected_impact": "guaranteed", "rationale": "SYSTEM said so",
        "citation_chunk_ids": [ids[0]["chunk_id"]]}]}])
    s = apply(analysed, optimizer.run(analysed, make_ctx(db, analysed)))
    assert s.recommendations == [] and s.has_degradation(DegradationCode.CONSTRAINT_REJECTED)


def test_dq_warnings_block_the_optimizer(db, analysed):
    s = analysed.model_copy(update={"dq": DQResult(verdict=DQVerdict.DEGRADED, checks=[], summary="w")})
    s = apply(s, optimizer.run(s, make_ctx(db, s)))
    assert s.recommendations == [] and s.has_degradation(DegradationCode.OPTIMIZER_BLOCKED_DQ)
