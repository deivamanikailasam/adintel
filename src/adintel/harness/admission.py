"""Admission control: tenant active, quota and daily cost cap, kill switches, idempotency."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.core.errors import KillSwitchEngaged, RateLimited
from adintel.harness.killswitch import KillSwitches
from adintel.observability.alerts import Severity, raise_alert
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo


class RateLimiter:
    """Sliding-window limiter per key (in-process; Redis-backed in multi-worker deployments)."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


_run_limiter: RateLimiter | None = None


def run_limiter() -> RateLimiter:
    global _run_limiter
    if _run_limiter is None:
        _run_limiter = RateLimiter(get_settings().tenant_runs_per_minute)
    return _run_limiter


@dataclass
class AdmissionResult:
    ok: bool
    reason: str | None = None


def tenant_cost_today(db: Database, tenant_id: str) -> float:
    day = utcnow().date().isoformat()
    return round(sum(float(r.get("cost_usd", 0)) for r in TenantScopedRepo(db, "cost_events", tenant_id)
                     .find({"day": day})), 6)


def admit(db: Database, *, tenant_id: str, brand_id: str) -> None:
    """Raise if the run must not start. Called before a run ID is assigned."""
    tenant = SystemRepo(db, "tenants", purpose="admission").find_one({"tenant_id": tenant_id})
    if tenant is None or not tenant.get("active", True):
        raise KillSwitchEngaged(f"tenant {tenant_id} is not active")
    scope = KillSwitches(db).engaged(tenant_id=tenant_id, brand_id=brand_id)
    if scope:
        raise KillSwitchEngaged(scope)
    if not run_limiter().allow(tenant_id):
        raise RateLimited(f"tenant {tenant_id} exceeded {get_settings().tenant_runs_per_minute} runs/minute")
    cap = get_settings().tenant_daily_cost_cap_usd
    spent = tenant_cost_today(db, tenant_id)
    if spent >= cap:
        raise RateLimited(f"tenant {tenant_id} reached its daily cost cap (${spent:.2f} of ${cap:.2f})")
    if spent >= 0.8 * cap:
        raise_alert(Severity.P3, "Tenant at 80% of daily AI cost cap", tenant_id=tenant_id,
                    details={"spent": spent, "cap": cap})
