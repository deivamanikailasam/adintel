"""Brand constraints — pure code, applied *after* the model, and again at approval time.

A prompt-injected "increase all budgets by 500%" fails here (``max_single_change_pct`` = 25%) no matter
what the model said. Exposure and risk are computed here, never taken from model output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from adintel.core.hashing import sha256_obj
from adintel.domain.enums import ActionType, RiskLevel
from adintel.domain.models import BrandRules


def snapshot_hash(entities: dict[str, dict[str, Any]], ids: list[str]) -> str:
    """Hash of the live state of the entities a recommendation touches (budget, status, version)."""
    return sha256_obj(
        {
            i: {k: entities[i].get(k) for k in ("daily_budget", "status", "version")}
            for i in sorted(ids)
            if i in entities
        }
    )


def exposure_usd(action: ActionType, amount: float, entities: dict[str, dict[str, Any]], target: str) -> float:
    if action == ActionType.PAUSE_ENTITY:
        return round(float(entities.get(target, {}).get("daily_budget") or 0), 2)
    return round(abs(amount), 2)


def risk_for(action: ActionType, exposure: float) -> tuple[RiskLevel, bool]:
    irreversible = False
    if action == ActionType.PAUSE_ENTITY or exposure >= 2000:
        return RiskLevel.HIGH, irreversible
    if exposure >= 500:
        return RiskLevel.MEDIUM, irreversible
    return RiskLevel.LOW, irreversible


def in_blackout(rules: BrandRules, now: datetime) -> str | None:
    for w in rules.blackout_windows:
        if w.start <= now <= w.end:
            return w.reason
    return None


def check(
    *,
    action: ActionType,
    source: str | None,
    target: str,
    amount: float,
    rules: BrandRules,
    entities: dict[str, dict[str, Any]],
    citations: list[str],
    retrieved_ids: list[str],
    now: datetime,
) -> list[str]:
    """Return the list of violated constraints (empty = passes)."""
    v: list[str] = []
    if action not in rules.allowed_actions:
        v.append(f"action {action} is not allowed for this brand")
    ids = [i for i in (source, target) if i]
    for i in ids:
        if i not in entities:
            v.append(f"unknown entity {i}")
        elif entities[i].get("status") != "ACTIVE":
            v.append(f"entity {i} is not active")
        if i in rules.protected_entity_ids:
            v.append(f"entity {i} is protected")
    if action in (ActionType.BUDGET_SHIFT, ActionType.BUDGET_CHANGE) and amount == 0:
        v.append("amount must be non-zero")
    cap = rules.max_single_change_pct / 100
    if action == ActionType.BUDGET_SHIFT:
        if not source:
            v.append("budget_shift needs a source entity")
        elif source in entities:
            src_budget = float(entities[source].get("daily_budget") or 0)
            if amount < 0:
                v.append("shift amount must be positive")
            if amount > cap * src_budget + 0.005:
                v.append(
                    f"shift ${amount:.2f} exceeds max_single_change_pct "
                    f"{rules.max_single_change_pct:.0f}% of source budget ${src_budget:.2f}"
                )
            if src_budget - amount < rules.min_daily_budget_usd:
                v.append(f"source budget would fall below ${rules.min_daily_budget_usd:.2f}")
        if source == target:
            v.append("source and target must differ")
    if action == ActionType.BUDGET_CHANGE and target in entities:
        b = float(entities[target].get("daily_budget") or 0)
        if abs(amount) > cap * b + 0.005:
            v.append(
                f"change ${amount:.2f} exceeds max_single_change_pct {rules.max_single_change_pct:.0f}% "
                f"of budget ${b:.2f}"
            )
        if b + amount < rules.min_daily_budget_usd:
            v.append(f"budget would fall below ${rules.min_daily_budget_usd:.2f}")
    if not citations:
        v.append("at least one citation is required")
    unknown = [c for c in citations if c not in retrieved_ids]
    if unknown:
        v.append(f"citations not in retrieved evidence: {unknown}")
    reason = in_blackout(rules, now)
    if reason:
        v.append(f"blackout window active: {reason}")
    return v
