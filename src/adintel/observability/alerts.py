"""Alert routing by severity.

| Severity | Examples | Route (local) | Route (production) |
|----------|----------|---------------|--------------------|
| P1 page now | cross-tenant violation, guardrail model down, all platforms failing, execution mismatch, audit chain break | log CRITICAL + notifications + webhook | PagerDuty 24/7 |
| P2 business hours | report SLO at risk, frontier outage, >3 step-limit hits/hour, DLQ depth > 0 | log ERROR + notifications + webhook | PagerDuty business hours |
| P3 | one platform degraded, a failed run, cost > 2x baseline, cache hit drop > 20% | notifications + webhook | Slack |
| P4 | single validation failures or fallbacks | metrics only | dashboard only |
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

import httpx

from adintel.core.clock import utcnow
from adintel.core.ids import new_id

log = logging.getLogger(__name__)


class Severity(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


def raise_alert(
    severity: Severity,
    title: str,
    *,
    tenant_id: str | None = None,
    brand_id: str | None = None,
    details: dict[str, Any] | None = None,
    audience: str = "on_call",
) -> dict[str, Any]:
    from adintel.config import get_settings
    from adintel.storage import get_database
    from adintel.storage.tenant_repo import SystemRepo

    alert = {
        "alert_id": new_id("alr"),
        "severity": str(severity),
        "title": title,
        "tenant_id": tenant_id,
        "brand_id": brand_id,
        "details": details or {},
        "audience": audience,
        "created_at": utcnow().isoformat(),
        "acknowledged": False,
    }
    level = {
        Severity.P1: logging.CRITICAL,
        Severity.P2: logging.ERROR,
        Severity.P3: logging.WARNING,
        Severity.P4: logging.INFO,
    }[severity]
    log.log(level, "alert", extra={"severity": str(severity), "title": title, "audience": audience})
    if severity == Severity.P4:
        return alert
    try:
        SystemRepo(get_database(), "notifications", purpose="alert routing").insert(dict(alert))
    except Exception:
        log.exception("alert_persist_failed")
    url = get_settings().alert_webhook_url
    if url:
        try:
            from adintel.security import egress

            egress.check(url, "alert webhook")
            httpx.post(url, json={"text": f"[{severity}] {title}", "alert": alert}, timeout=3.0)
        except Exception as exc:
            log.warning("alert_webhook_failed", extra={"reason": str(exc)[:200]})
    return alert


_hooks_installed = False


def install_security_hooks() -> None:
    """Wire tenant-isolation violations to a metric and a P1 page (idempotent)."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    from adintel.observability.metrics import TENANT_VIOLATIONS
    from adintel.storage.tenant_repo import register_violation_hook

    def _hook(tenant_id: str, collection: str, detail: str) -> None:
        TENANT_VIOLATIONS.labels(collection=collection).inc()
        raise_alert(
            Severity.P1,
            "Cross-tenant access attempt",
            tenant_id=tenant_id,
            details={"collection": collection, "detail": detail},
            audience="security",
        )

    register_violation_hook(_hook)
