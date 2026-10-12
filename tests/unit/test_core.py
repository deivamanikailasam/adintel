from datetime import UTC, date, datetime

import pytest

from adintel.config import Settings
from adintel.core.clock import FrozenClock
from adintel.core.errors import ConfigError
from adintel.core.hashing import canonical_json, hmac_sign, hmac_verify, sha256_obj
from adintel.domain.enums import RunStatus, Severity
from adintel.domain.state import FROZEN_FIELDS, RunState


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert sha256_obj({"d": date(2026, 1, 1)}) == sha256_obj({"d": "2026-01-01"})


def test_hmac_round_trip_and_tamper_detection():
    sig = hmac_sign("k", {"x": 1})
    assert hmac_verify("k", {"x": 1}, sig)
    assert not hmac_verify("k", {"x": 2}, sig)
    assert not hmac_verify("other", {"x": 1}, sig)


def test_frozen_clock_advances_only_when_told():
    clock = FrozenClock(datetime(2026, 10, 12, 2, 0, tzinfo=UTC))
    t0 = clock.now()
    clock.advance(seconds=30)
    assert (clock.now() - t0).total_seconds() == 30


def test_production_rejects_development_defaults():
    with pytest.raises(ConfigError) as exc:
        Settings(env="production").validate_for_environment()
    msg = str(exc.value)
    assert "JWT_SECRET" in msg and "APPROVAL_SIGNING_KEY" in msg and "DEV_LOGIN" in msg


def test_local_defaults_are_accepted():
    Settings(env="local").validate_for_environment()


def test_runstate_identity_fields_and_helpers():
    s = RunState(run_id="r", tenant_id="t", brand_id="b", period_start=date(2026, 10, 5),
                 period_end=date(2026, 10, 11))
    assert FROZEN_FIELDS == {"run_id", "tenant_id", "brand_id"}
    assert s.status == RunStatus.RUNNING
    assert 0.99 <= s.remaining_budget_fraction() <= 1.0
    assert Severity.HIGH.rank > Severity.MEDIUM.rank
    assert RunStatus.COMPLETED.terminal and not RunStatus.RUNNING.terminal
