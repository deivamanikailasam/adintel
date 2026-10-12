"""Deterministic synthetic ad platforms (ADR L-10).

Raw payloads use each platform's **native field shapes** (micros, string numbers, nested action arrays,
URNs, compact dates) so the normaliser exercised here is the same code used with live connectors.
Failure injection (outages, slow responses, schema drift) is driven by scenario events or by
``inject_failure`` in tests.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import date, timedelta
from typing import Any

import numpy as np

from adintel.connectors.base import PlatformConnector, RawFetch
from adintel.connectors.scenarios import FX_TO_USD, BrandWorld, EntitySpec, world_for
from adintel.core.errors import AuthError, PlatformUnavailable
from adintel.domain.enums import Platform
from adintel.security.secrets import Credential

WEEKDAY = [1.05, 1.00, 1.00, 1.02, 1.08, 0.90, 0.85]  # Mon..Sun

_failures: dict[tuple[str, Platform], str] = {}
_live_state: dict[tuple[str, str], dict[str, Any]] = {}
_lock = threading.Lock()


def inject_failure(brand_id: str, platform: Platform, kind: str | None) -> None:
    """kind: 'outage' | 'slow' | 'schema_drift' | None (clear)."""
    with _lock:
        if kind is None:
            _failures.pop((brand_id, platform), None)
        else:
            _failures[(brand_id, platform)] = kind


def reset_world() -> None:
    with _lock:
        _failures.clear()
        _live_state.clear()


def _rng(*parts: object) -> np.random.Generator:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16)
    return np.random.default_rng(seed)


def simulate_day(world: BrandWorld, platform: Platform, spec: EntitySpec, day: date, anchor: date,
                 brand_id: str) -> dict[str, float]:
    """Return USD-agnostic daily metrics for one entity (account currency)."""
    rng = _rng(brand_id, spec.entity_id, day.isoformat())
    days_from_end = (anchor - day).days
    trend = 1.0 + 0.0004 * (180 - min(days_from_end, 180))  # gentle growth
    spend = spec.daily_budget * 0.94 * WEEKDAY[day.weekday()] * trend * float(rng.lognormal(0, 0.06))
    cpc = spec.cpc * float(rng.lognormal(0, 0.04))
    ctr = spec.ctr * float(rng.lognormal(0, 0.04))
    cvr = spec.cvr
    for ev in world.events:
        if ev.platform not in (None, platform) or days_from_end >= ev.last_days or days_from_end < 0:
            continue
        if ev.kind == "spend_shift" and ev.params["campaign_id"] == spec.campaign_id:
            siblings = [e for e in world.entities[platform] if e.campaign_id == spec.campaign_id]
            base_total = sum(e.daily_budget for e in siblings) * 0.94 * WEEKDAY[day.weekday()] * trend
            new_total = base_total * float(ev.params.get("total_multiplier", 1.0))
            share = float(ev.params["share"])
            if spec.entity_id == ev.params["to_entity"]:
                spend = new_total * share * float(rng.lognormal(0, 0.03))
            else:
                others = sum(e.daily_budget for e in siblings if e.entity_id != ev.params["to_entity"])
                spend = new_total * (1 - share) * (spec.daily_budget / others) * float(rng.lognormal(0, 0.03))
        if ev.kind == "cpc_inflation":
            cpc *= float(ev.params.get("factor", 1.3))
    clicks = max(0, round(spend / cpc))
    impressions = max(clicks, round(clicks / max(ctr, 1e-4)))
    conversions = float(rng.poisson(max(0.0, clicks * cvr)))
    for ev in world.events:
        if ev.kind == "zero_conversions" and 0 <= days_from_end < ev.last_days:
            conversions = 0.0
    revenue = round(conversions * spec.aov * float(rng.lognormal(0, 0.05)), 2)
    return {"impressions": impressions, "clicks": clicks, "spend": round(spend, 2), "conversions": conversions,
            "revenue": revenue}


def _raw_row(platform: Platform, spec: EntitySpec, day: date, m: dict[str, float]) -> dict[str, Any]:
    if platform == Platform.GOOGLE_ADS:
        return {"segments.date": day.isoformat(), "campaign.id": spec.campaign_id, "campaign.name": spec.campaign_name,
                "ad_group.id": spec.entity_id, "ad_group.name": spec.entity_name,
                "metrics.impressions": int(m["impressions"]), "metrics.clicks": int(m["clicks"]),
                "metrics.cost_micros": int(round(m["spend"] * 1_000_000)), "metrics.conversions": m["conversions"],
                "metrics.conversions_value": m["revenue"],
                "campaign_budget.amount_micros": int(spec.daily_budget * 1_000_000)}
    if platform == Platform.META:
        return {"date_start": day.isoformat(), "date_stop": day.isoformat(), "campaign_id": spec.campaign_id,
                "campaign_name": spec.campaign_name, "adset_id": spec.entity_id, "adset_name": spec.entity_name,
                "impressions": str(int(m["impressions"])), "clicks": str(int(m["clicks"])), "spend": f"{m['spend']:.2f}",
                "actions": [{"action_type": "link_click", "value": str(int(m["clicks"]))},
                            {"action_type": "purchase", "value": str(int(m["conversions"]))}],
                "action_values": [{"action_type": "purchase", "value": f"{m['revenue']:.2f}"}],
                "daily_budget": str(int(spec.daily_budget * 100))}
    if platform == Platform.TIKTOK:
        return {"stat_time_day": f"{day.isoformat()} 00:00:00", "campaign_id": spec.campaign_id,
                "campaign_name": spec.campaign_name, "adgroup_id": spec.entity_id, "adgroup_name": spec.entity_name,
                "impressions": str(int(m["impressions"])), "clicks": str(int(m["clicks"])), "spend": f"{m['spend']:.2f}",
                "conversion": str(int(m["conversions"])), "total_complete_payment_rate": "0",
                "complete_payment_roas": "0", "total_purchase_value": f"{m['revenue']:.2f}",
                "budget": f"{spec.daily_budget:.2f}"}
    if platform == Platform.LINKEDIN:
        return {"dateRange": {"start": {"year": day.year, "month": day.month, "day": day.day}},
                "pivotValues": [f"urn:li:sponsoredCampaign:{spec.entity_id}"], "campaignName": spec.entity_name,
                "campaignGroup": f"urn:li:sponsoredCampaignGroup:{spec.campaign_id}",
                "campaignGroupName": spec.campaign_name, "impressions": int(m["impressions"]),
                "clicks": int(m["clicks"]), "costInLocalCurrency": f"{m['spend']:.2f}",
                "externalWebsiteConversions": int(m["conversions"]),
                "conversionValueInLocalCurrency": f"{m['revenue']:.2f}",
                "dailyBudget": {"amount": f"{spec.daily_budget:.2f}", "currencyCode": "USD"}}
    if platform == Platform.AMAZON_ADS:
        return {"date": day.strftime("%Y%m%d"), "campaignId": spec.campaign_id, "campaignName": spec.campaign_name,
                "adGroupId": spec.entity_id, "adGroupName": spec.entity_name, "impressions": int(m["impressions"]),
                "clicks": int(m["clicks"]), "cost": round(m["spend"], 2), "purchases14d": int(m["conversions"]),
                "sales14d": m["revenue"], "campaignBudgetAmount": spec.daily_budget}
    raise ValueError(platform)


class SyntheticConnector(PlatformConnector):
    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def _check_failure(self, brand_id: str) -> str | None:
        kind = _failures.get((brand_id, self.platform))
        if kind == "outage":
            raise PlatformUnavailable(f"{self.platform}: HTTP 503 Service Unavailable (synthetic)")
        if kind == "slow":
            time.sleep(30)
        return kind

    def fetch(self, cred: Credential, brand_id: str, start: date, end: date) -> RawFetch:
        if cred.scope not in ("read", "write"):
            raise AuthError("invalid credential scope")
        kind = self._check_failure(brand_id)
        world = world_for(brand_id)
        specs = world.entities.get(self.platform, [])
        rows: list[dict[str, Any]] = []
        day = start
        while day <= end:
            for spec in specs:
                row = _raw_row(self.platform, spec, day, simulate_day(world, self.platform, spec, day, end, brand_id))
                if kind == "schema_drift":
                    row["metrics.engaged_view_conversions" if self.platform == Platform.GOOGLE_ADS
                        else "new_metric_v2"] = 1
                rows.append(row)
            day += timedelta(days=1)
        return RawFetch(platform=self.platform, rows=rows, account_currency=world.currency.get(self.platform, "USD"),
                        api_version="synthetic-1")

    def _state(self, brand_id: str, entity_id: str) -> dict[str, Any]:
        with _lock:
            key = (brand_id, entity_id)
            if key not in _live_state:
                world = world_for(brand_id)
                spec = next((s for s in world.entities.get(self.platform, []) if s.entity_id == entity_id), None)
                if spec is None:
                    raise PlatformUnavailable(f"{self.platform}: entity {entity_id} not found (HTTP 404)")
                fx = FX_TO_USD[world.currency.get(self.platform, "USD")]
                budget = world.live_budgets.get(entity_id, spec.daily_budget * fx)
                _live_state[key] = {"entity_id": entity_id, "name": spec.entity_name, "campaign_id": spec.campaign_id,
                                    "daily_budget": round(budget, 2), "status": "ACTIVE", "version": 1}
            return dict(_live_state[key])

    def get_entity(self, cred: Credential, brand_id: str, entity_id: str) -> dict[str, Any]:
        self._check_failure(brand_id)
        return self._state(brand_id, entity_id)

    def apply_change(self, cred: Credential, brand_id: str, change: dict[str, Any]) -> dict[str, Any]:
        if cred.scope != "write":
            raise AuthError("apply_change requires a write-scope credential")
        self._check_failure(brand_id)
        entity_id = change["entity_id"]
        state = self._state(brand_id, entity_id)
        with _lock:
            st = _live_state[(brand_id, entity_id)]
            if change["op"] == "set_daily_budget":
                st["daily_budget"] = round(float(change["daily_budget"]), 2)
            elif change["op"] == "pause":
                st["status"] = "PAUSED"
            else:
                raise ValueError(f"unsupported op {change['op']}")
            st["version"] = state["version"] + 1
            return {"ok": True, "entity_id": entity_id, "new_state": dict(st),
                    "request_id": hashlib.sha256(repr(change).encode()).hexdigest()[:16]}
