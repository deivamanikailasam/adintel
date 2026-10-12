from datetime import date

import pytest

from adintel.connectors.normalize import normalise
from adintel.connectors.synthetic import SyntheticConnector, inject_failure, reset_world
from adintel.core.errors import AuthError, PlatformUnavailable
from adintel.domain.enums import Platform
from adintel.security.secrets import Credential, SecretStore

READ = Credential("brightwave", "meta", "read", "ref", {}, True)
WRITE = Credential("brightwave", "meta", "write", "ref", {}, True)
END = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def _world():
    reset_world()
    yield
    reset_world()


@pytest.mark.parametrize("platform,brand", [(Platform.GOOGLE_ADS, "urban-roast"), (Platform.META, "urban-roast"),
                                            (Platform.TIKTOK, "fitely"), (Platform.LINKEDIN, "cobalt-saas"),
                                            (Platform.AMAZON_ADS, "northpeak")])
def test_every_platform_normalises_to_usd_rows(platform, brand):
    raw = SyntheticConnector(platform).fetch(READ, brand, date(2026, 10, 1), END)
    rows, unmapped = normalise(raw, tenant_id="brightwave", brand_id=brand)
    assert rows and not unmapped
    assert all(r.platform == platform and r.spend >= 0 and r.clicks <= r.impressions for r in rows)
    assert {r.date for r in rows} == {date(2026, 10, d) for d in range(1, 12)}


def test_synthetic_data_is_deterministic():
    a = SyntheticConnector(Platform.META).fetch(READ, "urban-roast", date(2026, 9, 1), END).rows
    b = SyntheticConnector(Platform.META).fetch(READ, "urban-roast", date(2026, 9, 1), END).rows
    assert a == b


def test_eur_account_is_converted():
    raw = SyntheticConnector(Platform.TIKTOK).fetch(READ, "fitely", END, END)
    rows, _ = normalise(raw, tenant_id="t", brand_id="fitely")
    assert raw.account_currency == "EUR"
    assert rows[0].spend == pytest.approx(float(raw.rows[0]["spend"]) * 1.08, abs=0.01)
    assert rows[0].currency_original == "EUR"


def test_broken_tracking_scenario_has_zero_conversions_with_normal_clicks():
    raw = SyntheticConnector(Platform.META).fetch(READ, "northpeak", date(2026, 9, 1), END)
    rows, _ = normalise(raw, tenant_id="t", brand_id="northpeak")
    recent = [r for r in rows if (END - r.date).days < 6]
    older = [r for r in rows if (END - r.date).days >= 6]
    assert all(r.conversions == 0 for r in recent) and all(r.clicks > 100 for r in recent)
    assert sum(r.conversions for r in older) > 100


def test_spend_shift_scenario_moves_spend_to_cold_ad_set():
    raw = SyntheticConnector(Platform.META).fetch(READ, "urban-roast", date(2026, 9, 20), END)
    rows, _ = normalise(raw, tenant_id="t", brand_id="urban-roast")
    def share(days):
        sel = [r for r in rows if r.campaign_id == "cmp_ur_meta_rt" and days(r)]
        return sum(r.spend for r in sel if r.entity_id == "as_ur_b") / sum(r.spend for r in sel)
    assert share(lambda r: (END - r.date).days >= 4) == pytest.approx(0.30, abs=0.03)
    assert share(lambda r: (END - r.date).days < 4) == pytest.approx(0.75, abs=0.03)


def test_failure_injection_and_schema_drift():
    inject_failure("fitely", Platform.TIKTOK, "outage")
    with pytest.raises(PlatformUnavailable):
        SyntheticConnector(Platform.TIKTOK).fetch(READ, "fitely", END, END)
    inject_failure("fitely", Platform.META, "schema_drift")
    raw = SyntheticConnector(Platform.META).fetch(READ, "fitely", END, END)
    _, unmapped = normalise(raw, tenant_id="t", brand_id="fitely")
    assert unmapped == ["new_metric_v2"]


def test_writes_need_write_scope_and_change_live_state():
    c = SyntheticConnector(Platform.META)
    assert c.get_entity(READ, "urban-roast", "as_ur_b")["daily_budget"] == 800.0
    with pytest.raises(AuthError):
        c.apply_change(READ, "urban-roast", {"op": "set_daily_budget", "entity_id": "as_ur_b", "daily_budget": 600})
    out = c.apply_change(WRITE, "urban-roast", {"op": "set_daily_budget", "entity_id": "as_ur_b", "daily_budget": 600})
    assert out["new_state"]["daily_budget"] == 600 and out["new_state"]["version"] == 2


def test_secret_scopes_follow_process_role(monkeypatch):
    store = SecretStore()
    monkeypatch.setenv("ADINTEL_PROCESS_ROLE", "worker")
    assert store.get("t", "meta", "read").scope == "read"
    with pytest.raises(AuthError):
        store.get("t", "meta", "write")
    monkeypatch.setenv("ADINTEL_PROCESS_ROLE", "executor")
    assert store.get("t", "meta", "write").scope == "write"
    monkeypatch.setenv("ADINTEL_PROCESS_ROLE", "api")
    with pytest.raises(AuthError):
        store.get("t", "meta", "read")
