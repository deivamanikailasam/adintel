import json
import logging

from adintel.observability import context
from adintel.observability.alerts import Severity, install_security_hooks, raise_alert
from adintel.observability.logging import JsonFormatter
from adintel.observability.metrics import REGISTRY, TENANT_VIOLATIONS


def test_json_log_lines_carry_run_and_tenant_ids():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "agent_step", (), None)
    rec.agent = "analyst"
    with context.bind(run_id="run_1", tenant_id="t1", brand_id="b1"):
        out = json.loads(JsonFormatter().format(rec))
    assert out["run_id"] == "run_1" and out["tenant_id"] == "t1" and out["agent"] == "analyst"
    assert out["event"] == "agent_step"


def test_context_unbinds():
    with context.bind(run_id="r"):
        assert context.current()["run_id"] == "r"
    assert "run_id" not in context.current()


def test_alerts_are_persisted_except_p4(db):
    raise_alert(Severity.P3, "one platform degraded", tenant_id="t1")
    raise_alert(Severity.P4, "a single fallback")
    rows = db.collection("notifications").find({})
    assert [r["title"] for r in rows] == ["one platform degraded"]


def test_tenant_violation_increments_metric_and_pages(db):
    import pytest

    from adintel.core.errors import TenantIsolationViolation
    from adintel.storage import TenantScopedRepo

    install_security_hooks()
    before = REGISTRY.get_sample_value("adintel_tenant_isolation_violations_total", {"collection": "reports"}) or 0
    with pytest.raises(TenantIsolationViolation):
        TenantScopedRepo(db, "reports", "t1").find({"tenant_id": "t2"})
    after = REGISTRY.get_sample_value("adintel_tenant_isolation_violations_total", {"collection": "reports"})
    assert after == before + 1
    assert db.collection("notifications").find_one({"severity": "P1"})["audience"] == "security"
    assert TENANT_VIOLATIONS is not None
