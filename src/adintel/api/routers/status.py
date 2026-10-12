"""``GET /status`` — what a signed-in user needs to know about the system right now (the app's banner).

Coarse by design: component states and plain-English messages, no hostnames, versions or internals.
Model health is cached for 30 seconds so a page load never waits on a slow model server.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Depends

from adintel.api.deps import ANY_STAFF, db, require
from adintel.harness.killswitch import KillSwitches
from adintel.observability import host
from adintel.security.auth import Principal
from adintel.storage.base import Database

router = APIRouter(tags=["ops"])
_cache: dict[str, Any] = {"at": 0.0, "models": None}
_lock = threading.Lock()
MESSAGES = {
    "frontier": "Deep analysis is running on a backup model; reports may take longer.",
    "small": "The fast model is unavailable; some answers use a slower model.",
    "report": "Report writing is using a backup model.",
    "safety": "The safety check is unavailable: reports are held until it recovers.",
}


def _models() -> dict[str, bool]:
    with _lock:
        if _cache["models"] is not None and time.monotonic() - _cache["at"] < 30:
            return dict(_cache["models"])
    from adintel.llm.providers import get_provider
    from adintel.llm.registry import get_registry

    out = {}
    for name, tier in get_registry().tiers.items():
        if name not in MESSAGES:
            continue
        try:
            prov = get_provider(tier.provider)
            out[name] = bool(prov.health(tier).get("ok")) if hasattr(prov, "health") else True
        except Exception:
            out[name] = False
    with _lock:
        _cache.update(at=time.monotonic(), models=out)
    return out


@router.get("/status")
def status(p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    db_ok = database.ping()
    if not db_ok:
        messages.append({"level": "down", "text": "The database is unreachable; nothing can be saved."})
    models = _models()
    for tier, ok in models.items():
        if not ok:
            messages.append({"level": "down" if tier == "safety" else "degraded", "text": MESSAGES[tier]})
    sw = KillSwitches(database).engaged(tenant_id=p.tenant_id)
    if sw:
        messages.append(
            {"level": "degraded", "text": f"A kill switch is engaged ({sw.split(':')[0]}); new runs are paused."}
        )
    for sev, msg in host.problems(host.sample()):
        messages.append({"level": "down" if sev == "P1" else "degraded", "text": "Server: " + msg.split(" — ")[0]})
    overall = "down" if any(m["level"] == "down" for m in messages) else ("degraded" if messages else "ok")
    return {"status": overall, "components": {"database": db_ok, "models": models}, "messages": messages}
