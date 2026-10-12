import pytest

from adintel.agents import data_quality
from adintel.connectors.synthetic import inject_failure, reset_world
from adintel.domain.enums import DegradationCode, DQVerdict, Platform, RunStatus
from tests.helpers import apply, ingest, make_ctx


@pytest.fixture(autouse=True)
def _world(mock_llm):
    reset_world()
    yield
    reset_world()


def test_ingestion_fetches_all_platforms_and_summarises(db):
    s = ingest(db, "urban-roast")
    assert {str(f.platform) for f in s.fetches if f.ok} == {"meta", "google_ads"}
    assert s.metrics_ref["platforms"] and s.metrics_summary["current"]["spend"] > 0
    assert db.collection("metrics_daily").count({"brand_id": "urban-roast"}) == 180 * 5
    # idempotent upsert: a second ingestion does not duplicate rows
    ingest(db, "urban-roast")
    assert db.collection("metrics_daily").count({"brand_id": "urban-roast"}) == 180 * 5


def test_one_platform_down_is_a_disclosed_degradation(db, monkeypatch):
    monkeypatch.setattr("adintel.core.resilience.time.sleep", lambda s: None)
    inject_failure("fitely", Platform.TIKTOK, "outage")
    s = ingest(db, "fitely")
    assert s.has_degradation(DegradationCode.PLATFORM_UNAVAILABLE)
    assert "tiktok" in s.degradations[0].client_caveat
    assert s.status == RunStatus.RUNNING and "tiktok" not in s.metrics_ref["platforms"]


def test_all_platforms_down_fails_the_run(db, monkeypatch):
    monkeypatch.setattr("adintel.core.resilience.time.sleep", lambda s: None)
    for p in (Platform.META, Platform.GOOGLE_ADS):
        inject_failure("urban-roast", p, "outage")
    s = ingest(db, "urban-roast")
    assert s.status == RunStatus.FAILED and s.has_degradation(DegradationCode.ALL_PLATFORMS_UNAVAILABLE)


def test_schema_drift_is_flagged_and_a_mapping_is_proposed_not_applied(db):
    inject_failure("fitely", Platform.META, "schema_drift")
    s = ingest(db, "fitely")
    assert s.has_degradation(DegradationCode.SCHEMA_DRIFT)
    prop = db.collection("notifications").find_one({"kind": "schema_mapping_proposal"})
    assert prop["audience"] == "engineering"


@pytest.mark.parametrize("brand,verdict", [("urban-roast", DQVerdict.TRUSTWORTHY), ("fitely", DQVerdict.TRUSTWORTHY),
                                           ("cobalt-saas", DQVerdict.TRUSTWORTHY),
                                           ("northpeak", DQVerdict.UNTRUSTWORTHY)])
def test_data_quality_verdicts(db, brand, verdict):
    s = ingest(db, brand)
    s = apply(s, data_quality.run(s, make_ctx(db, s)))
    assert s.dq.verdict == verdict, [c for c in s.dq.checks if not c.passed]
    assert len(s.dq.checks) == 7


def test_broken_tracking_aborts_and_pages(db):
    s = ingest(db, "northpeak")
    s = apply(s, data_quality.run(s, make_ctx(db, s)))
    assert s.status == RunStatus.ABORTED_DATA_QUALITY
    assert "conversions exactly 0" in s.abort_reason
    alert = db.collection("notifications").find_one({"severity": "P2"})
    assert "Reporting paused" in alert["title"]
