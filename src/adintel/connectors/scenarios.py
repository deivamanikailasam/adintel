"""Synthetic ad-account worlds.

Each brand has campaigns → entities (ad sets / ad groups) with baseline economics, and optional events
relative to the *end* of the requested window ("the last 4 days"), so the demo reproduces the three
canonical brands on any date:

* ``urban-roast`` — Meta budget raised on the expensive "AS-B Retargeting Cold" ad set; Meta shifts
  spend there; campaign CPA ≈ +60% for 4 days. The ad set is fine; the allocation is wrong.
* ``fitely`` — clean; nothing above low severity. Its TikTok account reports in EUR.
* ``northpeak`` — conversions exactly zero for the last 6 days (since Tuesday) while clicks and spend
  look normal: broken tracking.
* ``cobalt-saas`` — B2B brand on LinkedIn + Google (covers the fifth platform).
* ``harbor-bikes`` — a second tenant's brand (a competitor) used by isolation tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adintel.domain.enums import Platform

FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.66}


@dataclass(frozen=True)
class EntitySpec:
    campaign_id: str
    campaign_name: str
    entity_id: str
    entity_name: str
    daily_budget: float  # account currency
    cpc: float
    ctr: float
    cvr: float
    aov: float


@dataclass(frozen=True)
class Event:
    kind: str  # spend_shift | zero_conversions | outage | schema_drift | cpc_inflation
    last_days: int = 0
    platform: Platform | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrandWorld:
    entities: dict[Platform, list[EntitySpec]]
    currency: dict[Platform, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    # current live budgets (USD) where they differ from the historical spec (e.g. after a change)
    live_budgets: dict[str, float] = field(default_factory=dict)


def _e(
    cid: str, cname: str, eid: str, ename: str, budget: float, cpc: float, ctr: float, cvr: float, aov: float
) -> EntitySpec:
    return EntitySpec(cid, cname, eid, ename, budget, cpc, ctr, cvr, aov)


WORLDS: dict[str, BrandWorld] = {
    "urban-roast": BrandWorld(
        entities={
            Platform.META: [
                _e(
                    "cmp_ur_meta_rt",
                    "Retargeting - Always On",
                    "as_ur_a",
                    "AS-A Retargeting Warm",
                    560,
                    1.10,
                    0.021,
                    0.075,
                    38.0,
                ),
                _e(
                    "cmp_ur_meta_rt",
                    "Retargeting - Always On",
                    "as_ur_b",
                    "AS-B Retargeting Cold",
                    240,
                    1.60,
                    0.012,
                    0.030,
                    36.0,
                ),
                _e(
                    "cmp_ur_meta_pro",
                    "Prospecting - Lookalike",
                    "as_ur_c",
                    "AS-C Lookalike 1%",
                    300,
                    1.35,
                    0.015,
                    0.040,
                    35.0,
                ),
            ],
            Platform.GOOGLE_ADS: [
                _e("cmp_ur_g_brand", "Brand Search", "ag_ur_1", "Brand - Exact", 150, 0.55, 0.12, 0.11, 34.0),
                _e(
                    "cmp_ur_g_shop",
                    "Shopping - Coffee Beans",
                    "ag_ur_2",
                    "Beans - All Products",
                    400,
                    0.80,
                    0.018,
                    0.045,
                    41.0,
                ),
            ],
        },
        events=[
            Event(
                "spend_shift",
                last_days=4,
                platform=Platform.META,
                params={
                    "campaign_id": "cmp_ur_meta_rt",
                    "to_entity": "as_ur_b",
                    "share": 0.75,
                    "total_multiplier": 1.10,
                },
            )
        ],
        live_budgets={"as_ur_a": 560.0, "as_ur_b": 800.0},
    ),
    "fitely": BrandWorld(
        entities={
            Platform.META: [
                _e(
                    "cmp_fi_meta_1",
                    "Spring Collection",
                    "as_fi_1",
                    "Women 25-44 Interests",
                    350,
                    0.95,
                    0.017,
                    0.032,
                    72.0,
                ),
            ],
            Platform.GOOGLE_ADS: [
                _e(
                    "cmp_fi_g_pmax", "PMax - Activewear", "ag_fi_1", "PMax Asset Group A", 500, 0.70, 0.022, 0.035, 68.0
                ),
            ],
            Platform.TIKTOK: [
                _e(
                    "cmp_fi_tt_1",
                    "Creator Spark Ads",
                    "adg_fi_1",
                    "Spark - Fitness Creators",
                    220,
                    0.45,
                    0.011,
                    0.018,
                    65.0,
                ),
            ],
        },
        currency={Platform.TIKTOK: "EUR"},
    ),
    "northpeak": BrandWorld(
        entities={
            Platform.META: [
                _e("cmp_np_meta_1", "Fall Hiking Gear", "as_np_1", "Hikers 30-55", 420, 1.05, 0.016, 0.030, 120.0),
            ],
            Platform.GOOGLE_ADS: [
                _e("cmp_np_g_1", "Search - Jackets", "ag_np_1", "Jackets - Phrase", 380, 1.20, 0.055, 0.040, 160.0),
            ],
            Platform.AMAZON_ADS: [
                _e("cmp_np_amz_1", "SP - Backpacks", "adg_np_1", "Backpacks Auto", 200, 0.85, 0.004, 0.090, 95.0),
            ],
        },
        events=[Event("zero_conversions", last_days=6)],
    ),
    "cobalt-saas": BrandWorld(
        entities={
            Platform.LINKEDIN: [
                _e("cg_co_1", "Demand Gen - IT Leaders", "li_co_1", "IT Directors NA", 300, 6.50, 0.006, 0.020, 900.0),
            ],
            Platform.GOOGLE_ADS: [
                _e(
                    "cmp_co_g_1",
                    "Search - Observability",
                    "ag_co_1",
                    "Observability - Exact",
                    250,
                    4.20,
                    0.045,
                    0.030,
                    900.0,
                ),
            ],
        },
    ),
    "harbor-bikes": BrandWorld(
        entities={
            Platform.META: [
                _e("cmp_hb_meta_1", "E-bike Launch", "as_hb_1", "Commuters 25-50", 500, 1.20, 0.014, 0.020, 1400.0),
            ],
        },
    ),
}


_EXTRA: dict[str, BrandWorld] = {}


def register_world(brand_id: str, world: BrandWorld) -> None:
    """Evals and tests register scenario variants (e.g. 40 golden E2E worlds)."""
    _EXTRA[brand_id] = world


def world_for(brand_id: str) -> BrandWorld:
    if brand_id in _EXTRA:
        return _EXTRA[brand_id]
    if brand_id in WORLDS:
        return WORLDS[brand_id]
    # a generic, clean world for any brand added through the API
    return BrandWorld(
        entities={
            Platform.GOOGLE_ADS: [
                _e(
                    f"cmp_{brand_id}_g",
                    "Search - Generic",
                    f"ag_{brand_id}_1",
                    "Generic - Broad",
                    200,
                    1.0,
                    0.03,
                    0.03,
                    60.0,
                )
            ]
        }
    )
