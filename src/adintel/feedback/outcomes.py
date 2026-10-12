"""Outcome tracking: 14 days after a change is executed, compare what happened with what was predicted.

The Optimizer predicts a CPA change range ("-34% to -22%"). This job measures the blended CPA of the
entities the change touched over the 14 days before execution and the 14 days after (the execution day
itself is excluded because it is half old budget, half new), and grades the prediction:

| Verdict | Meaning |
|---------|---------|
| ``within_range`` | actual change landed inside the predicted range |
| ``better_than_expected`` | CPA fell more than predicted |
| ``improved_less_than_expected`` | CPA fell, but by less than predicted |
| ``worsened`` | CPA rose — the account manager is notified |
| ``insufficient_data`` | too few days or zero conversions on either side; nothing is claimed |

It is pure arithmetic over stored metrics: no model is involved, so the measurement cannot be talked into
a better grade. Results feed the feedback flywheel (``feedback`` collection), the eval baselines and the
weekly triage report.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction
from adintel.harness.flags import FeatureFlags
from adintel.observability.metrics import OUTCOMES
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

WINDOW_DAYS = 14
MIN_DAYS_EACH_SIDE = 7


def _cpa(rows: list[dict[str, Any]]) -> float | None:
    conv = sum(float(r.get("conversions") or 0) for r in rows)
    spend = sum(float(r.get("spend") or 0) for r in rows)
    return round(spend / conv, 4) if conv > 0 else None


def grade(actual_pct: float, low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "within_range" if actual_pct <= 0 else "worsened"
    lo, hi = min(low, high), max(low, high)
    if lo <= actual_pct <= hi:
        return "within_range"
    if actual_pct < lo:
        return "better_than_expected"
    if actual_pct < 0:
        return "improved_less_than_expected"
    return "worsened"


def measure(db: Database, tenant_id: str, execution: dict[str, Any]) -> dict[str, Any]:
    """Compute (but do not store) the outcome of one executed change."""
    rec = TenantScopedRepo(db, "recommendations", tenant_id).find_one(
        {"recommendation_id": execution["recommendation_id"]}
    )
    if rec is None:
        raise LookupError(execution["recommendation_id"])
    executed = datetime.fromisoformat(str(execution["executed_at"])).date()
    ids = [i for i in (rec.get("source_entity_id"), rec.get("target_entity_id")) if i]
    rows = TenantScopedRepo(db, "metrics_daily", tenant_id).find(
        {
            "brand_id": rec["brand_id"],
            "entity_id": {"$in": ids},
            "date": {
                "$gte": (executed - timedelta(days=WINDOW_DAYS)).isoformat(),
                "$lte": (executed + timedelta(days=WINDOW_DAYS)).isoformat(),
            },
        }
    )
    before = [r for r in rows if str(r["date"]) < executed.isoformat()]
    after = [r for r in rows if str(r["date"]) > executed.isoformat()]
    days_before, days_after = len({r["date"] for r in before}), len({r["date"] for r in after})
    cpa_before, cpa_after = _cpa(before), _cpa(after)
    out: dict[str, Any] = {
        "recommendation_id": rec["recommendation_id"],
        "execution_id": execution["execution_id"],
        "brand_id": rec["brand_id"],
        "run_id": rec.get("run_id"),
        "action_type": rec.get("action_type"),
        "executed_on": executed.isoformat(),
        "window_days": WINDOW_DAYS,
        "days_before": days_before,
        "days_after": days_after,
        "cpa_before": cpa_before,
        "cpa_after": cpa_after,
        "predicted_low_pct": rec.get("expected_cpa_change_pct_low"),
        "predicted_high_pct": rec.get("expected_cpa_change_pct_high"),
        "actual_pct": None,
    }
    if cpa_before is None or cpa_after is None or days_before < MIN_DAYS_EACH_SIDE or days_after < MIN_DAYS_EACH_SIDE:
        out["verdict"] = "insufficient_data"
        return out
    actual = round((cpa_after - cpa_before) / cpa_before * 100, 2)
    out["actual_pct"] = actual
    out["verdict"] = grade(actual, out["predicted_low_pct"], out["predicted_high_pct"])
    return out


def track_outcomes(db: Database, tenant_id: str, *, today: date | None = None) -> list[dict[str, Any]]:
    """Measure every succeeded execution that is at least 14 days old and not yet measured."""
    today = today or utcnow().date()
    flags = FeatureFlags(db, tenant_id)
    outcomes = TenantScopedRepo(db, "outcomes", tenant_id)
    cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    measured: list[dict[str, Any]] = []
    for ex in TenantScopedRepo(db, "executions", tenant_id).find({"status": "succeeded"}):
        if str(ex["executed_at"])[:10] > cutoff:
            continue
        if not flags.enabled("outcome_tracking", brand_id=ex["brand_id"]):
            continue
        if outcomes.find_one({"recommendation_id": ex["recommendation_id"]}):
            continue
        result = {**measure(db, tenant_id, ex), "measured_at": utcnow().isoformat()}
        try:
            outcomes.insert(result)
        except DuplicateKey:
            continue  # another scheduler replica got there first
        _record(db, tenant_id, result)
        measured.append(result)
    return measured


def _record(db: Database, tenant_id: str, o: dict[str, Any]) -> None:
    OUTCOMES.labels(verdict=o["verdict"]).inc()
    TenantScopedRepo(db, "recommendations", tenant_id).update_one(
        {"recommendation_id": o["recommendation_id"]},
        {"$set": {"outcome": {k: o[k] for k in ("verdict", "actual_pct", "measured_at")}}},
    )
    TenantScopedRepo(db, "feedback", tenant_id).insert(
        {
            "kind": "outcome_measured",
            "recommendation_id": o["recommendation_id"],
            "brand_id": o["brand_id"],
            "run_id": o["run_id"],
            "verdict": o["verdict"],
            "actual_pct": o["actual_pct"],
            "predicted": [o["predicted_low_pct"], o["predicted_high_pct"]],
            "created_at": o["measured_at"],
        }
    )
    AuditLog(db, tenant_id, system_version=get_settings().system_version).append(
        AuditAction.OUTCOME_MEASURED,
        actor_type="system",
        actor_id="system:outcomes",
        subject_type="recommendation",
        subject_id=o["recommendation_id"],
        run_id=o["run_id"],
        details={"verdict": o["verdict"], "actual_pct": o["actual_pct"], "cpa_before": o["cpa_before"]},
    )
    if o["verdict"] == "worsened":
        TenantScopedRepo(db, "notifications", tenant_id).insert(
            {
                "kind": "outcome_worsened",
                "brand_id": o["brand_id"],
                "recommendation_id": o["recommendation_id"],
                "audience": "account_manager",
                "title": "An approved change did not work as expected",
                "detail": f"CPA moved {o['actual_pct']:+.1f}% in the 14 days after the change "
                f"(predicted {o['predicted_low_pct']}% to {o['predicted_high_pct']}%). Consider reverting.",
                "created_at": o["measured_at"],
            }
        )


def outcomes_job(db: Database, *, today: date | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in SystemRepo(db, "tenants", purpose="outcome tracking").find():
        for o in track_outcomes(db, t["tenant_id"], today=today):
            counts[o["verdict"]] = counts.get(o["verdict"], 0) + 1
    return counts
