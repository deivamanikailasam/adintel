"""Number tables are never embedded: a vector of 90 daily CPA values means almost nothing. A nightly
job turns each campaign period into a short sentence, and that sentence is embedded instead."""

from __future__ import annotations

from datetime import date
from typing import Any


def campaign_narrative(
    *,
    brand_name: str,
    platform: str,
    campaign_name: str,
    start: date,
    end: date,
    cur: dict[str, Any],
    prev: dict[str, Any],
) -> str:
    def fmt(v: Any, money: bool = False) -> str:
        if v is None:
            return "n/a"
        return f"${v:,.2f}" if money else f"{v:,}"

    direction = "flat"
    if cur.get("cpa") and prev.get("cpa"):
        change = (cur["cpa"] - prev["cpa"]) / prev["cpa"]
        direction = "rising" if change > 0.1 else "falling" if change < -0.1 else "stable"
    return (
        f"{brand_name} {platform} campaign '{campaign_name}' from {start:%b %d} to {end:%b %d}: spend "
        f"{fmt(cur.get('spend'), True)}, {fmt(cur.get('conversions'))} conversions, CPA "
        f"{fmt(cur.get('cpa'), True)} ({direction} versus the prior period), ROAS {fmt(cur.get('roas'))}."
    )
