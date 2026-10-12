"""Scenario worlds for the agent and E2E eval suites (registered as synthetic brands)."""

from __future__ import annotations

from typing import Any

from adintel.connectors.scenarios import BrandWorld, EntitySpec, Event, register_world
from adintel.domain.enums import Platform
from adintel.domain.models import Brand, BrandProfile, BrandRules
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

TENANT = "brightwave"


def make_world(spec: dict[str, Any]) -> BrandWorld:
    meta = [
        EntitySpec("cmp_x_rt", "Retargeting", "as_x_a", "AS-A Warm", 560, 1.10, 0.021, 0.075, 38.0),
        EntitySpec("cmp_x_rt", "Retargeting", "as_x_b", "AS-B Cold", 240, 1.60, 0.012, 0.030, 36.0),
    ]
    google = [EntitySpec("cmp_x_g", "Search", "ag_x_1", "Search - Exact", 300, 0.9, 0.05, 0.06, 40.0)]
    entities: dict[Platform, list[EntitySpec]] = {Platform.META: meta, Platform.GOOGLE_ADS: google}
    events: list[Event] = []
    live: dict[str, float] = {}
    kind = spec.get("kind", "clean")
    if kind == "spend_shift":
        events.append(
            Event(
                "spend_shift",
                last_days=spec.get("days", 4),
                platform=Platform.META,
                params={
                    "campaign_id": "cmp_x_rt",
                    "to_entity": "as_x_b",
                    "share": spec.get("share", 0.75),
                    "total_multiplier": 1.1,
                },
            )
        )
        live = {"as_x_a": 560.0, "as_x_b": 800.0}
    elif kind == "cpc_inflation":
        events.append(
            Event(
                "cpc_inflation",
                last_days=spec.get("days", 4),
                platform=Platform.META,
                params={"factor": spec.get("factor", 1.6)},
            )
        )
    elif kind == "zero_conversions":
        events.append(Event("zero_conversions", last_days=spec.get("days", 6)))
    if spec.get("outage"):
        entities[Platform.TIKTOK] = [EntitySpec("cmp_x_tt", "Spark", "adg_x_1", "Spark", 150, 0.5, 0.01, 0.02, 60.0)]
    return BrandWorld(entities=entities, events=events, live_budgets=live)


def install(db: Database, brand_id: str, spec: dict[str, Any]) -> list[str]:
    world = make_world(spec)
    register_world(brand_id, world)
    b = Brand(
        tenant_id=TENANT,
        brand_id=brand_id,
        name=f"Eval {brand_id}",
        platforms=sorted(world.entities, key=str),
        assigned_am="u_jordan",
        profile=BrandProfile(vertical="coffee", tone_cluster="warm"),
    )
    TenantScopedRepo(db, "brands", TENANT).update_one(
        {"brand_id": brand_id}, {"$set": b.model_dump(mode="json")}, upsert=True
    )
    TenantScopedRepo(db, "brand_rules", TENANT).update_one(
        {"brand_id": brand_id},
        {"$setOnInsert": BrandRules(tenant_id=TENANT, brand_id=brand_id).model_dump(mode="json")},
        upsert=True,
    )
    return [str(p) for p in b.platforms]
