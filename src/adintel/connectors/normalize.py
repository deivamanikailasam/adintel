"""Deterministic normalisation of native platform payloads into ``MetricRow`` (USD).

Unknown fields are not guessed at: they are reported as ``unmapped_fields`` (schema drift), the small
model may *propose* a mapping for review, and an engineer implements it here with a fixture and a
contract test (runbook: ad-platform schema drift).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from adintel.connectors.base import RawFetch
from adintel.connectors.scenarios import FX_TO_USD
from adintel.domain.enums import Platform
from adintel.domain.models import MetricRow

KNOWN_FIELDS: dict[Platform, set[str]] = {
    Platform.GOOGLE_ADS: {
        "segments.date",
        "campaign.id",
        "campaign.name",
        "ad_group.id",
        "ad_group.name",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.conversions_value",
        "campaign_budget.amount_micros",
    },
    Platform.META: {
        "date_start",
        "date_stop",
        "campaign_id",
        "campaign_name",
        "adset_id",
        "adset_name",
        "impressions",
        "clicks",
        "spend",
        "actions",
        "action_values",
        "daily_budget",
    },
    Platform.TIKTOK: {
        "stat_time_day",
        "campaign_id",
        "campaign_name",
        "adgroup_id",
        "adgroup_name",
        "impressions",
        "clicks",
        "spend",
        "conversion",
        "total_complete_payment_rate",
        "complete_payment_roas",
        "total_purchase_value",
        "budget",
    },
    Platform.LINKEDIN: {
        "dateRange",
        "pivotValues",
        "campaignName",
        "campaignGroup",
        "campaignGroupName",
        "impressions",
        "clicks",
        "costInLocalCurrency",
        "externalWebsiteConversions",
        "conversionValueInLocalCurrency",
        "dailyBudget",
    },
    Platform.AMAZON_ADS: {
        "date",
        "campaignId",
        "campaignName",
        "adGroupId",
        "adGroupName",
        "impressions",
        "clicks",
        "cost",
        "purchases14d",
        "sales14d",
        "campaignBudgetAmount",
    },
}


CANONICAL_FORMAT = "adintel-csv/1"
CANONICAL_FIELDS = {
    "date",
    "campaign_id",
    "campaign_name",
    "entity_id",
    "entity_name",
    "entity_type",
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "revenue",
    "daily_budget",
    "currency",
}


def _canonical_row(r: dict[str, Any]) -> dict[str, Any]:
    """One row of the bring-your-own-data CSV template (amounts in the account currency, not micros)."""
    budget = (r.get("daily_budget") or "").strip() if isinstance(r.get("daily_budget"), str) else r.get("daily_budget")
    return dict(
        date=date.fromisoformat(str(r["date"]).strip()),
        campaign_id=str(r["campaign_id"]).strip(),
        campaign_name=str(r["campaign_name"]).strip(),
        entity_id=str(r["entity_id"]).strip(),
        entity_name=str(r["entity_name"]).strip(),
        entity_type=(str(r.get("entity_type") or "").strip() or "ad_set"),
        impressions=int(float(r["impressions"])),
        clicks=int(float(r["clicks"])),
        spend=float(r["spend"]),
        conversions=float(r["conversions"]),
        revenue=float(r.get("revenue") or 0),
        daily_budget=float(budget) if budget not in (None, "") else None,
    )


def _action(items: list[dict[str, Any]] | None, kind: str) -> float:
    for a in items or []:
        if a.get("action_type") == kind:
            return float(a.get("value", 0))
    return 0.0


def _row(platform: Platform, r: dict[str, Any]) -> dict[str, Any]:
    if platform == Platform.GOOGLE_ADS:
        return dict(
            date=date.fromisoformat(r["segments.date"]),
            campaign_id=str(r["campaign.id"]),
            campaign_name=r["campaign.name"],
            entity_id=str(r["ad_group.id"]),
            entity_name=r["ad_group.name"],
            entity_type="ad_group",
            impressions=int(r["metrics.impressions"]),
            clicks=int(r["metrics.clicks"]),
            spend=int(r["metrics.cost_micros"]) / 1_000_000,
            conversions=float(r["metrics.conversions"]),
            revenue=float(r["metrics.conversions_value"]),
            daily_budget=int(r.get("campaign_budget.amount_micros", 0)) / 1_000_000 or None,
        )
    if platform == Platform.META:
        return dict(
            date=date.fromisoformat(r["date_start"]),
            campaign_id=r["campaign_id"],
            campaign_name=r["campaign_name"],
            entity_id=r["adset_id"],
            entity_name=r["adset_name"],
            entity_type="ad_set",
            impressions=int(r["impressions"]),
            clicks=int(r["clicks"]),
            spend=float(r["spend"]),
            conversions=_action(r.get("actions"), "purchase"),
            revenue=_action(r.get("action_values"), "purchase"),
            daily_budget=int(r["daily_budget"]) / 100 if r.get("daily_budget") else None,
        )
    if platform == Platform.TIKTOK:
        return dict(
            date=datetime.strptime(r["stat_time_day"], "%Y-%m-%d %H:%M:%S").date(),
            campaign_id=r["campaign_id"],
            campaign_name=r["campaign_name"],
            entity_id=r["adgroup_id"],
            entity_name=r["adgroup_name"],
            entity_type="ad_group",
            impressions=int(r["impressions"]),
            clicks=int(r["clicks"]),
            spend=float(r["spend"]),
            conversions=float(r["conversion"]),
            revenue=float(r["total_purchase_value"]),
            daily_budget=float(r["budget"]) if r.get("budget") else None,
        )
    if platform == Platform.LINKEDIN:
        d = r["dateRange"]["start"]
        return dict(
            date=date(d["year"], d["month"], d["day"]),
            campaign_id=r["campaignGroup"].rsplit(":", 1)[-1],
            campaign_name=r["campaignGroupName"],
            entity_id=r["pivotValues"][0].rsplit(":", 1)[-1],
            entity_name=r["campaignName"],
            entity_type="campaign",
            impressions=int(r["impressions"]),
            clicks=int(r["clicks"]),
            spend=float(r["costInLocalCurrency"]),
            conversions=float(r["externalWebsiteConversions"]),
            revenue=float(r["conversionValueInLocalCurrency"]),
            daily_budget=float(r["dailyBudget"]["amount"]) if r.get("dailyBudget") else None,
        )
    if platform == Platform.AMAZON_ADS:
        return dict(
            date=datetime.strptime(r["date"], "%Y%m%d").date(),
            campaign_id=r["campaignId"],
            campaign_name=r["campaignName"],
            entity_id=r["adGroupId"],
            entity_name=r["adGroupName"],
            entity_type="ad_group",
            impressions=int(r["impressions"]),
            clicks=int(r["clicks"]),
            spend=float(r["cost"]),
            conversions=float(r["purchases14d"]),
            revenue=float(r["sales14d"]),
            daily_budget=float(r["campaignBudgetAmount"]) if r.get("campaignBudgetAmount") else None,
        )
    raise ValueError(platform)


def normalise(fetch: RawFetch, *, tenant_id: str, brand_id: str) -> tuple[list[MetricRow], list[str]]:
    fx = FX_TO_USD.get(fetch.account_currency)
    if fx is None:
        raise ValueError(f"no FX rate for {fetch.account_currency}")
    canonical = fetch.api_version == CANONICAL_FORMAT
    known = CANONICAL_FIELDS if canonical else KNOWN_FIELDS[fetch.platform]
    unmapped: set[str] = set()
    out: list[MetricRow] = []
    for raw in fetch.rows:
        unmapped |= set(raw) - known
        r = _canonical_row(raw) if canonical else _row(fetch.platform, raw)
        out.append(
            MetricRow(
                tenant_id=tenant_id,
                brand_id=brand_id,
                platform=fetch.platform,
                date=r["date"],
                campaign_id=r["campaign_id"],
                campaign_name=r["campaign_name"],
                entity_id=r["entity_id"],
                entity_name=r["entity_name"],
                entity_type=r["entity_type"],
                impressions=r["impressions"],
                clicks=r["clicks"],
                spend=round(r["spend"] * fx, 2),
                conversions=r["conversions"],
                revenue=round(r["revenue"] * fx, 2),
                daily_budget=round(r["daily_budget"] * fx, 2) if r["daily_budget"] else None,
                currency_original=fetch.account_currency,
            )
        )
    return out, sorted(unmapped)
