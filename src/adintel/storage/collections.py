"""Collection catalogue: names, indexes and retention. Every index leads with ``tenant_id``."""

from __future__ import annotations

from dataclasses import dataclass, field

from adintel.storage.base import Database

DAY = 86_400


@dataclass(frozen=True)
class IndexSpec:
    keys: tuple[tuple[str, int], ...]
    unique: bool = False
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    tenant_scoped: bool
    purpose: str
    retention: str
    indexes: tuple[IndexSpec, ...] = field(default_factory=tuple)


T = ("tenant_id", 1)

CATALOGUE: tuple[CollectionSpec, ...] = (
    CollectionSpec("tenants", False, "Agencies", "indefinite", (IndexSpec((T,), unique=True),)),
    CollectionSpec("brands", True, "Client brands", "indefinite", (IndexSpec((T, ("brand_id", 1)), unique=True),)),
    CollectionSpec(
        "users",
        True,
        "People, roles, approval limits",
        "indefinite",
        (IndexSpec((T, ("user_id", 1)), unique=True), IndexSpec((("email", 1),), unique=True)),
    ),
    CollectionSpec(
        "metrics_daily",
        True,
        "Normalised daily rows (time series)",
        "25 months",
        (
            IndexSpec((T, ("brand_id", 1), ("date", 1))),
            IndexSpec((T, ("brand_id", 1), ("platform", 1), ("entity_id", 1), ("date", 1)), unique=True),
        ),
    ),
    CollectionSpec(
        "metrics_rollups",
        True,
        "Pre-computed daily rollups",
        "25 months",
        (IndexSpec((T, ("brand_id", 1), ("date", 1)), unique=True),),
    ),
    CollectionSpec(
        "runs",
        True,
        "Run records",
        "24 months",
        (IndexSpec((T, ("idempotency_key", 1)), unique=True), IndexSpec((T, ("brand_id", 1), ("created_at", -1)))),
    ),
    CollectionSpec(
        "run_checkpoints",
        True,
        "RunState after every step",
        "30 days",
        (IndexSpec((T, ("run_id", 1), ("step", 1)), unique=True), IndexSpec((("expire_at", 1),), ttl_seconds=0)),
    ),
    CollectionSpec(
        "run_events",
        True,
        "Progress events streamed to the UI (SSE)",
        "30 days",
        (IndexSpec((T, ("run_id", 1), ("seq", 1))),),
    ),
    CollectionSpec(
        "run_history",
        True,
        "Episodic memory: anomalies, actions, outcomes",
        "24 months",
        (IndexSpec((T, ("brand_id", 1), ("created_at", -1))),),
    ),
    CollectionSpec(
        "anomalies",
        True,
        "Detected anomalies and lifecycle",
        "24 months",
        (IndexSpec((T, ("brand_id", 1), ("status", 1))), IndexSpec((T, ("anomaly_id", 1)), unique=True)),
    ),
    CollectionSpec(
        "recommendations",
        True,
        "Proposed actions and approval state",
        "24 months",
        (IndexSpec((T, ("recommendation_id", 1)), unique=True), IndexSpec((T, ("status", 1), ("expires_at", 1)))),
    ),
    CollectionSpec(
        "approvals", True, "Signed approval records", "7 years", (IndexSpec((T, ("recommendation_id", 1))),)
    ),
    CollectionSpec(
        "executions",
        True,
        "Platform writes actually made",
        "7 years",
        (IndexSpec((T, ("recommendation_id", 1)), unique=True),),
    ),
    CollectionSpec(
        "reports", True, "Generated reports", "24 months", (IndexSpec((T, ("brand_id", 1), ("created_at", -1))),)
    ),
    CollectionSpec(
        "audit_log", True, "Append-only hash-chained audit", "7 years", (IndexSpec((T, ("seq", 1)), unique=True),)
    ),
    CollectionSpec(
        "llm_calls",
        True,
        "One record per model call",
        "13 months",
        (IndexSpec((T, ("run_id", 1))), IndexSpec((("expire_at", 1),), ttl_seconds=0)),
    ),
    CollectionSpec(
        "prompt_archive",
        True,
        "Full prompts and responses by hash",
        "13 months",
        (IndexSpec((T, ("sha256", 1)), unique=True), IndexSpec((("expire_at", 1),), ttl_seconds=0)),
    ),
    CollectionSpec("cost_events", True, "Cost per tenant, brand, agent", "25 months", (IndexSpec((T, ("day", 1))),)),
    CollectionSpec(
        "brand_rules",
        True,
        "Constraints + procedural memory",
        "indefinite",
        (IndexSpec((T, ("brand_id", 1)), unique=True),),
    ),
    CollectionSpec(
        "rule_proposals",
        True,
        "Suppression rules awaiting approval",
        "indefinite",
        (IndexSpec((T, ("brand_id", 1), ("status", 1))),),
    ),
    CollectionSpec(
        "platform_connections",
        True,
        "Ad-account links (secret refs only)",
        "indefinite",
        (IndexSpec((T, ("brand_id", 1), ("platform", 1)), unique=True),),
    ),
    CollectionSpec(
        "kb_chunks",
        True,
        "RAG knowledge base",
        "indefinite, versioned",
        (
            IndexSpec((T, ("brand_id", 1), ("doc_type", 1), ("is_active", 1))),
            IndexSpec((T, ("chunk_id", 1)), unique=True),
        ),
    ),
    CollectionSpec(
        "chat_sessions",
        True,
        "Conversational memory",
        "90 days",
        (IndexSpec((T, ("session_id", 1)), unique=True), IndexSpec((("expire_at", 1),), ttl_seconds=0)),
    ),
    CollectionSpec(
        "kill_switches",
        False,
        "Global/tenant/brand/agent switches",
        "indefinite",
        (IndexSpec((("scope", 1), ("key", 1)), unique=True),),
    ),
    CollectionSpec(
        "notifications", True, "Alerts and approval-queue notices", "90 days", (IndexSpec((T, ("created_at", -1))),)
    ),
    CollectionSpec(
        "feedback",
        True,
        "Ratings, rejections, modifications (flywheel)",
        "24 months",
        (IndexSpec((T, ("kind", 1), ("created_at", -1))),),
    ),
    CollectionSpec("eval_datasets", False, "Golden scenarios", "versioned", ()),
    CollectionSpec("secret_access_log", False, "Who read which secret reference", "13 months", ()),
)

BY_NAME = {c.name: c for c in CATALOGUE}


def ensure_indexes(db: Database) -> None:
    for spec in CATALOGUE:
        coll = db.collection(spec.name)
        for ix in spec.indexes:
            coll.create_index(ix.keys, unique=ix.unique, ttl_seconds=ix.ttl_seconds)
