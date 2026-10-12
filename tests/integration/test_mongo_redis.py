"""Integration tests against real services from `make up`. Run with: pytest -m integration"""

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

MONGO = os.environ.get("ADINTEL_MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
REDIS = os.environ.get("ADINTEL_REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def mongo():
    from adintel.storage.collections import ensure_indexes
    from adintel.storage.mongo import MongoDatabase

    db = MongoDatabase(MONGO, f"adintel_it_{uuid.uuid4().hex[:8]}", "auto")
    if not db.ping():
        pytest.skip("MongoDB not reachable")
    ensure_indexes(db)
    yield db
    db._client.drop_database(db._db.name)


def test_tenant_repo_and_unique_index_on_real_mongo(mongo):
    from adintel.core.errors import TenantIsolationViolation
    from adintel.storage import DuplicateKey, TenantScopedRepo

    runs = TenantScopedRepo(mongo, "runs", "t1")
    runs.insert({"run_id": "r1", "idempotency_key": "k"})
    with pytest.raises(DuplicateKey):
        runs.insert({"run_id": "r2", "idempotency_key": "k"})
    with pytest.raises(TenantIsolationViolation):
        runs.find({"tenant_id": "t2"})


def test_vector_search_prefilter_on_atlas_local(mongo):
    from adintel.rag.indexer import index_document
    from adintel.rag.retriever import Retriever, clear_cache

    clear_cache()
    mongo.ensure_vector_index(
        "kb_chunks", 384, ["tenant_id", "brand_id", "doc_type", "is_active", "vertical", "anonymised", "date"]
    )
    index_document(mongo, "t1", doc_id="d1", title="Playbook", text="## A\nbudget reallocation", doc_type="playbook")
    index_document(mongo, "t2", doc_id="d2", title="Other", text="## A\nbudget reallocation", doc_type="playbook")
    res = Retriever(mongo, "t1").search("budget reallocation", brand_id="b", use_cache=False)
    assert {c.doc_id for c in res.chunks} == {"d1"}


def test_redis_queue_visibility_and_dlq():
    redis = pytest.importorskip("redis")
    try:
        redis.Redis.from_url(REDIS).ping()
    except Exception:
        pytest.skip("Redis not reachable")
    from adintel.queueing.redis_queue import RedisQueue

    q = RedisQueue(f"it-{uuid.uuid4().hex[:6]}", REDIS, visibility=0.2, max_receives=2, fifo=True)
    q.send({"n": 1})
    q.send({"n": 2})
    m1 = q.receive(wait_seconds=1)
    assert m1.body == {"n": 1}  # FIFO
    q.ack(m1)
    q.receive(wait_seconds=1)
    import time

    time.sleep(0.3)  # not acked → visible again
    m2b = q.receive(wait_seconds=1)
    assert m2b.body == {"n": 2} and m2b.receives == 2
    time.sleep(0.3)
    assert q.receive(wait_seconds=0.5) is None and q.dlq_depth() == 1
