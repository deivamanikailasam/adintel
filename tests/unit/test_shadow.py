"""Shadow mode: a challenger sees real traffic but never affects a run."""

from pathlib import Path

import pytest
import yaml

from adintel.agents.orchestrator import OrchestratorOutput
from adintel.config import Settings
from adintel.core.errors import ConfigError
from adintel.llm import shadow
from adintel.llm.gateway import CallContext, LLMGateway
from adintel.llm.registry import ModelRegistry


def _raw(rate=1.0):
    raw = yaml.safe_load(Path("config/models.yaml").read_text())
    nxt = dict(raw["tiers"]["frontier"], model_id="mlx-community/Qwen-next-27B-8bit", fallback=None)
    raw["tiers"]["frontier_next"] = nxt
    raw["shadow"] = {"frontier": {"challenger": "frontier_next", "sample_rate": rate}}
    return raw


@pytest.fixture
def sync(monkeypatch):
    monkeypatch.setattr(shadow._sync, "on", True, raising=False)


def _call(db, raw):
    gw = LLMGateway(
        db,
        CallContext(tenant_id="brightwave", brand_id="urban-roast", run_id="r1"),
        registry=ModelRegistry(raw, Settings()),
    )
    return gw.structured(
        agent="orchestrator", prompt_id="orchestrator", schema=OrchestratorOutput, context={"anomalies": []}
    )


def test_challenger_result_is_recorded_not_used(db, mock_llm, sync):
    r = _call(db, _raw())
    assert r.tier == "frontier"
    [doc] = db.collection("shadow_results").find({})
    assert (
        doc["challenger_model"] == "mlx-community/Qwen-next-27B-8bit" and doc["valid"] and doc["field_agreement"] == 1.0
    )
    assert doc["champion_call_id"] == r.call_ids[-1]
    [rep] = shadow.report(db, "brightwave")
    assert rep["samples"] == 1 and rep["verdict"] == "collecting"


def test_failing_challenger_never_breaks_the_run(db, mock_llm, sync):
    mock_llm.take_down("frontier_next")
    r = _call(db, _raw())
    assert r.tier == "frontier" and not r.fallback_used
    assert db.collection("shadow_results").find_one({})["valid"] is False


def test_sampling_is_deterministic_and_respects_rate():
    keys = [f"call_{i}" for i in range(2000)]
    share = sum(shadow.sampled(k, 0.2) for k in keys) / len(keys)
    assert 0.15 < share < 0.25 and shadow.sampled("x", 0.5) == shadow.sampled("x", 0.5)


def test_safety_tier_and_unknown_challenger_are_refused():
    raw = _raw()
    raw["shadow"] = {"safety": {"challenger": "frontier_next"}}
    with pytest.raises(ConfigError, match="never shadowed"):
        ModelRegistry(raw, Settings())
    raw["shadow"] = {"frontier": {"challenger": "nope"}}
    with pytest.raises(ConfigError, match="must both be defined"):
        ModelRegistry(raw, Settings())


def test_ready_verdict_after_enough_agreeing_samples(db):
    from adintel.core.clock import utcnow
    from adintel.storage.tenant_repo import TenantScopedRepo

    repo = TenantScopedRepo(db, "shadow_results", "brightwave")
    for i in range(50):
        repo.insert(
            {
                "agent": "orchestrator",
                "challenger_model": "m2",
                "valid": True,
                "exact": i % 10 != 0,
                "field_agreement": 0.95,
                "champion_latency_ms": 900,
                "challenger_latency_ms": 700,
                "created_at": utcnow().isoformat(),
            }
        )
    [rep] = shadow.report(db, "brightwave")
    assert rep["verdict"] == "ready" and rep["p50_latency_ms"]["challenger"] == 700
