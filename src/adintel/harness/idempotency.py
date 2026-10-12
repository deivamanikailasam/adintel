"""Idempotency keys. Schedulers deliver at least once and people double-click: a duplicate trigger
must map to the existing run instead of double-charging (enforced by a unique index on ``runs``)."""

from __future__ import annotations

from datetime import date

from adintel.core.hashing import sha256_obj


def run_idempotency_key(*, tenant_id: str, brand_id: str, period_start: date, period_end: date, goal: str,
                        schedule_date: date | str) -> str:
    return sha256_obj({"tenant_id": tenant_id, "brand_id": brand_id, "period_start": period_start,
                       "period_end": period_end, "goal": goal, "schedule_date": str(schedule_date)})
