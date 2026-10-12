from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from adintel.agents import anomaly
from adintel.connectors.synthetic import reset_world
from adintel.domain.enums import DegradationCode, Metric, Severity
from adintel.domain.models import BrandRules, Suppression
from adintel.storage import TenantScopedRepo
from tests.helpers import PERIOD_END, apply, ingest, make_ctx


@pytest.fixture(autouse=True)
def _world(mock_llm):
    reset_world()
    yield


def _run(db, brand):
    s = ingest(db, brand)
    return apply(s, anomaly.run(s, make_ctx(db, s)))


def test_urban_roast_meta_cpa_spike_is_high_severity(db):
    s = _run(db, "urban-roast")
    top = s.material_anomalies()[0]
    assert top.campaign_id == "cmp_ur_meta_rt" and top.metric == Metric.CPA and top.direction == "up"
    assert top.severity in (Severity.HIGH, Severity.CRITICAL)
    assert 40 <= top.deviation_pct <= 90 and top.days >= 2 and top.observed > top.upper


def test_clean_brand_has_nothing_above_low(db):
    s = _run(db, "fitely")
    assert s.material_anomalies() == []


def test_detection_is_deterministic(db):
    a = _run(db, "urban-roast").anomalies
    b = _run(db, "urban-roast").anomalies
    assert [x.model_dump(exclude={"anomaly_id"}) for x in a] == [x.model_dump(exclude={"anomaly_id"}) for x in b]
    assert [x.anomaly_id for x in a] == [x.anomaly_id for x in b]


def test_weekly_seasonality_does_not_fire_every_monday():
    days = [PERIOD_END - timedelta(days=i) for i in range(120)][::-1]
    rng = np.random.default_rng(1)
    vals = np.array([100 * (1.4 if d.weekday() == 0 else 1.0) for d in days]) * rng.lognormal(0, 0.02, len(days))
    band = anomaly.detect_series(days, vals, PERIOD_END)
    flags = [o > h or o < lo for o, lo, h in zip(band["observed"], band["lower"], band["upper"])]
    assert not any(flags)


def test_insufficient_history_degrades(db):
    s = ingest(db, "fitely")
    s.metrics_ref["start"] = (PERIOD_END - timedelta(days=20)).isoformat()
    s = apply(s, anomaly.run(s, make_ctx(db, s)))
    assert s.has_degradation(DegradationCode.INSUFFICIENT_HISTORY) and s.anomaly_pass_done


def test_human_approved_suppression_hides_the_anomaly(db):
    rules = BrandRules(tenant_id="brightwave", brand_id="urban-roast", suppressions=[Suppression(
        description="Planned retargeting push", metric=Metric.CPA, entity_id="cmp_ur_meta_rt", approved_by="u_head",
        approved_at=datetime.now(UTC))])
    TenantScopedRepo(db, "brand_rules", "brightwave").insert(rules.model_dump(mode="json"))
    s = _run(db, "urban-roast")
    assert all(not (a.metric == Metric.CPA and a.campaign_id == "cmp_ur_meta_rt") for a in s.anomalies)


def test_severity_matrix():
    assert anomaly.severity_for(60, 1500) == Severity.HIGH
    assert anomaly.severity_for(120, 1500) == Severity.CRITICAL
    assert anomaly.severity_for(-8, 50) == Severity.LOW
    assert anomaly.severity_for(25, 200) == Severity.MEDIUM
