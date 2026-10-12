"""Seed catalogue + loader (``adintel seed``). Idempotent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adintel.connectors.scenarios import world_for
from adintel.core.clock import utcnow
from adintel.domain.enums import Platform, Role
from adintel.domain.models import Brand, BrandProfile, BrandRules, Tenant, User
from adintel.rag.indexer import index_document
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

KB = Path(__file__).parent / "kb"

TENANTS = [Tenant(tenant_id="brightwave", name="BrightWave Media"), Tenant(tenant_id="acme", name="Acme Agency")]

BRANDS = [
    (
        "brightwave",
        "urban-roast",
        "Urban Roast Coffee",
        "u_jordan",
        "warm",
        "coffee",
        "America/New_York",
        "Friendly, warm and practical; talks like a neighbourhood roaster.",
    ),
    (
        "brightwave",
        "fitely",
        "Fitely Activewear",
        "u_jordan",
        "energetic",
        "fitness",
        "America/Los_Angeles",
        "Energetic and encouraging; short sentences.",
    ),
    (
        "brightwave",
        "northpeak",
        "NorthPeak Outdoor",
        "u_priya",
        "neutral",
        "outdoor",
        "America/Denver",
        "Calm, factual, outdoorsy.",
    ),
    (
        "brightwave",
        "cobalt-saas",
        "Cobalt Observability",
        "u_priya",
        "formal",
        "b2b_saas",
        "America/Chicago",
        "Formal B2B tone; precise.",
    ),
    ("acme", "harbor-bikes", "Harbor Bikes", "u_acme_am", "neutral", "mobility", "Europe/London", ""),
]

USERS = [
    User(
        tenant_id="brightwave",
        user_id="u_jordan",
        email="jordan@brightwave.example",
        name="Jordan Lee",
        roles=[Role.ACCOUNT_MANAGER],
        approval_limit_usd=500,
        brand_ids=["urban-roast", "fitely"],
    ),
    User(
        tenant_id="brightwave",
        user_id="u_priya",
        email="priya@brightwave.example",
        name="Priya Shah",
        roles=[Role.ACCOUNT_MANAGER],
        approval_limit_usd=500,
        brand_ids=["northpeak", "cobalt-saas"],
    ),
    User(
        tenant_id="brightwave",
        user_id="u_sam",
        email="sam@brightwave.example",
        name="Sam Ortiz",
        roles=[Role.SENIOR_ACCOUNT_MANAGER],
        approval_limit_usd=2000,
    ),
    User(
        tenant_id="brightwave",
        user_id="u_hana",
        email="hana@brightwave.example",
        name="Hana Kim",
        roles=[Role.HEAD_OF_PERFORMANCE],
        approval_limit_usd=100000,
    ),
    User(
        tenant_id="brightwave",
        user_id="u_alex",
        email="alex@brightwave.example",
        name="Alex Rivera",
        roles=[Role.HEAD_OF_PERFORMANCE],
        approval_limit_usd=100000,
    ),
    User(
        tenant_id="brightwave",
        user_id="u_admin",
        email="admin@brightwave.example",
        name="Ali Admin",
        roles=[Role.ADMIN],
    ),
    User(
        tenant_id="brightwave",
        user_id="u_viewer",
        email="viewer@brightwave.example",
        name="Vic Viewer",
        roles=[Role.VIEWER],
    ),
    User(
        tenant_id="acme",
        user_id="u_acme_am",
        email="am@acme.example",
        name="Acme AM",
        roles=[Role.ACCOUNT_MANAGER],
        approval_limit_usd=500,
    ),
]

KB_DOCS: list[dict[str, Any]] = [
    {"tenant": "brightwave", "file": "playbook-budget-reallocation.md", "type": "playbook", "brand": "*"},
    {"tenant": "brightwave", "file": "playbook-cpa-inflation-diagnosis.md", "type": "playbook", "brand": "*"},
    {"tenant": "brightwave", "file": "playbook-broken-tracking.md", "type": "playbook", "brand": "*"},
    {"tenant": "brightwave", "file": "guideline-brightwave-reporting.md", "type": "guideline", "brand": "*"},
    {
        "tenant": "brightwave",
        "file": "incident-urban-roast-2026-03.md",
        "type": "incident",
        "brand": "urban-roast",
        "vertical": "coffee",
    },
    {
        "tenant": "brightwave",
        "file": "incident-coffee-vertical-allocation.md",
        "type": "incident",
        "brand": "bean-bros",
        "vertical": "coffee",
        "anonymise": ["Bean Bros Coffee", "Bean Bros"],
    },
    {"tenant": "brightwave", "file": "platform-meta-delivery.md", "type": "platform_doc", "brand": "*"},
    {"tenant": "brightwave", "file": "platform-google-ads-notes.md", "type": "platform_doc", "brand": "*"},
    {"tenant": "brightwave", "file": "guideline-fitely-tone.md", "type": "guideline", "brand": "fitely"},
    {"tenant": "acme", "file": "acme-playbook-confidential.md", "type": "playbook", "brand": "*"},
]


def seed(db: Database, *, with_kb: bool = True) -> dict[str, int]:
    tenants = SystemRepo(db, "tenants", purpose="seed")
    for t in TENANTS:
        tenants.update_one({"tenant_id": t.tenant_id}, {"$set": t.model_dump(mode="json")}, upsert=True)
    for tenant_id, brand_id, name, am, tone, vertical, tz, voice in BRANDS:
        b = Brand(
            tenant_id=tenant_id,
            brand_id=brand_id,
            name=name,
            platforms=sorted(world_for(brand_id).entities, key=str),
            assigned_am=am,
            profile=BrandProfile(tone_cluster=tone, vertical=vertical, timezone=tz, voice_notes=voice),
        )
        TenantScopedRepo(db, "brands", tenant_id).update_one(
            {"brand_id": brand_id}, {"$set": b.model_dump(mode="json")}, upsert=True
        )
        rules = BrandRules(tenant_id=tenant_id, brand_id=brand_id)
        TenantScopedRepo(db, "brand_rules", tenant_id).update_one(
            {"brand_id": brand_id}, {"$setOnInsert": rules.model_dump(mode="json")}, upsert=True
        )
        for p in b.platforms:
            TenantScopedRepo(db, "platform_connections", tenant_id).update_one(
                {"brand_id": brand_id, "platform": str(p)},
                {
                    "$set": {
                        "brand_id": brand_id,
                        "platform": str(p),
                        "account_ref": f"acct_{brand_id}_{p}",
                        "read_secret_ref": f"adintel/{tenant_id}/{p}/read",
                        "write_secret_ref": f"adintel/{tenant_id}/{p}/write",
                    }
                },
                upsert=True,
            )
    for u in USERS:
        TenantScopedRepo(db, "users", u.tenant_id).update_one(
            {"user_id": u.user_id}, {"$set": u.model_dump(mode="json")}, upsert=True
        )
    chunks = 0
    if with_kb:
        for d in KB_DOCS:
            text = (KB / d["file"]).read_text()
            title = text.splitlines()[0].lstrip("# ").strip()
            chunks += len(
                index_document(
                    db,
                    d["tenant"],
                    doc_id=f"kb:{d['file']}",
                    title=title,
                    text=text,
                    doc_type=d["type"],
                    brand_id=d["brand"],
                    vertical=d.get("vertical", "general"),
                    source="seed",
                    anonymise_names=d.get("anonymise"),
                )
            )
    return {
        "tenants": len(TENANTS),
        "brands": len(BRANDS),
        "users": len(USERS),
        "kb_chunks": chunks,
        "seeded_at": int(utcnow().timestamp()),
    }


__all__ = ["Platform", "seed"]
