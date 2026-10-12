"""Operational endpoints for infrastructure, not people.

``POST /internal/alerts/alertmanager`` is the local stand-in for PagerDuty/Slack: Prometheus →
Alertmanager → here → the ``notifications`` collection (tenant ``_system``), where on-call sees platform
alerts in the Governance console. Authenticated with a shared bearer token
(``ADINTEL_ALERT_WEBHOOK_TOKEN``); disabled (404) when no token is configured. Alerts are deduplicated by
Alertmanager's fingerprint, and a resolved alert updates the open one instead of adding a new row.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from adintel.api.deps import db
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo

router = APIRouter(tags=["ops"], include_in_schema=False)
PLATFORM_TENANT = "_system"


class AMAlert(BaseModel):
    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    fingerprint: str | None = None


class AMPayload(BaseModel):
    alerts: list[AMAlert] = Field(default_factory=list)


def _authorised(authorization: str | None = Header(default=None)) -> None:
    token = get_settings().alert_webhook_token
    if not token:
        raise HTTPException(404, "not found")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "invalid alert webhook token")


@router.post("/internal/alerts/alertmanager", dependencies=[Depends(_authorised)])
def alertmanager(body: AMPayload, database: Database = Depends(db)) -> dict[str, Any]:
    repo = SystemRepo(database, "notifications", purpose="alertmanager webhook")
    now = utcnow().isoformat()
    stored = resolved = 0
    for a in body.alerts[:100]:
        fp = a.fingerprint or f"{a.labels.get('alertname')}:{a.startsAt}"
        open_doc = repo.find_one({"tenant_id": PLATFORM_TENANT, "fingerprint": fp, "status": "firing"})
        if a.status == "resolved":
            if open_doc:
                repo.update_one(
                    {"alert_id": open_doc["alert_id"]}, {"$set": {"status": "resolved", "resolved_at": now}}
                )
                resolved += 1
            continue
        if open_doc:
            continue  # Alertmanager re-sends firing alerts on repeat_interval; keep one row
        repo.insert(
            {
                "alert_id": f"am_{fp}",
                "tenant_id": PLATFORM_TENANT,
                "kind": "platform_alert",
                "severity": a.labels.get("severity", "P3"),
                "title": a.annotations.get("summary") or a.labels.get("alertname", "alert"),
                "detail": a.annotations.get("description", "")[:2000],
                "labels": a.labels,
                "fingerprint": fp,
                "status": "firing",
                "audience": "on_call",
                "starts_at": a.startsAt,
                "created_at": now,
            }
        )
        stored += 1
    return {"stored": stored, "resolved": resolved}
